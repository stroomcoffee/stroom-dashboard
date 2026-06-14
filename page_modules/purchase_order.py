import streamlit as st
import pandas as pd
import plotly.express as px
from utils.database import run_query
from utils.style import PLOTLY_DARK, dark_xaxis, dark_yaxis, ACCENT, ACCENT2, TEXT, TEXT_MUTED
from utils.helpers import fmt_rupiah, fmt_number, status_badge, safe_date
import datetime


def show():
    st.title("Purchase Order")
    st.caption("Riwayat dan analisis purchase order bahan")

    # ── Hitung rentang tanggal ────────────────────────────────────
    _today = datetime.date.today()
    _df_dates = run_query("SELECT MIN(po_date) as mn, MAX(po_date) as mx FROM fact_purchase_order")
    _min_date = safe_date(_df_dates["mn"].iloc[0] if not _df_dates.empty else None, _today.replace(day=1))
    _max_date = safe_date(_df_dates["mx"].iloc[0] if not _df_dates.empty else None, _today)

    # ── Filter baris 1: tanggal + kategori + status ───────────────
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        date_range = st.date_input(
            "Rentang tanggal", value=(_min_date, _max_date),
            min_value=_min_date, max_value=_max_date
        )
    with col2:
        cats = run_query(
            "SELECT DISTINCT category FROM fact_purchase_order WHERE category!='' ORDER BY category"
        )
        cat_opts = ["Semua"] + cats["category"].tolist()
        sel_cat = st.selectbox("Kategori", cat_opts)

    with col3:
        statuses = run_query(
            "SELECT DISTINCT status FROM fact_purchase_order WHERE status!='' ORDER BY status"
        )
        stat_opts = ["Semua"] + statuses["status"].tolist()
        sel_status = st.selectbox("Status", stat_opts)

    # ── Filter baris 2: dropdown bahan (dinamis per kategori) ─────
    # Ambil daftar bahan berdasarkan kategori yang dipilih
    if sel_cat != "Semua":
        df_bahan_opts = run_query(
            "SELECT DISTINCT ingredient_name FROM fact_purchase_order WHERE category=? ORDER BY ingredient_name",
            [sel_cat]
        )
    else:
        df_bahan_opts = run_query(
            "SELECT DISTINCT ingredient_name FROM fact_purchase_order ORDER BY ingredient_name"
        )
    bahan_list = df_bahan_opts["ingredient_name"].tolist()

    col4, col5 = st.columns([2, 2])
    with col4:
        # Multiselect bahan — default kosong = semua
        selected_bahans = st.multiselect(
            f"Filter bahan {'(Kategori: ' + sel_cat + ')' if sel_cat != 'Semua' else '(Semua Kategori)'}",
            options=bahan_list,
            placeholder=f"Semua bahan{' ' + sel_cat if sel_cat != 'Semua' else ''} ditampilkan..."
        )
    with col5:
        search_bahan = st.text_input("Cari bahan", placeholder="Ketik nama bahan...")

    # ── Build WHERE clause ────────────────────────────────────────
    where_clauses = ["1=1"]
    params = []

    if len(date_range) == 2:
        where_clauses.append("CAST(po_date AS DATE) BETWEEN ? AND ?")
        params += [date_range[0], date_range[1]]
    if sel_cat != "Semua":
        where_clauses.append("category = ?")
        params.append(sel_cat)
    if sel_status != "Semua":
        where_clauses.append("status = ?")
        params.append(sel_status)
    if selected_bahans:
        ph = ",".join(["?" for _ in selected_bahans])
        where_clauses.append(f"ingredient_name IN ({ph})")
        params += selected_bahans
    if search_bahan:
        where_clauses.append("LOWER(ingredient_name) LIKE ?")
        params.append(f"%{search_bahan.lower()}%")

    where_str = " AND ".join(where_clauses)

    df_po = run_query(f"""
        SELECT * FROM fact_purchase_order
        WHERE {where_str}
        ORDER BY po_date DESC
    """, params if params else None)

    # ── KPI ───────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Item PO", len(df_po))
    with c2:
        st.metric("Jumlah PO", df_po["order_no"].nunique() if not df_po.empty else 0)
    with c3:
        st.metric("Total Nilai PO", fmt_rupiah(df_po["total_cost"].sum() if not df_po.empty else 0))
    with c4:
        completed = len(df_po[df_po["status"] == "Completed"]) if not df_po.empty else 0
        st.metric("PO Completed", completed)

    st.divider()

    # ── Charts ────────────────────────────────────────────────────
    if not df_po.empty:
        col_c1, col_c2 = st.columns(2)

        with col_c1:
            st.subheader("Nilai PO per hari")
            df_daily = df_po.copy()
            df_daily["tanggal"] = pd.to_datetime(df_daily["po_date"]).dt.strftime("%d-%b")
            df_daily_grp = (
                df_daily.groupby("tanggal")["total_cost"]
                .sum()
                .reset_index()
                .sort_values("tanggal")
            )
            fig1 = px.bar(
                df_daily_grp, x="tanggal", y="total_cost",
                color_discrete_sequence=[ACCENT],
                labels={"tanggal": "Tanggal", "total_cost": "Total Nilai"},
                text=df_daily_grp["total_cost"].apply(lambda x: fmt_rupiah(x))
            )
            fig1.update_layout(
                **PLOTLY_DARK, height=260,
                xaxis=dict(
                    type="category",  # ← kunci: category bukan date, skip tanggal kosong
                    showgrid=False, color=TEXT_MUTED, tickangle=-30
                ),
                yaxis=dark_yaxis(tickprefix="Rp ", tickformat=",.0f"),
                margin=dict(l=0, r=0, t=10, b=0)
            )
            fig1.update_traces(textposition="outside", textfont=dict(color=TEXT, size=9))
            st.plotly_chart(fig1, use_container_width=True)

        with col_c2:
            st.subheader("Top 10 bahan terbesar nilainya")
            df_top = df_po.groupby("ingredient_name")["total_cost"].sum().reset_index()
            df_top = df_top.nlargest(10, "total_cost")
            fig2 = px.bar(
                df_top, x="total_cost", y="ingredient_name", orientation="h",
                color_discrete_sequence=[ACCENT2],
                labels={"total_cost": "Total Nilai", "ingredient_name": ""}
            )
            fig2.update_layout(
                **PLOTLY_DARK, height=260,
                xaxis=dark_xaxis(tickprefix="Rp ", tickformat=",.0f", showgrid=True, gridcolor="#1E2235"),
                yaxis=dark_yaxis(autorange="reversed", showgrid=False),
                margin=dict(l=0, r=0, t=10, b=0)
            )
            st.plotly_chart(fig2, use_container_width=True)

        st.divider()

    # ── Tabel PO ──────────────────────────────────────────────────
    # Info filter aktif
    active_filters = []
    if sel_cat != "Semua":       active_filters.append(f"Kategori: **{sel_cat}**")
    if sel_status != "Semua":    active_filters.append(f"Status: **{sel_status}**")
    if selected_bahans:          active_filters.append(f"Bahan: **{', '.join(selected_bahans[:3])}{'...' if len(selected_bahans)>3 else ''}**")
    if search_bahan:             active_filters.append(f"Kata kunci: **{search_bahan}**")
    if active_filters:
        st.caption("Filter aktif: " + " · ".join(active_filters))

    st.subheader(f"Detail PO ({len(df_po)} baris)")

    if not df_po.empty:
        df_show = df_po.copy()
        df_show["po_date_fmt"]   = pd.to_datetime(df_show["po_date"]).dt.strftime("%d/%m/%Y %H:%M")
        df_show["in_stock_fmt"]  = df_show["in_stock"].apply(lambda x: fmt_number(x, 2))
        df_show["order_qty_fmt"] = df_show["order_qty"].apply(lambda x: fmt_number(x, 0))
        df_show["unit_cost_fmt"] = df_show["unit_cost"].apply(fmt_rupiah)
        df_show["total_cost_fmt"]= df_show["total_cost"].apply(fmt_rupiah)
        df_show["status_icon"]   = df_show["status"].apply(status_badge)

        st.dataframe(
            df_show[[
                "po_date_fmt", "order_no", "ingredient_name", "unit",
                "category", "in_stock_fmt", "order_qty_fmt",
                "unit_cost_fmt", "total_cost_fmt", "status_icon", "status"
            ]].rename(columns={
                "po_date_fmt":    "Tanggal",
                "order_no":       "No. PO",
                "ingredient_name":"Bahan",
                "unit":           "Satuan",
                "category":       "Kategori",
                "in_stock_fmt":   "Stok",
                "order_qty_fmt":  "Qty Order",
                "unit_cost_fmt":  "Harga Satuan",
                "total_cost_fmt": "Total",
                "status_icon":    "",
                "status":         "Status"
            }),
            use_container_width=True, hide_index=True, height=500
        )

        csv_data = df_po.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download data PO (CSV)",
            data=csv_data,
            file_name="purchase_order_stroom.csv",
            mime="text/csv"
        )
    else:
        st.info("Tidak ada data PO untuk filter yang dipilih.")

    st.divider()

    # ── Ringkasan per bahan ────────────────────────────────────────
    st.subheader("Ringkasan PO per bahan")
    df_summary = run_query(f"""
        SELECT
            ingredient_name as "Bahan",
            unit as "Satuan",
            category as "Kategori",
            COUNT(*) as "Jumlah PO",
            SUM(order_qty) as "Total Qty Order",
            AVG(unit_cost) as "Rata-rata Harga",
            SUM(total_cost) as "Total Nilai",
            MAX(po_date) as "PO Terakhir"
        FROM fact_purchase_order
        WHERE {where_str}
        GROUP BY ingredient_name, unit, category
        ORDER BY SUM(total_cost) DESC
    """, params if params else None)

    if not df_summary.empty:
        df_summary["Rata-rata Harga"] = df_summary["Rata-rata Harga"].apply(fmt_rupiah)
        df_summary["Total Nilai"]     = df_summary["Total Nilai"].apply(fmt_rupiah)
        df_summary["PO Terakhir"]     = pd.to_datetime(df_summary["PO Terakhir"]).dt.strftime("%d/%m/%Y")
        st.dataframe(df_summary, use_container_width=True, hide_index=True, height=400)