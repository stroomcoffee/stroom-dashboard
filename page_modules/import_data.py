import streamlit as st
import pandas as pd
from utils.importer import import_csv, import_adjustment
from utils.database import run_query


def show():
    st.title("Import Data CSV")
    st.caption("Upload file hasil export Moka POS. Data lama di luar rentang file tidak akan terhapus.")

    # ── Panduan format file ─────────────────────────────────────
    with st.expander("Panduan format file Moka POS", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**PO Ingredients**")
            st.caption("Menu: Inventory → Purchase Order → Export")
            st.code("Kolom wajib:\n- Order No.\n- Ingredient Name\n- In Stock\n- Unit Cost\n- Status")
        with c2:
            st.markdown("**Item Details (Transaksi)**")
            st.caption("Menu: Report → Item Details → Export")
            st.code("Kolom wajib:\n- Receipt Number\n- Items\n- Gross Sales\n- Net Sales\n- Date")
        with c3:
            st.markdown("**Recipes**")
            st.caption("Menu: Inventory → Recipes → Export")
            st.code("Kolom wajib:\n- Item Name\n- Ingredient Name\n- Ingredient Quantity\n- Ingredient Unit")

        st.divider()
        c4, c5, c6 = st.columns(3)
        with c4:
            st.markdown("**Inventory Adjustment** ✏️")
            st.caption("Menu: Inventory → Adjustment → Export")
            st.code("Kolom wajib:\n- Internal ID\n- Ingredient Name\n- In Stock\n- Actual Stock\n- Adjustment")
            st.info("File ini mengkoreksi stok PO yang salah input. Stok di Inventori & Dashboard otomatis pakai data adjustment.", icon="⚡")

        c5, c6, _ = st.columns(3)
        with c5:
            st.markdown("**Invoice Item Details** 🧾")
            st.caption("Menu: Report → Invoice → Item Details → Export")
            st.code("Kolom wajib:\n- Invoice Number\n- Items\n- Gross Sales\n- Net Sales\n- Date")
            st.info("Transaksi invoice/korporat (SPV, B2B). Digabung dengan Item Details untuk total penjualan & konsumsi bahan yang akurat.", icon="🧾")

    st.divider()

    # ── Upload Area ─────────────────────────────────────────────
    st.subheader("Upload file CSV")
    st.info(
        "Anda bisa upload satu atau lebih file sekaligus. "
        "Tipe file akan terdeteksi otomatis dari header kolom CSV.",
        icon="ℹ️"
    )

    uploaded_files = st.file_uploader(
        "Pilih file CSV (bisa multiple)",
        type=["csv"],
        accept_multiple_files=True,
        help="Drag & drop atau klik untuk memilih file. Bisa pilih lebih dari satu sekaligus."
    )

    if uploaded_files:
        st.write(f"**{len(uploaded_files)} file dipilih:**")
        for uf in uploaded_files:
            st.write(f"- `{uf.name}` ({uf.size / 1024:.1f} KB)")

        st.divider()

        # Preview sebelum import
        with st.expander("Preview data (5 baris pertama per file)", expanded=False):
            for uf in uploaded_files:
                uf.seek(0)
                try:
                    df_preview = pd.read_csv(uf, nrows=5)
                    st.markdown(f"**{uf.name}**")
                    st.dataframe(df_preview, use_container_width=True, hide_index=True)
                except Exception as e:
                    st.error(f"Gagal preview {uf.name}: {e}")
                uf.seek(0)

        st.divider()

        if st.button("Proses Import Semua File", type="primary", use_container_width=True):
            results = []
            progress = st.progress(0)
            status_text = st.empty()

            for i, uf in enumerate(uploaded_files):
                status_text.text(f"Memproses {uf.name}...")
                uf.seek(0)
                file_bytes = uf.read()
                result = import_csv(file_bytes, uf.name)
                results.append((uf.name, result))
                progress.progress((i + 1) / len(uploaded_files))

            progress.empty()
            status_text.empty()

            # Tampilkan hasil
            st.subheader("Hasil Import")
            all_success = True
            for fname, res in results:
                if res["success"]:
                    with st.container(border=True):
                        icon = "✅"
                        label = res.get("label", res["type"])
                        st.markdown(f"{icon} **{fname}** — {label}")
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("Total Baris", res.get("total_rows", 0))
                        col2.metric("Inserted", res.get("inserted", 0))
                        col3.metric("Updated", res.get("updated", 0))
                        col4.metric("Skipped/Replaced", res.get("skipped", 0))
                        if res.get("note"):
                            st.caption(f"ℹ️ {res['note']}")
                else:
                    all_success = False
                    st.error(f"❌ **{fname}** — Gagal: {res.get('message', 'Unknown error')}")

            if all_success:
                st.success("Semua file berhasil diimport! Data lama di luar rentang file tetap aman.")
                # Auto-upload ke Google Drive agar data permanen di cloud
                try:
                    from utils.gdrive_loader import upload_to_gdrive
                    import streamlit as st
                    with st.spinner("☁️ Menyimpan database ke Google Drive..."):
                        ok = upload_to_gdrive()
                    if ok:
                        st.success("☁️ Database berhasil disimpan ke Google Drive!")
                    else:
                        st.info("ℹ️ Mode lokal — database tidak di-sync ke Google Drive.")
                except Exception as e:
                    st.info(f"ℹ️ Upload GDrive dilewati: {e}")
                st.balloons()
            else:
                st.warning("Beberapa file gagal diimport. Cek pesan error di atas.")

    st.divider()

    # ── Riwayat Import ──────────────────────────────────────────
    st.subheader("Riwayat import")

    df_log = run_query("""
        SELECT
            file_type as "Tipe File",
            file_name as "Nama File",
            strftime(imported_at, '%d/%m/%Y %H:%M') as "Waktu Import",
            rows_inserted as "Inserted",
            rows_updated as "Updated",
            rows_skipped as "Skipped",
            status as "Status",
            message as "Keterangan"
        FROM import_log
        ORDER BY imported_at DESC
        LIMIT 50
    """)

    if not df_log.empty:
        # Color status column
        def highlight_status(val):
            if val == "success":
                return "color: green"
            return "color: red"

        st.dataframe(
            df_log,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Status": st.column_config.TextColumn("Status"),
            }
        )
    else:
        st.info("Belum ada riwayat import.")
