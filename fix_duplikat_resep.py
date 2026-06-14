"""
fix_duplikat_resep.py
---------------------
Jalankan SEKALI untuk membersihkan duplikat di fact_recipe.
Letakkan file ini di folder root project (sama dengan app.py), lalu jalankan:

    python fix_duplikat_resep.py

Tidak perlu import ulang CSV resep setelah ini.
"""

import duckdb
from pathlib import Path

DB_PATH = str(Path(__file__).parent / "stroom_inventory.duckdb")

def fix():
    con = duckdb.connect(DB_PATH)

    # Hitung sebelum
    before = con.execute("SELECT COUNT(*) FROM fact_recipe").fetchone()[0]
    duplikat = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT item_name, ingredient_name
            FROM fact_recipe
            GROUP BY item_name, ingredient_name
            HAVING COUNT(*) > 1
        )
    """).fetchone()[0]

    print(f"Sebelum: {before} baris, {duplikat} kombinasi menu+bahan yang duplikat")

    # Simpan data bersih (ambil 1 baris per menu+bahan, pilih qty terbaru)
    # Untuk qty berbeda → ambil yang recipe_id terbesar (import terakhir)
    con.execute("""
        CREATE OR REPLACE TABLE fact_recipe_clean AS
        SELECT
            ROW_NUMBER() OVER (ORDER BY item_name, ingredient_name) AS recipe_id,
            item_name,
            variant_name,
            ingredient_name,
            ingredient_qty,
            ingredient_unit,
            stock_alert,
            imported_at
        FROM (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY item_name, ingredient_name
                    ORDER BY recipe_id DESC
                ) AS rn
            FROM fact_recipe
        ) t
        WHERE rn = 1
    """)

    after = con.execute("SELECT COUNT(*) FROM fact_recipe_clean").fetchone()[0]
    print(f"Sesudah: {after} baris (berkurang {before - after} duplikat)")

    # Ganti tabel lama dengan yang bersih
    con.execute("DROP TABLE fact_recipe")
    con.execute("ALTER TABLE fact_recipe_clean RENAME TO fact_recipe")

    # Reset sequence
    con.execute("DROP SEQUENCE IF EXISTS seq_recipe")
    con.execute(f"CREATE SEQUENCE seq_recipe START {after + 1}")

    con.commit()
    con.close()

    print()
    print("✅ Selesai! Duplikat resep berhasil dibersihkan.")
    print(f"   {before} baris → {after} baris (hapus {before - after} duplikat)")
    print()
    print("Sekarang push ke GitHub:")
    print("  git add stroom_inventory.duckdb")
    print("  git commit -m 'fix: bersihkan duplikat resep'")
    print("  git push")

if __name__ == "__main__":
    fix()
