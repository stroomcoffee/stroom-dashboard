import streamlit as st
import pandas as pd
import datetime
import plotly.express as px
import plotly.graph_objects as go
from utils.database import run_query
from utils.style import PLOTLY_DARK, CHART_COLORS, dark_xaxis, dark_yaxis, BG2, BG3, TEXT_MUTED, ACCENT, ACCENT2, WARN, DANGER, TEXT, BORDER
from utils.helpers import fmt_rupiah, fmt_number, safe_date


def show():
    st.title("Transaksi Penjualan")
    st.caption("Analisis detail penjualan dari Moka POS — termasuk Invoice (B2B/Korporat)")

    # ── Hitung min/max tanggal di luar tab agar bisa dipakai semua tab ──
    today = datetime.date.today()
    df_dates = run_query("SELECT MIN(CAST(sale_date AS VARCHAR)) as mn, MAX(CAST(sale_date AS VARCHAR)) as mx FROM fact_sales_detail")
    raw_mn = df_dates["mn"].iloc[0] if not df_dates.empty else None
    raw_mx = df_dates["mx"].iloc[0] if not df_dates.empty else None
    min_date = safe_date(raw_mn, today.replace(day=1))
    max_date = safe_date(raw_mx, today)
    min_date = datetime.date(min_date.year, min_date.month, min_date.day)
    max_date = datetime.date(max_date.year, max_date.month, max_date.day)

    tab_retail, tab_invoice, tab_combined = st.tabs(["📋 Retail (Item Details)", "🧾 Invoice", "📊 Gabungan"])

    with tab_retail:

        # ── Filter ───────────────────────────────────────────────────
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            date_range = st.date_input("Rentang tanggal", value=(min_date, max_date),
                                       min_value=min_date, max_value=max_date)

        with col2:
            cats = run_query("""
                SELECT DISTINCT category FROM fact_sales_detail
                WHERE category NOT IN ('','Uncategorized','Stok BAR')
                ORDER BY category
            """)
            cat_opts = ["Semua"] + cats["category"].tolist()
            sel_cat = st.selectbox("Kategori", cat_opts)

        with col3:
            types = run_query("SELECT DISTINCT sales_type FROM fact_sales_detail WHERE sales_type != '' ORDER BY sales_type")
            type_opts = ["Semua"] + types["sales_type"].tolist()
            sel_type = st.selectbox("Tipe penjualan", type_opts)

        with col4:
            pays = run_query("SELECT DISTINCT payment_method FROM fact_sales_detail WHERE payment_method != '' ORDER BY payment_method")
            pay_opts = ["Semua"] + pays["payment_method"].tolist()
            sel_pay = st.selectbox("Metode bayar", pay_opts)

        # ── Build query ───────────────────────────────────────────────
        where = ["1=1"]
        params = []
        if len(date_range) == 2:
            d_start, d_end = date_range[0], date_range[1]
            where.append("sale_date BETWEEN ? AND ?")
            params += [d_start, d_end]
        else:
            d_start, d_end = min_date, max_date

        if sel_cat != "Semua":
            where.append("category = ?")
            params.append(sel_cat)
        if sel_type != "Semua":
            where.append("sales_type = ?")
            params.append(sel_type)
        if sel_pay != "Semua":
            where.append("payment_method = ?")
            params.append(sel_pay)
        where_str = " AND ".join(where)

        df = run_query(f"""
            SELECT * FROM fact_sales_detail
            WHERE {where_str}
            ORDER BY sale_date DESC, sale_time DESC
        """, params if params else None)

        # ── KPI ──────────────────────────────────────────────────────
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric("Total Transaksi", df["receipt_number"].nunique() if not df.empty else 0)
        with c2:
            st.metric("Total Item Terjual", int(df["quantity"].sum()) if not df.empty else 0)
        with c3:
            st.metric("Gross Sales", fmt_rupiah(df["gross_sales"].sum() if not df.empty else 0))
        with c4:
            st.metric("Total Diskon", fmt_rupiah(df["discounts"].sum() if not df.empty else 0))
        with c5:
            st.metric("Net Sales", fmt_rupiah(df["net_sales"].sum() if not df.empty else 0))

        st.divider()

        if not df.empty:
            # ── Tren harian ──────────────────────────────────────────
            st.subheader("Tren harian")
            df_daily = df.groupby("sale_date").agg(
                gross_sales=("gross_sales", "sum"),
                net_sales=("net_sales", "sum"),
                discounts=("discounts", "sum"),
                qty=("quantity", "sum"),
                transaksi=("receipt_number", "nunique")
            ).reset_index()

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=df_daily["sale_date"], y=df_daily["gross_sales"],
                name="Gross Sales", marker_color="#B5D4F4", opacity=0.8
            ))
            fig.add_trace(go.Scatter(
                x=df_daily["sale_date"], y=df_daily["net_sales"],
                name="Net Sales", line=dict(color=ACCENT, width=2.5), yaxis="y"
            ))
            fig.update_layout(
                **PLOTLY_DARK, height=300,
                xaxis=dark_xaxis(),
                yaxis=dark_yaxis(tickprefix="Rp ", tickformat=",.0f"),
                legend=dict(orientation="h", y=1.12, bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT)),
                barmode="overlay", margin=dict(l=0, r=0, t=10, b=0)
            )
            st.plotly_chart(fig, use_container_width=True)

            st.divider()

            # ── Per Kategori & Per Item ───────────────────────────────
            col_l, col_r = st.columns(2)

            with col_l:
                st.subheader("Penjualan per kategori")
                df_cat = df.groupby("category").agg(
                    net_sales=("net_sales", "sum"),
                    qty=("quantity", "sum")
                ).reset_index().sort_values("net_sales", ascending=False)
                fig2 = go.Figure(go.Bar(
                    x=df_cat["net_sales"], y=df_cat["category"], orientation="h",
                    marker=dict(color=df_cat["net_sales"],
                                colorscale=[[0,"#112228"],[1, ACCENT]], showscale=False),
                ))
                fig2.update_layout(**PLOTLY_DARK, height=300,
                                   xaxis=dark_xaxis(tickprefix="Rp ", tickformat=",.0f", showgrid=True, gridcolor="#1E2235"),
                                   yaxis=dark_yaxis(autorange="reversed", showgrid=False),
                                   margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig2, use_container_width=True)

            with col_r:
                st.subheader("Top 10 item terlaris")
                df_item = df.groupby("item_name").agg(
                    qty=("quantity", "sum"),
                    net_sales=("net_sales", "sum")
                ).reset_index().nlargest(10, "qty")
                fig3 = go.Figure(go.Bar(
                    x=df_item["qty"], y=df_item["item_name"], orientation="h",
                    marker=dict(color=df_item["net_sales"],
                                colorscale=[[0,"#111A2A"],[1, ACCENT2]], showscale=False),
                ))
                fig3.update_layout(**PLOTLY_DARK, height=300,
                                   xaxis=dark_xaxis(showgrid=True, gridcolor="#1E2235"),
                                   yaxis=dark_yaxis(autorange="reversed", showgrid=False),
                                   margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig3, use_container_width=True)

            st.divider()

            # ── Analisis per jam ──────────────────────────────────────
            st.subheader("Pola penjualan per jam")
            df["jam"] = df["sale_time"].str[:2].astype(str)
            df_jam = df.groupby("jam").agg(
                net_sales=("net_sales", "sum"),
                transaksi=("receipt_number", "nunique")
            ).reset_index().sort_values("jam")
            fig4 = go.Figure()
            fig4.add_trace(go.Bar(
                x=df_jam["jam"], y=df_jam["transaksi"],
                name="Jumlah Transaksi", marker_color=ACCENT2, opacity=0.7
            ))
            fig4.add_trace(go.Scatter(
                x=df_jam["jam"], y=df_jam["net_sales"],
                name="Net Sales", yaxis="y2",
                line=dict(color=ACCENT, width=2)
            ))
            fig4.update_layout(
                **PLOTLY_DARK, height=260,
                xaxis=dark_xaxis(title="Jam"),
                yaxis=dark_yaxis(title="Jumlah Transaksi"),
                yaxis2=dict(overlaying="y", side="right", showgrid=False,
                            color=TEXT_MUTED, tickprefix="Rp ", tickformat=",.0f"),
                legend=dict(orientation="h", y=1.12, bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT)),
                margin=dict(l=0, r=0, t=10, b=0)
            )
            st.plotly_chart(fig4, use_container_width=True)

            st.divider()

        # ── Tabel transaksi ───────────────────────────────────────────
        st.subheader(f"Detail transaksi ({len(df)} baris)")

        PAGE_SIZE = 200
        total_pages = max(1, (len(df) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = st.number_input("Halaman", min_value=1, max_value=total_pages, value=1) if total_pages > 1 else 1

        df_page = df.iloc[(page - 1) * PAGE_SIZE: page * PAGE_SIZE].copy()

        if not df_page.empty:
            df_page["gross_sales_fmt"] = df_page["gross_sales"].apply(fmt_rupiah)
            df_page["net_sales_fmt"]   = df_page["net_sales"].apply(fmt_rupiah)
            df_page["discounts_fmt"]   = df_page["discounts"].apply(fmt_rupiah)
            st.dataframe(
                df_page[[
                    "sale_date", "sale_time", "receipt_number", "category",
                    "item_name", "variant", "quantity", "gross_sales_fmt",
                    "discounts_fmt", "net_sales_fmt", "sales_type", "payment_method"
                ]].rename(columns={
                    "sale_date": "Tanggal", "sale_time": "Jam", "receipt_number": "No. Struk",
                    "category": "Kategori", "item_name": "Item", "variant": "Varian",
                    "quantity": "Qty", "gross_sales_fmt": "Gross Sales",
                    "discounts_fmt": "Diskon", "net_sales_fmt": "Net Sales",
                    "sales_type": "Tipe", "payment_method": "Pembayaran"
                }),
                use_container_width=True, hide_index=True, height=500
            )
            st.caption(f"Menampilkan {len(df_page)} dari {len(df)} baris (halaman {page}/{total_pages})")
        else:
            st.info("Tidak ada data untuk filter yang dipilih.")

        if not df.empty:
            csv_data = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download data transaksi (CSV)", data=csv_data,
                               file_name="transaksi_stroom.csv", mime="text/csv")

    # ── Tab Invoice ───────────────────────────────────────────────────
    with tab_invoice:
        st.subheader("Transaksi Invoice / Korporat")
        st.caption("Pesanan invoice B2B — SPV, perusahaan, catering, dll")

        col_i1, col_i2 = st.columns([3, 1])
        with col_i1:
            inv_range = st.date_input("Rentang tanggal invoice", value=(min_date, max_date),
                                      min_value=min_date, max_value=max_date,
                                      key="inv_date_range")
        inv_start = inv_range[0] if len(inv_range) == 2 else min_date
        inv_end   = inv_range[1] if len(inv_range) == 2 else max_date

        try:
            df_inv = run_query("""
                SELECT inv_date as sale_date, invoice_number, customer,
                       category, item_name, variant, quantity,
                       gross_sales, net_sales, sales_type, collected_by
                FROM fact_invoice
                WHERE inv_date BETWEEN ? AND ?
                ORDER BY inv_date DESC, invoice_number
            """, [inv_start, inv_end])

            if df_inv.empty:
                st.info("Belum ada data invoice untuk periode ini. Upload file Invoice Item Details dari halaman Import Data CSV.")
            else:
                ci1, ci2, ci3, ci4 = st.columns(4)
                ci1.metric("Total Invoice",  df_inv["invoice_number"].nunique())
                ci2.metric("Item Terjual",   f"{int(df_inv['quantity'].sum()):,}")
                ci3.metric("Gross Sales",    fmt_rupiah(df_inv["gross_sales"].sum()))
                ci4.metric("Net Sales",      fmt_rupiah(df_inv["net_sales"].sum()))

                st.dataframe(
                    df_inv.rename(columns={
                        "sale_date": "Tanggal", "invoice_number": "No. Invoice",
                        "customer": "Customer", "category": "Kategori",
                        "item_name": "Item", "variant": "Varian", "quantity": "Qty",
                        "gross_sales": "Gross", "net_sales": "Net",
                        "sales_type": "Tipe", "collected_by": "Kasir"
                    }),
                    use_container_width=True, hide_index=True, height=500
                )
                csv_inv = df_inv.to_csv(index=False).encode("utf-8")
                st.download_button("Download data invoice (CSV)", data=csv_inv,
                                   file_name="invoice_stroom.csv", mime="text/csv")
        except Exception:
            st.info("Belum ada data invoice. Upload file Invoice Item Details dari halaman Import Data CSV.")

    # ── Tab Gabungan ──────────────────────────────────────────────────
    with tab_combined:
        st.subheader("Gabungan Retail + Invoice")
        st.caption("Total penjualan sesungguhnya — retail kasir + invoice korporat")

        col_g1, _ = st.columns([3, 1])
        with col_g1:
            comb_range = st.date_input("Rentang tanggal", value=(min_date, max_date),
                                       min_value=min_date, max_value=max_date,
                                       key="comb_date_range")
        comb_start = comb_range[0] if len(comb_range) == 2 else min_date
        comb_end   = comb_range[1] if len(comb_range) == 2 else max_date

        try:
            df_comb = run_query("""
                SELECT sale_date, 'retail' as sumber,
                       receipt_number as doc_number, item_name, variant,
                       quantity, gross_sales, net_sales, sales_type, category
                FROM fact_sales_detail WHERE sale_date BETWEEN ? AND ?
                UNION ALL
                SELECT inv_date, 'invoice' as sumber,
                       invoice_number as doc_number, item_name, variant,
                       quantity, gross_sales, net_sales, sales_type, category
                FROM fact_invoice WHERE inv_date BETWEEN ? AND ?
                ORDER BY sale_date DESC
            """, [comb_start, comb_end, comb_start, comb_end])

            if df_comb.empty:
                st.info("Tidak ada data untuk periode ini.")
            else:
                retail_net  = df_comb[df_comb["sumber"] == "retail"]["net_sales"].sum()
                invoice_net = df_comb[df_comb["sumber"] == "invoice"]["net_sales"].sum()
                cc1, cc2, cc3 = st.columns(3)
                cc1.metric("Net Sales Retail",  fmt_rupiah(retail_net))
                cc2.metric("Net Sales Invoice",  fmt_rupiah(invoice_net))
                cc3.metric("Total Gabungan",     fmt_rupiah(retail_net + invoice_net))

                st.subheader("Top 20 item (retail + invoice)")
                df_top_comb = (
                    df_comb.groupby(["item_name", "sumber"])["quantity"]
                    .sum().reset_index()
                    .sort_values("quantity", ascending=False)
                    .head(20)
                )
                fig = px.bar(
                    df_top_comb, x="quantity", y="item_name", color="sumber",
                    orientation="h", barmode="stack",
                    color_discrete_map={"retail": ACCENT, "invoice": ACCENT2},
                    labels={"quantity": "Qty", "item_name": "", "sumber": "Sumber"}
                )
                fig.update_layout(
                    **PLOTLY_DARK, height=450,
                    xaxis=dark_xaxis(showgrid=True, gridcolor="#1E2235"),
                    yaxis=dark_yaxis(autorange="reversed", showgrid=False),
                    legend=dict(orientation="h", y=1.1, bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT)),
                    margin=dict(l=0, r=0, t=30, b=0)
                )
                st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"Error: {e}")
            st.info("Upload data retail dan invoice untuk melihat tampilan gabungan.")