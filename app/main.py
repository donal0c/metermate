"""
Energy Insight - Smart Meter Data Analysis Tool

A Streamlit application for energy consultants to analyze ESB Networks HDF files
and Excel/CSV energy data exports, generating professional visualizations for
energy audit reports.
"""

import os
import streamlit as st
import pandas as pd
import hashlib
import io
from pathlib import Path
from datetime import datetime, timedelta, date

from hdf_parser import (
    parse_hdf_file,
    get_summary_stats,
    detect_anomalies,
    get_summary_stats_flexible,
    detect_anomalies_flexible,
    PROVIDER_PRESETS,
)
from visualizations import (
    create_heatmap,
    create_daily_profile,
    create_tariff_breakdown,
    create_monthly_trend,
    create_daily_trend,
    create_import_export_comparison,
    create_baseload_chart,
)
from parse_result import (
    DataGranularity,
    DataSource,
    ColumnMapping,
    ParseResult,
    DataQualityReport,
)
from column_mapping import detect_columns, build_column_mapping, validate_mapping
from excel_parser import parse_excel_file, read_upload, get_sheet_names
from bill_parser import extract_bill, BillData, generic_to_legacy
from orchestrator import extract_bill_pipeline, extract_bill_from_image
from bill_verification import (
    validate_cross_reference,
    compute_verification,
    get_consumption_deltas,
    get_rate_comparison,
    VerificationResult,
    parse_bill_date,
)
from dataclasses import asdict
import plotly.graph_objects as go

# Page config
st.set_page_config(
    page_title="Energy Insight",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Professional Dark Theme CSS - HIGH CONTRAST
st.markdown("""
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
        gap: 4px;
    }

    .stTabs [data-baseweb="tab"] {
        background: transparent;
        border-radius: 6px;
        color: #cbd5e1 !important;
        font-weight: 500;
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

    /* Expanders - dark text on light background */
    .streamlit-expanderHeader {
        color: #1a1a2e !important;
        background: #f1f5f9;
    }

    .streamlit-expanderHeader p,
    .streamlit-expanderHeader span,
    .streamlit-expanderHeader svg {
        color: #1a1a2e !important;
    }

    [data-testid="stExpander"] summary {
        color: #1a1a2e !important;
    }

    [data-testid="stExpander"] summary p,
    [data-testid="stExpander"] summary span {
        color: #1a1a2e !important;
    }

    .streamlit-expanderContent {
        background: #151a24;
        color: #e2e8f0 !important;
    }

    /* Dividers */
    hr {
        border-color: #2d3548 !important;
    }

    /* Checkboxes */
    .stCheckbox label span {
        color: #e2e8f0 !important;
    }
</style>
""", unsafe_allow_html=True)


def load_logo():
    """Load logo from file if it exists."""
    logo_path = Path(__file__).parent / "logo.png"
    if logo_path.exists():
        return logo_path
    return None


def _get_tariff_rates() -> dict:
    """Get current tariff rates from widget keys as EUR/kWh."""
    return {
        'day': st.session_state.get('_tariff_day_widget', 28.14) / 100,
        'night': st.session_state.get('_tariff_night_widget', 14.79) / 100,
        'peak': st.session_state.get('_tariff_peak_widget', 30.02) / 100,
    }


def _render_date_filter_sidebar(df: pd.DataFrame):
    """Render date range filter controls in the sidebar. Returns filtered df."""
    if 'date' not in df.columns and 'datetime' not in df.columns:
        return df

    # Determine date bounds from data
    if 'datetime' in df.columns:
        all_dates = df['datetime'].dt.date
    else:
        all_dates = pd.to_datetime(df['date']).dt.date
    data_min = all_dates.min()
    data_max = all_dates.max()

    selected_periods = None

    with st.sidebar:
        st.markdown("### Date Range")

        period_options = [
            "All Data",
            "Last 7 Days",
            "Last 30 Days",
            "Last 90 Days",
            "Specific Month",
            "Custom Range",
        ]

        if 'date_filter_period' not in st.session_state:
            st.session_state.date_filter_period = "All Data"

        period = st.selectbox(
            "Period",
            options=period_options,
            index=period_options.index(st.session_state.date_filter_period),
            key="_date_filter_period_widget",
            label_visibility="collapsed",
        )
        st.session_state.date_filter_period = period

        start_date = data_min
        end_date = data_max

        if period == "Last 7 Days":
            start_date = data_max - timedelta(days=6)
        elif period == "Last 30 Days":
            start_date = data_max - timedelta(days=29)
        elif period == "Last 90 Days":
            start_date = data_max - timedelta(days=89)
        elif period == "Specific Month":
            # Build month options from data
            if 'year_month' in df.columns:
                months = sorted(df['year_month'].unique(), reverse=True)
            else:
                months = sorted(all_dates.apply(lambda d: d.strftime('%Y-%m')).unique(), reverse=True)
            selected_month = st.selectbox(
                "Month",
                options=months,
                key="_date_filter_month",
            )
            # Parse selected month to date range
            yr, mn = selected_month.split('-')
            start_date = date(int(yr), int(mn), 1)
            # Last day of month
            if int(mn) == 12:
                end_date = date(int(yr) + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(int(yr), int(mn) + 1, 1) - timedelta(days=1)
        elif period == "Custom Range":
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input(
                    "From",
                    value=data_min,
                    min_value=data_min,
                    max_value=data_max,
                    key="_date_filter_start",
                )
            with col2:
                end_date = st.date_input(
                    "To",
                    value=data_max,
                    min_value=data_min,
                    max_value=data_max,
                    key="_date_filter_end",
                )

        # Clamp to data bounds
        start_date = max(start_date, data_min)
        end_date = min(end_date, data_max)

        if period != "All Data":
            st.caption(f"{start_date.strftime('%d %b %Y')} — {end_date.strftime('%d %b %Y')}")

        st.divider()

        # Load type filter (only for interval data with tariff_period)
        if 'tariff_period' in df.columns:
            st.markdown("### Load Type")
            available_periods = sorted(df['tariff_period'].unique())
            selected_periods = st.multiselect(
                "Tariff periods",
                options=available_periods,
                default=available_periods,
                key="_load_type_filter",
                label_visibility="collapsed",
            )
            st.divider()

    # Apply date filter
    filtered = df
    if period != "All Data":
        filtered = _apply_date_filter(filtered, start_date, end_date)

    # Apply load type filter
    if selected_periods is not None and 'tariff_period' in filtered.columns:
        if selected_periods:
            filtered = filtered[filtered['tariff_period'].isin(selected_periods)].copy()
        else:
            # User deselected everything — show empty df
            filtered = filtered.iloc[:0].copy()

    return filtered


def _apply_date_filter(df: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    """Filter DataFrame to a date range (inclusive)."""
    if 'datetime' in df.columns:
        mask = (df['datetime'].dt.date >= start_date) & (df['datetime'].dt.date <= end_date)
    elif 'date' in df.columns:
        dates = pd.to_datetime(df['date']).dt.date
        mask = (dates >= start_date) & (dates <= end_date)
    else:
        return df
    return df[mask].copy()


def _is_hdf_file(file_content: bytes) -> bool:
    """Check if file content looks like an ESB Networks HDF CSV."""
    try:
        # Peek at the first few lines
        head = file_content[:2048].decode("utf-8", errors="ignore")
        # HDF files have these specific columns
        return "MPRN" in head and "Read Type" in head and "Read Value" in head
    except Exception:
        return False


def _parse_hdf_with_result(file_content: bytes, filename: str) -> ParseResult:
    """Wrap the existing HDF parser output in a ParseResult."""
    df = parse_hdf_file(file_content)
    stats = get_summary_stats(df)

    report = DataQualityReport(
        total_rows_raw=len(df),
        total_rows_clean=len(df),
        rows_dropped=0,
        issues=[],
        date_range_start=stats["start_date"],
        date_range_end=stats["end_date"],
        granularity=DataGranularity.HALF_HOURLY,
        completeness_pct=100.0,
    )

    return ParseResult(
        df=df,
        source=DataSource.HDF,
        granularity=DataGranularity.HALF_HOURLY,
        quality_report=report,
        original_filename=filename,
    )


def main():
    # Header
    st.markdown("## ⚡ Energy Insight")
    st.caption("Smart Meter Analysis for Energy Audits")

    # Sidebar
    with st.sidebar:
        # Try to load logo
        logo_path = load_logo()
        if logo_path:
            st.image(str(logo_path), width=180)
            st.divider()

        st.markdown("### 📁 Upload Data")
        analysis_mode = st.radio(
            "Mode",
            ["Single File", "Bill Comparison"],
            key="analysis_mode",
            horizontal=True,
        )

        uploaded_file = None
        uploaded_files = None
        if analysis_mode == "Single File":
            uploaded_file = st.file_uploader(
                "Energy Data File",
                type=['csv', 'xlsx', 'xls', 'pdf', 'jpg', 'jpeg', 'png'],
                help="Upload an ESB Networks HDF file (CSV), Excel spreadsheet, or electricity bill (PDF/JPG/PNG)",
                label_visibility="collapsed"
            )
        else:
            uploaded_files = st.file_uploader(
                "Upload Bills (PDF/Image)",
                type=['pdf', 'jpg', 'jpeg', 'png'],
                accept_multiple_files=True,
                help="Upload 2 or more electricity bills (PDF or photographed) for side-by-side comparison",
                label_visibility="collapsed",
                key="comparison_uploader",
            )

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

        st.divider()

        # Hide tariff panel during bill PDF view (rates come from bill itself)
        _bill_extensions = ('.pdf', '.jpg', '.jpeg', '.png')
        _is_bill_upload = (
            analysis_mode == "Bill Comparison"
            or (uploaded_file is not None and uploaded_file.name.lower().endswith(_bill_extensions))
            or st.session_state.get("_demo_file_name", "").lower().endswith(_bill_extensions)
        )

        if _is_bill_upload:
            if analysis_mode == "Bill Comparison":
                st.markdown("### 📊 Bill Comparison Mode")
                st.caption(
                    "Upload multiple bills to compare costs, consumption, and rates "
                    "across billing periods."
                )
            else:
                st.markdown("### 📄 Bill Extraction Mode")
                st.caption(
                    "Tariff rates are extracted directly from the uploaded bill. "
                    "Upload a CSV or Excel file to configure rates manually."
                )
            st.divider()

        # Initialise session state for tariff (needed even when hidden)
        default_rates = PROVIDER_PRESETS['Electric Ireland']
        if 'tariff_provider' not in st.session_state:
            st.session_state.tariff_provider = 'Electric Ireland'
        if '_tariff_day_widget' not in st.session_state:
            st.session_state._tariff_day_widget = default_rates['day']
        if '_tariff_night_widget' not in st.session_state:
            st.session_state._tariff_night_widget = default_rates['night']
        if '_tariff_peak_widget' not in st.session_state:
            st.session_state._tariff_peak_widget = default_rates['peak']

        if not _is_bill_upload:
            # Tariff rate inputs (hidden during bill extraction)
            st.markdown("### Tariff Rates")

            provider_names = list(PROVIDER_PRESETS.keys())

            def _on_provider_change():
                """Callback: update rate widget keys when provider changes."""
                provider = st.session_state._tariff_provider_widget
                if provider != 'Custom':
                    preset = PROVIDER_PRESETS[provider]
                    st.session_state._tariff_day_widget = preset['day']
                    st.session_state._tariff_night_widget = preset['night']
                    st.session_state._tariff_peak_widget = preset['peak']
                st.session_state.tariff_provider = provider

            def _on_rate_change():
                """Callback: switch to Custom when user manually edits a rate."""
                if st.session_state.tariff_provider != 'Custom':
                    current_preset = PROVIDER_PRESETS.get(st.session_state.tariff_provider, {})
                    if (abs(st.session_state._tariff_day_widget - current_preset.get('day', 0)) > 0.001 or
                        abs(st.session_state._tariff_night_widget - current_preset.get('night', 0)) > 0.001 or
                        abs(st.session_state._tariff_peak_widget - current_preset.get('peak', 0)) > 0.001):
                        st.session_state.tariff_provider = 'Custom'

            provider = st.selectbox(
                "Electricity Provider",
                options=provider_names,
                index=provider_names.index(st.session_state.tariff_provider),
                key='_tariff_provider_widget',
                on_change=_on_provider_change,
            )

            st.number_input(
                "Day rate (c/kWh)",
                min_value=0.0, max_value=100.0,
                step=0.5, format="%.2f",
                key='_tariff_day_widget',
                on_change=_on_rate_change,
            )
            st.number_input(
                "Night rate (c/kWh)",
                min_value=0.0, max_value=100.0,
                step=0.5, format="%.2f",
                key='_tariff_night_widget',
                on_change=_on_rate_change,
            )
            st.number_input(
                "Peak rate (c/kWh)",
                min_value=0.0, max_value=100.0,
                step=0.5, format="%.2f",
                key='_tariff_peak_widget',
                on_change=_on_rate_change,
            )

            st.caption("Rates inc. VAT. Verify against client's bill.")
            st.divider()

    # Main content — handle comparison mode or single file
    if analysis_mode == "Bill Comparison":
        if uploaded_files and len(uploaded_files) >= 2:
            _handle_bill_comparison(uploaded_files)
        elif uploaded_files:
            st.info("Upload at least 2 electricity bills (PDF or image) for comparison.")
        else:
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.markdown("---")
                st.markdown("### 📊 Bill Comparison")
                st.markdown(
                    "Upload 2 or more electricity bills (PDF or photo) using the sidebar "
                    "to compare costs, consumption, and rates across billing periods."
                )
                st.markdown("")
                st.markdown("**What you'll see:**")
                st.markdown("- Side-by-side summary of all bills")
                st.markdown("- Cost trends over time")
                st.markdown("- Consumption trends (kWh)")
                st.markdown("- Rate change analysis")
                st.markdown("- Excel export of comparison data")
                st.markdown("---")
        return

    if uploaded_file is not None:
        file_content = uploaded_file.getvalue()
        filename = uploaded_file.name
        # Clear demo state when user uploads a real file
        st.session_state.pop("_demo_file_content", None)
        st.session_state.pop("_demo_file_name", None)
    elif st.session_state.get("_demo_file_content") is not None:
        file_content = st.session_state._demo_file_content
        filename = st.session_state._demo_file_name
    else:
        show_welcome()
        return

    # Detect file type and route accordingly
    if filename.lower().endswith('.pdf'):
        _handle_bill_pdf(file_content, filename)
    elif filename.lower().endswith(('.jpg', '.jpeg', '.png')):
        _handle_bill_image(file_content, filename)
    elif _is_hdf_file(file_content):
        _handle_hdf_file(file_content, filename)
    else:
        _handle_excel_file(file_content, filename)


def _handle_hdf_file(file_content: bytes, filename: str):
    """Handle HDF file upload — direct to analysis (existing flow)."""
    # Cache parsed result in session_state to avoid re-parsing on rerun
    hdf_key = f"hdf_{filename}_{len(file_content)}"
    if st.session_state.get("_hdf_cache_key") != hdf_key:
        try:
            with st.spinner("Parsing HDF file..."):
                result = _parse_hdf_with_result(file_content, filename)
                st.session_state._hdf_cache_key = hdf_key
                st.session_state._hdf_cached_result = result
        except Exception as e:
            st.error(f"Error parsing file: {str(e)}")
            st.info("Please ensure this is a valid ESB Networks HDF file.")
            return

    result = st.session_state._hdf_cached_result
    full_df = result.df

    # --- Sidebar: bill verification uploader ---
    verification_result = _handle_verification_sidebar(full_df)

    # Date range filter (sidebar)
    df = _render_date_filter_sidebar(full_df)

    if len(df) == 0:
        st.warning("No data matches the current filters. Adjust the date range or load type above.")
        return

    # Recompute stats and anomalies on the filtered data
    stats = get_summary_stats(df)
    tariff_rates = _get_tariff_rates()
    anomalies = detect_anomalies(df, tariff_rates=tariff_rates)

    st.success(f"✓ Showing {len(df):,} readings from {stats['start_date'].strftime('%d %b %Y')} to {stats['end_date'].strftime('%d %b %Y')}")

    # Tabs for different sections — add Bill Verification if a bill is loaded
    has_verification = verification_result is not None
    if has_verification:
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📊 Overview",
            "🔥 Heatmap",
            "📈 Charts",
            "⚠️ Insights",
            "📥 Export",
            "🔍 Bill Verification",
        ])
    else:
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 Overview",
            "🔥 Heatmap",
            "📈 Charts",
            "⚠️ Insights",
            "📥 Export"
        ])

    with tab1:
        show_overview(stats, anomalies)
    with tab2:
        show_heatmap(df)
    with tab3:
        show_charts(df, stats, anomalies)
    with tab4:
        show_insights(df, stats, anomalies)
    with tab5:
        show_export(df, stats)

    if has_verification:
        with tab6:
            show_bill_verification(full_df, verification_result)


def _handle_verification_sidebar(hdf_df: pd.DataFrame) -> VerificationResult | None:
    """Render the bill verification uploader in the sidebar.

    Returns a VerificationResult if a valid bill has been uploaded and
    cross-referenced, or None otherwise.
    """
    hdf_stats = get_summary_stats(hdf_df)
    hdf_mprn = hdf_stats.get('mprn', '')

    with st.sidebar:
        st.markdown("### 🔍 Verify a Bill")
        st.caption("Upload a bill PDF to cross-check against this meter data.")

        verification_pdf = st.file_uploader(
            "Bill for verification",
            type=['pdf', 'jpg', 'jpeg', 'png'],
            key="verification_bill_uploader",
            label_visibility="collapsed",
        )

        if verification_pdf is None:
            # Clear cached verification when file is removed
            st.session_state.pop("_verification_result", None)
            st.session_state.pop("_verification_bill", None)
            st.session_state.pop("_verification_cache_key", None)
            return None

        # Cache to avoid re-extraction on every rerun
        v_content = verification_pdf.getvalue()
        v_key = f"verify_{verification_pdf.name}_{len(v_content)}"

        if st.session_state.get("_verification_cache_key") != v_key:
            try:
                with st.spinner("Extracting bill for verification..."):
                    v_name = verification_pdf.name.lower()
                    if v_name.endswith(('.jpg', '.jpeg', '.png')):
                        pipeline_result = extract_bill_from_image(v_content)
                    else:
                        pipeline_result = extract_bill_pipeline(v_content)
                    bill = generic_to_legacy(pipeline_result.bill)

                    # Validate cross-reference
                    v_result = validate_cross_reference(hdf_df, hdf_mprn, bill)

                    if v_result.valid:
                        v_result = compute_verification(hdf_df, bill, v_result)

                    st.session_state._verification_cache_key = v_key
                    st.session_state._verification_result = v_result
                    st.session_state._verification_bill = bill
            except Exception as e:
                st.error(f"Error extracting bill: {str(e)}")
                return None

        v_result = st.session_state.get("_verification_result")
        bill = st.session_state.get("_verification_bill")

        if v_result and not v_result.valid:
            st.error(v_result.block_reason)
            return None

        if v_result and v_result.valid:
            st.success(
                f"MPRN match: {v_result.hdf_mprn}\n\n"
                f"Coverage: {v_result.overlap_pct:.0f}% "
                f"({v_result.overlap_days}/{v_result.billing_days} days)"
            )

        st.divider()

        return v_result


def _handle_excel_file(file_content: bytes, filename: str):
    """Handle Excel/CSV upload with multi-step flow."""
    # Initialize session state for Excel flow
    if "excel_step" not in st.session_state:
        st.session_state.excel_step = 1
    if "excel_file_key" not in st.session_state:
        st.session_state.excel_file_key = None

    # Reset flow if a new file is uploaded
    current_key = f"{filename}_{len(file_content)}"
    if st.session_state.excel_file_key != current_key:
        st.session_state.excel_step = 1
        st.session_state.excel_file_key = current_key
        st.session_state.pop("excel_result", None)
        st.session_state.pop("excel_mapping_edits", None)

    step = st.session_state.excel_step

    if step == 1:
        _excel_step1_mapping(file_content, filename)
    elif step == 2:
        _excel_step2_quality(file_content, filename)
    elif step == 3:
        _excel_step3_analysis()


def _excel_step1_mapping(file_content: bytes, filename: str):
    """Step 1: Show raw preview, auto-detect columns, let user edit mapping."""
    st.markdown("### Step 1: Column Mapping")
    st.caption(f"File: **{filename}**")

    # Sheet selection for Excel files
    sheet_names = get_sheet_names(file_content, filename)
    selected_sheet = None
    if len(sheet_names) > 1:
        selected_sheet = st.selectbox(
            "Select sheet",
            options=sheet_names,
            help="This file has multiple sheets. Select the one containing energy data.",
            key="excel_sheet_select",
        )

    # Read raw data
    try:
        raw_df = read_upload(file_content, filename, sheet_name=selected_sheet)
    except Exception as e:
        st.error(f"Error reading file: {str(e)}")
        return

    # Show raw preview
    with st.expander("Raw Data Preview", expanded=True):
        st.dataframe(raw_df.head(10), use_container_width=True)
        st.caption(f"{len(raw_df):,} rows × {len(raw_df.columns)} columns")

    # Auto-detect columns
    candidates = detect_columns(raw_df)
    mapping = build_column_mapping(candidates)

    # When sheet changes, force-set widget values to auto-detected columns
    prev_sheet = st.session_state.get("_prev_sheet")
    if selected_sheet != prev_sheet:
        st.session_state["_prev_sheet"] = selected_sheet
        st.session_state["map_datetime"] = mapping.datetime_col or "(None)"
        st.session_state["map_import"] = mapping.import_kwh_col or "(None)"
        st.session_state["map_export"] = mapping.export_kwh_col or "(None)"
        st.session_state["map_mprn"] = mapping.mprn_col or "(None)"
        st.session_state["map_cost"] = mapping.cost_col or "(None)"

    # Show detection results
    st.markdown("#### Detected Column Mapping")

    if candidates:
        for field, candidate in candidates.items():
            tier_label = {1: "Exact", 2: "Fuzzy", 3: "Content"}.get(candidate.tier, "?")
            confidence_pct = candidate.confidence * 100
            st.markdown(
                f"- **{field}** → `{candidate.original_name}` "
                f"({tier_label} match, {confidence_pct:.0f}% confidence)"
            )
    else:
        st.warning("No columns could be auto-detected. Please map them manually below.")

    # Editable mapping — use auto-detected values as defaults, but respect user edits
    st.markdown("#### Edit Mapping")
    st.caption("Select the correct column for each field, or leave as 'None' if not available.")

    col_options = ["(None)"] + list(raw_df.columns)

    def _default_idx(field_val):
        if field_val and field_val in col_options:
            return col_options.index(field_val)
        return 0

    col1, col2 = st.columns(2)

    with col1:
        dt_col = st.selectbox(
            "Date/Time column *",
            options=col_options,
            index=_default_idx(mapping.datetime_col),
            key="map_datetime",
        )
        import_col = st.selectbox(
            "Import/Consumption (kWh) column *",
            options=col_options,
            index=_default_idx(mapping.import_kwh_col),
            key="map_import",
        )
        export_col = st.selectbox(
            "Export (kWh) column",
            options=col_options,
            index=_default_idx(mapping.export_kwh_col),
            key="map_export",
        )

    with col2:
        mprn_col = st.selectbox(
            "MPRN column",
            options=col_options,
            index=_default_idx(mapping.mprn_col),
            key="map_mprn",
        )
        cost_col = st.selectbox(
            "Cost column",
            options=col_options,
            index=_default_idx(mapping.cost_col),
            key="map_cost",
        )
        mprn_override = st.text_input(
            "MPRN (manual entry)",
            help="Enter the MPRN if it's not in the file or auto-detected incorrectly",
            key="mprn_override",
        )

    # Proceed button
    st.markdown("")
    if st.button("Proceed to Quality Check", type="primary"):
        # Build mapping from user selections
        user_mapping = ColumnMapping(
            datetime_col=dt_col if dt_col != "(None)" else None,
            import_kwh_col=import_col if import_col != "(None)" else None,
            export_kwh_col=export_col if export_col != "(None)" else None,
            mprn_col=mprn_col if mprn_col != "(None)" else None,
            cost_col=cost_col if cost_col != "(None)" else None,
            detection_tier=mapping.detection_tier,
            confidence=mapping.confidence,
        )

        # Validate
        errors = validate_mapping(user_mapping, raw_df)
        if errors:
            for e in errors:
                st.error(e)
            return

        # Store mapping and advance
        st.session_state.excel_mapping = user_mapping
        st.session_state.excel_mprn_override = mprn_override
        st.session_state.excel_sheet = selected_sheet
        st.session_state.excel_step = 2
        st.rerun()


def _excel_step2_quality(file_content: bytes, filename: str):
    """Step 2: Parse, clean, show quality report."""
    st.markdown("### Step 2: Data Quality Report")

    mapping = st.session_state.get("excel_mapping")
    mprn_override = st.session_state.get("excel_mprn_override")
    selected_sheet = st.session_state.get("excel_sheet")

    if not mapping:
        st.session_state.excel_step = 1
        st.rerun()
        return

    # Parse the file
    try:
        with st.spinner("Cleaning and validating data..."):
            result = parse_excel_file(
                file_content,
                filename,
                column_mapping=mapping,
                mprn_override=mprn_override if mprn_override else None,
                sheet_name=selected_sheet,
            )
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        st.session_state.excel_step = 1
        return

    report = result.quality_report

    # Show quality metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Raw Rows", f"{report.total_rows_raw:,}")
    with col2:
        st.metric("Clean Rows", f"{report.total_rows_clean:,}")
    with col3:
        st.metric("Rows Dropped", f"{report.rows_dropped:,}")
    with col4:
        st.metric("Completeness", f"{report.completeness_pct:.0f}%")

    # Granularity
    granularity_labels = {
        DataGranularity.HALF_HOURLY: "30-minute intervals",
        DataGranularity.HOURLY: "Hourly",
        DataGranularity.DAILY: "Daily",
        DataGranularity.MONTHLY: "Monthly",
        DataGranularity.UNKNOWN: "Unknown",
    }
    st.info(f"**Detected granularity:** {granularity_labels.get(result.granularity, 'Unknown')}")

    if report.date_range_start and report.date_range_end:
        st.caption(
            f"Date range: {report.date_range_start.strftime('%d %b %Y')} — "
            f"{report.date_range_end.strftime('%d %b %Y')}"
        )

    # Quality issues
    if report.issues:
        st.markdown("#### Quality Issues")
        for issue in report.issues:
            icon = {"error": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(issue.severity, "•")
            fixed_tag = " *(auto-fixed)*" if issue.auto_fixed else ""
            st.markdown(f"{icon} **{issue.category}**: {issue.message}{fixed_tag}")
            if issue.details:
                st.caption(f"  {issue.details}")
    else:
        st.success("✓ No quality issues found.")

    # Data preview
    if len(result.df) > 0:
        with st.expander("Cleaned Data Preview", expanded=False):
            st.dataframe(result.df.head(20), use_container_width=True)

    # Not usable?
    if not report.is_usable:
        st.error("Data has critical issues and cannot be analyzed. Please fix the issues above and re-upload.")
        if st.button("← Back to Mapping"):
            st.session_state.excel_step = 1
            st.rerun()
        return

    # Store result and show navigation
    st.session_state.excel_result = result

    st.markdown("")
    col1, col2, _ = st.columns([1, 1, 2])
    with col1:
        if st.button("← Back to Mapping"):
            st.session_state.excel_step = 1
            st.rerun()
    with col2:
        if st.button("Proceed to Analysis →", type="primary"):
            st.session_state.excel_step = 3
            st.rerun()


def _excel_step3_analysis():
    """Step 3: Show analysis tabs with graceful degradation."""
    result = st.session_state.get("excel_result")
    if not result or len(result.df) == 0:
        st.session_state.excel_step = 1
        st.rerun()
        return

    full_df = result.df
    granularity = result.granularity

    # Date range filter (sidebar)
    df = _render_date_filter_sidebar(full_df)

    if len(df) == 0:
        st.warning("No data matches the current filters. Adjust the date range or load type above.")
        # Back button still available
        st.markdown("")
        if st.button("← Back to Quality Report"):
            st.session_state.excel_step = 2
            st.rerun()
        return

    # Compute stats and anomalies on filtered data
    stats = get_summary_stats_flexible(df, granularity)
    tariff_rates = _get_tariff_rates()
    anomalies = detect_anomalies_flexible(df, granularity, tariff_rates=tariff_rates)

    # Success banner
    date_info = ""
    if stats.get("start_date") and stats.get("end_date"):
        date_info = f" from {stats['start_date'].strftime('%d %b %Y')} to {stats['end_date'].strftime('%d %b %Y')}"
    st.success(f"✓ Showing {len(df):,} readings{date_info}")

    # Build tabs based on granularity
    _show_analysis(result, df, stats, anomalies, granularity)

    # Back button
    st.markdown("")
    if st.button("← Back to Quality Report"):
        st.session_state.excel_step = 2
        st.rerun()


def _show_analysis(result: ParseResult, df: pd.DataFrame, stats: dict, anomalies: list, granularity: DataGranularity):
    """Build tab list based on granularity and show analysis."""
    if granularity.is_interval:
        # Full 5-tab layout for interval data
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 Overview",
            "🔥 Heatmap",
            "📈 Charts",
            "⚠️ Insights",
            "📥 Export"
        ])
        with tab1:
            show_overview(stats, anomalies)
        with tab2:
            show_heatmap(df)
        with tab3:
            show_charts(df, stats, anomalies)
        with tab4:
            show_insights(df, stats, anomalies)
        with tab5:
            show_export(df, stats)
    else:
        # Reduced tabs for daily/monthly (no heatmap)
        tab1, tab3, tab4, tab5 = st.tabs([
            "📊 Overview",
            "📈 Charts",
            "⚠️ Insights",
            "📥 Export"
        ])
        with tab1:
            show_overview_flexible(stats, anomalies, granularity)
        with tab3:
            show_charts_flexible(df, stats, granularity)
        with tab4:
            show_insights_flexible(df, stats, anomalies, granularity)
        with tab5:
            show_export_flexible(df, stats, granularity)


def show_welcome():
    """Show welcome screen when no file is uploaded."""
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("---")
        st.markdown("### 👋 Welcome to Energy Insight")
        st.markdown("Upload an energy data file to get started — HDF, Excel, CSV, or a PDF electricity bill.")

        st.markdown("")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**📊 Key Metrics**")
            st.caption("Total consumption, baseload, peak demand")

            st.markdown("**🔥 Usage Heatmap**")
            st.caption("Patterns by hour and day of week")

        with col_b:
            st.markdown("**⚠️ Anomaly Detection**")
            st.caption("Night loads, spikes, unusual patterns")

            st.markdown("**📥 Excel Export**")
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
                if st.button("📊 Try sample HDF data", use_container_width=True):
                    with open(_hdf_path, "rb") as f:
                        st.session_state._demo_file_content = f.read()
                    st.session_state._demo_file_name = "HDF_sample.csv"
                    st.rerun()
            else:
                st.button("📊 Sample HDF (not found)", disabled=True,
                          use_container_width=True)

        with demo_col2:
            _sample_bill = os.path.join(_sample_dir, "1845.pdf")
            if os.path.exists(_sample_bill):
                if st.button("📄 Try sample bill", use_container_width=True):
                    with open(_sample_bill, "rb") as f:
                        st.session_state._demo_file_content = f.read()
                    st.session_state._demo_file_name = "sample_bill.pdf"
                    st.rerun()
            else:
                st.button("📄 Sample bill (not found)", disabled=True,
                          use_container_width=True)

        st.markdown("---")

        st.markdown("#### Supported Formats")
        st.markdown("""
        **ESB Networks HDF** (recommended)
        1. Log into [ESB Networks Portal](https://myaccount.esbnetworks.ie/)
        2. Navigate to **My Usage** → **Download Data**
        3. Select "30 Minute Readings in kWh"
        4. Download and upload using the sidebar

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


def _handle_bill_pdf(file_content: bytes, filename: str):
    """Handle PDF bill upload — extract and display summary."""
    content_hash = hashlib.md5(file_content).hexdigest()
    bill_key = f"bill_{filename}_{len(file_content)}_{content_hash}"
    if st.session_state.get("_bill_cache_key") != bill_key:
        try:
            with st.spinner("Extracting bill data..."):
                pipeline_result = extract_bill_pipeline(file_content)
                bill = generic_to_legacy(pipeline_result.bill)
                st.session_state._bill_cache_key = bill_key
                st.session_state._bill_cached_result = bill
                st.session_state._bill_raw_text = pipeline_result.bill.raw_text
        except Exception as e:
            st.error(f"Error extracting bill: {str(e)}")
            st.info("Please ensure this is a valid electricity bill PDF.")
            return

    bill = st.session_state._bill_cached_result
    raw_text = st.session_state.get("_bill_raw_text")
    show_bill_summary(bill, raw_text=raw_text)


def _handle_bill_image(file_content: bytes, filename: str):
    """Handle image bill upload (JPG/PNG) — extract and display summary."""
    content_hash = hashlib.md5(file_content).hexdigest()
    bill_key = f"bill_img_{filename}_{len(file_content)}_{content_hash}"
    if st.session_state.get("_bill_cache_key") != bill_key:
        try:
            with st.spinner("Extracting bill from image..."):
                pipeline_result = extract_bill_from_image(file_content)
                bill = generic_to_legacy(pipeline_result.bill)
                st.session_state._bill_cache_key = bill_key
                st.session_state._bill_cached_result = bill
                st.session_state._bill_raw_text = pipeline_result.bill.raw_text
        except Exception as e:
            st.error(f"Error extracting bill from image: {str(e)}")
            st.info("Please ensure this is a clear photo of an electricity bill.")
            return

    bill = st.session_state._bill_cached_result
    raw_text = st.session_state.get("_bill_raw_text")
    show_bill_summary(bill, raw_text=raw_text)


def show_bill_summary(bill: BillData, raw_text: str | None = None):
    """Display extracted bill data as a clean single-page summary."""

    # --- Header with per-section breakdown ---
    confidence_pct = round(bill.confidence_score * 100)
    supplier_label = bill.supplier or "Unknown supplier"

    # Per-section field counts for actionable breakdown
    _sections = {
        "Account": ["supplier", "customer_name", "mprn", "account_number",
                     "meter_number", "invoice_number"],
        "Billing": ["bill_date", "billing_period_start", "billing_period_end"],
        "Consumption": ["day_units_kwh", "night_units_kwh", "peak_units_kwh",
                        "total_units_kwh"],
        "Costs": ["day_cost", "night_cost", "peak_cost", "subtotal_before_vat",
                  "standing_charge_total", "pso_levy", "vat_amount",
                  "total_this_period"],
        "Balance": ["previous_balance", "payments_received", "amount_due"],
    }
    bill_dict = asdict(bill)
    section_parts = []
    total_extracted = 0
    total_expected = 0
    for section_name, fields in _sections.items():
        count = sum(1 for f in fields if bill_dict.get(f) is not None)
        section_parts.append(f"{section_name}: {count}/{len(fields)}")
        total_extracted += count
        total_expected += len(fields)

    section_summary = " · ".join(section_parts)

    if confidence_pct >= 80:
        st.success(
            f"**{supplier_label}** — {total_extracted}/{total_expected} fields "
            f"(confidence: {confidence_pct}%)\n\n"
            f"{section_summary}"
        )
    else:
        st.warning(
            f"**{supplier_label}** — {total_extracted}/{total_expected} fields "
            f"(confidence: {confidence_pct}%)\n\n"
            f"{section_summary}\n\n"
            "Please verify fields marked with a warning icon."
        )


    # --- Extraction Method Info (for debugging/transparency) ---
    if bill.extraction_method:
        st.markdown(
            f'<div style="padding: 0.4rem 0.8rem; background: #1e293b; border-radius: 4px; '
            f'margin-bottom: 0.8rem; color: #94a3b8; font-size: 0.8rem;">'
            f'<strong>Extraction path:</strong> {bill.extraction_method}</div>',
            unsafe_allow_html=True,
        )

    # --- Extraction Warnings (immediately after confidence banner) ---
    if bill.warnings:
        for w in bill.warnings:
            st.markdown(
                f'<div style="padding: 0.5rem 0.8rem; border-left: 3px solid #f59e0b; '
                f'background: #1e2433; border-radius: 0 4px 4px 0; margin-bottom: 0.4rem; '
                f'color: #e2e8f0; font-size: 0.85rem;">{w}</div>',
                unsafe_allow_html=True,
            )

    def _fmt(value, prefix="", suffix="", fmt_spec=None):
        """Format a value for display, returning '—' if None."""
        if value is None:
            return "—"
        if fmt_spec:
            return f"{prefix}{value:{fmt_spec}}{suffix}"
        return f"{prefix}{value}{suffix}"

    def _field_html(label, value, warn=False):
        """Render a single key-value field, with optional warning styling."""
        if warn and value is not None:
            return (
                f'<div style="border-left: 3px solid #f59e0b; padding-left: 0.5rem; '
                f'margin-bottom: 0.4rem;">'
                f'<span style="color: #94a3b8; font-size: 0.8rem;">{label}</span><br>'
                f'<span style="color: #e2e8f0; font-family: \'JetBrains Mono\', monospace; '
                f'font-size: 0.95rem;">⚠️ {value}</span></div>'
            )
        display_val = value if value is not None else "—"
        color = "#64748b" if value is None else "#e2e8f0"
        return (
            f'<div style="margin-bottom: 0.4rem;">'
            f'<span style="color: #94a3b8; font-size: 0.8rem;">{label}</span><br>'
            f'<span style="color: {color}; font-family: \'JetBrains Mono\', monospace; '
            f'font-size: 0.95rem;">{display_val}</span></div>'
        )

    # Determine which fields have warnings (low confidence)
    warn_fields = set()
    for w in bill.warnings:
        # Extract field names mentioned in warning messages
        if "Critical field" in w:
            # e.g. "Critical field 'mprn' not extracted"
            field_match = w.split("'")[1] if "'" in w else ""
            if field_match:
                warn_fields.add(field_match)

    # --- Section 1: Account Details ---
    st.subheader("🏢 Account Details")
    cols = st.columns(4)
    account_fields = [
        ("Supplier", bill.supplier, 'supplier'),
        ("Customer", bill.customer_name, 'customer_name'),
        ("MPRN", bill.mprn, 'mprn'),
        ("Account No.", bill.account_number, 'account_number'),
        ("Meter No.", bill.meter_number, 'meter_number'),
        ("Invoice No.", bill.invoice_number, 'invoice_number'),
    ]
    for i, (label, value, field_name) in enumerate(account_fields):
        with cols[i % 4]:
            st.markdown(
                _field_html(label, value, warn=field_name in warn_fields),
                unsafe_allow_html=True,
            )

    # --- Section 2: Billing Period (hide if all empty) ---
    _has_billing = any(v is not None for v in [
        bill.bill_date, bill.billing_period_start, bill.billing_period_end,
    ])
    if _has_billing:
        st.subheader("📅 Billing Period")
        cols = st.columns(3)
        with cols[0]:
            st.markdown(_field_html("Bill Date", bill.bill_date), unsafe_allow_html=True)
        with cols[1]:
            period = "—"
            if bill.billing_period_start and bill.billing_period_end:
                period = f"{bill.billing_period_start} → {bill.billing_period_end}"
            elif bill.billing_period_start:
                period = bill.billing_period_start
            st.markdown(
                _field_html("Period", period,
                            warn='billing_period_start' in warn_fields or 'billing_period_end' in warn_fields),
                unsafe_allow_html=True,
            )
        with cols[2]:
            days = None
            if bill.billing_period_start and bill.billing_period_end:
                from datetime import datetime as dt
                _date_fmts = ["%d/%m/%Y", "%d %b %Y", "%d.%m.%Y", "%d %B %Y"]
                for fmt in _date_fmts:
                    try:
                        start = dt.strptime(bill.billing_period_start, fmt)
                        end = dt.strptime(bill.billing_period_end, fmt)
                        days = (end - start).days
                        break
                    except (ValueError, TypeError):
                        continue
            st.markdown(
                _field_html("Days", f"{days}" if days else None),
                unsafe_allow_html=True,
            )

    # --- Section 3: Consumption (hide if all empty) ---
    _has_consumption = any(v is not None for v in [
        bill.day_units_kwh, bill.night_units_kwh, bill.peak_units_kwh,
        bill.total_units_kwh, bill.day_rate, bill.night_rate, bill.peak_rate,
    ])
    if _has_consumption:
        st.subheader("⚡ Consumption")
        cols = st.columns(4)
        consumption_fields = [
            ("Day Units", bill.day_units_kwh, "kWh"),
            ("Night Units", bill.night_units_kwh, "kWh"),
            ("Peak Units", bill.peak_units_kwh, "kWh"),
            ("Total Units", bill.total_units_kwh, "kWh"),
        ]
        for i, (label, value, unit) in enumerate(consumption_fields):
            with cols[i]:
                display = _fmt(value, suffix=f" {unit}", fmt_spec=",.1f") if value is not None else None
                st.markdown(_field_html(label, display), unsafe_allow_html=True)

        # Rates row
        if any(v is not None for v in [bill.day_rate, bill.night_rate, bill.peak_rate]):
            cols = st.columns(4)
            rate_fields = [
                ("Day Rate", bill.day_rate),
                ("Night Rate", bill.night_rate),
                ("Peak Rate", bill.peak_rate),
            ]
            for i, (label, value) in enumerate(rate_fields):
                with cols[i]:
                    display = f"€{value:.4f}/kWh" if value is not None else None
                    st.markdown(_field_html(label, display), unsafe_allow_html=True)

    # --- Section 4: Costs ---
    st.subheader("💰 Costs")
    cols = st.columns(4)
    cost_fields = [
        ("Day Cost", bill.day_cost),
        ("Night Cost", bill.night_cost),
        ("Peak Cost", bill.peak_cost),
        ("Subtotal", bill.subtotal_before_vat),
    ]
    for i, (label, value) in enumerate(cost_fields):
        with cols[i]:
            display = f"€{value:,.2f}" if value is not None else None
            st.markdown(_field_html(label, display), unsafe_allow_html=True)

    # Additional cost line items
    line_items = []
    if bill.standing_charge_total is not None:
        detail = ""
        if bill.standing_charge_days and bill.standing_charge_rate:
            detail = f" ({bill.standing_charge_days} days at €{bill.standing_charge_rate}/day)"
        line_items.append(("Standing Charge", f"€{bill.standing_charge_total:,.2f}{detail}"))
    if bill.pso_levy is not None:
        line_items.append(("PSO Levy", f"€{bill.pso_levy:,.2f}"))
    if bill.discount is not None:
        line_items.append(("Discount", f"€{bill.discount:,.2f} CR"))
    if bill.vat_amount is not None:
        vat_detail = f" ({bill.vat_rate_pct:.0f}%)" if bill.vat_rate_pct else ""
        line_items.append(("VAT", f"€{bill.vat_amount:,.2f}{vat_detail}"))
    if bill.total_this_period is not None:
        line_items.append(("Total This Period", f"€{bill.total_this_period:,.2f}"))

    if line_items:
        for label, value in line_items:
            is_total = label == "Total This Period"
            weight = "700" if is_total else "400"
            size = "1rem" if is_total else "0.9rem"
            st.markdown(
                f'<div style="display: flex; justify-content: space-between; '
                f'padding: 0.3rem 0; border-bottom: 1px solid #1e2433;">'
                f'<span style="color: #94a3b8; font-size: {size};">{label}</span>'
                f'<span style="color: #e2e8f0; font-family: \'JetBrains Mono\', monospace; '
                f'font-size: {size}; font-weight: {weight};">{value}</span></div>',
                unsafe_allow_html=True,
            )

    # Solar export credit
    if bill.export_units is not None or bill.export_credit is not None:
        st.markdown("")
        st.caption("Solar Export")
        detail = ""
        if bill.export_units and bill.export_rate:
            detail = f" ({bill.export_units:,.1f} kWh at €{bill.export_rate:.4f}/kWh)"
        if bill.export_credit is not None:
            st.markdown(
                f'<div style="border-left: 3px solid #22c55e; padding-left: 0.5rem;">'
                f'<span style="color: #22c55e; font-family: \'JetBrains Mono\', monospace;">'
                f'€{bill.export_credit:,.2f} credit{detail}</span></div>',
                unsafe_allow_html=True,
            )

    # --- Section 5: Balance (hide if all empty) ---
    _has_balance = any(v is not None for v in [
        bill.previous_balance, bill.payments_received, bill.amount_due,
    ])
    if _has_balance:
        st.subheader("🏦 Balance")
        cols = st.columns(3)
        with cols[0]:
            display = f"€{bill.previous_balance:,.2f}" if bill.previous_balance is not None else None
            st.markdown(_field_html("Previous Balance", display), unsafe_allow_html=True)
        with cols[1]:
            display = f"€{bill.payments_received:,.2f}" if bill.payments_received is not None else None
            st.markdown(_field_html("Payments Received", display), unsafe_allow_html=True)
        with cols[2]:
            if bill.amount_due is not None:
                st.markdown(
                    f'<div style="border-left: 3px solid #4ade80; padding-left: 0.5rem;">'
                    f'<span style="color: #94a3b8; font-size: 0.8rem;">Amount Due</span><br>'
                    f'<span style="color: #4ade80; font-family: \'JetBrains Mono\', monospace; '
                    f'font-size: 1.3rem; font-weight: 700;">€{bill.amount_due:,.2f}</span></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(_field_html("Amount Due", None), unsafe_allow_html=True)

    # --- Export ---
    st.divider()
    st.subheader("📥 Export")
    excel_buffer = generate_bill_excel(bill)
    mprn_part = bill.mprn or "unknown"
    date_part = (bill.bill_date or "").replace(" ", "_") or "undated"
    st.download_button(
        label="Download as Excel",
        data=excel_buffer,
        file_name=f"bill_extract_{mprn_part}_{date_part}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="bill_download",
    )
    st.caption(
        f"Extraction method: {bill.extraction_method} · "
        f"Confidence: {confidence_pct}%"
    )

    # --- Raw Text Debug (collapsed by default) ---
    if raw_text:
        with st.expander("🔍 Raw Extracted Text", expanded=False):
            st.code(raw_text, language=None)


def generate_bill_excel(bill: BillData) -> io.BytesIO:
    """Generate an Excel file from extracted bill data."""
    buffer = io.BytesIO()
    data = asdict(bill)
    skip_meta = {'extraction_method', 'confidence_score', 'warnings'}

    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        # Sheet 1: Bill Summary
        field_labels = {
            'supplier': 'Supplier',
            'customer_name': 'Customer Name',
            'premises': 'Premises',
            'mprn': 'MPRN',
            'account_number': 'Account Number',
            'invoice_number': 'Invoice Number',
            'meter_number': 'Meter Number',
            'dg_code': 'DG Code',
            'mcc_code': 'MCC Code',
            'bill_date': 'Bill Date',
            'billing_period_start': 'Billing Period Start',
            'billing_period_end': 'Billing Period End',
            'payment_due_date': 'Payment Due Date',
            'contract_end_date': 'Contract End Date',
            'ceg_export_start': 'CEG Export Start',
            'ceg_export_end': 'CEG Export End',
            'day_units_kwh': 'Day Units (kWh)',
            'night_units_kwh': 'Night Units (kWh)',
            'peak_units_kwh': 'Peak Units (kWh)',
            'total_units_kwh': 'Total Units (kWh)',
            'day_rate': 'Day Rate (EUR/kWh)',
            'night_rate': 'Night Rate (EUR/kWh)',
            'peak_rate': 'Peak Rate (EUR/kWh)',
            'day_cost': 'Day Cost (EUR)',
            'night_cost': 'Night Cost (EUR)',
            'peak_cost': 'Peak Cost (EUR)',
            'standing_charge_days': 'Standing Charge Days',
            'standing_charge_rate': 'Standing Charge Rate (EUR/day)',
            'standing_charge_total': 'Standing Charge Total (EUR)',
            'discount': 'Discount (EUR)',
            'pso_levy': 'PSO Levy (EUR)',
            'subtotal_before_vat': 'Subtotal Before VAT (EUR)',
            'vat_rate_pct': 'VAT Rate (%)',
            'vat_amount': 'VAT Amount (EUR)',
            'total_this_period': 'Total This Period (EUR)',
            'export_units': 'Export Units (kWh)',
            'export_rate': 'Export Rate (EUR/kWh)',
            'export_credit': 'Export Credit (EUR)',
            'previous_balance': 'Previous Balance (EUR)',
            'payments_received': 'Payments Received (EUR)',
            'amount_due': 'Amount Due (EUR)',
            'tariff_type': 'Tariff Type',
            'eab_current': 'Current EAB (EUR)',
            'eab_new': 'New EAB (EUR)',
        }
        rows = []
        for key, value in data.items():
            if key in skip_meta:
                continue
            label = field_labels.get(key, key.replace('_', ' ').title())
            rows.append((label, value))

        pd.DataFrame(rows, columns=['Field', 'Value']).to_excel(
            writer, sheet_name='Bill Summary', index=False
        )

        # Sheet 2: Extraction Metadata
        metadata = [
            ('Extraction Method', bill.extraction_method),
            ('Confidence Score', f"{bill.confidence_score:.1%}"),
            ('Warnings', '; '.join(bill.warnings) if bill.warnings else 'None'),
            ('Supplier Detected', bill.supplier or 'Unknown'),
        ]
        pd.DataFrame(metadata, columns=['Field', 'Value']).to_excel(
            writer, sheet_name='Extraction Metadata', index=False
        )

    buffer.seek(0)
    return buffer


def show_overview(stats: dict, anomalies: list):
    """Show overview with key metrics (interval data)."""
    st.header("Overview")

    # Key metrics row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Import",
            f"{stats['total_import_kwh']:,.0f} kWh",
            help="Total energy imported from grid"
        )

    with col2:
        st.metric(
            "Daily Average",
            f"{stats['avg_daily_import_kwh']:.1f} kWh",
            help="Average daily consumption"
        )

    with col3:
        st.metric(
            "Baseload",
            f"{stats['baseload_kw']:.2f} kW",
            help="Average minimum consumption (always-on load)"
        )

    with col4:
        st.metric(
            "Peak Demand",
            f"{stats['peak_kw']:.1f} kW",
            help=f"Maximum demand on {stats['peak_time'].strftime('%d %b %Y %H:%M')}"
        )

    st.divider()

    # Second row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Data Period",
            f"{stats['date_range_days']} days",
            help=f"{stats['start_date'].strftime('%d %b %Y')} to {stats['end_date'].strftime('%d %b %Y')}"
        )

    with col2:
        st.metric("MPRN", stats['mprn'])

    with col3:
        if stats['has_solar']:
            st.metric(
                "Solar Export",
                f"{stats['total_export_kwh']:,.0f} kWh",
                help="Total energy exported to grid"
            )
        else:
            st.metric("Solar", "Not detected")

    with col4:
        weekday_weekend_diff = ((stats['weekend_avg_kwh'] / stats['weekday_avg_kwh']) - 1) * 100
        st.metric(
            "Weekend vs Weekday",
            f"{weekday_weekend_diff:+.0f}%",
            help=f"Weekday: {stats['weekday_avg_kwh']:.0f} kWh/day, Weekend: {stats['weekend_avg_kwh']:.0f} kWh/day"
        )

    # Quick alerts
    if anomalies:
        st.divider()
        st.subheader("⚠️ Quick Alerts")
        alert_anomalies = [a for a in anomalies
                          if a.get('category') == 'anomaly'
                          and a.get('severity') in ('warning', 'alert')]
        if alert_anomalies:
            cols = st.columns(min(len(alert_anomalies), 3))
            for i, a in enumerate(alert_anomalies[:3]):
                with cols[i]:
                    cost = a.get('annual_cost_eur', 0)
                    st.metric(
                        a['title'],
                        f"\u20ac{cost:,.0f}/yr" if cost > 0 else a.get('severity', '').title(),
                    )
        else:
            st.success("No significant issues detected.")


def show_overview_flexible(stats: dict, anomalies: list, granularity: DataGranularity):
    """Show overview with graceful degradation for non-interval data."""
    st.header("Overview")

    # Key metrics row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Import",
            f"{stats['total_import_kwh']:,.0f} kWh",
            help="Total energy imported from grid"
        )

    with col2:
        st.metric(
            "Daily Average",
            f"{stats['avg_daily_import_kwh']:.1f} kWh",
            help="Average daily consumption"
        )

    with col3:
        if stats.get('baseload_kw') is not None:
            st.metric(
                "Baseload",
                f"{stats['baseload_kw']:.2f} kW",
                help="Average minimum consumption (always-on load)"
            )
        else:
            st.metric(
                "Baseload",
                "N/A",
                help="Baseload calculation requires interval (30-min/hourly) data"
            )

    with col4:
        if stats.get('peak_kw') is not None and stats.get('peak_time') is not None:
            st.metric(
                "Peak Demand",
                f"{stats['peak_kw']:.1f} kW",
                help=f"Maximum demand on {stats['peak_time'].strftime('%d %b %Y %H:%M')}"
            )
        else:
            st.metric(
                "Peak Demand",
                "N/A",
                help="Peak demand calculation requires interval data"
            )

    st.divider()

    # Second row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Data Period",
            f"{stats['date_range_days']} days",
            help=(
                f"{stats['start_date'].strftime('%d %b %Y')} to {stats['end_date'].strftime('%d %b %Y')}"
                if stats.get('start_date') and stats.get('end_date') else "Unknown"
            )
        )

    with col2:
        st.metric("MPRN", stats.get('mprn', 'Unknown'))

    with col3:
        if stats.get('has_solar'):
            st.metric(
                "Solar Export",
                f"{stats['total_export_kwh']:,.0f} kWh",
                help="Total energy exported to grid"
            )
        else:
            st.metric("Solar", "Not detected")

    with col4:
        weekday_avg = stats.get('weekday_avg_kwh', 0)
        weekend_avg = stats.get('weekend_avg_kwh', 0)
        if weekday_avg and weekday_avg > 0:
            weekday_weekend_diff = ((weekend_avg / weekday_avg) - 1) * 100
            st.metric(
                "Weekend vs Weekday",
                f"{weekday_weekend_diff:+.0f}%",
                help=f"Weekday: {weekday_avg:.0f} kWh/day, Weekend: {weekend_avg:.0f} kWh/day"
            )
        else:
            st.metric("Weekend vs Weekday", "N/A")

    # Granularity notice
    granularity_labels = {
        DataGranularity.DAILY: "daily",
        DataGranularity.MONTHLY: "monthly",
    }
    gran_label = granularity_labels.get(granularity, str(granularity.value))
    st.info(f"This is **{gran_label}** data. Some metrics (baseload, peak demand, tariff breakdown) require interval-level (30-min/hourly) data.")

    # Quick alerts
    if anomalies:
        st.divider()
        st.subheader("⚠️ Quick Alerts")
        for a in anomalies[:3]:
            severity_icon = {'info': 'ℹ️', 'warning': '⚠️', 'alert': '🚨'}.get(a['severity'], '•')
            st.markdown(f"{severity_icon} **{a['title']}**: {a['description']}")


def show_heatmap(df: pd.DataFrame):
    """Show the usage heatmap."""
    st.header("Usage Heatmap")
    st.caption("Average consumption by hour and day of week")

    fig = create_heatmap(df)
    st.plotly_chart(fig, use_container_width=True)

    # Auto-generated interpretation from actual data
    _heatmap_interpretation(df)


def _heatmap_interpretation(df: pd.DataFrame):
    """Generate data-driven heatmap interpretation text."""
    if 'hour' not in df.columns or 'import_kwh' not in df.columns:
        return

    try:
        day_col = 'day_of_week' if 'day_of_week' in df.columns else None

        # Peak usage: hour with highest average consumption
        hourly_avg = df.groupby('hour')['import_kwh'].mean()
        peak_hour = int(hourly_avg.idxmax())
        peak_kwh = hourly_avg.max()

        # Night usage (23:00-06:00) vs day usage (07:00-22:00)
        night_hours = [23, 0, 1, 2, 3, 4, 5, 6]
        day_hours = list(range(7, 23))
        night_avg = hourly_avg.reindex(night_hours).mean()
        day_avg = hourly_avg.reindex(day_hours).mean()

        # Lowest usage hour
        min_hour = int(hourly_avg.idxmin())
        min_kwh = hourly_avg.min()

        parts = []
        parts.append(
            f"**Peak usage** is at **{peak_hour:02d}:00** "
            f"averaging **{peak_kwh:.2f} kWh** per interval."
        )
        parts.append(
            f"**Lowest usage** is at **{min_hour:02d}:00** "
            f"({min_kwh:.2f} kWh)."
        )

        if night_avg > 0:
            night_pct = (night_avg / day_avg * 100) if day_avg > 0 else 0
            if night_pct > 60:
                parts.append(
                    f"Night-time usage ({night_avg:.2f} kWh avg) is "
                    f"**{night_pct:.0f}% of daytime** — this is high and may "
                    "indicate always-on loads worth investigating."
                )
            elif night_pct > 30:
                parts.append(
                    f"Night-time usage ({night_avg:.2f} kWh avg) is "
                    f"**{night_pct:.0f}% of daytime** — moderate baseload."
                )
            else:
                parts.append(
                    f"Night-time usage ({night_avg:.2f} kWh avg) is "
                    f"**{night_pct:.0f}% of daytime** — low baseload, typical "
                    "for premises that shut down overnight."
                )

        # Weekday vs weekend if day_of_week available
        if day_col:
            weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
            weekends = ['Saturday', 'Sunday']
            wd_mask = df[day_col].isin(weekdays)
            we_mask = df[day_col].isin(weekends)
            if wd_mask.any() and we_mask.any():
                wd_avg = df.loc[wd_mask, 'import_kwh'].mean()
                we_avg = df.loc[we_mask, 'import_kwh'].mean()
                if we_avg > wd_avg * 1.1:
                    parts.append(
                        f"Weekend usage ({we_avg:.2f} kWh) is "
                        f"**higher than weekdays** ({wd_avg:.2f} kWh)."
                    )
                elif wd_avg > we_avg * 1.1:
                    parts.append(
                        f"Weekday usage ({wd_avg:.2f} kWh) is "
                        f"**higher than weekends** ({we_avg:.2f} kWh), "
                        "consistent with a commercial profile."
                    )

        st.info("**Heatmap insights:** " + " ".join(parts))
    except Exception:
        # Fallback to generic guidance
        st.info(
            "**Reading the heatmap:** Darker colors indicate higher consumption. "
            "Look for unexpected patterns like high usage at 3am on weekends."
        )


def show_charts(df: pd.DataFrame, stats: dict, anomalies: list = None):
    """Show various analysis charts (interval data)."""
    st.header("Analysis Charts")

    # Daily profile
    st.subheader("📊 Daily Load Profile")
    fig_profile = create_daily_profile(df, anomalies=anomalies)
    st.plotly_chart(fig_profile, use_container_width=True)

    # Daily trend (90 days)
    st.subheader("📈 Daily Trend")
    fig_daily = create_daily_trend(df, last_n_days=90, anomalies=anomalies)
    st.plotly_chart(fig_daily, use_container_width=True)

    # Two columns for tariff and monthly
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("⏰ Tariff Breakdown")
        fig_tariff = create_tariff_breakdown(df)
        st.plotly_chart(fig_tariff, use_container_width=True)

    with col2:
        st.subheader("📅 Monthly Trend")
        fig_monthly = create_monthly_trend(df, anomalies=anomalies)
        st.plotly_chart(fig_monthly, use_container_width=True)

    # Solar comparison if available
    if stats['has_solar']:
        st.subheader("☀️ Import vs Export (Solar)")
        fig_solar = create_import_export_comparison(df)
        st.plotly_chart(fig_solar, use_container_width=True)

    # Baseload analysis
    st.subheader("🔌 Baseload Analysis")
    fig_baseload = create_baseload_chart(df, anomalies=anomalies)
    st.plotly_chart(fig_baseload, use_container_width=True)


def show_charts_flexible(df: pd.DataFrame, stats: dict, granularity: DataGranularity):
    """Show charts with graceful degradation based on granularity."""
    st.header("Analysis Charts")

    if granularity == DataGranularity.DAILY:
        # Daily trend
        if 'date' in df.columns:
            st.subheader("📈 Daily Consumption Trend")
            fig_daily = create_daily_trend(df, last_n_days=len(df))
            st.plotly_chart(fig_daily, use_container_width=True)

        # Monthly trend
        if 'year_month' in df.columns:
            st.subheader("📅 Monthly Trend")
            fig_monthly = create_monthly_trend(df)
            st.plotly_chart(fig_monthly, use_container_width=True)

    elif granularity == DataGranularity.MONTHLY:
        # Monthly trend only
        if 'year_month' in df.columns:
            st.subheader("📅 Monthly Trend")
            fig_monthly = create_monthly_trend(df)
            st.plotly_chart(fig_monthly, use_container_width=True)
        else:
            st.info("Not enough data to generate charts at monthly granularity.")

    else:
        # Unknown granularity — try monthly trend
        if 'year_month' in df.columns:
            st.subheader("📅 Monthly Trend")
            fig_monthly = create_monthly_trend(df)
            st.plotly_chart(fig_monthly, use_container_width=True)

    # Note about unavailable charts
    if not granularity.is_interval:
        st.info("Load profile, tariff breakdown, heatmap, and baseload charts require interval-level (30-min/hourly) data.")


def _render_anomaly_cards(anomalies: list):
    """Render anomaly cards with severity-colored borders and cost display."""
    severity_order = {'alert': 0, 'warning': 1, 'info': 2}
    severity_colors = {'info': '#3b82f6', 'warning': '#f59e0b', 'alert': '#ef4444'}
    severity_icons = {'info': 'ℹ️', 'warning': '⚠️', 'alert': '🚨'}

    sorted_anomalies = sorted(
        anomalies,
        key=lambda a: severity_order.get(a.get('severity', 'info'), 3)
    )

    for a in sorted_anomalies:
        sev = a.get('severity', 'info')
        color = severity_colors.get(sev, '#3b82f6')
        icon = severity_icons.get(sev, '•')
        cost = a.get('annual_cost_eur', 0)
        recommendation = a.get('recommendation', '')

        cost_html = ''
        if cost > 1:
            cost_html = (
                '<div style="text-align: right; padding-left: 1.5rem; min-width: 100px;">'
                f'<div style="color: {color}; font-family: \'JetBrains Mono\', monospace; '
                f'font-size: 1.3rem; font-weight: 700;">\u20ac{cost:,.0f}</div>'
                '<div style="color: #64748b; font-size: 0.75rem;">per year</div>'
                '</div>'
            )

        rec_html = ''
        if recommendation:
            rec_html = (
                '<div style="color: #cbd5e1; font-size: 0.85rem; font-style: italic;">'
                f'{recommendation}</div>'
            )

        card_html = (
            f'<div style="padding: 1rem 1.2rem; border-left: 4px solid {color}; '
            f'background: #1e2433; border-radius: 0 8px 8px 0; margin-bottom: 0.75rem;">'
            f'<div style="display: flex; justify-content: space-between; align-items: flex-start;">'
            f'<div style="flex: 1;">'
            f'<div style="color: #ffffff; font-weight: 600; font-size: 1rem; margin-bottom: 0.3rem;">'
            f'{icon} {a["title"]}</div>'
            f'<div style="color: #94a3b8; font-size: 0.9rem; margin-bottom: 0.5rem;">'
            f'{a["description"]}</div>'
            f'{rec_html}'
            f'</div>{cost_html}</div></div>'
        )

        st.markdown(card_html, unsafe_allow_html=True)


def show_insights(df: pd.DataFrame, stats: dict, anomalies: list):
    """Show anomalies and insights (interval data)."""
    st.header("Insights & Anomalies")

    if not anomalies:
        st.success("✓ No significant anomalies detected in the consumption pattern.")
    else:
        # Cost impact headline row
        total_waste = sum(a.get('annual_cost_eur', 0) for a in anomalies if a.get('category') == 'anomaly')
        total_savings = sum(a.get('annual_cost_eur', 0) for a in anomalies if a.get('category') == 'insight')
        severity_counts = {}
        for a in anomalies:
            sev = a.get('severity', 'info')
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        severity_parts = []
        for sev in ['alert', 'warning', 'info']:
            if sev in severity_counts:
                severity_parts.append(f"{severity_counts[sev]} {sev}")
        severity_summary = ', '.join(severity_parts)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Estimated Annual Waste", f"\u20ac{total_waste:,.0f}")
        with col2:
            st.metric("Potential Savings", f"\u20ac{total_savings:,.0f}")
        with col3:
            st.metric("Issues Found", len(anomalies), delta=severity_summary, delta_color="off")

        st.divider()

        # Anomaly cards sorted by severity
        _render_anomaly_cards(anomalies)

    # Tariff optimization
    st.divider()
    st.subheader("💰 Tariff Optimization")

    night_pct = stats['tariff_night_kwh'] / stats['total_import_kwh'] * 100
    peak_pct = stats['tariff_peak_kwh'] / stats['total_import_kwh'] * 100

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Night Usage", f"{night_pct:.1f}%")
        if night_pct < 30:
            st.caption("Consider shifting loads to night hours (23:00-08:00) for cheaper rates.")
        else:
            st.caption("✓ Good use of night-rate electricity.")

    with col2:
        st.metric("Peak Usage", f"{peak_pct:.1f}%")
        if peak_pct > 15:
            st.caption("⚠️ High peak usage (17:00-19:00). Consider shifting to avoid highest rates.")
        else:
            st.caption("✓ Peak period usage is reasonable.")


def show_insights_flexible(df: pd.DataFrame, stats: dict, anomalies: list, granularity: DataGranularity):
    """Show insights with graceful degradation."""
    st.header("Insights & Anomalies")

    if not anomalies:
        st.success("✓ No significant anomalies detected in the consumption pattern.")
    else:
        # Cost impact headline (if cost data available)
        has_costs = any(a.get('annual_cost_eur', 0) > 0 for a in anomalies)
        if has_costs:
            total_waste = sum(a.get('annual_cost_eur', 0) for a in anomalies if a.get('category') == 'anomaly')
            total_savings = sum(a.get('annual_cost_eur', 0) for a in anomalies if a.get('category') == 'insight')
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Estimated Annual Waste", f"\u20ac{total_waste:,.0f}")
            with col2:
                st.metric("Potential Savings", f"\u20ac{total_savings:,.0f}")
            with col3:
                st.metric("Issues Found", len(anomalies))
            st.divider()

        # Anomaly cards sorted by severity
        _render_anomaly_cards(anomalies)

    # Tariff optimization only for interval data
    if stats.get('tariff_night_kwh') is not None and stats.get('tariff_peak_kwh') is not None:
        st.divider()
        st.subheader("💰 Tariff Optimization")

        total = stats['total_import_kwh']
        if total > 0:
            night_pct = stats['tariff_night_kwh'] / total * 100
            peak_pct = stats['tariff_peak_kwh'] / total * 100

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Night Usage", f"{night_pct:.1f}%")
                if night_pct < 30:
                    st.caption("Consider shifting loads to night hours (23:00-08:00) for cheaper rates.")
                else:
                    st.caption("✓ Good use of night-rate electricity.")

            with col2:
                st.metric("Peak Usage", f"{peak_pct:.1f}%")
                if peak_pct > 15:
                    st.caption("⚠️ High peak usage (17:00-19:00). Consider shifting to avoid highest rates.")
                else:
                    st.caption("✓ Peak period usage is reasonable.")
    else:
        st.info("Tariff optimization analysis requires interval-level (30-min/hourly) data to classify usage by time-of-use period.")


def show_export(df: pd.DataFrame, stats: dict):
    """Show export options (interval data)."""
    st.header("Export Data")

    st.markdown("Select what to include in your Excel export:")

    col1, col2 = st.columns(2)

    with col1:
        include_summary = st.checkbox("Summary Statistics", value=True)
        include_hourly = st.checkbox("Hourly Averages", value=True)
        include_daily = st.checkbox("Daily Totals", value=True)

    with col2:
        include_monthly = st.checkbox("Monthly Totals", value=True)
        include_tariff = st.checkbox("Tariff Breakdown", value=True)
        include_raw = st.checkbox("Raw 30-min Data", value=False,
                                  help="Warning: This can be a large dataset")

    st.markdown("")

    if st.button("📥 Generate Excel Export", type="primary"):
        excel_buffer = generate_excel_export(
            df, stats,
            include_summary=include_summary,
            include_hourly=include_hourly,
            include_daily=include_daily,
            include_monthly=include_monthly,
            include_tariff=include_tariff,
            include_raw=include_raw
        )

        filename = f"energy_analysis_{stats['mprn']}_{datetime.now().strftime('%Y%m%d')}.xlsx"

        st.download_button(
            label="⬇️ Download Excel File",
            data=excel_buffer.getvalue(),
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    st.divider()
    st.subheader("🖼️ Chart Export")
    st.caption("Right-click on any chart and select 'Download plot as PNG' to save individual charts.")


def show_bill_verification(hdf_df: pd.DataFrame, v: VerificationResult):
    """Display the Bill Verification tab content."""
    st.header("Bill Verification")
    st.caption("Cross-referencing meter readings against billed amounts")

    # --- Warnings ---
    for issue in v.issues:
        st.warning(issue)

    # --- 1. Match Status ---
    st.subheader("Match Status")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("MPRN", v.hdf_mprn)
    with col2:
        st.metric("Data Coverage", f"{v.overlap_pct:.0f}%")
    with col3:
        st.metric("Billing Days", f"{v.overlap_days}/{v.billing_days}")

    if v.bill_start and v.bill_end:
        st.caption(
            f"Bill period: {v.bill_start.strftime('%d %b %Y')} — "
            f"{v.bill_end.strftime('%d %b %Y')}"
        )

    st.divider()

    # --- 2. Consumption Comparison ---
    st.subheader("Consumption Comparison")
    st.caption("Meter readings vs billed consumption by tariff period")

    deltas = get_consumption_deltas(v)
    delta_df = pd.DataFrame(deltas)

    # Style: highlight significant differences
    st.dataframe(
        delta_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            'Period': st.column_config.TextColumn(width="small"),
            'Meter (kWh)': st.column_config.NumberColumn(format="%.1f"),
            'Bill (kWh)': st.column_config.NumberColumn(format="%.1f"),
            'Delta (kWh)': st.column_config.NumberColumn(format="%+.1f"),
            'Delta (%)': st.column_config.NumberColumn(format="%+.1f%%"),
        },
    )

    # Consumption summary metrics
    if v.hdf_total_kwh and v.bill_total_kwh:
        delta_kwh = v.bill_total_kwh - v.hdf_total_kwh
        delta_pct = (delta_kwh / v.hdf_total_kwh) * 100 if v.hdf_total_kwh else 0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Meter Total", f"{v.hdf_total_kwh:,.1f} kWh")
        with col2:
            st.metric("Bill Total", f"{v.bill_total_kwh:,.1f} kWh")
        with col3:
            status = "within tolerance" if abs(delta_pct) <= 5 else "DISCREPANCY"
            st.metric(
                "Difference",
                f"{delta_kwh:+,.1f} kWh",
                delta=f"{delta_pct:+.1f}% — {status}",
                delta_color="off" if abs(delta_pct) <= 5 else "inverse",
            )

    # Consumption bar chart
    if v.bill_day_kwh is not None or v.bill_night_kwh is not None:
        fig = go.Figure()

        periods = ['Day', 'Night', 'Peak']
        meter_vals = [v.hdf_day_kwh, v.hdf_night_kwh, v.hdf_peak_kwh]
        bill_vals = [v.bill_day_kwh, v.bill_night_kwh, v.bill_peak_kwh]

        fig.add_trace(go.Bar(
            x=periods,
            y=meter_vals,
            name='Meter (HDF)',
            marker_color='#4ade80',
        ))
        fig.add_trace(go.Bar(
            x=periods,
            y=[bv if bv is not None else 0 for bv in bill_vals],
            name='Bill',
            marker_color='#3b82f6',
        ))

        fig.update_layout(
            barmode='group',
            xaxis_title="Tariff Period",
            yaxis_title="Consumption (kWh)",
            template="plotly_dark",
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(family="DM Sans", color="#e2e8f0"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # --- 3. Cost Verification ---
    st.subheader("Cost Verification")
    st.caption("Meter consumption x bill rates vs bill stated cost")

    cost_rows = []
    if v.expected_cost_day is not None:
        cost_rows.append({
            'Component': 'Day Energy',
            'Meter kWh': v.hdf_day_kwh,
            'Bill Rate': v.bill_day_rate,
            'Expected Cost': v.expected_cost_day,
        })
    if v.expected_cost_night is not None:
        cost_rows.append({
            'Component': 'Night Energy',
            'Meter kWh': v.hdf_night_kwh,
            'Bill Rate': v.bill_night_rate,
            'Expected Cost': v.expected_cost_night,
        })
    if v.expected_cost_peak is not None:
        cost_rows.append({
            'Component': 'Peak Energy',
            'Meter kWh': v.hdf_peak_kwh,
            'Bill Rate': v.bill_peak_rate,
            'Expected Cost': v.expected_cost_peak,
        })

    if cost_rows:
        cost_df = pd.DataFrame(cost_rows)
        st.dataframe(
            cost_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                'Component': st.column_config.TextColumn(width="small"),
                'Meter kWh': st.column_config.NumberColumn(format="%.1f"),
                'Bill Rate': st.column_config.NumberColumn(format="%.4f"),
                'Expected Cost': st.column_config.NumberColumn(format="%.2f"),
            },
        )

    if v.expected_cost_total is not None:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(
                "Expected Energy Cost",
                f"\u20ac{v.expected_cost_total:,.2f}",
            )
        with col2:
            if v.bill_cost_total is not None:
                st.metric("Bill Total", f"\u20ac{v.bill_cost_total:,.2f}")
            else:
                st.metric("Bill Total", "\u2014")
        with col3:
            if v.bill_cost_total is not None and v.expected_cost_total:
                cost_delta = v.bill_cost_total - v.expected_cost_total
                st.metric(
                    "Difference",
                    f"\u20ac{cost_delta:+,.2f}",
                    delta="includes standing charge, PSO, VAT" if cost_delta > 0 else None,
                    delta_color="off",
                )

    st.divider()

    # --- 4. Rate Comparison ---
    st.subheader("Rate Comparison")
    st.caption("Bill rates vs provider preset rates")

    bill = st.session_state.get("_verification_bill")
    supplier = bill.supplier if bill else None
    rate_rows = get_rate_comparison(v, provider=supplier)
    rate_df = pd.DataFrame(rate_rows)

    st.dataframe(
        rate_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            'Period': st.column_config.TextColumn(width="small"),
            'Bill Rate (EUR/kWh)': st.column_config.NumberColumn(format="%.4f"),
            'Preset Rate (EUR/kWh)': st.column_config.NumberColumn(format="%.4f"),
        },
    )

    st.divider()

    # --- 5. Export / Solar Check ---
    if v.hdf_export_kwh and v.hdf_export_kwh > 0:
        st.subheader("Export / Solar Check")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Meter Export", f"{v.hdf_export_kwh:,.1f} kWh")
        with col2:
            if v.bill_export_units is not None:
                st.metric("Bill Export", f"{v.bill_export_units:,.1f} kWh")
            else:
                st.metric("Bill Export", "\u2014")

        if v.bill_export_credit is not None:
            from hdf_parser import CEG_RATE_EUR
            expected_credit = v.hdf_export_kwh * CEG_RATE_EUR
            st.caption(
                f"Expected export credit at CEG rate (\u20ac{CEG_RATE_EUR}/kWh): "
                f"\u20ac{expected_credit:,.2f} | Bill states: \u20ac{v.bill_export_credit:,.2f}"
            )

        st.divider()

    # --- 6. Standing Charge Check ---
    if v.bill_standing_days is not None:
        st.subheader("Standing Charge Check")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Bill Standing Days", v.bill_standing_days)
        with col2:
            st.metric("Billing Period Days", v.billing_days)

        if v.bill_standing_days != v.billing_days:
            st.warning(
                f"Standing charge days ({v.bill_standing_days}) "
                f"differs from billing period length ({v.billing_days} days)."
            )
        else:
            st.success("Standing charge days match billing period length.")


def show_export_flexible(df: pd.DataFrame, stats: dict, granularity: DataGranularity):
    """Show export options with graceful degradation."""
    st.header("Export Data")

    st.markdown("Select what to include in your Excel export:")

    col1, col2 = st.columns(2)

    with col1:
        include_summary = st.checkbox("Summary Statistics", value=True, key="exp_summary")
        include_daily = st.checkbox("Daily Totals", value=True, key="exp_daily") if granularity.has_daily_detail else False

    with col2:
        include_monthly = st.checkbox("Monthly Totals", value=True, key="exp_monthly")
        include_raw = st.checkbox("Raw Data", value=False, key="exp_raw",
                                  help="Include all cleaned data rows")

    st.markdown("")

    if st.button("📥 Generate Excel Export", type="primary", key="exp_generate"):
        excel_buffer = generate_excel_export_flexible(
            df, stats, granularity,
            include_summary=include_summary,
            include_daily=include_daily,
            include_monthly=include_monthly,
            include_raw=include_raw,
        )

        mprn = stats.get('mprn', 'unknown')
        filename = f"energy_analysis_{mprn}_{datetime.now().strftime('%Y%m%d')}.xlsx"

        st.download_button(
            label="⬇️ Download Excel File",
            data=excel_buffer.getvalue(),
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="exp_download",
        )

    st.divider()
    st.subheader("🖼️ Chart Export")
    st.caption("Right-click on any chart and select 'Download plot as PNG' to save individual charts.")


def generate_excel_export(
    df: pd.DataFrame,
    stats: dict,
    include_summary: bool = True,
    include_hourly: bool = True,
    include_daily: bool = True,
    include_monthly: bool = True,
    include_tariff: bool = True,
    include_raw: bool = False
) -> io.BytesIO:
    """Generate an Excel file with selected data (interval data)."""
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        if include_summary:
            summary_data = {
                'Metric': [
                    'MPRN', 'Start Date', 'End Date', 'Days of Data',
                    'Total Import (kWh)', 'Total Export (kWh)', 'Net Import (kWh)',
                    'Daily Average (kWh)', 'Baseload (kW)', 'Peak Demand (kW)',
                    'Peak Time', 'Weekday Avg (kWh/day)', 'Weekend Avg (kWh/day)',
                ],
                'Value': [
                    stats['mprn'],
                    stats['start_date'].strftime('%Y-%m-%d'),
                    stats['end_date'].strftime('%Y-%m-%d'),
                    stats['date_range_days'],
                    round(stats['total_import_kwh'], 1),
                    round(stats['total_export_kwh'], 1),
                    round(stats['net_import_kwh'], 1),
                    round(stats['avg_daily_import_kwh'], 1),
                    round(stats['baseload_kw'], 2),
                    round(stats['peak_kw'], 1),
                    stats['peak_time'].strftime('%Y-%m-%d %H:%M'),
                    round(stats['weekday_avg_kwh'], 1),
                    round(stats['weekend_avg_kwh'], 1),
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)

        if include_hourly:
            hourly = df.groupby('hour').agg({
                'import_kwh': 'mean',
                'export_kwh': 'mean'
            }).reset_index()
            hourly.columns = ['Hour', 'Avg Import (kWh)', 'Avg Export (kWh)']
            hourly['Avg Import (kW)'] = hourly['Avg Import (kWh)'] * 2
            hourly.to_excel(writer, sheet_name='Hourly Averages', index=False)

        if include_daily:
            daily = df.groupby('date').agg({
                'import_kwh': 'sum',
                'export_kwh': 'sum'
            }).reset_index()
            daily.columns = ['Date', 'Import (kWh)', 'Export (kWh)']
            daily.to_excel(writer, sheet_name='Daily Totals', index=False)

        if include_monthly:
            monthly = df.groupby('year_month').agg({
                'import_kwh': 'sum',
                'export_kwh': 'sum'
            }).reset_index()
            monthly.columns = ['Month', 'Import (kWh)', 'Export (kWh)']
            monthly.to_excel(writer, sheet_name='Monthly Totals', index=False)

        if include_tariff:
            tariff = df.groupby('tariff_period')['import_kwh'].sum().reset_index()
            tariff.columns = ['Tariff Period', 'Total (kWh)']
            tariff['Percentage'] = tariff['Total (kWh)'] / tariff['Total (kWh)'].sum() * 100
            tariff.to_excel(writer, sheet_name='Tariff Breakdown', index=False)

        if include_raw:
            export_df = df[['datetime', 'import_kwh', 'export_kwh', 'tariff_period']].copy()
            export_df['datetime'] = export_df['datetime'].dt.tz_localize(None)
            export_df.to_excel(writer, sheet_name='Raw Data', index=False)

    buffer.seek(0)
    return buffer


def generate_excel_export_flexible(
    df: pd.DataFrame,
    stats: dict,
    granularity: DataGranularity,
    include_summary: bool = True,
    include_daily: bool = True,
    include_monthly: bool = True,
    include_raw: bool = False,
) -> io.BytesIO:
    """Generate an Excel file with graceful degradation for non-interval data."""
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        if include_summary:
            rows = [
                ('MPRN', stats.get('mprn', 'Unknown')),
                ('Days of Data', stats.get('date_range_days', 'N/A')),
                ('Total Import (kWh)', round(stats['total_import_kwh'], 1)),
                ('Total Export (kWh)', round(stats['total_export_kwh'], 1)),
                ('Net Import (kWh)', round(stats['net_import_kwh'], 1)),
                ('Daily Average (kWh)', round(stats['avg_daily_import_kwh'], 1)),
            ]
            if stats.get('start_date'):
                rows.insert(1, ('Start Date', stats['start_date'].strftime('%Y-%m-%d')))
            if stats.get('end_date'):
                rows.insert(2, ('End Date', stats['end_date'].strftime('%Y-%m-%d')))
            if stats.get('baseload_kw') is not None:
                rows.append(('Baseload (kW)', round(stats['baseload_kw'], 2)))
            if stats.get('peak_kw') is not None:
                rows.append(('Peak Demand (kW)', round(stats['peak_kw'], 1)))
            if stats.get('weekday_avg_kwh'):
                rows.append(('Weekday Avg (kWh/day)', round(stats['weekday_avg_kwh'], 1)))
            if stats.get('weekend_avg_kwh'):
                rows.append(('Weekend Avg (kWh/day)', round(stats['weekend_avg_kwh'], 1)))

            summary_df = pd.DataFrame(rows, columns=['Metric', 'Value'])
            summary_df.to_excel(writer, sheet_name='Summary', index=False)

        if include_daily and 'date' in df.columns:
            daily = df.groupby('date').agg({
                'import_kwh': 'sum',
                'export_kwh': 'sum'
            }).reset_index()
            daily.columns = ['Date', 'Import (kWh)', 'Export (kWh)']
            daily.to_excel(writer, sheet_name='Daily Totals', index=False)

        if include_monthly and 'year_month' in df.columns:
            monthly = df.groupby('year_month').agg({
                'import_kwh': 'sum',
                'export_kwh': 'sum'
            }).reset_index()
            monthly.columns = ['Month', 'Import (kWh)', 'Export (kWh)']
            monthly.to_excel(writer, sheet_name='Monthly Totals', index=False)

        if include_raw:
            export_cols = [c for c in ['datetime', 'import_kwh', 'export_kwh', 'mprn'] if c in df.columns]
            export_df = df[export_cols].copy()
            if 'datetime' in export_df.columns:
                try:
                    export_df['datetime'] = export_df['datetime'].dt.tz_localize(None)
                except TypeError:
                    pass  # Already tz-naive
            export_df.to_excel(writer, sheet_name='Raw Data', index=False)

    buffer.seek(0)
    return buffer


# ---------------------------------------------------------------------------
# Multi-bill comparison
# ---------------------------------------------------------------------------


def _parse_bill_date(date_str):
    """Try to parse a date string from bill extraction. Returns date or None."""
    if not date_str:
        return None
    from datetime import datetime as dt
    formats = [
        "%d/%m/%Y", "%d %b %Y", "%d %B %Y", "%d.%m.%Y",
        "%Y-%m-%d", "%d-%m-%Y",
    ]
    for fmt in formats:
        try:
            return dt.strptime(date_str.strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _bill_label(row) -> str:
    """Generate a short label for a bill in comparison charts."""
    if row.get('period_start') is not None and pd.notna(row['period_start']):
        return row['period_start'].strftime('%b %Y')
    if row.get('bill_date') and row['bill_date']:
        parsed = _parse_bill_date(row['bill_date'])
        if parsed:
            return parsed.strftime('%b %Y')
        return str(row['bill_date'])[:10]
    return str(row['filename'])[:20]


def _handle_bill_comparison(uploaded_files):
    """Handle multiple PDF bills for side-by-side comparison."""
    file_data = [(f.getvalue(), f.name) for f in uploaded_files]
    content_hash = hashlib.md5(
        b"".join(content for content, _ in file_data)
    ).hexdigest()
    cache_key = f"comparison_{content_hash}"

    if st.session_state.get("_comparison_cache_key") != cache_key:
        bills = []
        errors = []
        progress = st.progress(0, text="Extracting bills...")
        for i, (content, filename) in enumerate(file_data):
            progress.progress(
                (i + 1) / len(file_data),
                text=f"Extracting {filename}...",
            )
            try:
                if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    pipeline_result = extract_bill_from_image(content)
                else:
                    pipeline_result = extract_bill_pipeline(content)
                bill = generic_to_legacy(pipeline_result.bill)
                bills.append((bill, filename))
            except Exception as e:
                errors.append((filename, str(e)))
        progress.empty()
        st.session_state._comparison_cache_key = cache_key
        st.session_state._comparison_bills = bills
        st.session_state._comparison_errors = errors

    bills = st.session_state._comparison_bills
    errors = st.session_state.get("_comparison_errors", [])

    if errors:
        for filename, err in errors:
            st.warning(f"Failed to extract **{filename}**: {err}")

    if len(bills) < 2:
        st.error("Need at least 2 successfully extracted bills for comparison.")
        return

    show_bill_comparison(bills)


def show_bill_comparison(bills):
    """Display multi-bill comparison view with tabs."""
    st.subheader(f"Bill Comparison — {len(bills)} bills")

    # Build comparison DataFrame
    rows = []
    for bill, filename in bills:
        period_start = _parse_bill_date(bill.billing_period_start)
        period_end = _parse_bill_date(bill.billing_period_end)
        bill_date_parsed = _parse_bill_date(bill.bill_date)
        sort_date = period_start or bill_date_parsed

        rows.append({
            'filename': filename,
            'supplier': bill.supplier or 'Unknown',
            'mprn': bill.mprn or '',
            'bill_date': bill.bill_date or '',
            'billing_period': (
                f"{bill.billing_period_start} — {bill.billing_period_end}"
                if bill.billing_period_start and bill.billing_period_end
                else ''
            ),
            'sort_date': sort_date,
            'period_start': period_start,
            'period_end': period_end,
            'total_kwh': bill.total_units_kwh,
            'day_kwh': bill.day_units_kwh,
            'night_kwh': bill.night_units_kwh,
            'peak_kwh': bill.peak_units_kwh,
            'day_rate': bill.day_rate,
            'night_rate': bill.night_rate,
            'peak_rate': bill.peak_rate,
            'standing_charge': bill.standing_charge_total,
            'subtotal': bill.subtotal_before_vat,
            'vat': bill.vat_amount,
            'total_cost': bill.total_this_period,
            'amount_due': bill.amount_due,
            'confidence': bill.confidence_score,
        })

    df = pd.DataFrame(rows)

    # Sort by date if available
    if df['sort_date'].notna().any():
        df = df.sort_values('sort_date').reset_index(drop=True)

    # Generate chart labels
    df['label'] = df.apply(_bill_label, axis=1)

    # Deduplicate labels by appending index when needed
    label_counts = df['label'].value_counts()
    if (label_counts > 1).any():
        seen = {}
        new_labels = []
        for label in df['label']:
            if label_counts[label] > 1:
                idx = seen.get(label, 0) + 1
                seen[label] = idx
                new_labels.append(f"{label} ({idx})")
            else:
                new_labels.append(label)
        df['label'] = new_labels

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Summary",
        "Cost Trends",
        "Consumption",
        "Rate Analysis",
        "Export",
    ])

    with tab1:
        _comparison_summary(df)
    with tab2:
        _comparison_cost_trends(df)
    with tab3:
        _comparison_consumption(df)
    with tab4:
        _comparison_rates(df)
    with tab5:
        _comparison_export(df, bills)


def _comparison_summary(df: pd.DataFrame):
    """Show summary table and key aggregate metrics."""
    st.markdown("### Side-by-Side Comparison")

    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        total_cost = df['total_cost'].sum()
        st.metric(
            "Total Cost",
            f"€{total_cost:,.2f}" if pd.notna(total_cost) and total_cost > 0 else "—",
        )
    with col2:
        total_kwh = df['total_kwh'].sum()
        st.metric(
            "Total kWh",
            f"{total_kwh:,.0f}" if pd.notna(total_kwh) and total_kwh > 0 else "—",
        )
    with col3:
        valid_costs = df['total_cost'].dropna()
        avg_cost = valid_costs.mean() if len(valid_costs) > 0 else None
        st.metric(
            "Avg Cost/Bill",
            f"€{avg_cost:,.2f}" if avg_cost else "—",
        )
    with col4:
        if (
            df['total_kwh'].notna().any()
            and df['total_cost'].notna().any()
            and df['total_kwh'].sum() > 0
        ):
            avg_rate = df['total_cost'].sum() / df['total_kwh'].sum()
            st.metric("Avg €/kWh", f"€{avg_rate:.4f}")
        else:
            st.metric("Avg €/kWh", "—")

    st.divider()

    # Display table
    display_cols = {
        'filename': 'File',
        'supplier': 'Supplier',
        'billing_period': 'Period',
        'total_kwh': 'Total kWh',
        'total_cost': 'Total (€)',
        'day_kwh': 'Day kWh',
        'night_kwh': 'Night kWh',
        'standing_charge': 'Standing (€)',
        'vat': 'VAT (€)',
        'confidence': 'Confidence',
    }

    available_cols = [c for c in display_cols if c in df.columns]
    display_df = df[available_cols].rename(
        columns={k: v for k, v in display_cols.items() if k in available_cols}
    )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            'Total kWh': st.column_config.NumberColumn(format="%.1f"),
            'Total (€)': st.column_config.NumberColumn(format="€%.2f"),
            'Day kWh': st.column_config.NumberColumn(format="%.1f"),
            'Night kWh': st.column_config.NumberColumn(format="%.1f"),
            'Standing (€)': st.column_config.NumberColumn(format="€%.2f"),
            'VAT (€)': st.column_config.NumberColumn(format="€%.2f"),
            'Confidence': st.column_config.NumberColumn(format="%.0%%"),
        },
    )


def _comparison_cost_trends(df: pd.DataFrame):
    """Show cost trend chart across bills."""
    st.markdown("### Cost Trends Over Time")

    labels = df['label'].tolist()
    has_cost = df['total_cost'].notna().any()

    if not has_cost:
        st.info("No cost data available in the extracted bills.")
        return

    fig = go.Figure()

    # Total cost
    fig.add_trace(go.Scatter(
        x=labels,
        y=df['total_cost'],
        mode='lines+markers',
        name='Total Cost',
        line=dict(color='#4ade80', width=3),
        marker=dict(size=10),
    ))

    # Subtotal
    if df['subtotal'].notna().any():
        fig.add_trace(go.Scatter(
            x=labels,
            y=df['subtotal'],
            mode='lines+markers',
            name='Subtotal (ex VAT)',
            line=dict(color='#3b82f6', width=2, dash='dot'),
            marker=dict(size=8),
        ))

    # Standing charge
    if df['standing_charge'].notna().any():
        fig.add_trace(go.Scatter(
            x=labels,
            y=df['standing_charge'],
            mode='lines+markers',
            name='Standing Charge',
            line=dict(color='#f59e0b', width=2, dash='dash'),
            marker=dict(size=8),
        ))

    fig.update_layout(
        xaxis_title="Billing Period",
        yaxis_title="Cost (€)",
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="DM Sans", color="#e2e8f0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )

    st.plotly_chart(fig, use_container_width=True)

    # Cost change summary
    valid = df.dropna(subset=['total_cost'])
    if len(valid) >= 2:
        first_cost = valid.iloc[0]['total_cost']
        last_cost = valid.iloc[-1]['total_cost']
        change = last_cost - first_cost
        change_pct = (change / first_cost * 100) if first_cost else 0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("First Bill", f"€{first_cost:,.2f}")
        with col2:
            st.metric("Latest Bill", f"€{last_cost:,.2f}")
        with col3:
            st.metric("Change", f"€{change:+,.2f}", delta=f"{change_pct:+.1f}%")


def _comparison_consumption(df: pd.DataFrame):
    """Show consumption trend charts."""
    st.markdown("### Consumption Trends")

    labels = df['label'].tolist()
    has_kwh = df['total_kwh'].notna().any()

    if not has_kwh:
        st.info("No consumption data available in the extracted bills.")
        return

    # Total consumption bar chart
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels,
        y=df['total_kwh'],
        name='Total kWh',
        marker_color='#4ade80',
        text=[f"{v:,.0f}" if pd.notna(v) else "" for v in df['total_kwh']],
        textposition='auto',
    ))
    fig.update_layout(
        xaxis_title="Billing Period",
        yaxis_title="Consumption (kWh)",
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="DM Sans", color="#e2e8f0"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Day/Night/Peak breakdown
    has_breakdown = (
        df['day_kwh'].notna().any()
        or df['night_kwh'].notna().any()
        or df['peak_kwh'].notna().any()
    )
    if has_breakdown:
        st.markdown("#### Day/Night/Peak Breakdown")

        fig2 = go.Figure()
        if df['day_kwh'].notna().any():
            fig2.add_trace(go.Bar(
                x=labels, y=df['day_kwh'],
                name='Day', marker_color='#f59e0b',
            ))
        if df['night_kwh'].notna().any():
            fig2.add_trace(go.Bar(
                x=labels, y=df['night_kwh'],
                name='Night', marker_color='#3b82f6',
            ))
        if df['peak_kwh'].notna().any():
            fig2.add_trace(go.Bar(
                x=labels, y=df['peak_kwh'],
                name='Peak', marker_color='#ef4444',
            ))

        fig2.update_layout(
            barmode='stack',
            xaxis_title="Billing Period",
            yaxis_title="Consumption (kWh)",
            template="plotly_dark",
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(family="DM Sans", color="#e2e8f0"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig2, use_container_width=True)

    # Consumption change summary
    valid = df.dropna(subset=['total_kwh'])
    if len(valid) >= 2:
        st.divider()
        first = valid.iloc[0]['total_kwh']
        last = valid.iloc[-1]['total_kwh']
        change = last - first
        change_pct = (change / first * 100) if first else 0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("First Bill", f"{first:,.0f} kWh")
        with col2:
            st.metric("Latest Bill", f"{last:,.0f} kWh")
        with col3:
            st.metric("Change", f"{change:+,.0f} kWh", delta=f"{change_pct:+.1f}%")


def _comparison_rates(df: pd.DataFrame):
    """Show rate comparison across bills."""
    st.markdown("### Rate Analysis")

    has_rates = (
        df['day_rate'].notna().any()
        or df['night_rate'].notna().any()
        or df['peak_rate'].notna().any()
    )

    if not has_rates:
        st.info("No unit rate data available in the extracted bills.")
        return

    labels = df['label'].tolist()

    fig = go.Figure()

    if df['day_rate'].notna().any():
        fig.add_trace(go.Scatter(
            x=labels, y=df['day_rate'],
            mode='lines+markers', name='Day Rate',
            line=dict(color='#f59e0b', width=2),
            marker=dict(size=8),
        ))

    if df['night_rate'].notna().any():
        fig.add_trace(go.Scatter(
            x=labels, y=df['night_rate'],
            mode='lines+markers', name='Night Rate',
            line=dict(color='#3b82f6', width=2),
            marker=dict(size=8),
        ))

    if df['peak_rate'].notna().any():
        fig.add_trace(go.Scatter(
            x=labels, y=df['peak_rate'],
            mode='lines+markers', name='Peak Rate',
            line=dict(color='#ef4444', width=2),
            marker=dict(size=8),
        ))

    fig.update_layout(
        xaxis_title="Billing Period",
        yaxis_title="Rate (€/kWh)",
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="DM Sans", color="#e2e8f0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )

    st.plotly_chart(fig, use_container_width=True)

    # Rate change table
    st.markdown("#### Rate Changes")
    rate_data = []
    for rate_name, rate_col in [('Day', 'day_rate'), ('Night', 'night_rate'), ('Peak', 'peak_rate')]:
        valid = df.dropna(subset=[rate_col])
        if len(valid) >= 2:
            first = valid.iloc[0][rate_col]
            last = valid.iloc[-1][rate_col]
            change = last - first
            change_pct = (change / first * 100) if first else 0
            rate_data.append({
                'Tariff': rate_name,
                'First Bill': f"€{first:.4f}",
                'Latest Bill': f"€{last:.4f}",
                'Change': f"€{change:+.4f}",
                'Change %': f"{change_pct:+.1f}%",
            })

    if rate_data:
        st.dataframe(pd.DataFrame(rate_data), hide_index=True, use_container_width=True)
    else:
        st.caption("Rate changes require at least 2 bills with rate data for the same tariff.")


def _comparison_export(df: pd.DataFrame, bills):
    """Export comparison data as Excel."""
    st.markdown("### Export Comparison Data")

    if st.button("Generate Comparison Excel", type="primary", key="comparison_export_btn"):
        buffer = _generate_comparison_excel(df, bills)
        st.download_button(
            label="Download Excel File",
            data=buffer.getvalue(),
            file_name=f"bill_comparison_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="comparison_download",
        )


def _generate_comparison_excel(df: pd.DataFrame, bills) -> io.BytesIO:
    """Generate Excel comparison workbook."""
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        # Summary sheet
        summary_cols = [
            'filename', 'supplier', 'mprn', 'bill_date', 'billing_period',
            'total_kwh', 'day_kwh', 'night_kwh', 'peak_kwh',
            'day_rate', 'night_rate', 'peak_rate',
            'standing_charge', 'subtotal', 'vat', 'total_cost', 'amount_due',
        ]
        summary_labels = {
            'filename': 'File', 'supplier': 'Supplier', 'mprn': 'MPRN',
            'bill_date': 'Bill Date', 'billing_period': 'Billing Period',
            'total_kwh': 'Total kWh', 'day_kwh': 'Day kWh',
            'night_kwh': 'Night kWh', 'peak_kwh': 'Peak kWh',
            'day_rate': 'Day Rate (€/kWh)', 'night_rate': 'Night Rate (€/kWh)',
            'peak_rate': 'Peak Rate (€/kWh)',
            'standing_charge': 'Standing Charge (€)', 'subtotal': 'Subtotal (€)',
            'vat': 'VAT (€)', 'total_cost': 'Total Cost (€)',
            'amount_due': 'Amount Due (€)',
        }

        available = [c for c in summary_cols if c in df.columns]
        export_df = df[available].rename(
            columns={k: v for k, v in summary_labels.items() if k in available}
        )
        export_df.to_excel(writer, sheet_name='Comparison', index=False)

        # Individual bill sheets
        for bill, filename in bills:
            bill_dict = asdict(bill)
            bill_rows = [
                (k.replace('_', ' ').title(), v)
                for k, v in bill_dict.items()
                if k not in {'extraction_method', 'confidence_score', 'warnings'}
            ]
            # Excel sheet name max 31 chars
            sheet_name = filename[:31].replace('/', '-').replace('\\', '-')
            pd.DataFrame(bill_rows, columns=['Field', 'Value']).to_excel(
                writer, sheet_name=sheet_name, index=False,
            )

    buffer.seek(0)
    return buffer


if __name__ == "__main__":
    main()
