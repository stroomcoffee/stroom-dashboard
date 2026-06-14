import streamlit as st
import pandas as pd
import plotly.express as px
from utils.database import run_query
from utils.style import PLOTLY_DARK, CHART_COLORS, dark_xaxis, dark_yaxis, BG2, BG3, TEXT_MUTED, ACCENT, ACCENT2, WARN, DANGER, TEXT, BORDER
from utils.helpers import fmt_number, fmt_rupiah


def show():
    st.title("Inventori Bahan")
    st.caption("Status stok terkini — adjustment diutamakan di atas data PO jika tersedia")

    # ── Filter ──────────────────────────────────────────────────
    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
    with col_f1:
        search = st.text_input("Cari bahan", placeholder="Ketik nama bahan...")
    with col_f2:
        categories = run_query("SELECT DISTINCT category FROM v_stok_final WHERE category IS NOT NULL ORDER BY category")
        cat_list = ["Semua"] + categories["category"].tolist()
        selected_cat = st.selectbox("Kategori", cat_list)
    with col_f3:
        stock_filter = st.selectbox("Filter stok", ["Semua", "Stok rendah (<1000)", "Stok negatif", "Stok normal"])

    # ── Query stok final dari view ───────────────────────────────
    df_stok = run_query("""
        SELECT ingredient_name, unit, category,
               stok_final, po_in_stock, adj_actual_stock,
               adjustment, adj_date, po_date, order_no, stok_source
        FROM v_stok_final
        ORDER BY stok_final ASC NULLS FIRST
    """)

    # Apply filters
    if search:
        df_stok = df_stok[df_stok["ingredient_name"].str.lower().str.contains(search.lower())]
    if selected_cat != "Semua":
        df_stok = df_stok[df_stok["category"] == selected_cat]
    if stock_filter == "Stok rendah (<1000)":
        df_stok = df_stok[(df_stok["stok_final"] >= 0) & (df_stok["stok_final"] < 1000)]
    elif stock_filter == "Stok negatif":
        df_stok = df_stok[df_stok["stok_final"] < 0]
    elif stock_filter == "Stok normal":
        df_stok = df_stok[df_stok["stok_final"] >= 1000]

    # ── KPI Cards ───────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Total Jenis Bahan", len(df_stok))
    with c2:
        neg = len(df_stok[df_stok["stok_final"] < 0])
        st.metric("Stok Negatif 🔴", neg)
    with c3:
        low = len(df_stok[(df_stok["stok_final"] >= 0) & (df_stok["stok_final"] < 500)])
        st.metric("Stok Rendah 🟡", low)
    with c4:
        normal = len(df_stok[df_stok["stok_final"] >= 1000])
        st.metric("Stok Normal 🟢", normal)
    with c5:
        adj_count = len(df_stok[df_stok["stok_source"] == "adjusted"])
        st.metric("Sudah di-adjust", adj_count)

    # ── Info adjustment ──────────────────────────────────────────
    if (df_stok["stok_source"] == "adjusted").any():
        st.info(
            f"⚡ **{adj_count} bahan** menggunakan stok dari **Inventory Adjustment** (bukan PO). "
            "Kolom sumber menunjukkan 'adjusted' atau 'po_only'.",
            icon="ℹ️"
        )

    st.divider()

    # ── Chart: Top bahan stok rendah ────────────────────────────
    st.subheader("Bahan dengan stok paling rendah")
    df_chart = df_stok.nsmallest(15, "stok_final").copy()
    if not df_chart.empty:
        df_chart["warna"] = df_chart["stok_final"].apply(
            lambda x: "Negatif" if x < 0 else ("Rendah" if x < 500 else "Menengah")
        )
        color_map = {"Negatif": "#E24B4A", "Rendah": "#EF9F27", "Menengah": "#1D9E75"}
        fig = px.bar(
            df_chart, x="stok_final", y="ingredient_name", orientation="h",
            color="warna", color_discrete_map=color_map,
            labels={"stok_final": "Stok Final", "ingredient_name": ""},
        )
        fig.update_layout(
            height=420, margin=dict(l=0, r=0, t=10, b=0),
            legend_title="Status Stok",
            **PLOTLY_DARK,
            yaxis=dict(autorange="reversed")
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Tabel stok lengkap ───────────────────────────────────────
    st.subheader(f"Daftar stok bahan ({len(df_stok)} item)")

    def stock_icon(val):
        if val < 0: return "🔴"
        if val < 500: return "🟡"
        return "🟢"

    def source_badge(val):
        return "✏️ adj" if val == "adjusted" else "📦 po"

    df_display = df_stok.copy()
    df_display["Status"]        = df_display["stok_final"].apply(stock_icon)
    df_display["Sumber"]        = df_display["stok_source"].apply(source_badge)
    df_display["Stok Final"]    = df_display["stok_final"].apply(lambda x: fmt_number(x, 2))
    df_display["Stok PO"]       = df_display["po_in_stock"].apply(lambda x: fmt_number(x, 2) if pd.notna(x) else "-")
    df_display["Stok Adj"]      = df_display["adj_actual_stock"].apply(lambda x: fmt_number(x, 2) if pd.notna(x) else "-")
    df_display["Tgl Adj"]       = pd.to_datetime(df_display["adj_date"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("-")
    df_display["Tgl PO"]        = pd.to_datetime(df_display["po_date"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("-")

    st.dataframe(
        df_display[[
            "Status", "Sumber", "ingredient_name", "Stok Final", "unit",
            "category", "Stok Adj", "Tgl Adj", "Stok PO", "Tgl PO", "order_no"
        ]].rename(columns={
            "ingredient_name": "Nama Bahan",
            "unit": "Satuan",
            "category": "Kategori",
            "order_no": "No. PO"
        }),
        use_container_width=True, hide_index=True, height=550
    )

    st.caption("✏️ adj = stok dari Inventory Adjustment | 📦 po = stok dari Purchase Order")

    csv_data = df_display[["ingredient_name","stok_final","unit","category","stok_source","adj_date","po_date"]].to_csv(index=False).encode("utf-8")
    st.download_button("Download data stok (CSV)", data=csv_data,
                       file_name="stok_bahan_stroom.csv", mime="text/csv")
