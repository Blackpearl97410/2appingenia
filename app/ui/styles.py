"""
app/ui/styles.py
Deux palettes CSS (light / dark) avec variables CSS.
Le thème actif est stocké dans st.session_state["theme"].
"""
from __future__ import annotations

import streamlit as st

# ── Palette light ──────────────────────────────────────────────────────────────
_LIGHT_VARS = """
    --bg-main:        #f8fafc;
    --bg-surface:     #ffffff;
    --bg-surface2:    #f1f5f9;
    --bg-sidebar:     #1e293b;
    --border:         #e2e8f0;
    --border-accent:  #6366f1;
    --text-primary:   #0f172a;
    --text-secondary: #475569;
    --text-muted:     #94a3b8;
    --text-sidebar:   #f1f5f9;
    --text-sidebar-m: #cbd5e1;
    --accent:         #6366f1;
    --accent-hover:   #4f46e5;
    --accent-subtle:  #ede9fe;
    --accent-text:    #4f46e5;
    --code-bg:        #ede9fe;
    --code-text:      #4f46e5;
    --shadow-sm:      0 1px 4px rgba(15,23,42,0.08);
    --shadow-md:      0 6px 20px rgba(99,102,241,0.18);
    --metric-value:   #0f172a;
    --metric-label:   #64748b;
    --h1-color:       #1e293b;
    --h2-color:       #1e293b;
    --h3-color:       #334155;
    --expander-bg:    #ffffff;
    --input-bg:       #ffffff;
    --input-border:   #cbd5e1;
    --input-text:     #0f172a;
    --divider:        #e2e8f0;
"""

# ── Palette dark ───────────────────────────────────────────────────────────────
_DARK_VARS = """
    --bg-main:        #0f172a;
    --bg-surface:     #1e293b;
    --bg-surface2:    #273548;
    --bg-sidebar:     #0a0f1e;
    --border:         #334155;
    --border-accent:  #818cf8;
    --text-primary:   #f1f5f9;
    --text-secondary: #cbd5e1;
    --text-muted:     #94a3b8;
    --text-sidebar:   #f1f5f9;
    --text-sidebar-m: #94a3b8;
    --accent:         #818cf8;
    --accent-hover:   #6366f1;
    --accent-subtle:  #1e1b4b;
    --accent-text:    #a5b4fc;
    --code-bg:        #1e1b4b;
    --code-text:      #a5b4fc;
    --shadow-sm:      0 1px 4px rgba(0,0,0,0.35);
    --shadow-md:      0 6px 20px rgba(129,140,248,0.25);
    --metric-value:   #f1f5f9;
    --metric-label:   #94a3b8;
    --h1-color:       #f1f5f9;
    --h2-color:       #e2e8f0;
    --h3-color:       #cbd5e1;
    --expander-bg:    #1e293b;
    --input-bg:       #273548;
    --input-border:   #475569;
    --input-text:     #f1f5f9;
    --divider:        #334155;
"""

# ── CSS structurel utilisant les variables ─────────────────────────────────────
_CSS_BODY = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ── Racine : injection des variables selon le thème actif ── */
:root { %(vars)s }

/* ── Base ── */
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
section.main,
.block-container {
    font-family: 'Inter', sans-serif !important;
    background-color: var(--bg-main) !important;
    color: var(--text-primary) !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div {
    background-color: var(--bg-sidebar) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div,
[data-testid="stSidebar"] label {
    color: var(--text-sidebar) !important;
}
[data-testid="stSidebar"] .stRadio > div > label {
    color: var(--text-sidebar-m) !important;
    border-radius: 6px;
    padding: 5px 10px;
    transition: background 0.18s;
}
[data-testid="stSidebar"] .stRadio > div > label:hover {
    background: rgba(148,163,184,0.15) !important;
    color: var(--text-sidebar) !important;
}

/* ── Titres ── */
h1 {
    color: var(--h1-color) !important;
    font-weight: 800 !important;
    border-bottom: 3px solid var(--accent) !important;
    padding-bottom: 8px !important;
    display: inline-block !important;
}
h2 { color: var(--h2-color) !important; font-weight: 700 !important; }
h3 { color: var(--h3-color) !important; font-weight: 600 !important; }

/* ── Paragraphes & listes ── */
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] span,
p, li {
    color: var(--text-primary) !important;
}
[data-testid="stCaptionContainer"] p,
[data-testid="stCaptionContainer"] span {
    color: var(--text-secondary) !important;
    font-size: 0.875rem !important;
}

/* ── Metric cards ── */
[data-testid="metric-container"] {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border) !important;
    border-left: 4px solid var(--accent) !important;
    border-radius: 10px !important;
    padding: 14px 20px !important;
    box-shadow: var(--shadow-sm) !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease !important;
}
[data-testid="metric-container"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: var(--shadow-md) !important;
}
[data-testid="metric-container"] [data-testid="stMetricLabel"] p,
[data-testid="metric-container"] label {
    color: var(--metric-label) !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.07em !important;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] div,
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: var(--metric-value) !important;
    font-weight: 800 !important;
    font-size: 1.55rem !important;
}

/* ── Boutons ── */
.stButton > button {
    background: var(--accent) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    padding: 9px 22px !important;
    transition: background 0.18s, transform 0.15s, box-shadow 0.15s !important;
}
.stButton > button:hover {
    background: var(--accent-hover) !important;
    transform: translateY(-1px) !important;
    box-shadow: var(--shadow-md) !important;
}

/* ── Expanders ── */
[data-testid="stExpander"] {
    background: var(--expander-bg) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary span {
    color: var(--text-primary) !important;
    font-weight: 600 !important;
}
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] p {
    color: var(--text-primary) !important;
}

/* ── Inputs ── */
textarea, input[type="text"], .stTextInput input, .stTextArea textarea {
    background: var(--input-bg) !important;
    border-color: var(--input-border) !important;
    color: var(--input-text) !important;
    border-radius: 6px !important;
}

/* ── Code inline ── */
code {
    background: var(--code-bg) !important;
    color: var(--code-text) !important;
    border-radius: 4px !important;
    padding: 2px 7px !important;
    font-size: 0.82em !important;
    font-weight: 600 !important;
}

/* ── Dataframes ── */
[data-testid="stDataFrame"] {
    border-radius: 8px !important;
    border: 1px solid var(--border) !important;
    overflow: hidden;
}

/* ── Dividers ── */
hr {
    border-color: var(--divider) !important;
    margin: 1.5rem 0 !important;
}

/* ── Widgets label ── */
.stSelectbox label, .stTextInput label,
.stTextArea label, .stRadio label,
.stCheckbox label, .stSlider label,
.stFileUploader label {
    color: var(--text-primary) !important;
    font-weight: 500 !important;
}

/* ── Write / st.write text ── */
[data-testid="stText"] {
    color: var(--text-primary) !important;
}

/* ── Selectbox & multiselect ── */
[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
[data-testid="baseButton-secondary"] {
    background: var(--input-bg) !important;
    color: var(--input-text) !important;
    border-color: var(--input-border) !important;
}
</style>
"""


def _build_css(dark: bool) -> str:
    vars_block = _DARK_VARS if dark else _LIGHT_VARS
    return _CSS_BODY % {"vars": vars_block}


def inject_global_styles() -> None:
    """Injecte le CSS adapté au thème choisi (stocké dans session_state)."""
    dark = st.session_state.get("theme_dark", False)
    st.markdown(_build_css(dark), unsafe_allow_html=True)


def render_theme_toggle() -> None:
    """Affiche le sélecteur de thème dans la sidebar."""
    current = st.session_state.get("theme_dark", False)
    label = "🌙 Mode sombre" if not current else "☀️ Mode clair"
    if st.sidebar.button(label, key="btn_theme_toggle", use_container_width=True):
        st.session_state["theme_dark"] = not current
        st.rerun()
