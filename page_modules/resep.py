import streamlit as st
import pandas as pd
import plotly.express as px
from utils.database import run_query
from utils.style import PLOTLY_DARK, CHART_COLORS, BG2, TEXT_MUTED, ACCENT, ACCENT2, WARN, DANGER, TEXT, BORDER
from utils.helpers import fmt_number, alert_color


def show():
    st.title("Resep & BOM")
    st.caption("Bill of Materials — kebutuhan bahan per menu")

    # ── Filter ───────────────────────────────────────────────────
    col1, col2, col3 = st.columns([3, 2, 2])
    with col1:
        search_menu = st.text_input("Cari menu", placeholder="Nama menu...")
    with col2:
        search_bahan = st.text_input("Cari bahan", placeholder="Nama bahan...")
    with col3:
        alert_filter = st.selectbox("Filter stock alert", ["Semua", "Out", "Low", "Normal"])

    # ── Query ─────────────────────────────────────────────────────
    where = ["1=1"]
    params = []
    if search_menu:
        where.append("LOWER(item_name) LIKE ?")
        params.append(f"%{search_menu.lower()}%")
    if search_bahan:
        where.append("LOWER(ingredient_name) LIKE ?")
        params.append(f"%{search_bahan.lower()}%")
    if alert_filter == "Out":
        where.append("stock_alert = 'Out'")
    elif alert_filter == "Low":
        where.append("stock_alert = 'Low'")
    elif alert_filter == "Normal":
        where.append("(stock_alert = '' OR stock_alert IS NULL)")
    where_str = " AND ".join(where)

    df = run_query(f"""
        SELECT item_name, variant_name, ingredient_name,
               ingredient_qty, ingredient_unit, stock_alert
        FROM fact_recipe
        WHERE {where_str}
        ORDER BY item_name, variant_name, ingredient_name
    """, params if params else None)

    # ── KPI ──────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    total_menu = run_query("SELECT COUNT(DISTINCT item_name) as v FROM fact_recipe")
    total_bahan = run_query("SELECT COUNT(DISTINCT ingredient_name) as v FROM fact_recipe")
    out_count = run_query("SELECT COUNT(DISTINCT ingredient_name) as v FROM fact_recipe WHERE stock_alert = 'Out'")
    low_count = run_query("SELECT COUNT(DISTINCT ingredient_name) as v FROM fact_recipe WHERE stock_alert = 'Low'")

    with c1:
        st.metric("Total Menu", total_menu["v"].iloc[0])
    with c2:
        st.metric("Total Bahan Digunakan", total_bahan["v"].iloc[0])
    with c3:
        st.metric("Bahan Stock Out 🔴", out_count["v"].iloc[0])
    with c4:
        st.metric("Bahan Stock Low 🟡", low_count["v"].iloc[0])

    st.divider()

    # ── Chart: Bahan paling banyak digunakan di resep ─────────────
    col_ca, col_cb = st.columns(2)

    with col_ca:
        st.subheader("Bahan paling banyak digunakan")
        df_usage = run_query("""
            SELECT ingredient_name, COUNT(DISTINCT item_name) as jumlah_menu, stock_alert
            FROM fact_recipe
            GROUP BY ingredient_name, stock_alert
            ORDER BY jumlah_menu DESC
            LIMIT 15
        """)
        if not df_usage.empty:
            df_usage["warna"] = df_usage["stock_alert"].apply(
                lambda x: "Out" if x == "Out" else ("Low" if x == "Low" else "Normal")
            )
            color_map = {"Out": "#E24B4A", "Low": "#EF9F27", "Normal": "#1D9E75"}
            fig1 = px.bar(
                df_usage, x="jumlah_menu", y="ingredient_name", orientation="h",
                color="warna", color_discrete_map=color_map,
                labels={"jumlah_menu": "Digunakan di N menu", "ingredient_name": ""}
            )
            fig1.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0),
                               legend_title="Stock Alert",
                               **PLOTLY_DARK,
                               yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig1, use_container_width=True)

    with col_cb:
        st.subheader("Menu dengan bahan terbanyak")
        df_complex = run_query("""
            SELECT item_name, COUNT(*) as jumlah_bahan
            FROM fact_recipe
            GROUP BY item_name
            ORDER BY jumlah_bahan DESC
            LIMIT 15
        """)
        if not df_complex.empty:
            fig2 = px.bar(
                df_complex, x="jumlah_bahan", y="item_name", orientation="h",
                color_discrete_sequence=["#534AB7"],
                labels={"jumlah_bahan": "Jumlah Bahan", "item_name": ""}
            )
            fig2.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0),
                               **PLOTLY_DARK,
                               yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # ── Tampilan per menu ─────────────────────────────────────────
    st.subheader("Detail resep per menu")

    view_mode = st.radio("Mode tampilan", ["Tabel flat", "Per menu (card)"], horizontal=True)

    if view_mode == "Tabel flat":
        if not df.empty:
            df_show = df.copy()
            df_show["alert_icon"] = df_show["stock_alert"].apply(alert_color)
            df_show["qty_fmt"] = df_show["ingredient_qty"].apply(lambda x: fmt_number(x, 2))
            st.dataframe(
                df_show[[
                    "item_name", "variant_name", "ingredient_name",
                    "qty_fmt", "ingredient_unit", "alert_icon", "stock_alert"
                ]].rename(columns={
                    "item_name": "Menu", "variant_name": "Varian",
                    "ingredient_name": "Bahan", "qty_fmt": "Qty",
                    "ingredient_unit": "Satuan", "alert_icon": "",
                    "stock_alert": "Stock Alert"
                }),
                use_container_width=True, hide_index=True, height=600
            )
        else:
            st.info("Tidak ada data resep untuk filter yang dipilih.")

    else:  # Per menu card
        if not df.empty:
            menu_list = df["item_name"].unique().tolist()
            st.write(f"{len(menu_list)} menu ditemukan")

            # Tampilkan 3 kolom cards
            cols_per_row = 3
            for i in range(0, len(menu_list), cols_per_row):
                row_cols = st.columns(cols_per_row)
                for j, menu in enumerate(menu_list[i:i + cols_per_row]):
                    with row_cols[j]:
                        df_menu = df[df["item_name"] == menu].copy()
                        has_out = (df_menu["stock_alert"] == "Out").any()
                        has_low = (df_menu["stock_alert"] == "Low").any()
                        badge = "🔴" if has_out else ("🟡" if has_low else "🟢")

                        with st.container(border=True):
                            st.markdown(f"**{badge} {menu}**")
                            for _, row in df_menu.iterrows():
                                icon = alert_color(row["stock_alert"])
                                qty = fmt_number(row["ingredient_qty"], 2)
                                variant_txt = f" *({row['variant_name']})*" if row["variant_name"] else ""
                                st.caption(
                                    f"{icon} {row['ingredient_name']}{variant_txt}: "
                                    f"{qty} {row['ingredient_unit']}"
                                )
        else:
            st.info("Tidak ada data.")

    st.divider()

    # ── Simulasi kebutuhan bahan ───────────────────────────────────
    st.subheader("Simulasi kebutuhan bahan")
    st.caption("Hitung total bahan yang dibutuhkan jika memproduksi menu tertentu dalam jumlah tertentu")

    df_all_menu = run_query("SELECT DISTINCT item_name FROM fact_recipe ORDER BY item_name")
    if not df_all_menu.empty:
        col_s1, col_s2 = st.columns([3, 1])
        with col_s1:
            selected_menus = st.multiselect("Pilih menu", df_all_menu["item_name"].tolist())
        with col_s2:
            qty_produksi = st.number_input("Jumlah porsi", min_value=1, value=10)

        if selected_menus:
            placeholders = ",".join(["?" for _ in selected_menus])
            df_sim = run_query(f"""
                SELECT ingredient_name, ingredient_unit, SUM(ingredient_qty) as total_per_porsi
                FROM fact_recipe
                WHERE item_name IN ({placeholders})
                GROUP BY ingredient_name, ingredient_unit
                ORDER BY total_per_porsi DESC
            """, selected_menus)

            if not df_sim.empty:
                df_sim["total_kebutuhan"] = df_sim["total_per_porsi"] * qty_produksi
                df_sim["qty_fmt"] = df_sim["total_kebutuhan"].apply(lambda x: fmt_number(x, 2))
                df_sim["per_porsi_fmt"] = df_sim["total_per_porsi"].apply(lambda x: fmt_number(x, 2))
                st.dataframe(
                    df_sim[["ingredient_name", "ingredient_unit", "per_porsi_fmt", "qty_fmt"]].rename(columns={
                        "ingredient_name": "Bahan",
                        "ingredient_unit": "Satuan",
                        "per_porsi_fmt": "Per Porsi",
                        "qty_fmt": f"Total ({qty_produksi} porsi)"
                    }),
                    use_container_width=True, hide_index=True
                )
