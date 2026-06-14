import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import plotly.graph_objects as go
from utils.database import run_query
from utils.style import (PLOTLY_DARK, CHART_COLORS, dark_xaxis, dark_yaxis,
                         BG2, BG3, TEXT_MUTED, ACCENT, ACCENT2, WARN, DANGER, TEXT, BORDER)
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
               adjustment, adj_date, po_date, order_no, stok_source,
               po_after_adj, konsumsi_after_adj
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
    df_display["Status"]         = df_display["stok_final"].apply(stock_icon)
    df_display["Sumber"]         = df_display["stok_source"].apply(source_badge)
    df_display["Stok Adj"]       = df_display["adj_actual_stock"].apply(lambda x: fmt_number(x, 2) if pd.notna(x) else "-")
    df_display["Tgl Adj"]        = pd.to_datetime(df_display["adj_date"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("-")
    df_display["PO Setelah Adj"] = df_display["po_after_adj"].apply(lambda x: fmt_number(x, 2) if pd.notna(x) and x > 0 else "-")
    df_display["Konsumsi"]       = df_display["konsumsi_after_adj"].apply(lambda x: fmt_number(x, 2) if pd.notna(x) and x > 0 else "-")
    df_display["Stok Real"]      = df_display["stok_final"].apply(lambda x: fmt_number(x, 2))
    df_display["Tgl PO"]         = pd.to_datetime(df_display["po_date"], errors="coerce").dt.strftime("%d/%m/%Y").fillna("-")

    st.dataframe(
        df_display[[
            "Status", "Sumber", "ingredient_name", "unit", "category",
            "Stok Adj", "Tgl Adj", "PO Setelah Adj", "Konsumsi", "Stok Real"
        ]].rename(columns={
            "ingredient_name": "Nama Bahan",
            "unit": "Satuan",
            "category": "Kategori",
        }),
        use_container_width=True, hide_index=True, height=550
    )

    st.caption("Stok Real = Stok Adjustment + PO Setelah Adj − Konsumsi Penjualan | ✏️ adj = dari Adjustment | 📦 po = dari PO")

    csv_data = df_display[["ingredient_name","unit","category","stok_source","Stok Adj","Tgl Adj","PO Setelah Adj","Konsumsi","Stok Real"]].to_csv(index=False).encode("utf-8")
    st.download_button("Download data stok (CSV)", data=csv_data,
                       file_name="stok_real_stroom.csv", mime="text/csv")

    st.divider()

    # ── Analisis Konsumsi Bahan per Periode ─────────────────────
    st.subheader("Analisis Konsumsi Bahan per Periode")
    st.caption("Estimasi konsumsi bahan berdasarkan penjualan × resep dalam periode tertentu")

    today = datetime.date.today()
    col_k1, col_k2, col_k3 = st.columns([2, 2, 2])
    with col_k1:
        k_range = st.date_input(
            "Rentang tanggal konsumsi",
            value=(today.replace(day=1), today),
            key="konsumsi_date_range"
        )
    with col_k2:
        df_bahan_list = run_query("""
            SELECT DISTINCT r.ingredient_name
            FROM fact_recipe r
            ORDER BY r.ingredient_name
        """)
        bahan_options = df_bahan_list["ingredient_name"].tolist() if not df_bahan_list.empty else []
        selected_bahan = st.multiselect(
            "Pilih bahan (max 5)",
            options=bahan_options,
            default=bahan_options[:3] if len(bahan_options) >= 3 else bahan_options,
            max_selections=5,
            key="konsumsi_bahan_select"
        )
    with col_k3:
        tampilan = st.radio(
            "Tampilan",
            ["Per hari", "Per minggu"],
            horizontal=True,
            key="konsumsi_tampilan"
        )

    if len(k_range) == 2 and selected_bahan:
        k_start, k_end = k_range
        bahan_in = "'" + "','".join(selected_bahan) + "'"

        df_konsumsi = run_query(f"""
            SELECT
                s.sale_date,
                r.ingredient_name,
                r.ingredient_unit as unit,
                SUM(s.quantity * r.ingredient_qty) as total_konsumsi
            FROM fact_sales_detail s
            JOIN fact_recipe r ON LOWER(TRIM(s.item_name)) = LOWER(TRIM(r.item_name))
            WHERE s.sale_date BETWEEN ? AND ?
              AND r.ingredient_name IN ({bahan_in})
              AND s.quantity > 0
              AND r.ingredient_qty > 0
            GROUP BY s.sale_date, r.ingredient_name, r.ingredient_unit
            ORDER BY s.sale_date
        """, [k_start, k_end])

        if not df_konsumsi.empty:
            df_konsumsi["sale_date"] = pd.to_datetime(df_konsumsi["sale_date"])

            if tampilan == "Per minggu":
                df_konsumsi["periode"] = df_konsumsi["sale_date"].dt.to_period("W").apply(
                    lambda r: r.start_time.strftime("%d/%m")
                )
            else:
                df_konsumsi["periode"] = df_konsumsi["sale_date"].dt.strftime("%d/%m")

            df_plot = df_konsumsi.groupby(["periode", "ingredient_name", "unit"])["total_konsumsi"].sum().reset_index()

            warna_list = [ACCENT, ACCENT2, WARN, DANGER, "#A78BFA"]
            fig_k = go.Figure()
            for i, bahan in enumerate(selected_bahan):
                df_b = df_plot[df_plot["ingredient_name"] == bahan]
                if df_b.empty:
                    continue
                unit = df_b["unit"].iloc[0]
                warna = warna_list[i % len(warna_list)]
                fig_k.add_trace(go.Scatter(
                    x=df_b["periode"], y=df_b["total_konsumsi"],
                    name=f"{bahan} ({unit})",
                    mode="lines+markers",
                    line=dict(color=warna, width=2.5),
                    marker=dict(size=6, color=warna),
                    hovertemplate=f"<b>{bahan}</b><br>%{{x}}<br>Konsumsi: %{{y:,.1f}} {unit}<extra></extra>"
                ))

            fig_k.update_layout(
                **PLOTLY_DARK,
                height=380,
                xaxis=dark_xaxis(title="Tanggal"),
                yaxis=dark_yaxis(title="Jumlah Konsumsi"),
                legend=dict(orientation="h", y=1.12, x=0, bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT)),
                margin=dict(l=0, r=0, t=40, b=0)
            )
            st.plotly_chart(fig_k, use_container_width=True)

            st.markdown("**Total konsumsi per bahan dalam periode ini:**")
            df_summary = df_plot.groupby(["ingredient_name", "unit"])["total_konsumsi"].sum().reset_index()
            df_summary.columns = ["Nama Bahan", "Satuan", "Total Konsumsi"]
            df_summary["Total Konsumsi"] = df_summary["Total Konsumsi"].apply(lambda x: f"{x:,.1f}")
            st.dataframe(df_summary.sort_values("Nama Bahan"), use_container_width=True, hide_index=True)
        else:
            st.info("Tidak ada data konsumsi untuk bahan dan periode yang dipilih.")
    elif not selected_bahan:
        st.info("Pilih minimal 1 bahan untuk melihat pergerakan konsumsi.")