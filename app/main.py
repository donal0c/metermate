"""Energy Insight - Smart Meter Data Analysis Tool

Home page for the Streamlit multipage app. Navigate to Bill Extractor
or Meter Analysis using the sidebar.
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
    initial_sidebar_state="expanded"
)

# Apply dark theme from shared module
apply_theme()


def _load_logo():
    """Load logo from file if it exists."""
    logo_path = Path(__file__).parent / "logo.png"
    if logo_path.exists():
        return logo_path
    return None


# --- Sidebar ---
with st.sidebar:
    logo_path = _load_logo()
    if logo_path:
        st.image(str(logo_path), width=180)
        st.divider()

    st.markdown("### About")
    st.markdown("""
    Analyze energy consumption data to generate insights
    and visualizations for professional energy audits.

    **Supported formats:**
    - ESB Networks HDF (30-min CSV)
    - Excel spreadsheets (.xlsx, .xls)
    - CSV files with energy data
    - Electricity bills (PDF)
    - Photographed bills (JPG, PNG)
    """)

# --- Main content ---
st.markdown("## \u26a1 Energy Insight")
st.caption("Smart Meter Analysis for Energy Audits")

col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    st.markdown("---")
    st.markdown("### \U0001f44b Welcome to Energy Insight")
    st.markdown("Upload an energy data file to get started \u2014 use the sidebar to navigate to the right tool.")

    st.markdown("")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**\U0001f4c4 Bill Extractor**")
        st.caption("Extract data from PDF or photographed electricity bills. Compare multiple bills side-by-side.")

        st.markdown("**\U0001f4ca Key Metrics**")
        st.caption("Total consumption, baseload, peak demand")

    with col_b:
        st.markdown("**\U0001f4c8 Meter Analysis**")
        st.caption("Analyze HDF, Excel, or CSV energy data with heatmaps, trend charts, and anomaly detection.")

        st.markdown("**\U0001f4e5 Excel Export**")
        st.caption("Audit-ready data exports")

    st.markdown("---")

    # Demo buttons
    st.markdown("#### Try It Now")
    demo_col1, demo_col2 = st.columns(2)

    _sample_dir = os.path.join(os.path.dirname(__file__), "..", "Steve_bills")
    _hdf_path = os.path.join(os.path.dirname(__file__), "..",
                             "HDF_calckWh_10306268587_03-02-2026.csv")

    with demo_col1:
        if os.path.exists(_hdf_path):
            if st.button("\U0001f4ca Try sample HDF data", use_container_width=True):
                with open(_hdf_path, "rb") as f:
                    st.session_state._demo_file_content = f.read()
                st.session_state._demo_file_name = "HDF_sample.csv"
                st.switch_page("pages/2_Meter_Analysis.py")
        else:
            st.button("\U0001f4ca Sample HDF (not found)", disabled=True,
                      use_container_width=True)

    with demo_col2:
        _sample_bill = os.path.join(_sample_dir, "1845.pdf")
        if os.path.exists(_sample_bill):
            if st.button("\U0001f4c4 Try sample bill", use_container_width=True):
                with open(_sample_bill, "rb") as f:
                    st.session_state._demo_file_content = f.read()
                st.session_state._demo_file_name = "sample_bill.pdf"
                st.switch_page("pages/1_Bill_Extractor.py")
        else:
            st.button("\U0001f4c4 Sample bill (not found)", disabled=True,
                      use_container_width=True)

    st.markdown("---")

    st.markdown("#### Supported Formats")
    st.markdown("""
    **ESB Networks HDF** (recommended)
    1. Log into [ESB Networks Portal](https://myaccount.esbnetworks.ie/)
    2. Navigate to **My Usage** \u2192 **Download Data**
    3. Select "30 Minute Readings in kWh"
    4. Download and upload via **Meter Analysis**

    **Excel / CSV**
    - Upload any spreadsheet with energy consumption data
    - Columns are auto-detected (date, kWh, MPRN, cost)
    - Works with ESB, Electric Ireland, SSE Airtricity, Flogas exports

    **Electricity Bill (PDF)**
    - Upload a scanned or digital electricity bill
    - Auto-extracts supplier, consumption, costs, and balance
    - Supports Energia, Electric Ireland, SSE Airtricity, and more

    **Photographed Bill (JPG, PNG)**
    - Upload a photo of a paper bill
    - Uses OCR and AI vision to extract data
    - Best results with clear, well-lit photos
    """)
