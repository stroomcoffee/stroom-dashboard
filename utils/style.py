import streamlit as st

BG         = "#0F1117"
BG2        = "#1A1D27"
BG3        = "#22263A"
ACCENT     = "#00C896"
ACCENT2    = "#3D8EF0"
WARN       = "#F5A623"
DANGER     = "#F04D4D"
TEXT       = "#E8EAF0"
TEXT_MUTED = "#7A7F99"
BORDER     = "#2A2D3E"

PLOTLY_DARK = dict(
    plot_bgcolor  = BG2,
    paper_bgcolor = BG2,
    font          = dict(color=TEXT, family="Inter, sans-serif", size=12),
    hoverlabel    = dict(bgcolor=BG3, font=dict(color=TEXT), bordercolor=BORDER),
)

CHART_COLORS = [ACCENT, ACCENT2, WARN, "#C084FC", "#FB7185", "#34D399", "#F97316"]


def dark_xaxis(**kwargs):
    base = dict(showgrid=False, color=TEXT_MUTED, zeroline=False)
    base.update(kwargs)
    return base


def dark_yaxis(**kwargs):
    base = dict(showgrid=True, gridcolor="#1E2235", color=TEXT_MUTED, zeroline=False)
    base.update(kwargs)
    return base


def inject_css():
    st.markdown(f"""
    <style>
    /* ── Metric cards ── */
    [data-testid="metric-container"] {{
        background: {BG2} !important;
        border: 1px solid {BORDER} !important;
        border-radius: 14px !important;
        padding: 20px 24px !important;
    }}
    [data-testid="metric-container"]:hover {{
        border-color: {ACCENT} !important;
    }}
    [data-testid="metric-container"] label {{
        color: {TEXT_MUTED} !important;
        font-size: 0.75rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
    }}
    [data-testid="metric-container"] [data-testid="stMetricValue"] {{
        color: {TEXT} !important;
        font-size: 1.6rem !important;
        font-weight: 700 !important;
    }}

    /* ── Buttons ── */
    .stButton > button {{
        border-radius: 8px !important;
        font-weight: 500 !important;
        transition: all 0.15s !important;
    }}
    .stButton > button[kind="primary"] {{
        background: {ACCENT} !important;
        color: #0F1117 !important;
        border-color: {ACCENT} !important;
        font-weight: 600 !important;
    }}

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab"] {{
        border-radius: 8px !important;
    }}
    .stTabs [aria-selected="true"] {{
        color: {ACCENT} !important;
    }}

    /* ── Divider ── */
    hr {{ border-color: {BORDER} !important; }}

    /* ── Scrollbar ── */
    ::-webkit-scrollbar {{ width: 5px; height: 5px; }}
    ::-webkit-scrollbar-track {{ background: {BG}; }}
    ::-webkit-scrollbar-thumb {{ background: {BG3}; border-radius: 99px; }}

    /* ── Custom badge ── */
    .badge-danger  {{ background: rgba(240,77,77,0.15);  color: #F04D4D; border-radius: 6px; padding: 2px 8px; font-size: 0.75rem; font-weight: 600; }}
    .badge-warn    {{ background: rgba(245,166,35,0.15); color: #F5A623; border-radius: 6px; padding: 2px 8px; font-size: 0.75rem; font-weight: 600; }}
    .badge-success {{ background: rgba(0,200,150,0.12);  color: #00C896; border-radius: 6px; padding: 2px 8px; font-size: 0.75rem; font-weight: 600; }}
    .dash-card-title {{
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: {TEXT_MUTED};
        margin-bottom: 12px;
    }}
    </style>
    """, unsafe_allow_html=True)
