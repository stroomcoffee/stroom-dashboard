import streamlit as st
from utils.gdrive_loader import ensure_db
ensure_db()

st.set_page_config(
    page_title="Stroom Inventory",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="expanded"
)

from utils.database import (
    init_database, ensure_adjustment_table, ensure_semi_finished_table,
    create_stock_view, run_query
)
from utils.style import inject_css

inject_css()
init_database()
ensure_adjustment_table()
ensure_semi_finished_table()
create_stock_view()

if "active_page" not in st.session_state:
    st.session_state["active_page"] = "Dashboard"


# ── Helper ────────────────────────────────────────────────────────
def _table_exists(table_name: str) -> bool:
    try:
        run_query(f"SELECT 1 FROM {table_name} LIMIT 1")
        return True
    except Exception:
        return False


# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.title("🥗 Stroom")
    st.caption("Jakarta Gambir · Inventory")
    st.divider()

    pages = [
        "📊 Dashboard",
        "📥 Import Data CSV",
        "📦 Inventori Bahan",
        "🛒 Purchase Order",
        "💰 Transaksi Penjualan",
        "🧾 Konsumsi Bahan",
        "🍳 Resep & BOM",
        "🧪 Resep Turunan",
        "📈 Analitik Lanjutan",
    ]

    for p in pages:
        name = p.split(" ", 1)[1]
        active = st.session_state["active_page"] == name
        if st.button(p, key=f"btn_{name}", use_container_width=True,
                     type="primary" if active else "secondary"):
            st.session_state["active_page"] = name
            st.rerun()

    st.divider()

    try:
        tx  = int(run_query("SELECT COUNT(*) as v FROM fact_sales_detail")["v"].iloc[0])
        po  = int(run_query("SELECT COUNT(DISTINCT order_no) as v FROM fact_purchase_order")["v"].iloc[0])
        rec = int(run_query("SELECT COUNT(DISTINCT item_name) as v FROM fact_recipe")["v"].iloc[0])
        neg = int(run_query("SELECT COUNT(*) as v FROM v_stok_final WHERE stok_final < 0")["v"].iloc[0])
        inv = int(run_query("SELECT COUNT(DISTINCT invoice_number) as v FROM fact_invoice")["v"].iloc[0]) if _table_exists("fact_invoice") else 0
        st.caption(f"🧾 Transaksi: **{tx:,}**")
        st.caption(f"📋 Invoice: **{inv:,}**")
        st.caption(f"📦 PO: **{po:,}**")
        st.caption(f"🍽️ Resep: **{rec:,}** menu")
        st.caption(f"⚠️ Stok negatif: **{neg}**")
    except Exception:
        pass

    st.divider()
    st.caption("v1.3.0 · DuckDB + Streamlit")


# ── Router ────────────────────────────────────────────────────────
page = st.session_state["active_page"]

if page == "Dashboard":
    from page_modules import dashboard; dashboard.show()
elif page == "Import Data CSV":
    from page_modules import import_data; import_data.show()
elif page == "Inventori Bahan":
    from page_modules import inventori; inventori.show()
elif page == "Purchase Order":
    from page_modules import purchase_order; purchase_order.show()
elif page == "Transaksi Penjualan":
    from page_modules import transaksi; transaksi.show()
elif page == "Konsumsi Bahan":
    from page_modules import konsumsi_bahan; konsumsi_bahan.show()
elif page == "Resep & BOM":
    from page_modules import resep; resep.show()
elif page == "Resep Turunan":
    from page_modules import semi_finished; semi_finished.show()
elif page == "Analitik Lanjutan":
    from page_modules import analitik; analitik.show()