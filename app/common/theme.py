"""Theme configuration for Energy Insight.

Provides the dark theme CSS, color constants, font configuration,
and the Plotly chart template used across all pages.
"""
import streamlit as st

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
PRIMARY_GREEN = "#4ade80"
GREEN_GRADIENT_START = "#4ade80"
GREEN_GRADIENT_END = "#22c55e"
BG_PRIMARY = "#0f1419"
BG_SECONDARY = "#0a0f14"
SIDEBAR_BG = "#1a1f2e"
CARD_BG = "#1e2433"
BORDER_COLOR = "#2d3548"
TEXT_PRIMARY = "#ffffff"
TEXT_BODY = "#e2e8f0"
TEXT_SECONDARY = "#cbd5e1"
TEXT_MUTED = "#94a3b8"
TEXT_DIM = "#64748b"
SEVERITY_INFO = "#3b82f6"
SEVERITY_WARNING = "#f59e0b"
SEVERITY_ALERT = "#ef4444"
SOLAR_GREEN = "#22c55e"

# ---------------------------------------------------------------------------
# Font families
# ---------------------------------------------------------------------------
FONT_HEADING = "'DM Sans', sans-serif"
FONT_MONO = "'JetBrains Mono', monospace"

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
_THEME_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    .stApp {
        background: linear-gradient(180deg, #0f1419 0%, #0a0f14 100%);
    }

    #MainMenu, footer {visibility: hidden;}

    /* Keep sidebar toggle button visible */
    [data-testid="collapsedControl"] {
        visibility: visible !important;
        color: #4ade80 !important;
    }

    .main .block-container {
        padding-top: 2rem;
        max-width: 1400px;
    }

    /* ALL TEXT - HIGH CONTRAST */
    .stApp, .stApp p, .stApp span, .stApp div, .stApp label, .stApp li {
        color: #e2e8f0 !important;
    }

    h1, h2, h3, h4, h5, h6,
    .stApp h1, .stApp h2, .stApp h3 {
        font-family: 'DM Sans', sans-serif !important;
        color: #ffffff !important;
    }

    /* Markdown text */
    .stMarkdown, .stMarkdown p, .stMarkdown span, .stMarkdown li {
        color: #e2e8f0 !important;
    }

    /* Captions - still visible but lighter */
    .stCaption, [data-testid="stCaptionContainer"] {
        color: #94a3b8 !important;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: #1a1f2e;
        border-right: 1px solid #2d3548;
    }

    section[data-testid="stSidebar"] > div {
        padding-top: 1rem;
    }

    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] div,
    section[data-testid="stSidebar"] li,
    section[data-testid="stSidebar"] label {
        color: #cbd5e1 !important;
    }

    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: #ffffff !important;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: #1e2433;
        border-radius: 8px;
        padding: 4px;
        gap: 2px;
    }

    .stTabs [data-baseweb="tab"] {
        background: transparent;
        border-radius: 6px;
        color: #cbd5e1 !important;
        font-weight: 500;
        padding: 0.5rem 1rem !important;
    }

    .stTabs [aria-selected="true"] {
        background: #4ade80 !important;
        color: #000 !important;
    }

    .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {
        display: none;
    }

    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #4ade80, #22c55e);
        color: #000;
        border: none;
        font-weight: 600;
    }

    .stDownloadButton > button {
        background: #1e2433;
        border: 1px solid #2d3548;
        color: #ffffff !important;
    }

    /* Metrics */
    [data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', monospace !important;
        color: #ffffff !important;
    }

    [data-testid="stMetricLabel"] {
        color: #94a3b8 !important;
    }

    /* File uploader - dark text on light background */
    [data-testid="stFileUploader"] {
        border: 2px dashed #3d4a5c;
        border-radius: 8px;
        padding: 1rem;
    }

    [data-testid="stFileUploader"]:hover {
        border-color: #4ade80;
    }

    /* The inner dropzone has white background, so use dark text */
    [data-testid="stFileUploader"] section {
        color: #1a1a2e !important;
    }

    [data-testid="stFileUploader"] section p,
    [data-testid="stFileUploader"] section span,
    [data-testid="stFileUploader"] section small {
        color: #374151 !important;
    }

    [data-testid="stFileUploader"] button {
        color: #1a1a2e !important;
    }

    /* File name display outside dropzone */
    [data-testid="stFileUploader"] > div > div:last-child {
        color: #cbd5e1 !important;
    }

    /* Links */
    a {
        color: #4ade80 !important;
    }

    /* Info boxes */
    .stAlert {
        background: #1e2433 !important;
        border: 1px solid #2d3548;
    }

    .stAlert p, .stAlert span {
        color: #e2e8f0 !important;
    }

    /* Expanders */
    .streamlit-expanderHeader {
        color: #e2e8f0 !important;
        background: #1e2433;
    }

    .streamlit-expanderHeader p,
    .streamlit-expanderHeader span,
    .streamlit-expanderHeader svg {
        color: #e2e8f0 !important;
    }

    [data-testid="stExpander"] summary {
        color: #e2e8f0 !important;
    }

    [data-testid="stExpander"] summary p,
    [data-testid="stExpander"] summary span {
        color: #e2e8f0 !important;
    }

    .streamlit-expanderContent {
        background: #151a24;
        color: #e2e8f0 !important;
    }

    /* Dividers */
    hr {
        border-color: #2d3548 !important;
    }

    /* Hide Streamlit platform artifacts */
    .stDeployButton, [data-testid="stToolbar"] {
        display: none !important;
    }

    header[data-testid="stHeader"] {
        background: transparent !important;
    }

    /* Checkboxes */
    .stCheckbox label span {
        color: #e2e8f0 !important;
    }

    /* Workflow cards on landing page */
    .workflow-card {
        flex: 1;
        display: block;
        text-decoration: none !important;
        background: #1e2433;
        border: 1px solid #2d3548;
        border-radius: 12px;
        padding: 2rem;
        transition: all 0.2s ease;
        cursor: pointer;
    }

    .workflow-card:hover {
        border-color: #4ade80 !important;
        box-shadow: 0 8px 24px rgba(74, 222, 128, 0.15);
        transform: translateY(-2px) scale(1.02);
    }

    .workflow-card .card-arrow {
        opacity: 0.5;
        transition: opacity 0.2s ease, transform 0.2s ease;
    }

    .workflow-card:hover .card-arrow {
        opacity: 1;
        transform: translateX(4px);
    }

    /* Empty state cards */
    .empty-state-card {
        text-align: center;
        padding: 3rem 2rem;
        background: linear-gradient(135deg, #1e2433 0%, #151a24 100%);
        border: 1px solid #2d3548;
        border-radius: 16px;
        margin: 1.5rem auto;
        max-width: 600px;
    }

    .empty-state-card .empty-icon {
        font-size: 3rem;
        margin-bottom: 1rem;
        opacity: 0.9;
    }

    .empty-state-card h3 {
        color: #ffffff !important;
        font-family: 'DM Sans', sans-serif !important;
        font-size: 1.4rem !important;
        margin-bottom: 0.5rem !important;
    }

    .empty-state-card p {
        color: #94a3b8 !important;
        font-size: 0.95rem;
        line-height: 1.6;
        margin-bottom: 0.5rem;
    }

    .empty-state-card .format-tags {
        display: flex;
        justify-content: center;
        flex-wrap: wrap;
        gap: 0.5rem;
        margin-top: 1rem;
    }

    .empty-state-card .format-tag {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        background: #0f1419;
        border: 1px solid #2d3548;
        border-radius: 20px;
        color: #94a3b8 !important;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem;
    }

    /* Error state for failed extraction */
    .extraction-failed-card {
        padding: 2rem;
        background: linear-gradient(135deg, rgba(239,68,68,0.05) 0%, #151a24 100%);
        border: 1px solid rgba(239,68,68,0.2);
        border-radius: 12px;
        margin: 1rem 0;
    }

    .extraction-failed-card h4 {
        color: #ef4444 !important;
        font-family: 'DM Sans', sans-serif !important;
        margin-bottom: 0.5rem !important;
    }

    .extraction-failed-card .suggestion-list {
        color: #cbd5e1 !important;
        font-size: 0.9rem;
        line-height: 1.8;
        padding-left: 1rem;
    }

    .extraction-failed-card .suggestion-list li {
        color: #cbd5e1 !important;
    }


</style>
"""


def apply_theme():
    """Inject the dark theme CSS into the current Streamlit page."""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)
