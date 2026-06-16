import streamlit as st
import pandas as pd
import datetime
import plotly.graph_objects as go
from utils.database import run_query
from utils.helpers import fmt_rupiah, fmt_number
from utils.pdf_export import generate_dashboard_pdf
from utils.style import (PLOTLY_DARK, CHART_COLORS, dark_xaxis, dark_yaxis,
                          ACCENT, ACCENT2, WARN, DANGER, BG2, BG3, BORDER, TEXT, TEXT_MUTED)


def _invoice_exists() -> bool:
    try:
        run_query("SELECT 1 FROM fact_invoice LIMIT 1")
        return True
    except Exception:
        return False


def show():
    # ── Header ─────────────────────────────────────────────────────
    st.markdown("""
        <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:4px">
            <h1 style="margin:0;font-size:1.8rem;font-weight:700;letter-spacing:-0.03em">Dashboard</h1>
            <span style="font-size:0.8rem;color:#7A7F99;font-weight:500">Stroom · Jakarta Gambir</span>
        </div>
    """, unsafe_allow_html=True)

    # ── Filter tanggal ──────────────────────────────────────────────
    today = datetime.date.today()

    def _to_date(val, fallback):
        try:
            if val is None: return fallback
            if pd.isnull(val): return fallback
            if isinstance(val, datetime.datetime): return val.date()
            if isinstance(val, datetime.date): return val
            if isinstance(val, str): return datetime.date.fromisoformat(val[:10])
            return pd.Timestamp(val).date()
        except Exception:
            return fallback

    df_dates = run_query("SELECT MIN(CAST(sale_date AS VARCHAR)) as mn, MAX(CAST(sale_date AS VARCHAR)) as mx FROM fact_sales_detail")
    raw_mn = df_dates["mn"].iloc[0] if not df_dates.empty else None
    raw_mx = df_dates["mx"].iloc[0] if not df_dates.empty else None
    min_date = _to_date(raw_mn, today.replace(day=1))
    max_date = _to_date(raw_mx, today)
    min_date = datetime.date(min_date.year, min_date.month, min_date.day)
    max_date = datetime.date(max_date.year, max_date.month, max_date.day)

    # Proses tombol shortcut SEBELUM widget date_input di-render
    # agar tidak terjadi konflik session_state setelah widget terbentuk
    col_d1, col_d2, col_d3, col_d4 = st.columns([3, 1, 1, 1])

    with col_d2:
        st.write("")
        if st.button("Bulan ini", use_container_width=True):
            _today = datetime.date.today()
            st.session_state["dashboard_date_range"] = (_today.replace(day=1), _today)
            st.rerun()
    with col_d3:
        st.write("")
        if st.button("Semua data", use_container_width=True):
            st.session_state["dashboard_date_range"] = (min_date, max_date)
            st.rerun()
    with col_d4:
        st.write("")
        if st.button("⬇ Export PDF", use_container_width=True, type="primary"):
            st.session_state["_pdf_ready"] = True

    # Render date_input setelah tombol diproses
    with col_d1:
        date_range = st.date_input(
            "Rentang tanggal", value=(min_date, max_date),
            min_value=min_date, max_value=max_date, key="dashboard_date_range"
        )

    d_start, d_end = (date_range if len(date_range) == 2 else (min_date, max_date))

    # ── Filter BAR / KITCHEN ────────────────────────────────────────
    BAR_CATEGORIES     = ("Beverage Kopi", "Beverage Non Kopi", "Beverage Teh",
                          "Beverage Non Kopi/Teh", "Mocktail", "Stok BAR")
    KITCHEN_CATEGORIES = ("Food", "Snack", "Pasta", "Pastry", "Makanan")

    _st_opts = ["Semua", "BAR", "KITCHEN"]
    _st_col1, _st_col2 = st.columns([1, 5])
    with _st_col1:
        station_filter = st.radio(
            "Filter Stasiun", _st_opts,
            horizontal=True,
            key="dashboard_station",
            label_visibility="collapsed"
        )

    if station_filter == "BAR":
        _cat_in = "'" + "','".join(BAR_CATEGORIES) + "'"
        f_station = f"AND category IN ({_cat_in})"
    elif station_filter == "KITCHEN":
        _cat_in = "'" + "','".join(KITCHEN_CATEGORIES) + "'"
        f_station = f"AND category IN ({_cat_in})"
    else:
        f_station = ""

    # Badge info stasiun aktif
    if station_filter != "Semua":
        _color = "#3B82F6" if station_filter == "BAR" else "#F97316"
        st.markdown(
            f'<div style="margin:-8px 0 8px 0;font-size:0.75rem;color:{_color};font-weight:600">'
            f'Menampilkan data {station_filter} saja</div>',
            unsafe_allow_html=True
        )

    f = f"sale_date BETWEEN ? AND ? {f_station}"
    p = [d_start, d_end]

    # ── KPI ────────────────────────────────────────────────────────
    fi = f"inv_date BETWEEN ? AND ? {f_station}"
    inv_ok = _invoice_exists()
    net_sales    = run_query(f"SELECT COALESCE(SUM(net_sales),0) as v FROM fact_sales_detail WHERE {f}", p)["v"].iloc[0]
    net_invoice  = run_query(f"SELECT COALESCE(SUM(net_sales),0) as v FROM fact_invoice WHERE {fi}", p)["v"].iloc[0] if inv_ok else 0
    gross_sales  = run_query(f"SELECT COALESCE(SUM(gross_sales),0) as v FROM fact_sales_detail WHERE {f}", p)["v"].iloc[0]
    gross_inv    = run_query(f"SELECT COALESCE(SUM(gross_sales),0) as v FROM fact_invoice WHERE {fi}", p)["v"].iloc[0] if inv_ok else 0
    total_disc   = run_query(f"SELECT COALESCE(SUM(discounts),0) as v FROM fact_sales_detail WHERE {f}", p)["v"].iloc[0]
    total_tx     = run_query(f"SELECT COUNT(DISTINCT receipt_number) as v FROM fact_sales_detail WHERE {f}", p)["v"].iloc[0]
    total_inv    = run_query(f"SELECT COUNT(DISTINCT invoice_number) as v FROM fact_invoice WHERE {fi}", p)["v"].iloc[0] if inv_ok else 0
    total_qty    = run_query(f"SELECT COALESCE(SUM(quantity),0) as v FROM fact_sales_detail WHERE {f}", p)["v"].iloc[0]
    qty_inv      = run_query(f"SELECT COALESCE(SUM(quantity),0) as v FROM fact_invoice WHERE {fi}", p)["v"].iloc[0] if inv_ok else 0
    net_combined = net_sales + net_invoice
    avg_tx       = net_sales / total_tx if total_tx > 0 else 0
    total_bahan  = run_query("SELECT COUNT(DISTINCT ingredient_name) as v FROM fact_purchase_order")["v"].iloc[0]
    stok_negatif = run_query("SELECT COUNT(*) as v FROM v_stok_final WHERE stok_final < 0")["v"].iloc[0]

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Net Sales", fmt_rupiah(net_sales))
    with c2: st.metric("Gross Sales", fmt_rupiah(gross_sales + gross_inv))
    with c3: st.metric("Total Diskon", fmt_rupiah(total_disc))
    with c4: st.metric("Transaksi", f"{int(total_tx):,}")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    c5, c6, c7, c8 = st.columns(4)
    with c5: st.metric("Total Invoice", fmt_rupiah(net_invoice),
                        help="Total nilai invoice pada periode ini (terpisah dari Net Sales kasir)")
    with c6: st.metric("Item Terjual", f"{int(total_qty + qty_inv):,}")
    with c7: st.metric("Avg / Transaksi", fmt_rupiah(avg_tx))
    with c8: st.metric("Stok Negatif 🔴 (saat ini)", f"{int(stok_negatif):,}", help="Jumlah bahan dengan stok negatif saat ini. Tidak dipengaruhi filter tanggal karena merupakan saldo akhir inventori.")

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # ── Tren harian + Top menu ──────────────────────────────────────
    col_trend, col_top = st.columns([3, 2])

    with col_trend:
        st.markdown('<p class="dash-card-title">Tren penjualan harian</p>', unsafe_allow_html=True)
        df_trend = run_query(f"""
            SELECT sale_date,
                   SUM(gross_sales) as gross_sales,
                   SUM(net_sales) as net_sales,
                   COUNT(DISTINCT receipt_number) as transaksi
            FROM fact_sales_detail
            WHERE sale_date IS NOT NULL AND {f}
            GROUP BY sale_date ORDER BY sale_date
        """, p)
        if not df_trend.empty:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=df_trend["sale_date"], y=df_trend["transaksi"],
                name="Transaksi", yaxis="y2",
                marker=dict(color="rgba(200,200,255,0.07)", line_width=0)
            ))
            fig.add_trace(go.Scatter(
                x=df_trend["sale_date"], y=df_trend["gross_sales"],
                name="Gross Sales", line=dict(color=ACCENT2, width=1.5, dash="dot")
            ))
            fig.add_trace(go.Scatter(
                x=df_trend["sale_date"], y=df_trend["net_sales"],
                name="Net Sales", line=dict(color=ACCENT, width=2.5),
                fill="tozeroy", fillcolor="rgba(0,200,150,0.07)"
            ))
            fig.update_layout(
                **PLOTLY_DARK,
                height=300,
                xaxis=dark_xaxis(),
                yaxis=dark_yaxis(tickprefix="Rp ", tickformat=",.0f"),
                yaxis2=dict(overlaying="y", side="right", showgrid=False,
                            color=TEXT_MUTED,
                            title=dict(text='Transaksi', font=dict(color=TEXT_MUTED, size=11))),
                legend=dict(orientation="h", y=1.12, x=0,
                            bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT)),
                barmode="overlay", margin=dict(l=0, r=0, t=30, b=0)
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Belum ada data.")

    with col_top:
        st.markdown('<p class="dash-card-title">Top 10 menu terlaris</p>', unsafe_allow_html=True)
        df_top = run_query(f"""
            SELECT item_name, SUM(quantity) as qty, SUM(net_sales) as sales
            FROM fact_sales_detail WHERE {f}
            GROUP BY item_name ORDER BY qty DESC LIMIT 10
        """, p)
        if not df_top.empty:
            fig_top = go.Figure(go.Bar(
                x=df_top["qty"], y=df_top["item_name"],
                orientation="h",
                marker=dict(color=df_top["sales"],
                            colorscale=[[0,"#1A2A3A"],[1, ACCENT]],
                            showscale=False),
                text=df_top["qty"], textposition="inside",
                textfont=dict(color=TEXT, size=11),
                hovertemplate="<b>%{y}</b><br>Qty: %{x}<extra></extra>"
            ))
            fig_top.update_layout(
                **PLOTLY_DARK,
                height=300,
                xaxis=dark_xaxis(showgrid=True, gridcolor="#1E2235"),
                yaxis=dark_yaxis(autorange="reversed", showgrid=False),
                margin=dict(l=0, r=0, t=30, b=0)
            )
            st.plotly_chart(fig_top, use_container_width=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── Per kategori + Per jam ──────────────────────────────────────
    col_cat, col_jam = st.columns(2)

    with col_cat:
        st.markdown('<p class="dash-card-title">Penjualan per kategori</p>', unsafe_allow_html=True)
        df_cat = run_query(f"""
            SELECT category, SUM(net_sales) as total
            FROM fact_sales_detail
            WHERE category NOT IN ('Harga Karyawan','Uncategorized','Online Sales','Stok BAR','Add Ons')
              AND {f}
            GROUP BY category ORDER BY total DESC
        """, p)
        if not df_cat.empty:
            fig2 = go.Figure(go.Bar(
                x=df_cat["total"], y=df_cat["category"], orientation="h",
                marker=dict(color=df_cat["total"],
                            colorscale=[[0,"#112228"],[0.5,"#0A6E56"],[1, ACCENT]],
                            showscale=False),
                hovertemplate="<b>%{y}</b><br>Rp %{x:,.0f}<extra></extra>"
            ))
            fig2.update_layout(
                **PLOTLY_DARK,
                height=310,
                xaxis=dark_xaxis(tickprefix="Rp ", tickformat=",.0f", showgrid=True, gridcolor="#1E2235"),
                yaxis=dark_yaxis(autorange="reversed", showgrid=False),
                margin=dict(l=0, r=0, t=30, b=0)
            )
            st.plotly_chart(fig2, use_container_width=True)

    with col_jam:
        st.markdown('<p class="dash-card-title">Pola penjualan per jam</p>', unsafe_allow_html=True)
        df_jam = run_query(f"""
            SELECT SUBSTR(sale_time, 1, 2) as jam,
                   SUM(net_sales) as net_sales,
                   COUNT(DISTINCT receipt_number) as transaksi
            FROM fact_sales_detail
            WHERE {f} AND sale_time IS NOT NULL AND sale_time != ''
            GROUP BY jam ORDER BY jam
        """, p)
        if not df_jam.empty:
            def fmt_jt_jam(val):
                jt = val / 1_000_000
                if jt == 0: return ""
                if jt == int(jt): return f"{int(jt)}Jt"
                return f"{jt:.1f}Jt"

            label_jam_trx = [str(int(v)) if v > 0 else "" for v in df_jam["transaksi"]]
            label_jam_net = [fmt_jt_jam(v) for v in df_jam["net_sales"]]

            fig_jam = go.Figure()
            fig_jam.add_trace(go.Bar(
                x=df_jam["jam"], y=df_jam["transaksi"],
                name="Transaksi",
                marker=dict(color=ACCENT2, opacity=0.75, cornerradius=4),
                text=label_jam_trx,
                textposition="outside",
                textfont=dict(size=10, color=ACCENT2),
            ))
            fig_jam.add_trace(go.Scatter(
                x=df_jam["jam"], y=df_jam["net_sales"],
                name="Net Sales", yaxis="y2",
                line=dict(color=ACCENT, width=2.5),
                mode="lines+markers+text",
                marker=dict(size=6, color=ACCENT),
                text=label_jam_net,
                textposition="top center",
                textfont=dict(size=9, color=ACCENT),
            ))
            max_trx = df_jam["transaksi"].max()
            fig_jam.update_layout(
                **PLOTLY_DARK,
                height=340,
                xaxis=dark_xaxis(title="Jam"),
                yaxis=dark_yaxis(title="Transaksi", range=[0, max_trx * 1.3]),
                yaxis2=dict(overlaying="y", side="right", showgrid=False,
                            color=TEXT_MUTED, tickprefix="Rp ", tickformat=",.0f"),
                legend=dict(orientation="h", y=1.12, bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT)),
                margin=dict(l=0, r=40, t=30, b=0)
            )
            st.plotly_chart(fig_jam, use_container_width=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── Summary Report Penjualan per Hari ──────────────────────────
    st.markdown('<p class="dash-card-title">Total Penjualan per Hari dalam Seminggu</p>', unsafe_allow_html=True)

    df_daily = run_query(f"""
        SELECT
            sale_date,
            COUNT(DISTINCT receipt_number) as transaksi,
            SUM(gross_sales) as gross_sales,
            SUM(discounts) as diskon,
            SUM(net_sales) as net_sales
        FROM fact_sales_detail
        WHERE {f}
        GROUP BY sale_date
        ORDER BY sale_date ASC
    """, p)

    if not df_daily.empty:
        urutan_hari = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
        hari_map = {0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis", 4: "Jumat", 5: "Sabtu", 6: "Minggu"}

        df_daily["sale_date_dt"] = pd.to_datetime(df_daily["sale_date"])
        df_daily["hari"] = df_daily["sale_date_dt"].dt.dayofweek.map(hari_map)

        # Kelompokkan & total per hari
        df_dow = df_daily.groupby("hari").agg(
            gross_sales=("gross_sales", "sum"),
            diskon=("diskon", "sum"),
            net_sales=("net_sales", "sum"),
            transaksi=("transaksi", "sum"),
        ).reindex(urutan_hari).fillna(0).reset_index()

        def fmt_jt(val):
            """Format angka ke satuan Jt, contoh: 6500000 -> 6.5Jt"""
            jt = val / 1_000_000
            if jt == int(jt):
                return f"{int(jt)}Jt"
            return f"{jt:.1f}Jt"

        label_gross = [fmt_jt(v) for v in df_dow["gross_sales"]]
        label_net   = [fmt_jt(v) for v in df_dow["net_sales"]]
        label_trx   = [f"{int(v):,}" for v in df_dow["transaksi"]]

        # Warna gradient per hari untuk Net Sales
        net_colors = [
            "#00C896", "#00B887", "#00A878", "#009869",
            "#00885A", "#00784B", "#00683C"
        ]
        gross_colors = [
            "#3B82F6", "#3373DC", "#2B64C2", "#2355A8",
            "#1B468E", "#133774", "#0B285A"
        ]

        fig_dow = go.Figure()

        # Bar Gross Sales
        fig_dow.add_trace(go.Bar(
            name="Gross Sales",
            x=df_dow["hari"],
            y=df_dow["gross_sales"],
            marker=dict(
                color=gross_colors,
                line=dict(color="rgba(255,255,255,0.08)", width=1),
                cornerradius=6,
            ),
            text=label_gross,
            textposition="outside",
            textfont=dict(size=11, color="#90B4FF", family="monospace"),
            hovertemplate="<b>%{x}</b><br>Gross Sales: Rp %{y:,.0f}<extra></extra>",
            width=0.35,
            offset=-0.19,
        ))

        # Bar Net Sales
        fig_dow.add_trace(go.Bar(
            name="Net Sales",
            x=df_dow["hari"],
            y=df_dow["net_sales"],
            marker=dict(
                color=net_colors,
                line=dict(color="rgba(255,255,255,0.08)", width=1),
                cornerradius=6,
            ),
            text=label_net,
            textposition="outside",
            textfont=dict(size=11, color=ACCENT, family="monospace"),
            hovertemplate="<b>%{x}</b><br>Net Sales: Rp %{y:,.0f}<extra></extra>",
            width=0.35,
            offset=0.19,
        ))

        # Line Avg Transaksi
        fig_dow.add_trace(go.Scatter(
            name="Total Transaksi",
            x=df_dow["hari"],
            y=df_dow["transaksi"],
            yaxis="y2",
            mode="lines+markers+text",
            line=dict(color=WARN, width=2.5, dash="dot"),
            marker=dict(size=9, color=WARN, line=dict(color="#1A1A2E", width=2)),
            text=label_trx,
            textposition="top center",
            textfont=dict(size=10, color=WARN),
            hovertemplate="<b>%{x}</b><br>Total Transaksi: %{y:,}<extra></extra>",
        ))

        max_y = max(df_dow["gross_sales"].max(), df_dow["net_sales"].max())

        fig_dow.update_layout(
            **PLOTLY_DARK,
            height=400,
            barmode="overlay",
            xaxis=dark_xaxis(
                categoryorder="array",
                categoryarray=urutan_hari,
                tickfont=dict(size=13, color=TEXT),
            ),
            yaxis=dark_yaxis(
                tickprefix="Rp ",
                tickformat=",.0f",
                range=[0, max_y * 1.25],
                showgrid=True,
                gridcolor="rgba(255,255,255,0.04)",
            ),
            yaxis2=dict(
                overlaying="y", side="right", showgrid=False,
                color=WARN,
                tickfont=dict(color=WARN, size=10),
                title=dict(text="Total Transaksi", font=dict(color=WARN, size=11)),
            ),
            legend=dict(
                orientation="h", y=1.13, x=0,
                bgcolor="rgba(0,0,0,0)",
                font=dict(color=TEXT, size=12),
            ),
            margin=dict(l=0, r=40, t=40, b=0),
        )
        st.plotly_chart(fig_dow, use_container_width=True)
    else:
        st.info("Belum ada data penjualan harian.")

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # ── Sales type + PO + Alert ─────────────────────────────────────
    col_pie, col_po, col_alert = st.columns([2, 2, 3])

    with col_pie:
        st.markdown('<p class="dash-card-title">Tipe & Metode Bayar</p>', unsafe_allow_html=True)
        df_type = run_query(f"SELECT sales_type, SUM(net_sales) as total FROM fact_sales_detail WHERE {f} GROUP BY sales_type ORDER BY total DESC", p)
        df_pay  = run_query(f"SELECT payment_method, SUM(net_sales) as total FROM fact_sales_detail WHERE {f} GROUP BY payment_method ORDER BY total DESC", p)

        if not df_type.empty:
            fig_pie = go.Figure(go.Pie(
                labels=df_type["sales_type"], values=df_type["total"],
                hole=0.55,
                marker=dict(colors=CHART_COLORS, line=dict(color=BG2, width=2)),
                textfont=dict(size=10, color=TEXT),
                textposition="inside", textinfo="percent"
            ))
            fig_pie.update_layout(
                **PLOTLY_DARK,
                height=150, margin=dict(l=0, r=0, t=0, b=0), showlegend=False
            )
            st.plotly_chart(fig_pie, use_container_width=True)
            total_type = df_type["total"].sum()
            for _, row in df_type.head(4).iterrows():
                pct = row["total"] / total_type * 100
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;font-size:0.75rem;'
                    f'color:{TEXT_MUTED};margin:1px 0">'
                    f'<span>{row["sales_type"]}</span>'
                    f'<span style="color:{TEXT}">{pct:.1f}%</span></div>',
                    unsafe_allow_html=True
                )

        if not df_pay.empty:
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            fig_pay = go.Figure(go.Pie(
                labels=df_pay["payment_method"], values=df_pay["total"],
                hole=0.55,
                marker=dict(colors=CHART_COLORS[::-1], line=dict(color=BG2, width=2)),
                textfont=dict(size=10, color=TEXT),
                textposition="inside", textinfo="percent"
            ))
            fig_pay.update_layout(
                **PLOTLY_DARK,
                height=150, margin=dict(l=0, r=0, t=0, b=0), showlegend=False
            )
            st.plotly_chart(fig_pay, use_container_width=True)

    with col_po:
        st.markdown('<p class="dash-card-title">Ringkasan Purchase Order</p>', unsafe_allow_html=True)
        # Hanya Completed, dibagi BAR dan KITCHEN
        df_po_sum = run_query("""
            SELECT 
                COALESCE(category, 'Lainnya') as category,
                COUNT(DISTINCT order_no) as jml_po,
                SUM(total_cost) as nilai
            FROM fact_purchase_order
            WHERE po_date BETWEEN ? AND ?
              AND status = 'Completed'
            GROUP BY category
            ORDER BY category
        """, [d_start, d_end])

        if not df_po_sum.empty:
            total_po_val = df_po_sum["nilai"].sum()
            total_po_jml = df_po_sum["jml_po"].sum()
            st.markdown(
                f'<div style="font-size:1.5rem;font-weight:700;color:{ACCENT};letter-spacing:-0.02em">'
                f'{fmt_rupiah(total_po_val)}</div>'
                f'<div style="font-size:0.72rem;color:{TEXT_MUTED};margin-bottom:6px">'
                f'Total nilai PO Completed ({int(total_po_jml)} PO)</div>',
                unsafe_allow_html=True
            )
            # Warna per kategori
            cat_colors = {"BAR": "#3B82F6", "KITCHEN": "#F97316", "Lainnya": ACCENT}
            cat_icons  = {"BAR": "🍹", "KITCHEN": "🍳", "Lainnya": "📦"}
            for _, row in df_po_sum.iterrows():
                cat   = row["category"]
                color = cat_colors.get(cat, ACCENT)
                icon  = cat_icons.get(cat, "📦")
                pct   = (row["nilai"] / total_po_val * 100) if total_po_val > 0 else 0
                st.markdown(
                    f'<div style="padding:8px 0;border-bottom:1px solid {BORDER}">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;font-size:0.82rem;margin-bottom:4px">'
                    f'<span style="color:{color};font-weight:700">{icon} {cat}</span>'
                    f'<span style="color:{TEXT_MUTED};font-size:0.75rem">{int(row["jml_po"])} PO</span>'
                    f'<span style="color:{TEXT};font-weight:600">{fmt_rupiah(row["nilai"])}</span></div>'
                    f'<div style="height:4px;background:{BG3};border-radius:2px">'
                    f'<div style="width:{pct:.1f}%;height:4px;background:{color};border-radius:2px"></div>'
                    f'</div></div>',
                    unsafe_allow_html=True
                )

    with col_alert:
        st.markdown('<p class="dash-card-title">Alert stok bahan</p>', unsafe_allow_html=True)
        df_alert = run_query("""
            SELECT ingredient_name, stok_final, unit, stok_source
            FROM v_stok_final WHERE stok_final < 1000
            ORDER BY stok_final ASC LIMIT 12
        """)
        if not df_alert.empty:
            for _, row in df_alert.iterrows():
                v = row["stok_final"]
                if v < 0:
                    badge, bar_color = "badge-danger", DANGER
                elif v < 300:
                    badge, bar_color = "badge-warn", WARN
                else:
                    badge, bar_color = "badge-success", ACCENT
                pct = max(0, min(100, (v / 1000) * 100))
                src = "✏️" if row["stok_source"] == "adjusted" else "📦"
                st.markdown(f"""
                    <div style="padding:5px 0;border-bottom:1px solid {BORDER}">
                      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px">
                        <span style="font-size:0.8rem;color:{TEXT};font-weight:500">{src} {row['ingredient_name']}</span>
                        <span class="{badge}" style="font-size:0.7rem">{fmt_number(v,1)} {row['unit']}</span>
                      </div>
                      <div style="height:3px;background:{BG3};border-radius:2px">
                        <div style="width:{pct}%;height:3px;background:{bar_color};border-radius:2px"></div>
                      </div>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.success("Semua stok aman.")

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # ── Import log ──────────────────────────────────────────────────
    st.markdown('<p class="dash-card-title">Riwayat import terakhir</p>', unsafe_allow_html=True)
    df_log = run_query("""
        SELECT file_type, file_name,
               strftime(imported_at, '%d/%m/%Y %H:%M') as waktu,
               rows_inserted, rows_updated, status
        FROM import_log ORDER BY imported_at DESC LIMIT 8
    """)
    if not df_log.empty:
        st.dataframe(
            df_log.rename(columns={
                "file_type":"Tipe","file_name":"File","waktu":"Waktu",
                "rows_inserted":"Inserted","rows_updated":"Updated","status":"Status"
            }),
            use_container_width=True, hide_index=True, height=220
        )
    else:
        st.info("Belum ada riwayat import.")

    # ── Export PDF ────────────────────────────────────────────────
    if st.session_state.get("_pdf_ready"):
        with st.spinner("Membuat PDF..."):
            df_top_pdf = run_query(f"""
                SELECT item_name, SUM(quantity) as qty, SUM(net_sales) as sales
                FROM fact_sales_detail WHERE {f}
                GROUP BY item_name ORDER BY qty DESC LIMIT 15
            """, p)
            df_top_pdf["sales"] = df_top_pdf["sales"].apply(fmt_rupiah)

            df_cat_pdf = run_query(f"""
                SELECT category, SUM(net_sales) as total
                FROM fact_sales_detail
                WHERE category NOT IN ('Harga Karyawan','Uncategorized','Online Sales','Stok BAR','Add Ons')
                  AND {f}
                GROUP BY category ORDER BY total DESC
            """, p)
            df_cat_pdf["total"] = df_cat_pdf["total"].apply(fmt_rupiah)

            # FIX: filter po_date di PDF juga
            df_po_pdf = run_query("""
                SELECT status, COUNT(DISTINCT order_no) as jml_po, SUM(total_cost) as nilai
                FROM fact_purchase_order
                WHERE po_date BETWEEN ? AND ?
                GROUP BY status
            """, [d_start, d_end])
            df_po_pdf["nilai"] = df_po_pdf["nilai"].apply(fmt_rupiah)

            df_alert_pdf = run_query("""
                SELECT ingredient_name, stok_final, unit, stok_source
                FROM v_stok_final WHERE stok_final < 1000 ORDER BY stok_final ASC
            """)

            date_str = f"{d_start.strftime('%d/%m/%Y')} - {d_end.strftime('%d/%m/%Y')}"
            pdf_bytes = generate_dashboard_pdf({
                "date_range":   date_str,
                "net_sales":    fmt_rupiah(net_sales),
                "gross_sales":  fmt_rupiah(gross_sales),
                "total_disc":   fmt_rupiah(total_disc),
                "total_tx":     f"{int(total_tx):,}",
                "total_qty":    f"{int(total_qty):,}",
                "avg_tx":       fmt_rupiah(avg_tx),
                "total_bahan":  f"{int(total_bahan):,}",
                "stok_negatif": f"{int(stok_negatif):,}",
                "top_menu":     df_top_pdf,
                "sales_by_cat": df_cat_pdf,
                "po_summary":   df_po_pdf,
                "stock_alerts": df_alert_pdf,
            })

        fname = f"Stroom_Dashboard_{d_start.strftime('%d%m%Y')}_{d_end.strftime('%d%m%Y')}.pdf"
        st.download_button(
            label="📄 Download PDF Laporan",
            data=pdf_bytes,
            file_name=fname,
            mime="application/pdf",
            type="primary",
            use_container_width=False
        )
        st.session_state["_pdf_ready"] = False