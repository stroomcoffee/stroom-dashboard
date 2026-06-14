import pandas as pd
import duckdb
import io
from datetime import datetime
from pathlib import Path

DB_PATH = str(Path(__file__).parent.parent / "stroom_inventory.duckdb")


def _detect_file_type(df: pd.DataFrame) -> str:
    cols = set(df.columns.str.strip())
    if "Order No." in cols and "Ingredient Name" in cols and "In Stock" in cols:
        return "po_ingredients"
    if "Receipt Number" in cols and "Items" in cols and "Gross Sales" in cols:
        return "item_details"
    if "Item Name" in cols and "Ingredient Name" in cols and "Ingredient Quantity" in cols:
        return "recipes"
    if "Internal ID" in cols and "Actual Stock" in cols and "Adjustment" in cols:
        return "adjustment"
    if "Invoice Number" in cols and "Items" in cols and "Gross Sales" in cols:
        return "invoice"
    return "unknown"


def _clean_po(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()
    df["po_date"] = pd.to_datetime(df["Date (DD/MM/YYYY)"], dayfirst=True, errors="coerce")
    df["order_no"] = df["Order No."].fillna("").str.strip()
    df["outlet_name"] = df["Outlet Name"].fillna("").str.strip()
    df["supplier_name"] = df["Supplier Name"].fillna("Unknown Supplier").str.strip()
    df["created_by"] = df["Created By"].fillna("").str.strip()
    df["approved_by"] = df["Approved By"].fillna("").str.strip()
    df["ingredient_name"] = df["Ingredient Name"].fillna("").str.strip()
    df["unit"] = df["Unit"].fillna("").str.strip()
    df["category"] = df["Category"].fillna("").str.strip()
    df["in_stock"] = pd.to_numeric(df["In Stock"], errors="coerce").fillna(0)
    df["order_qty"] = pd.to_numeric(df["Order"], errors="coerce").fillna(0)
    df["unit_cost"] = pd.to_numeric(df["Unit Cost"], errors="coerce").fillna(0)
    df["total_cost"] = pd.to_numeric(df["Total"], errors="coerce").fillna(0)
    df["fulfillment"] = df["Fufillment"].fillna("").str.strip()
    df["status"] = df["Status"].fillna("").str.strip()
    df = df[df["ingredient_name"] != ""]
    df = df[df["order_no"] != ""]
    return df


def _clean_items(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()
    df["sale_date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce").dt.date
    df["outlet"] = df["Outlet"].fillna("").str.strip()
    df["receipt_number"] = df["Receipt Number"].fillna("").str.strip()
    df["sale_time"] = df["Time"].fillna("").str.strip()
    df["category"] = df["Category"].fillna("").str.strip()
    df["brand"] = df["Brand"].fillna("").str.strip()
    df["item_name"] = df["Items"].fillna("").str.strip()
    df["variant"] = df["Variant"].fillna("").str.strip()
    df["sku"] = df["SKU"].fillna("").str.strip()
    df["quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).astype(int)
    df["modifier_applied"] = df["Modifier Applied"].fillna("").str.strip()
    df["discount_applied"] = df["Discount Applied"].fillna("").str.strip()
    df["gross_sales"] = pd.to_numeric(df["Gross Sales"], errors="coerce").fillna(0)
    df["discounts"] = pd.to_numeric(df["Discounts"], errors="coerce").fillna(0)
    df["refunds"] = pd.to_numeric(df["Refunds"], errors="coerce").fillna(0)
    df["net_sales"] = pd.to_numeric(df["Net Sales"], errors="coerce").fillna(0)
    df["gratuity"] = pd.to_numeric(df["Gratuity"], errors="coerce").fillna(0)
    df["tax"] = pd.to_numeric(df["Tax"], errors="coerce").fillna(0)
    df["sales_type"] = df["Sales Type"].fillna("").str.strip()
    df["collected_by"] = df["Collected By"].fillna("").str.strip()
    df["served_by"] = df["Served By"].fillna("").str.strip()
    df["customer"] = df["Customer"].fillna("").str.strip()
    df["payment_method"] = df["Payment Method"].fillna("").str.strip()
    df["event_type"] = df["Event Type"].fillna("").str.strip()
    df["reason_of_refund"] = df["Reason of Refund"].fillna("").str.strip()
    df = df[df["item_name"] != ""]
    df = df[df["receipt_number"] != ""]
    return df


def _clean_recipes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()
    df["Item Name"] = df["Item Name"].ffill()
    df["item_name"] = df["Item Name"].fillna("").str.strip()
    df["variant_name"] = df["Variant Name"].fillna("").str.strip()
    df["ingredient_name"] = df["Ingredient Name"].fillna("").str.strip()
    df["ingredient_qty"] = pd.to_numeric(df["Ingredient Quantity"], errors="coerce").fillna(0)
    df["ingredient_unit"] = df["Ingredient Unit"].fillna("").str.strip()
    df["stock_alert"] = df["Ingredient Stock Alert"].fillna("").str.strip()
    df = df[df["item_name"] != ""]
    df = df[df["ingredient_name"] != ""]
    return df


def import_csv(file_bytes: bytes, filename: str) -> dict:
    try:
        df_raw = pd.read_csv(io.BytesIO(file_bytes))
    except Exception as e:
        return {"success": False, "message": f"Gagal membaca CSV: {e}", "type": "unknown"}

    file_type = _detect_file_type(df_raw)

    if file_type == "unknown":
        return {
            "success": False,
            "message": "Format file tidak dikenali. Pastikan file adalah export Moka POS yang valid.",
            "type": "unknown"
        }

    if file_type == "po_ingredients":
        return _import_po(df_raw, filename)
    elif file_type == "item_details":
        return _import_items(df_raw, filename)
    elif file_type == "recipes":
        return _import_recipes(df_raw, filename)
    elif file_type == "adjustment":
        return import_adjustment(file_bytes, filename)
    elif file_type == "invoice":
        return _import_invoice(df_raw, filename)


def _import_po(df_raw: pd.DataFrame, filename: str) -> dict:
    df = _clean_po(df_raw)
    con = duckdb.connect(DB_PATH)
    inserted = updated = skipped = 0

    try:
        for _, row in df.iterrows():
            existing = con.execute(
                "SELECT po_id FROM fact_purchase_order WHERE order_no = ? AND ingredient_name = ?",
                [row["order_no"], row["ingredient_name"]]
            ).fetchone()

            if existing:
                con.execute("""
                    UPDATE fact_purchase_order SET
                        po_date = ?, outlet_name = ?, supplier_name = ?,
                        created_by = ?, approved_by = ?, unit = ?, category = ?,
                        in_stock = ?, order_qty = ?, unit_cost = ?, total_cost = ?,
                        fulfillment = ?, status = ?, imported_at = current_timestamp
                    WHERE order_no = ? AND ingredient_name = ?
                """, [
                    row["po_date"], row["outlet_name"], row["supplier_name"],
                    row["created_by"], row["approved_by"], row["unit"], row["category"],
                    row["in_stock"], row["order_qty"], row["unit_cost"], row["total_cost"],
                    row["fulfillment"], row["status"],
                    row["order_no"], row["ingredient_name"]
                ])
                updated += 1
            else:
                po_id = con.execute("SELECT nextval('seq_po')").fetchone()[0]
                con.execute("""
                    INSERT INTO fact_purchase_order (
                        po_id, po_date, outlet_name, supplier_name, order_no,
                        created_by, approved_by, ingredient_name, unit, category,
                        in_stock, order_qty, unit_cost, total_cost, fulfillment, status
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, [
                    po_id, row["po_date"], row["outlet_name"], row["supplier_name"],
                    row["order_no"], row["created_by"], row["approved_by"],
                    row["ingredient_name"], row["unit"], row["category"],
                    row["in_stock"], row["order_qty"], row["unit_cost"],
                    row["total_cost"], row["fulfillment"], row["status"]
                ])
                inserted += 1

        _write_log(con, "po_ingredients", filename, inserted, updated, skipped, "success", "")
        con.commit()
    except Exception as e:
        con.close()
        return {"success": False, "message": str(e), "type": "po_ingredients"}
    finally:
        con.close()

    return {
        "success": True,
        "type": "po_ingredients",
        "label": "PO Ingredients",
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "total_rows": len(df)
    }


def _import_items(df_raw: pd.DataFrame, filename: str) -> dict:
    """
    Strategi: DELETE per tanggal yang ada di file, lalu INSERT semua baris.
    Menghindari data hilang akibat item yang sama muncul beberapa kali
    dalam satu receipt (Moka POS behaviour).
    """
    df = _clean_items(df_raw)
    con = duckdb.connect(DB_PATH)

    try:
        dates_in_file = [d for d in df["sale_date"].dropna().unique().tolist()]
        deleted = 0
        for d in dates_in_file:
            deleted += con.execute(
                "SELECT COUNT(*) FROM fact_sales_detail WHERE sale_date = ?", [d]
            ).fetchone()[0]
            con.execute("DELETE FROM fact_sales_detail WHERE sale_date = ?", [d])

        # Reset sequence
        max_id = con.execute("SELECT COALESCE(MAX(sale_id),0) FROM fact_sales_detail").fetchone()[0]
        con.execute("DROP SEQUENCE IF EXISTS seq_sale")
        con.execute(f"CREATE SEQUENCE seq_sale START {max_id + 1}")

        inserted = 0
        for _, row in df.iterrows():
            variant_key = row["variant"] if row["variant"] and str(row["variant"]) not in ("", "nan") else "__no_variant__"
            sale_id = con.execute("SELECT nextval('seq_sale')").fetchone()[0]
            con.execute("""
                INSERT INTO fact_sales_detail (
                    sale_id, outlet, receipt_number, sale_date, sale_time,
                    category, brand, item_name, variant, sku, quantity,
                    modifier_applied, discount_applied, gross_sales, discounts,
                    refunds, net_sales, gratuity, tax, sales_type, collected_by,
                    served_by, customer, payment_method, event_type, reason_of_refund
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, [
                sale_id, row["outlet"], row["receipt_number"], row["sale_date"],
                row["sale_time"], row["category"], row["brand"], row["item_name"],
                variant_key, row["sku"], row["quantity"],
                row["modifier_applied"], row["discount_applied"],
                row["gross_sales"], row["discounts"], row["refunds"],
                row["net_sales"], row["gratuity"], row["tax"],
                row["sales_type"], row["collected_by"], row["served_by"],
                row["customer"], row["payment_method"], row["event_type"],
                row["reason_of_refund"]
            ])
            inserted += 1

        _write_log(con, "item_details", filename, inserted, 0, deleted, "success",
                   f"Replaced {deleted} rows across {len(dates_in_file)} dates")
        con.commit()
    except Exception as e:
        con.close()
        return {"success": False, "message": str(e), "type": "item_details"}
    finally:
        con.close()

    return {
        "success": True,
        "type": "item_details",
        "label": "Item Details (Transaksi)",
        "inserted": inserted,
        "updated": 0,
        "skipped": deleted,
        "total_rows": len(df),
        "note": f"{len(dates_in_file)} tanggal di-replace. {inserted} baris inserted, {deleted} baris lama dihapus."
    }


def _import_recipes(df_raw: pd.DataFrame, filename: str) -> dict:
    df = _clean_recipes(df_raw)
    con = duckdb.connect(DB_PATH)

    try:
        old_count = con.execute("SELECT COUNT(*) FROM fact_recipe").fetchone()[0]
        con.execute("DELETE FROM fact_recipe")
        con.execute("DROP SEQUENCE IF EXISTS seq_recipe")
        con.execute("CREATE SEQUENCE seq_recipe START 1")

        inserted = 0
        for _, row in df.iterrows():
            recipe_id = con.execute("SELECT nextval('seq_recipe')").fetchone()[0]
            con.execute("""
                INSERT INTO fact_recipe (
                    recipe_id, item_name, variant_name, ingredient_name,
                    ingredient_qty, ingredient_unit, stock_alert
                ) VALUES (?,?,?,?,?,?,?)
            """, [
                recipe_id, row["item_name"], row["variant_name"],
                row["ingredient_name"], row["ingredient_qty"],
                row["ingredient_unit"], row["stock_alert"]
            ])
            inserted += 1

        _write_log(con, "recipes", filename, inserted, 0, old_count, "success",
                   f"Replaced {old_count} old records")
        con.commit()
    except Exception as e:
        con.close()
        return {"success": False, "message": str(e), "type": "recipes"}
    finally:
        con.close()

    return {
        "success": True,
        "type": "recipes",
        "label": "Recipes",
        "inserted": inserted,
        "updated": 0,
        "skipped": old_count,
        "total_rows": len(df),
        "note": f"Seluruh data resep diganti ({old_count} data lama dihapus, {inserted} data baru)"
    }


def _clean_invoice(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()
    df["inv_date"]        = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce").dt.date
    df["outlet"]          = df["Outlet"].fillna("").str.strip()
    df["invoice_number"]  = df["Invoice Number"].fillna("").str.strip()
    df["inv_time"]        = df["Time"].fillna("").str.strip()
    df["category"]        = df["Category"].fillna("").str.strip()
    df["item_name"]       = df["Items"].fillna("").str.strip()
    df["variant"]         = df["Variant"].fillna("").str.strip()
    df["quantity"]        = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).astype(int)
    df["modifier_applied"]= df["Modifier Applied"].fillna("").str.strip()
    df["gross_sales"]     = pd.to_numeric(df["Gross Sales"], errors="coerce").fillna(0)
    df["discounts"]       = pd.to_numeric(df["Discounts"], errors="coerce").fillna(0)
    df["refunds"]         = pd.to_numeric(df["Refunds"], errors="coerce").fillna(0)
    df["net_sales"]       = pd.to_numeric(df["Net Sales"], errors="coerce").fillna(0)
    df["gratuity"]        = pd.to_numeric(df["Gratuity"], errors="coerce").fillna(0)
    df["tax"]             = pd.to_numeric(df["Tax"], errors="coerce").fillna(0)
    df["sales_type"]      = df["Sales Type"].fillna("").str.strip()
    df["collected_by"]    = df["Collected By"].fillna("").str.strip()
    df["served_by"]       = df["Served By"].fillna("").str.strip()
    df["customer"]        = df["Customer"].fillna("").str.strip()
    df["event_type"]      = df["Event Type"].fillna("").str.strip()
    return df[df["item_name"] != ""]


def _import_invoice(df_raw: pd.DataFrame, filename: str) -> dict:
    """
    Strategi: DELETE per tanggal + INSERT ulang semua baris.
    Sama seperti item_details — invoice bisa punya item sama dalam satu invoice.
    """
    df = _clean_invoice(df_raw)
    con = duckdb.connect(DB_PATH)

    try:
        # Pastikan tabel ada
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
        try:
            con.execute("CREATE SEQUENCE IF NOT EXISTS seq_inv START 1")
        except Exception:
            pass

        dates_in_file = [d for d in df["inv_date"].dropna().unique().tolist()]
        deleted = 0
        for d in dates_in_file:
            deleted += con.execute("SELECT COUNT(*) FROM fact_invoice WHERE inv_date=?", [d]).fetchone()[0]
            con.execute("DELETE FROM fact_invoice WHERE inv_date=?", [d])

        max_id = con.execute("SELECT COALESCE(MAX(inv_id),0) FROM fact_invoice").fetchone()[0]
        con.execute("DROP SEQUENCE IF EXISTS seq_inv")
        con.execute(f"CREATE SEQUENCE seq_inv START {max_id+1}")

        inserted = 0
        for _, row in df.iterrows():
            inv_id = con.execute("SELECT nextval('seq_inv')").fetchone()[0]
            con.execute("""
                INSERT INTO fact_invoice (
                    inv_id, outlet, invoice_number, inv_date, inv_time,
                    category, item_name, variant, quantity, modifier_applied,
                    gross_sales, discounts, refunds, net_sales, gratuity, tax,
                    sales_type, collected_by, served_by, customer, event_type
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, [
                inv_id, row["outlet"], row["invoice_number"], row["inv_date"],
                row["inv_time"], row["category"], row["item_name"], row["variant"],
                row["quantity"], row["modifier_applied"], row["gross_sales"],
                row["discounts"], row["refunds"], row["net_sales"], row["gratuity"],
                row["tax"], row["sales_type"], row["collected_by"], row["served_by"],
                row["customer"], row["event_type"]
            ])
            inserted += 1

        _write_log(con, "invoice", filename, inserted, 0, deleted, "success",
                   f"Invoice dari {len(df['customer'].unique())} customer, {len(dates_in_file)} tanggal")
        con.commit()
    except Exception as e:
        con.close()
        return {"success": False, "message": str(e), "type": "invoice"}
    finally:
        con.close()

    return {
        "success": True,
        "type": "invoice",
        "label": "Invoice Item Details",
        "inserted": inserted,
        "updated": 0,
        "skipped": deleted,
        "total_rows": len(df),
        "note": f"{inserted} baris invoice dari {df['customer'].nunique()} customer disimpan. Tanggal lain aman."
    }


def _write_log(con, file_type, filename, inserted, updated, skipped, status, message):
    log_id = con.execute("SELECT nextval('seq_log')").fetchone()[0]
    con.execute("""
        INSERT INTO import_log (log_id, file_type, file_name, rows_inserted, rows_updated, rows_skipped, status, message)
        VALUES (?,?,?,?,?,?,?,?)
    """, [log_id, file_type, filename, inserted, updated, skipped, status, message])


def _clean_adjustment(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()
    df["internal_id"]     = df["Internal ID"].astype(str).str.strip()
    df["adj_date"]        = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df["outlet"]          = df["Outlet"].fillna("").str.strip()
    df["ingredient_name"] = df["Ingredient Name"].fillna("").str.strip()
    df["in_stock"]        = pd.to_numeric(df["In Stock"], errors="coerce").fillna(0)
    df["actual_stock"]    = pd.to_numeric(df["Actual Stock"], errors="coerce").fillna(0)
    df["adjustment"]      = pd.to_numeric(df["Adjustment"], errors="coerce").fillna(0)
    df["unit"]            = df["Unit"].fillna("").str.strip()
    df["note"]            = df["Note"].fillna("").str.strip() if "Note" in df.columns else ""
    return df[df["ingredient_name"] != ""]


def import_adjustment(file_bytes: bytes, filename: str) -> dict:
    try:
        df_raw = pd.read_csv(io.BytesIO(file_bytes))
    except Exception as e:
        return {"success": False, "message": f"Gagal membaca CSV: {e}", "type": "adjustment"}

    # Validasi kolom wajib
    required = {"Internal ID", "Ingredient Name", "In Stock", "Actual Stock", "Adjustment"}
    if not required.issubset(set(df_raw.columns.str.strip())):
        return {
            "success": False,
            "message": f"Kolom wajib tidak ditemukan. Pastikan file adalah export Inventory Adjustment dari Moka POS.",
            "type": "adjustment"
        }

    from utils.database import ensure_adjustment_table, DB_PATH
    ensure_adjustment_table()

    df = _clean_adjustment(df_raw)
    con = duckdb.connect(DB_PATH)
    inserted = updated = 0

    try:
        for _, row in df.iterrows():
            existing = con.execute(
                "SELECT adj_id FROM fact_adjustment WHERE internal_id = ?",
                [row["internal_id"]]
            ).fetchone()

            if existing:
                con.execute("""
                    UPDATE fact_adjustment SET
                        adj_date=?, outlet=?, ingredient_name=?,
                        in_stock=?, actual_stock=?, adjustment=?,
                        unit=?, note=?, imported_at=current_timestamp
                    WHERE internal_id=?
                """, [
                    row["adj_date"], row["outlet"], row["ingredient_name"],
                    row["in_stock"], row["actual_stock"], row["adjustment"],
                    row["unit"], row["note"], row["internal_id"]
                ])
                updated += 1
            else:
                adj_id = con.execute("SELECT nextval('seq_adj')").fetchone()[0]
                con.execute("""
                    INSERT INTO fact_adjustment (
                        adj_id, internal_id, adj_date, outlet, ingredient_name,
                        in_stock, actual_stock, adjustment, unit, note
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """, [
                    adj_id, row["internal_id"], row["adj_date"], row["outlet"],
                    row["ingredient_name"], row["in_stock"], row["actual_stock"],
                    row["adjustment"], row["unit"], row["note"]
                ])
                inserted += 1

        _write_log(con, "adjustment", filename, inserted, updated, 0, "success",
                   f"Stock adjustment untuk {df['ingredient_name'].nunique()} bahan")
        con.commit()
    except Exception as e:
        con.close()
        return {"success": False, "message": str(e), "type": "adjustment"}
    finally:
        con.close()

    return {
        "success": True,
        "type": "adjustment",
        "label": "Inventory Adjustment",
        "inserted": inserted,
        "updated": updated,
        "skipped": 0,
        "total_rows": len(df),
        "note": f"Adjustment untuk {df['ingredient_name'].nunique()} bahan berhasil disimpan. Stok di Inventori & Dashboard otomatis terupdate."
    }
