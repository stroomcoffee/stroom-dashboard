# ============================================================
# TAMBAHAN UNTUK utils/database.py
# ============================================================
# 1. Tempel fungsi ensure_semi_finished_table() ini di utils/database.py
#    (letakkan dekat fungsi ensure_adjustment_table())
# 2. Panggil ensure_semi_finished_table() di app.py, sejajar dengan
#    ensure_adjustment_table() yang sudah ada
# 3. REPLACE seluruh fungsi create_stock_view() yang lama dengan
#    versi baru di bagian bawah file ini
# ============================================================


def ensure_semi_finished_table():
    """
    Buat tabel fact_semi_finished_recipe jika belum ada.
    Tabel ini menyimpan resep turunan: bahan mentah apa saja
    yang dipakai untuk membuat 1 batch Semi-Finished Ingredient
    (contoh: Bumbu Base XO, Sambal Base, Prepared Katsu, dst)
    yang tidak melalui sistem PO sendiri di Moka.
    """
    con = get_connection()
    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_semi_finished_recipe (
            sf_id INTEGER PRIMARY KEY,
            semi_finished_name VARCHAR,   -- contoh: 'Bumbu Base XO'
            batch_yield_qty DOUBLE,       -- contoh: 2000
            batch_yield_unit VARCHAR,     -- contoh: 'gram (g)'
            raw_ingredient_name VARCHAR,  -- contoh: 'Bawang Merah'
            raw_qty DOUBLE,               -- contoh: 250
            raw_unit VARCHAR,             -- contoh: 'gram (g)'
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("CREATE SEQUENCE IF NOT EXISTS seq_sf START 1")
    con.commit()
    con.close()


# ============================================================
# REPLACE create_stock_view() YANG LAMA DENGAN INI
# ============================================================

def create_stock_view():
    """
    Buat atau replace view v_stok_final.

    Logika stok real (3 tahap):
      1. Adjustment terakhir per bahan = titik awal
      2. + PO Completed yang masuk SETELAH adjustment terakhir
      3. - Konsumsi penjualan SETELAH adjustment terakhir, dihitung 2 cara:
         a. Konsumsi LANGSUNG — bahan dipakai langsung di resep menu
         b. Konsumsi TIDAK LANGSUNG — bahan dipakai sebagai komponen
            Semi-Finished Ingredient, yang Semi-Finished itu sendiri
            dipakai di resep menu (fact_semi_finished_recipe)
    """
    con = get_connection()
    con.execute("""
        CREATE OR REPLACE VIEW v_stok_final AS
        WITH
        adj_latest AS (
            SELECT a.ingredient_name,
                   a.actual_stock  AS adj_actual_stock,
                   a.in_stock      AS adj_in_stock,
                   a.adjustment,
                   a.adj_date,
                   a.unit          AS adj_unit,
                   a.note
            FROM fact_adjustment a
            INNER JOIN (
                SELECT ingredient_name, MAX(adj_date) AS latest
                FROM fact_adjustment
                GROUP BY ingredient_name
            ) lt ON a.ingredient_name = lt.ingredient_name
                 AND a.adj_date = lt.latest
            QUALIFY ROW_NUMBER() OVER (PARTITION BY a.ingredient_name ORDER BY a.adj_id DESC) = 1
        ),
        po_latest AS (
            SELECT po.ingredient_name,
                   po.in_stock   AS po_in_stock,
                   po.unit,
                   po.category,
                   po.po_date    AS po_date,
                   po.order_no
            FROM fact_purchase_order po
            INNER JOIN (
                SELECT ingredient_name, MAX(po_date) AS latest
                FROM fact_purchase_order
                GROUP BY ingredient_name
            ) lt ON po.ingredient_name = lt.ingredient_name
                 AND po.po_date = lt.latest
            QUALIFY ROW_NUMBER() OVER (PARTITION BY po.ingredient_name ORDER BY po.po_id DESC) = 1
        ),
        po_after_adj AS (
            SELECT p.ingredient_name,
                   SUM(p.order_qty) AS total_po_after
            FROM fact_purchase_order p
            JOIN adj_latest a ON p.ingredient_name = a.ingredient_name
            WHERE p.po_date > a.adj_date
              AND p.status = 'Completed'
            GROUP BY p.ingredient_name
        ),
        -- (a) Konsumsi LANGSUNG: bahan dipakai langsung di resep menu
        konsumsi_langsung AS (
            SELECT r.ingredient_name,
                   SUM(s.quantity * r.ingredient_qty) AS total_konsumsi
            FROM fact_sales_detail s
            JOIN fact_recipe r ON LOWER(TRIM(s.item_name)) = LOWER(TRIM(r.item_name))
            JOIN adj_latest a ON r.ingredient_name = a.ingredient_name
            WHERE CAST(s.sale_date AS TIMESTAMP) > a.adj_date
              AND s.quantity > 0
              AND r.ingredient_qty > 0
            GROUP BY r.ingredient_name
        ),
        -- (b) Konsumsi TIDAK LANGSUNG: lewat Semi-Finished Ingredient
        --     menu -> semi-finished -> raw material
        konsumsi_via_semi_finished AS (
            SELECT
                sf.raw_ingredient_name AS ingredient_name,
                SUM(
                    s.quantity                         -- qty menu terjual
                    * r.ingredient_qty                 -- gram semi-finished per porsi menu
                    / sf.batch_yield_qty                -- dibagi hasil 1 batch semi-finished
                    * sf.raw_qty                        -- dikali qty raw material per batch
                ) AS total_konsumsi
            FROM fact_sales_detail s
            JOIN fact_recipe r
                 ON LOWER(TRIM(s.item_name)) = LOWER(TRIM(r.item_name))
            JOIN fact_semi_finished_recipe sf
                 ON LOWER(TRIM(r.ingredient_name)) = LOWER(TRIM(sf.semi_finished_name))
            JOIN adj_latest a
                 ON sf.raw_ingredient_name = a.ingredient_name
            WHERE CAST(s.sale_date AS TIMESTAMP) > a.adj_date
              AND s.quantity > 0
              AND r.ingredient_qty > 0
              AND sf.batch_yield_qty > 0
            GROUP BY sf.raw_ingredient_name
        ),
        -- Gabungkan konsumsi langsung + tidak langsung per bahan
        konsumsi_total AS (
            SELECT ingredient_name, SUM(total_konsumsi) AS total_konsumsi
            FROM (
                SELECT * FROM konsumsi_langsung
                UNION ALL
                SELECT * FROM konsumsi_via_semi_finished
            )
            GROUP BY ingredient_name
        ),
        combined AS (
            SELECT
                COALESCE(pl.ingredient_name, al.ingredient_name) AS ingredient_name,
                COALESCE(pl.unit, al.adj_unit)                   AS unit,
                pl.category,
                al.adj_actual_stock,
                al.adjustment,
                al.adj_date,
                pl.po_in_stock,
                pl.po_date,
                pl.order_no,
                COALESCE(pa.total_po_after, 0)    AS po_after_adj,
                COALESCE(kt.total_konsumsi, 0)    AS konsumsi_after_adj,
                CASE
                    WHEN al.ingredient_name IS NOT NULL THEN
                        al.adj_actual_stock
                        + COALESCE(pa.total_po_after, 0)
                        - COALESCE(kt.total_konsumsi, 0)
                    ELSE
                        pl.po_in_stock
                END AS stok_final,
                CASE
                    WHEN al.ingredient_name IS NOT NULL THEN 'adjusted'
                    ELSE 'po_only'
                END AS stok_source
            FROM po_latest pl
            FULL OUTER JOIN adj_latest al ON pl.ingredient_name = al.ingredient_name
            LEFT JOIN po_after_adj pa ON COALESCE(pl.ingredient_name, al.ingredient_name) = pa.ingredient_name
            LEFT JOIN konsumsi_total kt ON COALESCE(pl.ingredient_name, al.ingredient_name) = kt.ingredient_name
        )
        SELECT
            ingredient_name,
            unit,
            category,
            stok_final,
            po_in_stock,
            adj_actual_stock,
            adjustment,
            adj_date,
            po_date,
            order_no,
            stok_source,
            po_after_adj,
            konsumsi_after_adj
        FROM combined
    """)
    con.commit()
    con.close()