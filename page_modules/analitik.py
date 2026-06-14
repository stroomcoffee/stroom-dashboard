import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.database import run_query
from utils.style import PLOTLY_DARK, CHART_COLORS, dark_xaxis, dark_yaxis, BG2, BG3, TEXT_MUTED, ACCENT, ACCENT2, WARN, DANGER, TEXT, BORDER
from utils.helpers import fmt_rupiah, fmt_number


def show():
    st.title("Analitik Lanjutan")
    st.caption("Analisis lintas data: penjualan, bahan, resep, dan biaya")

    tab1, tab2, tab3 = st.tabs([
        "Estimasi Biaya Bahan vs Penjualan",
        "Analisis Bahan Kritis",
        "Performa per Periode"
    ])

    # ─────────────────────────────────────────────────────────────
    # Tab 1: Estimasi HPP sederhana
    # ─────────────────────────────────────────────────────────────
    with tab1:
        st.subheader("Estimasi biaya bahan (HPP) vs penjualan")
        st.caption(
            "Estimasi dihitung dari: qty terjual × kebutuhan bahan per porsi × rata-rata harga bahan dari PO. "
            "Ini adalah perkiraan, bukan HPP akurat."
        )

        # Join sales + recipe + PO cost
        df_hpp = run_query("""
            WITH sales_agg AS (
                SELECT item_name, SUM(quantity) as total_qty, SUM(net_sales) as total_sales
                FROM fact_sales_detail
                GROUP BY item_name
            ),
            recipe_cost AS (
                SELECT r.item_name,
                       SUM(r.ingredient_qty * COALESCE(p.avg_cost, 0)) as estimated_cogs_per_unit
                FROM fact_recipe r
                LEFT JOIN (
                    SELECT ingredient_name, AVG(unit_cost) as avg_cost
                    FROM fact_purchase_order
                    WHERE unit_cost > 0
                    GROUP BY ingredient_name
                ) p ON r.ingredient_name = p.ingredient_name
                GROUP BY r.item_name
            )
            SELECT
                s.item_name,
                s.total_qty,
                s.total_sales,
                COALESCE(rc.estimated_cogs_per_unit, 0) as cogs_per_unit,
                s.total_qty * COALESCE(rc.estimated_cogs_per_unit, 0) as total_estimated_cogs,
                s.total_sales - (s.total_qty * COALESCE(rc.estimated_cogs_per_unit, 0)) as estimated_gp,
                CASE
                    WHEN s.total_sales > 0
                    THEN ((s.total_sales - s.total_qty * COALESCE(rc.estimated_cogs_per_unit, 0))
                          / s.total_sales * 100)
                    ELSE 0
                END as gp_pct
            FROM sales_agg s
            LEFT JOIN recipe_cost rc ON s.item_name = rc.item_name
            ORDER BY estimated_gp DESC
        """)

        if not df_hpp.empty:
            # Summary KPI
            total_sales = df_hpp["total_sales"].sum()
            total_cogs = df_hpp["total_estimated_cogs"].sum()
            total_gp = df_hpp["estimated_gp"].sum()
            avg_gp_pct = (total_gp / total_sales * 100) if total_sales > 0 else 0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Net Sales", fmt_rupiah(total_sales))
            c2.metric("Est. Total COGS", fmt_rupiah(total_cogs))
            c3.metric("Est. Gross Profit", fmt_rupiah(total_gp))
            c4.metric("Est. GP Margin", f"{avg_gp_pct:.1f}%")

            # Scatter: GP% vs volume
            st.subheader("GP% vs volume penjualan per menu")
            df_scatter = df_hpp[df_hpp["total_sales"] > 0].copy()
            df_scatter = df_scatter[df_scatter["cogs_per_unit"] > 0]
            if not df_scatter.empty:
                fig = px.scatter(
                    df_scatter,
                    x="total_sales", y="gp_pct",
                    size="total_qty", text="item_name",
                    color="gp_pct",
                    color_continuous_scale=["#2A1212", "#F04D4D"],
                    labels={
                        "total_sales": "Total Net Sales",
                        "gp_pct": "Est. GP%",
                        "total_qty": "Qty Terjual"
                    },
                    size_max=40
                )
                fig.update_traces(textposition="top center", textfont_size=9)
                fig.update_layout(
                    height=450, margin=dict(l=0, r=0, t=10, b=0),
                    **PLOTLY_DARK
                )
                fig.update_xaxes(tickprefix="Rp ", tickformat=",.0f", showgrid=True, gridcolor="#1E2235")
                fig.update_yaxes(ticksuffix="%", showgrid=True, gridcolor="#1E2235")
                st.plotly_chart(fig, use_container_width=True)

            # Table
            df_hpp_show = df_hpp.copy()
            df_hpp_show["total_sales"] = df_hpp_show["total_sales"].apply(fmt_rupiah)
            df_hpp_show["total_estimated_cogs"] = df_hpp_show["total_estimated_cogs"].apply(fmt_rupiah)
            df_hpp_show["estimated_gp"] = df_hpp_show["estimated_gp"].apply(fmt_rupiah)
            df_hpp_show["cogs_per_unit"] = df_hpp_show["cogs_per_unit"].apply(lambda x: fmt_rupiah(x))
            df_hpp_show["gp_pct"] = df_hpp_show["gp_pct"].apply(lambda x: f"{x:.1f}%")

            st.dataframe(
                df_hpp_show.rename(columns={
                    "item_name": "Menu", "total_qty": "Qty",
                    "total_sales": "Net Sales", "cogs_per_unit": "Est. COGS/Unit",
                    "total_estimated_cogs": "Est. Total COGS",
                    "estimated_gp": "Est. GP", "gp_pct": "GP%"
                }),
                use_container_width=True, hide_index=True, height=400
            )
        else:
            st.info("Data belum cukup untuk kalkulasi HPP. Pastikan data PO, transaksi, dan resep sudah diimport.")

    # ─────────────────────────────────────────────────────────────
    # Tab 2: Analisis bahan kritis
    # ─────────────────────────────────────────────────────────────
    with tab2:
        st.subheader("Bahan kritis — stok rendah tapi dipakai banyak menu")

        df_critical = run_query("""
            WITH bahan_usage AS (
                SELECT ingredient_name, COUNT(DISTINCT item_name) as menu_count
                FROM fact_recipe
                GROUP BY ingredient_name
            ),
            stok_terkini AS (
                SELECT po.ingredient_name, po.in_stock, po.unit, po.category
                FROM fact_purchase_order po
                INNER JOIN (
                    SELECT ingredient_name, MAX(po_date) as latest
                    FROM fact_purchase_order GROUP BY ingredient_name
                ) lt ON po.ingredient_name = lt.ingredient_name AND po.po_date = lt.latest
            )
            SELECT
                s.ingredient_name,
                s.unit,
                s.category,
                s.in_stock,
                COALESCE(u.menu_count, 0) as menu_count,
                r.stock_alert
            FROM stok_terkini s
            LEFT JOIN bahan_usage u ON s.ingredient_name = u.ingredient_name
            LEFT JOIN (
                SELECT DISTINCT ingredient_name, stock_alert
                FROM fact_recipe WHERE stock_alert IN ('Out','Low')
            ) r ON s.ingredient_name = r.ingredient_name
            WHERE s.in_stock < 1000 OR r.stock_alert IS NOT NULL
            ORDER BY u.menu_count DESC NULLS LAST, s.in_stock ASC
        """)

        if not df_critical.empty:
            c1, c2 = st.columns(2)
            with c1:
                fig_crit = px.scatter(
                    df_critical,
                    x="in_stock", y="menu_count",
                    color="stock_alert",
                    text="ingredient_name",
                    color_discrete_map={"Out": "#E24B4A", "Low": "#EF9F27", None: "#1D9E75"},
                    labels={"in_stock": "Stok Saat Ini", "menu_count": "Digunakan di N Menu"},
                    size_max=20
                )
                fig_crit.update_traces(textposition="top center", textfont_size=8)
                fig_crit.update_layout(height=400, margin=dict(l=0, r=0, t=10, b=0),
                                       **PLOTLY_DARK)
                st.plotly_chart(fig_crit, use_container_width=True)

            with c2:
                df_critical["status"] = df_critical["stock_alert"].apply(
                    lambda x: "🔴 Out" if x == "Out" else ("🟡 Low" if x == "Low" else "🟢 OK")
                )
                df_critical["in_stock_fmt"] = df_critical["in_stock"].apply(lambda x: fmt_number(x, 2))
                st.dataframe(
                    df_critical[["status", "ingredient_name", "unit", "in_stock_fmt", "menu_count", "category"]].rename(
                        columns={
                            "status": "Alert", "ingredient_name": "Bahan",
                            "unit": "Satuan", "in_stock_fmt": "Stok",
                            "menu_count": "Digunakan di Menu", "category": "Kategori"
                        }
                    ),
                    use_container_width=True, hide_index=True, height=400
                )
        else:
            st.success("Tidak ada bahan kritis yang terdeteksi.")

    # ─────────────────────────────────────────────────────────────
    # Tab 3: Performa per periode
    # ─────────────────────────────────────────────────────────────
    with tab3:
        st.subheader("Performa penjualan per periode")

        period_type = st.radio("Granularitas", ["Harian", "Mingguan"], horizontal=True)

        if period_type == "Harian":
            df_period = run_query("""
                SELECT
                    sale_date as periode,
                    COUNT(DISTINCT receipt_number) as transaksi,
                    SUM(quantity) as total_qty,
                    SUM(gross_sales) as gross_sales,
                    SUM(discounts) as total_diskon,
                    SUM(net_sales) as net_sales,
                    SUM(net_sales) / COUNT(DISTINCT receipt_number) as avg_per_transaksi
                FROM fact_sales_detail
                GROUP BY sale_date
                ORDER BY sale_date
            """)
        else:
            df_period = run_query("""
                SELECT
                    DATE_TRUNC('week', sale_date) as periode,
                    COUNT(DISTINCT receipt_number) as transaksi,
                    SUM(quantity) as total_qty,
                    SUM(gross_sales) as gross_sales,
                    SUM(discounts) as total_diskon,
                    SUM(net_sales) as net_sales,
                    SUM(net_sales) / COUNT(DISTINCT receipt_number) as avg_per_transaksi
                FROM fact_sales_detail
                GROUP BY DATE_TRUNC('week', sale_date)
                ORDER BY periode
            """)

        if not df_period.empty:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df_period["periode"], y=df_period["gross_sales"],
                                 name="Gross Sales", marker_color="#B5D4F4"))
            fig.add_trace(go.Bar(x=df_period["periode"], y=df_period["net_sales"],
                                 name="Net Sales", marker_color="#1D9E75"))
            fig.add_trace(go.Scatter(x=df_period["periode"], y=df_period["transaksi"],
                                     name="Transaksi", yaxis="y2",
                                     line=dict(color="#D85A30", width=2)))
            fig.update_layout(
                height=350, barmode="group",
                legend=dict(orientation="h", y=1.12),
                yaxis=dict(tickprefix="Rp ", tickformat=",.0f"),
                yaxis2=dict(overlaying="y", side="right", title="Transaksi"),
                margin=dict(l=0, r=0, t=10, b=0),
                **PLOTLY_DARK
            )
            st.plotly_chart(fig, use_container_width=True)

            # Summary table
            df_period_show = df_period.copy()
            for col in ["gross_sales", "total_diskon", "net_sales", "avg_per_transaksi"]:
                df_period_show[col] = df_period_show[col].apply(fmt_rupiah)
            st.dataframe(
                df_period_show.rename(columns={
                    "periode": "Periode", "transaksi": "Transaksi",
                    "total_qty": "Total Qty", "gross_sales": "Gross Sales",
                    "total_diskon": "Diskon", "net_sales": "Net Sales",
                    "avg_per_transaksi": "Avg/Transaksi"
                }),
                use_container_width=True, hide_index=True
            )
        else:
            st.info("Belum ada data transaksi.")
