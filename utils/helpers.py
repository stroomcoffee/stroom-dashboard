import locale
import pandas as pd


def fmt_rupiah(value: float) -> str:
    try:
        return f"Rp {value:,.0f}".replace(",", ".")
    except Exception:
        return "Rp 0"


def fmt_number(value: float, decimals: int = 0) -> str:
    try:
        return f"{value:,.{decimals}f}".replace(",", ".")
    except Exception:
        return "0"


def pct_change(current: float, previous: float) -> str:
    if previous == 0:
        return "+0%"
    pct = ((current - previous) / previous) * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


def status_badge(status: str) -> str:
    mapping = {
        "Completed": "🟢",
        "Waiting on Approval": "🟡",
        "Cancelled": "🔴",
    }
    return mapping.get(status, "⚪")


def alert_color(alert: str) -> str:
    if alert == "Out":
        return "🔴"
    if alert == "Low":
        return "🟡"
    return "🟢"


def safe_div(a, b, default=0):
    return a / b if b != 0 else default


MOKA_FILE_HINTS = {
    "po_ingredients": {
        "label": "PO Ingredients",
        "desc": "Export dari menu Inventory → Purchase Order",
        "cols_required": ["Order No.", "Ingredient Name", "In Stock"],
        "color": "#1D9E75",
    },
    "item_details": {
        "label": "Item Details (Transaksi)",
        "desc": "Export dari menu Report → Item Details",
        "cols_required": ["Receipt Number", "Items", "Gross Sales"],
        "color": "#378ADD",
    },
    "recipes": {
        "label": "Recipes",
        "desc": "Export dari menu Inventory → Recipes",
        "cols_required": ["Item Name", "Ingredient Name", "Ingredient Quantity"],
        "color": "#D85A30",
    },
}


import datetime as _dt
import pandas as _pd

def safe_date(val, fallback=None):
    """Konversi Timestamp / NaT / str / None ke datetime.date dengan aman."""
    if fallback is None:
        fallback = _dt.date.today()
    try:
        if val is None: return fallback
        # Cek NaT/NaN sebelum apapun
        if _pd.isnull(val): return fallback
        if isinstance(val, _dt.datetime): return val.date()
        if isinstance(val, _dt.date): return val
        if isinstance(val, str): return _dt.date.fromisoformat(val[:10])
        ts = _pd.Timestamp(val)
        if _pd.isna(ts): return fallback
        return ts.date()
    except Exception:
        return fallback
