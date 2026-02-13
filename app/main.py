"""Energy Insight - Task-Oriented Landing Page

Home page for the Streamlit multipage app. Provides two clear workflow
cards (Bill Extractor, Meter Analysis) and subtle sample-data links.
"""

import os
import streamlit as st
from pathlib import Path

from common.theme import apply_theme

# Page config
st.set_page_config(
    page_title="Energy Insight",
    page_icon="\u26a1",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Apply dark theme from shared module
apply_theme()


def _load_logo():
    """Load logo from file if it exists."""
    logo_path = Path(__file__).parent / "logo.png"
    if logo_path.exists():
        return logo_path
    return None


# --- Sidebar (minimal - just logo) ---
with st.sidebar:
    logo_path = _load_logo()
    if logo_path:
        st.image(str(logo_path), width=180)

# --- Hero Section ---
_, hero_col, _ = st.columns([1, 3, 1])
with hero_col:
    st.markdown("## \u26a1 Energy Insight")
    st.caption("Cork Energy Consultancy")
    st.markdown("Upload bills or meter data to get started.")

    st.markdown("")

    # --- Workflow Cards ---
    _CARD_HTML = """
    <div data-testid="workflow-cards" style="display: flex; gap: 1.5rem; margin: 1rem 0 2rem 0;">
        <a href="/Bill_Extractor" target="_self" data-testid="card-bill-extractor"
           class="workflow-card"
           style="flex: 1; display: block; text-decoration: none;">
            <div style="font-size: 2.5rem; margin-bottom: 0.75rem;">\U0001f4c4</div>
            <div style="color: #ffffff !important; font-family: 'DM Sans', sans-serif;
                        font-size: 1.3rem; font-weight: 600; margin-bottom: 0.5rem;">
                Extract Bills
            </div>
            <div style="color: #94a3b8 !important; font-size: 0.95rem; line-height: 1.5;">
                Upload PDF or photographed electricity bills.
                Extract costs, consumption, and rates automatically.
            </div>
            <div class="card-arrow"
                 style="color: #4ade80; font-size: 0.9rem; margin-top: 1rem;">
                Bill Extractor \u2192
            </div>
        </a>
        <a href="/Meter_Analysis" target="_self" data-testid="card-meter-analysis"
           class="workflow-card"
           style="flex: 1; display: block; text-decoration: none;">
            <div style="font-size: 2.5rem; margin-bottom: 0.75rem;">\U0001f4ca</div>
            <div style="color: #ffffff !important; font-family: 'DM Sans', sans-serif;
                        font-size: 1.3rem; font-weight: 600; margin-bottom: 0.5rem;">
                Analyse Meter Data
            </div>
            <div style="color: #94a3b8 !important; font-size: 0.95rem; line-height: 1.5;">
                Upload ESB Networks HDF or Excel files.
                Heatmaps, anomaly detection, and insights.
            </div>
            <div class="card-arrow"
                 style="color: #4ade80; font-size: 0.9rem; margin-top: 1rem;">
                Meter Analysis \u2192
            </div>
        </a>
    </div>
    """
    st.markdown(_CARD_HTML, unsafe_allow_html=True)

    # --- Sample Data (subtle text links) ---
    _sample_dir = os.path.join(os.path.dirname(__file__), "..", "Steve_bills")
    _hdf_path = os.path.join(os.path.dirname(__file__), "..",
                             "HDF_calckWh_10306268587_03-02-2026.csv")

    st.markdown(
        '<div style="color: #64748b; font-size: 0.85rem; margin-top: 0.5rem;">'
        'Or try with sample data:</div>',
        unsafe_allow_html=True,
    )

    sample_col1, sample_col2, _ = st.columns([1, 1, 2])

    with sample_col1:
        if os.path.exists(_hdf_path):
            if st.button("Sample HDF data", key="demo_hdf", type="secondary"):
                with open(_hdf_path, "rb") as f:
                    st.session_state._demo_file_content = f.read()
                st.session_state._demo_file_name = "HDF_sample.csv"
                st.switch_page("pages/2_Meter_Analysis.py")
        else:
            st.button("Sample HDF data", key="demo_hdf",
                      type="secondary", disabled=True)

    with sample_col2:
        _sample_bill = os.path.join(_sample_dir, "1845.pdf")
        if os.path.exists(_sample_bill):
            if st.button("Sample bill", key="demo_bill", type="secondary"):
                with open(_sample_bill, "rb") as f:
                    st.session_state._demo_file_content = f.read()
                st.session_state._demo_file_name = "sample_bill.pdf"
                st.switch_page("pages/1_Bill_Extractor.py")
        else:
            st.button("Sample bill", key="demo_bill",
                      type="secondary", disabled=True)
