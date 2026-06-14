import duckdb
import os
from pathlib import Path

DB_PATH = str(Path(__file__).parent.parent / "stroom_inventory.duckdb")


def get_connection():
    return duckdb.connect(DB_PATH)


def init_database():
    con = get_connection()
    con.executemany("PRAGMA", []) if False else None

    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_ingredient (
            ingredient_id   INTEGER PRIMARY KEY,
            ingredient_name VARCHAR NOT NULL,
            unit            VARCHAR,
            category        VARCHAR,
            stok_minimum    DOUBLE DEFAULT 0,
            created_at      TIMESTAMP DEFAULT current_timestamp,
            updated_at      TIMESTAMP DEFAULT current_timestamp,
            UNIQUE (ingredient_name)
        )
    """)

    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_ingredient START 1
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_supplier (
            supplier_id    INTEGER PRIMARY KEY,
            supplier_name  VARCHAR NOT NULL,
            supplier_phone VARCHAR,
            supplier_email VARCHAR,
            created_at     TIMESTAMP DEFAULT current_timestamp,
            UNIQUE (supplier_name)
        )
    """)

    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_supplier START 1
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_menu (
            menu_id      INTEGER PRIMARY KEY,
            item_name    VARCHAR NOT NULL,
            category     VARCHAR,
            brand        VARCHAR,
            aktif        BOOLEAN DEFAULT true,
            created_at   TIMESTAMP DEFAULT current_timestamp,
            UNIQUE (item_name)
        )
    """)

    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_menu START 1
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_purchase_order (
            po_id          INTEGER PRIMARY KEY,
            po_date        TIMESTAMP,
            outlet_name    VARCHAR,
            supplier_name  VARCHAR,
            order_no       VARCHAR NOT NULL,
            created_by     VARCHAR,
            approved_by    VARCHAR,
            ingredient_name VARCHAR NOT NULL,
            unit           VARCHAR,
            category       VARCHAR,
            in_stock       DOUBLE,
            order_qty      DOUBLE,
            unit_cost      DOUBLE,
            total_cost     DOUBLE,
            fulfillment    VARCHAR,
            status         VARCHAR,
            imported_at    TIMESTAMP DEFAULT current_timestamp,
            UNIQUE (order_no, ingredient_name)
        )
    """)

    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_po START 1
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_sales_detail (
            sale_id         INTEGER PRIMARY KEY,
            outlet          VARCHAR,
            receipt_number  VARCHAR NOT NULL,
            sale_date       DATE,
            sale_time       VARCHAR,
            category        VARCHAR,
            brand           VARCHAR,
            item_name       VARCHAR NOT NULL,
            variant         VARCHAR,
            sku             VARCHAR,
            quantity        INTEGER,
            modifier_applied VARCHAR,
            discount_applied VARCHAR,
            gross_sales     DOUBLE,
            discounts       DOUBLE,
            refunds         DOUBLE,
            net_sales       DOUBLE,
            gratuity        DOUBLE,
            tax             DOUBLE,
            sales_type      VARCHAR,
            collected_by    VARCHAR,
            served_by       VARCHAR,
            customer        VARCHAR,
            payment_method  VARCHAR,
            event_type      VARCHAR,
            reason_of_refund VARCHAR,
            imported_at     TIMESTAMP DEFAULT current_timestamp
        )
    """)

    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_sale START 1
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_recipe (
            recipe_id           INTEGER PRIMARY KEY,
            item_name           VARCHAR NOT NULL,
            variant_name        VARCHAR,
            ingredient_name     VARCHAR NOT NULL,
            ingredient_qty      DOUBLE,
            ingredient_unit     VARCHAR,
            stock_alert         VARCHAR,
            imported_at         TIMESTAMP DEFAULT current_timestamp
        )
    """)

    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_recipe START 1
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_invoice (
            inv_id          INTEGER PRIMARY KEY,
            outlet          VARCHAR,
            invoice_number  VARCHAR NOT NULL,
            inv_date        DATE,
            inv_time        VARCHAR,
            category        VARCHAR,
            item_name       VARCHAR NOT NULL,
            variant         VARCHAR,
            quantity        INTEGER,
            modifier_applied VARCHAR,
            gross_sales     DOUBLE,
            discounts       DOUBLE,
            refunds         DOUBLE,
            net_sales       DOUBLE,
            gratuity        DOUBLE,
            tax             DOUBLE,
            sales_type      VARCHAR,
            collected_by    VARCHAR,
            served_by       VARCHAR,
            customer        VARCHAR,
            event_type      VARCHAR,
            imported_at     TIMESTAMP DEFAULT current_timestamp
        )
    """)

    con.execute("CREATE SEQUENCE IF NOT EXISTS seq_inv START 1")

    con.execute("""
        CREATE TABLE IF NOT EXISTS import_log (
            log_id       INTEGER PRIMARY KEY,
            file_type    VARCHAR,
            file_name    VARCHAR,
            imported_at  TIMESTAMP DEFAULT current_timestamp,
            rows_inserted INTEGER DEFAULT 0,
            rows_updated  INTEGER DEFAULT 0,
            rows_skipped  INTEGER DEFAULT 0,
            status        VARCHAR,
            message       VARCHAR
        )
    """)

    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_log START 1
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS alert_config (
            alert_id        INTEGER PRIMARY KEY,
            ingredient_name VARCHAR NOT NULL UNIQUE,
            threshold_low   DOUBLE DEFAULT 0,
            threshold_critical DOUBLE DEFAULT 0,
            aktif           BOOLEAN DEFAULT true,
            updated_at      TIMESTAMP DEFAULT current_timestamp
        )
    """)

    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_alert START 1
    """)

    con.close()


def run_query(sql: str, params=None):
    con = get_connection()
    try:
        if params:
            result = con.execute(sql, params).df()
        else:
            result = con.execute(sql).df()
        return result
    finally:
        con.close()


def execute_write(sql: str, params=None):
    con = get_connection()
    try:
        if params:
            con.execute(sql, params)
        else:
            con.execute(sql)
        con.commit()
    finally:
        con.close()


def ensure_adjustment_table():
    """Tambahkan tabel adjustment jika belum ada (safe to call multiple times)."""
    con = get_connection()
    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_adjustment (
            adj_id          INTEGER PRIMARY KEY,
            internal_id     VARCHAR,
            adj_date        TIMESTAMP,
            outlet          VARCHAR,
            ingredient_name VARCHAR NOT NULL,
            in_stock        DOUBLE,
            actual_stock    DOUBLE,
            adjustment      DOUBLE,
            unit            VARCHAR,
            note            VARCHAR,
            imported_at     TIMESTAMP DEFAULT current_timestamp,
            UNIQUE (internal_id)
        )
    """)
    con.execute("CREATE SEQUENCE IF NOT EXISTS seq_adj START 1")
    con.commit()
    con.close()


def create_stock_view():
    """
    Buat atau replace view v_stok_final.
    Logika: ambil actual_stock dari adjustment terbaru per bahan jika ada,
    kalau tidak ada pakai in_stock dari PO terbaru.
    """
    con = get_connection()
    con.execute("""
        CREATE OR REPLACE VIEW v_stok_final AS
        WITH po_latest AS (
            SELECT po.ingredient_name,
                   po.in_stock   AS po_in_stock,
                   po.unit,
                   po.category,
                   po.po_date    AS po_date,
                   po.order_no,
                   po.status     AS po_status
            FROM fact_purchase_order po
            INNER JOIN (
                SELECT ingredient_name, MAX(po_date) AS latest
                FROM fact_purchase_order
                GROUP BY ingredient_name
            ) lt ON po.ingredient_name = lt.ingredient_name
                 AND po.po_date = lt.latest
            QUALIFY ROW_NUMBER() OVER (PARTITION BY po.ingredient_name ORDER BY po.po_id DESC) = 1
        ),
        adj_latest AS (
            SELECT a.ingredient_name,
                   a.actual_stock AS adj_actual_stock,
                   a.in_stock     AS adj_in_stock,
                   a.adjustment,
                   a.adj_date,
                   a.unit         AS adj_unit,
                   a.note
            FROM fact_adjustment a
            INNER JOIN (
                SELECT ingredient_name, MAX(adj_date) AS latest
                FROM fact_adjustment
                GROUP BY ingredient_name
            ) lt ON a.ingredient_name = lt.ingredient_name
                 AND a.adj_date = lt.latest
            QUALIFY ROW_NUMBER() OVER (PARTITION BY a.ingredient_name ORDER BY a.adj_id DESC) = 1
        )
        SELECT
            COALESCE(po.ingredient_name, adj.ingredient_name)   AS ingredient_name,
            COALESCE(po.unit, adj.adj_unit)                     AS unit,
            po.category,
            -- Stok final: pakai actual_stock dari adjustment jika ada, fallback ke PO
            CASE
                WHEN adj.ingredient_name IS NOT NULL THEN adj.adj_actual_stock
                ELSE po.po_in_stock
            END                                                  AS stok_final,
            po.po_in_stock,
            adj.adj_actual_stock,
            adj.adjustment,
            adj.adj_date,
            po.po_date,
            po.order_no,
            CASE
                WHEN adj.ingredient_name IS NOT NULL THEN 'adjusted'
                ELSE 'po_only'
            END                                                  AS stok_source
        FROM po_latest po
        FULL OUTER JOIN adj_latest adj ON po.ingredient_name = adj.ingredient_name
    """)
    con.commit()
    con.close()
