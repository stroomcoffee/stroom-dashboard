import duckdb
from pathlib import Path

DB_PATH = str(Path(__file__).parent / "stroom_inventory.duckdb")

con = duckdb.connect(DB_PATH)

hasil = con.execute("""
    SELECT * FROM v_stok_final 
    WHERE ingredient_name = 'Gula Putih'
""").df()

if hasil.empty:
    print("Gula Putih sudah tidak ada di database lokal")
else:
    print("Gula Putih MASIH ADA di database lokal:")
    print(hasil.to_string())

con.close()
