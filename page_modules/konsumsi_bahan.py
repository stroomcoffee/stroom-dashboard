import streamlit as st
import pandas as pd
import datetime
import plotly.graph_objects as go
from utils.database import run_query
from utils.helpers import fmt_number
from utils.style import PLOTLY_DARK, dark_xaxis, dark_yaxis, ACCENT, ACCENT2, TEXT, TEXT_MUTED


def _get_consumption(d_start, d_end, selected_menus=None, selected_variants=None):
    """
    Hitung estimasi konsumsi bahan dari retail + invoice × resep.
    selected_variants: list variant yang dipilih, None = semua.
    Hasil: satu baris per item_name + ingredient (semua variant sudah diagregasi).
    """
    menu_filter    = ""
    variant_filter = ""
    params = [d_start, d_end, d_start, d_end]

    if selected_menus:
        ph = ",".join(["?" for _ in selected_menus])
        menu_filter = f"AND s.item_name IN ({ph})"
        params += list(selected_menus)

    if selected_variants is not None:
        # None = semua, list kosong tidak akan terjadi (sudah dihandle caller)
        # Konversi "(Tanpa Variant)" kembali ke '' untuk match DB
        db_variants = [("" if v == "(Tanpa Variant)" else v) for v in selected_variants]
        ph = ",".join(["?" for _ in db_variants])
        variant_filter = f"AND s.variant IN ({ph})"
        params += db_variants

    df = run_query(f"""
        WITH sales_combined AS (
            SELECT item_name,
                   CASE WHEN variant IN ('__no_variant__','') THEN '' ELSE variant END as variant,
                   SUM(quantity) as total_qty
            FROM fact_sales_detail WHERE sale_date BETWEEN ? AND ?
            GROUP BY item_name,
                     CASE WHEN variant IN ('__no_variant__','') THEN '' ELSE variant END
            UNION ALL
            SELECT item_name,
                   CASE WHEN variant IN ('__no_variant__','') THEN '' ELSE variant END as variant,
                   SUM(quantity) as total_qty
            FROM fact_invoice WHERE inv_date BETWEEN ? AND ?
            GROUP BY item_name,
                     CASE WHEN variant IN ('__no_variant__','') THEN '' ELSE variant END
        ),
        sales_agg AS (
            SELECT item_name, variant, SUM(total_qty) as total_qty
            FROM sales_combined
            GROUP BY item_name, variant
        ),
        recipe_priority AS (
            SELECT item_name, variant_name, ingredient_name, ingredient_qty, ingredient_unit,
                   CASE WHEN variant_name = '' THEN 0 ELSE 1 END as priority
            FROM fact_recipe
        ),
        best_recipe AS (
            SELECT DISTINCT ON (s.item_name, s.variant, r.ingredient_name)
                   s.item_name, s.variant, s.total_qty,
                   r.ingredient_name, r.ingredient_qty, r.ingredient_unit
            FROM sales_agg s
            INNER JOIN recipe_priority r
                ON s.item_name = r.item_name
               AND (r.variant_name = s.variant OR r.variant_name = '')
            WHERE s.total_qty > 0
            {menu_filter}
            {variant_filter}
            ORDER BY s.item_name, s.variant, r.ingredient_name, r.priority DESC
        )
        SELECT
            item_name,
            ingredient_name,
            ingredient_unit,
            SUM(total_qty)                  AS total_porsi_terjual,
            MAX(ingredient_qty)             AS qty_per_porsi,
            SUM(total_qty * ingredient_qty) AS total_konsumsi
        FROM best_recipe
        GROUP BY item_name, ingredient_name, ingredient_unit
        ORDER BY item_name, total_konsumsi DESC
    """, params)

    return df


def _summary_by_ingredient(df):
    if df.empty:
        return df
    return (
        df.groupby(["ingredient_name", "ingredient_unit"])
        .agg(total_konsumsi=("total_konsumsi", "sum"))
        .reset_index()
        .sort_values("total_konsumsi", ascending=False)
    )


def show():
    st.title("Konsumsi Bahan")
    st.caption("Estimasi pemakaian bahan berdasarkan transaksi retail + invoice × resep")

    # ── Ambil data filter awal ────────────────────────────────────
    today = datetime.date.today()
    df_dates = run_query(
        "SELECT MIN(CAST(sale_date AS VARCHAR)) as mn, MAX(CAST(sale_date AS VARCHAR)) as mx FROM fact_sales_detail"
    )
    raw_mn = df_dates["mn"].iloc[0] if not df_dates.empty else None
    raw_mx = df_dates["mx"].iloc[0] if not df_dates.empty else None
    min_date = datetime.date(*[int(x) for x in (raw_mn or str(today))[:10].split("-")])
    max_date = datetime.date(*[int(x) for x in (raw_mx or str(today))[:10].split("-")])

    # Ambil semua variant dari DB
    df_variants = run_query("""
        SELECT DISTINCT
            CASE WHEN variant IN ('__no_variant__','') THEN '(Tanpa Variant)' ELSE variant END as variant
        FROM fact_sales_detail
        WHERE variant IS NOT NULL
        ORDER BY variant
    """)
    all_variants = df_variants["variant"].tolist()

    all_menus = run_query("SELECT DISTINCT item_name FROM fact_recipe ORDER BY item_name")

    # ── Filter row 1: tanggal + variant ──────────────────────────
    col_f1, col_f2 = st.columns([2, 2])
    with col_f1:
        date_range = st.date_input(
            "Rentang tanggal", value=(min_date, max_date),
            min_value=min_date, max_value=max_date
        )
    with col_f2:
        # Tambah opsi "Semua Variant" di paling atas
        variant_options = ["Semua Variant"] + all_variants
        selected_variant_opts = st.multiselect(
            "Filter variant",
            options=variant_options,
            default=["Semua Variant"],
            help="Pilih 'Semua Variant' untuk menggabungkan semua variant, atau pilih spesifik (Ice, Hot, dll)"
        )

    # ── Filter row 2: menu + tampilan ────────────────────────────
    col_f3, col_f4 = st.columns([3, 1])
    with col_f3:
        selected_menus = st.multiselect(
            "Filter menu (kosong = semua menu)",
            options=all_menus["item_name"].tolist(),
            placeholder="Pilih menu tertentu..."
        )
    with col_f4:
        st.write("")
        group_by = st.radio("Tampilan", ["Per bahan", "Per menu"], horizontal=True)

    # ── Resolve filter variant ────────────────────────────────────
    if not selected_variant_opts or "Semua Variant" in selected_variant_opts:
        # Semua variant → tidak filter
        active_variants = None
        variant_label = "Semua Variant"
    else:
        active_variants = selected_variant_opts
        variant_label = " + ".join(active_variants)

    d_start = date_range[0] if len(date_range) == 2 else min_date
    d_end   = date_range[1] if len(date_range) == 2 else max_date

    # ── Hitung konsumsi ───────────────────────────────────────────
    with st.spinner("Menghitung estimasi konsumsi bahan..."):
        df_raw     = _get_consumption(d_start, d_end,
                                      selected_menus=selected_menus or None,
                                      selected_variants=active_variants)
        df_summary = _summary_by_ingredient(df_raw)

    if df_raw.empty:
        st.warning("Tidak ada data. Pastikan data transaksi dan resep sudah diimport, atau ubah filter.")
        return

    # ── KPI ───────────────────────────────────────────────────────
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # Hitung qty sesuai filter variant
    if active_variants is None:
        retail_qty  = int(run_query("SELECT COALESCE(SUM(quantity),0) as v FROM fact_sales_detail WHERE sale_date BETWEEN ? AND ?", [d_start, d_end])["v"].iloc[0])
        invoice_qty = int(run_query("SELECT COALESCE(SUM(quantity),0) as v FROM fact_invoice WHERE inv_date BETWEEN ? AND ?", [d_start, d_end])["v"].iloc[0])
    else:
        db_vars = [("" if v == "(Tanpa Variant)" else v) for v in active_variants]
        ph = ",".join(["?" for _ in db_vars])
        retail_qty  = int(run_query(f"SELECT COALESCE(SUM(quantity),0) as v FROM fact_sales_detail WHERE sale_date BETWEEN ? AND ? AND CASE WHEN variant IN ('__no_variant__','') THEN '' ELSE variant END IN ({ph})", [d_start, d_end] + db_vars)["v"].iloc[0])
        invoice_qty = int(run_query(f"SELECT COALESCE(SUM(quantity),0) as v FROM fact_invoice WHERE inv_date BETWEEN ? AND ? AND CASE WHEN variant IN ('__no_variant__','') THEN '' ELSE variant END IN ({ph})", [d_start, d_end] + db_vars)["v"].iloc[0])

    total_qty = retail_qty + invoice_qty
    pct_inv   = (invoice_qty / total_qty * 100) if total_qty > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Menu terhitung", df_raw["item_name"].nunique())
    with c2: st.metric("Jenis bahan terpakai", df_summary["ingredient_name"].nunique())
    with c3: st.metric("Total porsi terjual", f"{total_qty:,}",
                       delta=f"+{invoice_qty:,} invoice" if invoice_qty > 0 else None)
    with c4: st.metric("Variant ditampilkan", variant_label)

    st.info(
        f"**{retail_qty:,} retail** + **{invoice_qty:,} invoice** · "
        f"{d_start.strftime('%d/%m/%Y')} – {d_end.strftime('%d/%m/%Y')} · "
        f"Variant: **{variant_label}**",
        icon="ℹ️"
    )

    st.divider()

    # ════════════════════════════════════════════════════════════
    # MODE: PER BAHAN
    # ════════════════════════════════════════════════════════════
    if group_by == "Per bahan":

        st.subheader("Top 20 bahan paling banyak dikonsumsi")

        df_chart = df_summary.head(20).copy()
        df_chart["label"] = df_chart["ingredient_name"] + " (" + df_chart["ingredient_unit"] + ")"

        fig = go.Figure(go.Bar(
            x=df_chart["total_konsumsi"],
            y=df_chart["label"],
            orientation="h",
            marker=dict(
                color=df_chart["total_konsumsi"],
                colorscale=[[0, "#112228"], [0.5, "#0A6E56"], [1, ACCENT]],
                showscale=False
            ),
            text=df_chart["total_konsumsi"].apply(lambda x: fmt_number(x, 0)),
            textposition="inside",
            textfont=dict(color=TEXT, size=11),
            hovertemplate="<b>%{y}</b><br>Konsumsi: %{x:,.1f}<extra></extra>"
        ))
        fig.update_layout(
            **PLOTLY_DARK, height=520,
            xaxis=dark_xaxis(showgrid=True, gridcolor="#1E2235"),
            yaxis=dark_yaxis(autorange="reversed", showgrid=False),
            margin=dict(l=0, r=0, t=10, b=0)
        )
        st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # Tabel + search
        st.subheader("Detail semua bahan")
        col_s1, col_s2 = st.columns([3, 1])
        with col_s1:
            search_ing = st.text_input("Cari bahan", placeholder="Ketik nama bahan...")
        with col_s2:
            sort_by = st.selectbox("Urutkan", ["Konsumsi terbesar ↓", "Nama A-Z"])

        df_tbl = df_summary.copy()
        if search_ing:
            df_tbl = df_tbl[df_tbl["ingredient_name"].str.lower().str.contains(search_ing.lower())]
        if sort_by == "Nama A-Z":
            df_tbl = df_tbl.sort_values("ingredient_name")

        df_tbl["Est. Konsumsi"] = df_tbl["total_konsumsi"].apply(lambda x: fmt_number(x, 2))
        st.dataframe(
            df_tbl[["ingredient_name","ingredient_unit","Est. Konsumsi"]].rename(columns={
                "ingredient_name": "Bahan", "ingredient_unit": "Satuan"
            }),
            use_container_width=True, hide_index=True, height=450
        )

        # Stok vs konsumsi
        st.divider()
        st.subheader("Stok tersedia vs estimasi konsumsi")
        st.caption("🔴 Defisit  |  🟡 Menipis (sisa < 30% konsumsi)  |  🟢 Aman")

        df_stok = run_query("SELECT ingredient_name, stok_final FROM v_stok_final")
        df_cmp  = df_summary.merge(df_stok, on="ingredient_name", how="left")
        df_cmp["stok_final"]    = df_cmp["stok_final"].fillna(0)
        df_cmp["sisa_estimasi"] = df_cmp["stok_final"] - df_cmp["total_konsumsi"]
        thr = df_cmp["total_konsumsi"].median() * 0.3
        df_cmp["Status"] = df_cmp["sisa_estimasi"].apply(
            lambda x: "🔴 Defisit" if x < 0 else ("🟡 Menipis" if x < thr else "🟢 Aman")
        )
        if search_ing:
            df_cmp = df_cmp[df_cmp["ingredient_name"].str.lower().str.contains(search_ing.lower())]

        st.dataframe(
            df_cmp.assign(
                Stok=df_cmp["stok_final"].apply(lambda x: fmt_number(x, 1)),
                Konsumsi=df_cmp["total_konsumsi"].apply(lambda x: fmt_number(x, 1)),
                Sisa=df_cmp["sisa_estimasi"].apply(lambda x: fmt_number(x, 1)),
            )[["Status","ingredient_name","ingredient_unit","Stok","Konsumsi","Sisa"]].rename(columns={
                "ingredient_name": "Bahan", "ingredient_unit": "Satuan",
                "Stok": "Stok Tersedia", "Konsumsi": "Est. Konsumsi", "Sisa": "Est. Sisa"
            }),
            use_container_width=True, hide_index=True, height=450
        )
        n_def = int((df_cmp["sisa_estimasi"] < 0).sum())
        if n_def > 0:
            st.error(f"⚠️ {n_def} bahan estimasi konsumsinya melebihi stok tersedia.")

    # ════════════════════════════════════════════════════════════
    # MODE: PER MENU
    # ════════════════════════════════════════════════════════════
    else:
        st.subheader("Konsumsi bahan per menu")
        st.caption("Pilih satu menu untuk melihat detail bahan yang digunakan")

        menus_available = sorted(df_raw["item_name"].unique().tolist())
        selected_menu   = st.selectbox("Pilih menu", menus_available)

        df_menu = df_raw[df_raw["item_name"] == selected_menu].sort_values("total_konsumsi", ascending=False)

        if not df_menu.empty:
            total_porsi = int(df_menu["total_porsi_terjual"].iloc[0])

            km1, km2, km3 = st.columns(3)
            km1.metric("Menu", selected_menu)
            km2.metric("Total porsi terjual", f"{total_porsi:,}")
            km3.metric("Jumlah bahan di resep", len(df_menu))

            # Chart bahan untuk menu ini
            df_c = df_menu.sort_values("total_konsumsi", ascending=True).copy()
            df_c["label"] = df_c["ingredient_name"] + " (" + df_c["ingredient_unit"] + ")"

            fig2 = go.Figure(go.Bar(
                y=df_c["label"],
                x=df_c["total_konsumsi"],
                orientation="h",
                marker=dict(
                    color=df_c["total_konsumsi"],
                    colorscale=[[0, "#0A3D2B"], [1, ACCENT]],
                    showscale=False
                ),
                text=df_c["total_konsumsi"].apply(lambda x: fmt_number(x, 1)),
                textposition="outside",
                textfont=dict(color=TEXT, size=11),
                customdata=df_c["qty_per_porsi"],
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "Total konsumsi: %{x:,.1f}<br>"
                    "Per porsi: %{customdata:.2f}<br>"
                    f"Variant filter: {variant_label}"
                    "<extra></extra>"
                )
            ))
            fig2.update_layout(
                **PLOTLY_DARK, height=max(300, len(df_menu) * 55),
                xaxis=dark_xaxis(showgrid=True, gridcolor="#1E2235"),
                yaxis=dark_yaxis(showgrid=False),
                margin=dict(l=0, r=110, t=20, b=0)
            )
            st.plotly_chart(fig2, use_container_width=True)

            # Tabel detail
            df_show = df_menu.copy()
            df_show["Qty/Porsi"]     = df_show["qty_per_porsi"].apply(lambda x: fmt_number(x, 2))
            df_show["Total Porsi"]   = df_show["total_porsi_terjual"].apply(lambda x: f"{int(x):,}")
            df_show["Est. Konsumsi"] = df_show["total_konsumsi"].apply(lambda x: fmt_number(x, 2))
            st.dataframe(
                df_show[["ingredient_name","ingredient_unit","Qty/Porsi","Total Porsi","Est. Konsumsi"]].rename(columns={
                    "ingredient_name": "Bahan", "ingredient_unit": "Satuan"
                }),
                use_container_width=True, hide_index=True
            )

        st.divider()

        # Ringkasan semua menu
        st.subheader("Perbandingan porsi terjual semua menu")
        df_ms = (
            df_raw.groupby("item_name")["total_porsi_terjual"]
            .max().reset_index()
            .sort_values("total_porsi_terjual", ascending=False)
        )
        fig3 = go.Figure(go.Bar(
            x=df_ms["total_porsi_terjual"], y=df_ms["item_name"],
            orientation="h",
            marker=dict(color=df_ms["total_porsi_terjual"],
                        colorscale=[[0,"#111A2A"],[1, ACCENT2]], showscale=False),
            text=df_ms["total_porsi_terjual"].apply(lambda x: f"{int(x):,}"),
            textposition="inside", textfont=dict(color=TEXT, size=10),
            hovertemplate="<b>%{y}</b><br>Porsi: %{x:,}<extra></extra>"
        ))
        fig3.update_layout(
            **PLOTLY_DARK, height=max(400, len(df_ms) * 26),
            xaxis=dark_xaxis(title="Porsi Terjual", showgrid=True, gridcolor="#1E2235"),
            yaxis=dark_yaxis(autorange="reversed", showgrid=False),
            margin=dict(l=0, r=0, t=10, b=0)
        )
        st.plotly_chart(fig3, use_container_width=True)

    st.divider()

    # Download
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button(
            "📥 Download detail per menu × bahan",
            data=df_raw.to_csv(index=False).encode("utf-8"),
            file_name=f"konsumsi_detail_{d_start}_{d_end}.csv",
            mime="text/csv", use_container_width=True
        )
    with col_dl2:
        st.download_button(
            "📥 Download ringkasan per bahan",
            data=df_summary.to_csv(index=False).encode("utf-8"),
            file_name=f"konsumsi_summary_{d_start}_{d_end}.csv",
            mime="text/csv", use_container_width=True
        )