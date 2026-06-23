import streamlit as st
import pandas as pd
from utils.database import run_query, get_connection
from utils.style import BORDER, TEXT, TEXT_MUTED, ACCENT, ACCENT2, BG3


# Daftar Semi-Finished Ingredient yang teridentifikasi dari Moka
# (Recipes > Semi-Finished Ingredient). Dipakai sebagai pilihan default
# di dropdown, tapi user tetap bisa ketik nama baru.
KNOWN_SEMI_FINISHED = [
    "Bumbu Base XO", "Sambal Base", "Prepared Katsu", "Prepared Presto Iga",
    "Prepared Dry Rubbed", "Salad Base", "Base Iga Bakar", "Base Kuah Soto Betawi",
    "Base Soto Betawi", "Base Stuffed Tofu", "Base Tahu Bakso",
    "Bumbu Based Saos Cireng", "Masteran Cabe Garam", "Masteran Mendoan",
    "Prepared Ayam Asam Manis", "Sambal Ijo",
]

UNIT_OPTIONS = ["gram (g)", "kilogram (kg)", "millilitre (ml)", "litre (l)", "pieces (pcs)"]


def _next_sf_id():
    con = get_connection()
    val = con.execute("SELECT nextval('seq_sf')").fetchone()[0]
    con.close()
    return val


def show():
    st.title("Resep Turunan (Semi-Finished Ingredient)")
    st.caption(
        "Untuk bahan yang dibuat manual oleh tim Kitchen/BAR dan tidak punya PO sendiri di Moka "
        "(contoh: Bumbu Base XO, Sambal Base). Input resep turunannya di sini agar konsumsi bahan "
        "mentahnya tetap ter-track otomatis lewat menu yang memakainya."
    )

    st.divider()

    # ── Form tambah / edit resep turunan ──────────────────────────
    st.subheader("Tambah resep turunan")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        sf_name = st.selectbox(
            "Nama Semi-Finished Ingredient",
            options=["(Pilih atau ketik baru di bawah)"] + KNOWN_SEMI_FINISHED,
            key="sf_select"
        )
        sf_name_custom = st.text_input(
            "Atau ketik nama baru",
            placeholder="Contoh: Bumbu Rendang Base",
            key="sf_custom"
        )
        final_sf_name = sf_name_custom.strip() if sf_name_custom.strip() else (
            sf_name if sf_name != "(Pilih atau ketik baru di bawah)" else ""
        )
    with col2:
        batch_qty = st.number_input("Hasil 1 batch", min_value=0.0, value=2000.0, step=1.0, key="sf_batch_qty")
    with col3:
        batch_unit = st.selectbox("Satuan hasil", UNIT_OPTIONS, key="sf_batch_unit")

    st.markdown("**Bahan mentah yang dipakai untuk 1 batch ini:**")

    # Session state untuk baris bahan dinamis
    if "sf_rows" not in st.session_state:
        st.session_state["sf_rows"] = [{"name": "", "qty": 0.0, "unit": "gram (g)"}]

    rows_to_remove = []
    for i, row in enumerate(st.session_state["sf_rows"]):
        rc1, rc2, rc3, rc4 = st.columns([3, 1, 1, 0.5])
        with rc1:
            row["name"] = st.text_input(f"Bahan #{i+1}", value=row["name"], key=f"sf_row_name_{i}", placeholder="Contoh: Bawang Merah")
        with rc2:
            row["qty"] = st.number_input("Qty", min_value=0.0, value=row["qty"], step=1.0, key=f"sf_row_qty_{i}")
        with rc3:
            row["unit"] = st.selectbox("Satuan", UNIT_OPTIONS, index=UNIT_OPTIONS.index(row["unit"]) if row["unit"] in UNIT_OPTIONS else 0, key=f"sf_row_unit_{i}")
        with rc4:
            st.write("")
            if st.button("🗑", key=f"sf_row_del_{i}"):
                rows_to_remove.append(i)

    if rows_to_remove:
        for idx in sorted(rows_to_remove, reverse=True):
            st.session_state["sf_rows"].pop(idx)
        st.rerun()

    if st.button("+ Tambah Bahan"):
        st.session_state["sf_rows"].append({"name": "", "qty": 0.0, "unit": "gram (g)"})
        st.rerun()

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if st.button("💾 Simpan Resep Turunan", type="primary", use_container_width=True):
        valid_rows = [r for r in st.session_state["sf_rows"] if r["name"].strip() and r["qty"] > 0]
        if not final_sf_name:
            st.error("Nama Semi-Finished Ingredient wajib diisi.")
        elif batch_qty <= 0:
            st.error("Hasil 1 batch harus lebih dari 0.")
        elif not valid_rows:
            st.error("Minimal harus ada 1 bahan mentah dengan qty > 0.")
        else:
            con = get_connection()
            # Hapus resep lama untuk semi-finished ini (replace, bukan tambah)
            con.execute("DELETE FROM fact_semi_finished_recipe WHERE semi_finished_name = ?", [final_sf_name])
            for r in valid_rows:
                sf_id = _next_sf_id_inline(con)
                con.execute("""
                    INSERT INTO fact_semi_finished_recipe
                    (sf_id, semi_finished_name, batch_yield_qty, batch_yield_unit,
                     raw_ingredient_name, raw_qty, raw_unit)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, [sf_id, final_sf_name, batch_qty, batch_unit, r["name"].strip(), r["qty"], r["unit"]])
            con.commit()
            con.close()

            st.success(f"Resep turunan '{final_sf_name}' berhasil disimpan ({len(valid_rows)} bahan).")
            st.session_state["sf_rows"] = [{"name": "", "qty": 0.0, "unit": "gram (g)"}]

            # Auto-upload ke GDrive jika tersedia
            try:
                from utils.gdrive_loader import upload_to_gdrive
                with st.spinner("☁️ Menyimpan ke Google Drive..."):
                    ok = upload_to_gdrive()
                if ok:
                    st.success("☁️ Tersimpan ke Google Drive.")
            except Exception:
                pass

            st.rerun()

    st.divider()

    # ── Daftar resep turunan yang sudah tersimpan ─────────────────
    st.subheader("Resep turunan tersimpan")

    df_sf = run_query("""
        SELECT semi_finished_name, batch_yield_qty, batch_yield_unit,
               raw_ingredient_name, raw_qty, raw_unit
        FROM fact_semi_finished_recipe
        ORDER BY semi_finished_name, raw_ingredient_name
    """)

    if df_sf.empty:
        st.info("Belum ada resep turunan yang diinput. Mulai dengan form di atas.")
        return

    for sf_name_group in df_sf["semi_finished_name"].unique():
        df_group = df_sf[df_sf["semi_finished_name"] == sf_name_group]
        batch_info = f"{df_group['batch_yield_qty'].iloc[0]:.0f} {df_group['batch_yield_unit'].iloc[0]}"

        with st.expander(f"**{sf_name_group}** — hasil {batch_info} ({len(df_group)} bahan)"):
            df_show = df_group[["raw_ingredient_name", "raw_qty", "raw_unit"]].rename(columns={
                "raw_ingredient_name": "Bahan Mentah",
                "raw_qty": "Qty",
                "raw_unit": "Satuan"
            })
            st.dataframe(df_show, use_container_width=True, hide_index=True)

            if st.button(f"🗑 Hapus resep '{sf_name_group}'", key=f"del_sf_{sf_name_group}"):
                con = get_connection()
                con.execute("DELETE FROM fact_semi_finished_recipe WHERE semi_finished_name = ?", [sf_name_group])
                con.commit()
                con.close()
                st.success(f"Resep '{sf_name_group}' dihapus.")
                st.rerun()

    st.divider()
    st.caption(
        "Menu yang memakai Semi-Finished Ingredient ini (dari fact_recipe) akan otomatis "
        "menghitung konsumsi bahan mentah secara proporsional berdasarkan resep turunan di atas. "
        "Lihat hasilnya di menu Inventori Bahan."
    )


def _next_sf_id_inline(con):
    return con.execute("SELECT nextval('seq_sf')").fetchone()[0]
