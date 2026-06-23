import duckdb
import pandas as pd
import streamlit as st
from pathlib import Path

DB_PATH = str(Path(__file__).parent.parent / "stroom_inventory.duckdb")


def get_connection():
    """Buka koneksi baru ke database DuckDB."""
    return duckdb.connect(DB_PATH)


def run_query(sql: str, params: list = None) -> pd.DataFrame:
    """Jalankan query SELECT dan kembalikan hasilnya sebagai DataFrame."""
    con = get_connection()
    try:
        if params:
            result = con.execute(sql, params).df()
        else:
            result = con.execute(sql).df()
    finally:
        con.close()
    return result


def init_database():
    """
    Inisialisasi tabel-tabel utama jika belum ada.
    Dipanggil sekali setiap app start.
    """
    con = get_connection()

    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_sales_detail (
            sale_id INTEGER,
            sale_date DATE,
            sale_time VARCHAR,
            receipt_number VARCHAR,
            item_name VARCHAR,
            category VARCHAR,
            sales_type VARCHAR,
            payment_method VARCHAR,
            quantity DOUBLE,
            gross_sales DOUBLE,
            discounts DOUBLE,
            net_sales DOUBLE,
            outlet_name VARCHAR,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_invoice (
            invoice_id INTEGER,
            inv_date DATE,
            invoice_number VARCHAR,
            item_name VARCHAR,
            category VARCHAR,
            quantity DOUBLE,
            gross_sales DOUBLE,
            net_sales DOUBLE,
            outlet_name VARCHAR,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_purchase_order (
            po_id INTEGER,
            order_no VARCHAR,
            po_date DATE,
            ingredient_name VARCHAR,
            order_qty DOUBLE,
            in_stock DOUBLE,
            unit VARCHAR,
            category VARCHAR,
            total_cost DOUBLE,
            status VARCHAR,
            outlet_name VARCHAR,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_recipe (
            recipe_id INTEGER,
            item_name VARCHAR,
            variant_name VARCHAR,
            ingredient_name VARCHAR,
            ingredient_qty DOUBLE,
            ingredient_unit VARCHAR,
            stock_alert VARCHAR,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS import_log (
            log_id INTEGER,
            file_type VARCHAR,
            file_name VARCHAR,
            rows_inserted INTEGER,
            rows_updated INTEGER,
            status VARCHAR,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.execute("CREATE SEQUENCE IF NOT EXISTS seq_sale START 1")
    con.execute("CREATE SEQUENCE IF NOT EXISTS seq_invoice START 1")
    con.execute("CREATE SEQUENCE IF NOT EXISTS seq_po START 1")
    con.execute("CREATE SEQUENCE IF NOT EXISTS seq_recipe START 1")
    con.execute("CREATE SEQUENCE IF NOT EXISTS seq_log START 1")

    con.commit()
    con.close()


def ensure_adjustment_table():
    """Buat tabel fact_adjustment jika belum ada."""
    con = get_connection()
    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_adjustment (
            adj_id INTEGER PRIMARY KEY,
            ingredient_name VARCHAR,
            adj_date TIMESTAMP,
            actual_stock DOUBLE,
            in_stock DOUBLE,
            adjustment DOUBLE,
            unit VARCHAR,
            note VARCHAR,
            outlet_name VARCHAR,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("CREATE SEQUENCE IF NOT EXISTS seq_adj START 1")
    con.commit()
    con.close()


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
            semi_finished_name VARCHAR,
            batch_yield_qty DOUBLE,
            batch_yield_unit VARCHAR,
            raw_ingredient_name VARCHAR,
            raw_qty DOUBLE,
            raw_unit VARCHAR,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("CREATE SEQUENCE IF NOT EXISTS seq_sf START 1")
    con.commit()
    con.close()


def create_stock_view():
    """
    Buat atau replace view v_stok_final.

    Logika stok real (3 tahap):
      1. Adjustment terakhir per bahan = titik awal
      2. + PO Completed yang masuk SETELAH adjustment terakhir
      3. - Konsumsi penjualan SETELAH adjustment terakhir, dihitung 2 cara:
         a. Konsumsi LANGSUNG - bahan dipakai langsung di resep menu
         b. Konsumsi TIDAK LANGSUNG - bahan dipakai sebagai komponen
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
        konsumsi_via_semi_finished AS (
            SELECT
                sf.raw_ingredient_name AS ingredient_name,
                SUM(
                    s.quantity
                    * r.ingredient_qty
                    / sf.batch_yield_qty
                    * sf.raw_qty
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