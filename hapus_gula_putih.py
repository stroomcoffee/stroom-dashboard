import duckdb
from pathlib import Path

DB_PATH = str(Path(__file__).parent / "stroom_inventory.duckdb")

con = duckdb.connect(DB_PATH)

# Cek dulu
hasil = con.execute("SELECT COUNT(*) FROM fact_purchase_order WHERE ingredient_name = 'Gula Putih'").fetchone()
print(f"Ditemukan {hasil[0]} baris PO untuk Gula Putih")

# Hapus
con.execute("DELETE FROM fact_purchase_order WHERE ingredient_name = 'Gula Putih'")
con.commit()
con.close()
print("Gula Putih berhasil dihapus!")
