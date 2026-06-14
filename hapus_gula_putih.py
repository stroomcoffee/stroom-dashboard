import duckdb
from pathlib import Path

DB_PATH = str(Path(__file__).parent / "stroom_inventory.duckdb")

con = duckdb.connect(DB_PATH)

# Hapus dari fact_purchase_order
po = con.execute("SELECT COUNT(*) FROM fact_purchase_order WHERE ingredient_name = 'Gula Putih'").fetchone()[0]
con.execute("DELETE FROM fact_purchase_order WHERE ingredient_name = 'Gula Putih'")
print(f"Hapus {po} baris dari fact_purchase_order")

# Hapus dari fact_adjustment
adj = con.execute("SELECT COUNT(*) FROM fact_adjustment WHERE ingredient_name = 'Gula Putih'").fetchone()[0]
con.execute("DELETE FROM fact_adjustment WHERE ingredient_name = 'Gula Putih'")
print(f"Hapus {adj} baris dari fact_adjustment")

con.commit()
con.close()
print()
print("Gula Putih berhasil dihapus dari semua tabel!")