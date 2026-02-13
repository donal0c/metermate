"""Energy Insight - Meter Analysis

Analyze ESB Networks HDF files, Excel spreadsheets, and CSV energy data
with heatmaps, trend charts, anomaly detection, and bill verification.
"""

import streamlit as st
import pandas as pd
import io
from pathlib import Path
from datetime import datetime, timedelta, date

from hdf_parser import (
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
    ColumnMapping,
    ParseResult,
    DataQualityReport,
)
from column_mapping import detect_columns, build_column_mapping, validate_mapping
from excel_parser import parse_excel_file, read_upload, get_sheet_names
from bill_parser import BillData, generic_to_legacy
from orchestrator import extract_bill_pipeline, extract_bill_from_image
from bill_verification import (
    validate_cross_reference,
    compute_verification,
    get_consumption_deltas,
    get_rate_comparison,
    VerificationResult,
)

from common.theme import apply_theme
from common.components import render_anomaly_cards
from common.session import (
    is_hdf_file,
    make_cache_key,
    parse_hdf_with_result,
)
import plotly.graph_objects as go

st.set_page_config(
    page_title="Meter Analysis - Energy Insight",
    page_icon="\U0001f4ca",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()


# =========================================================================
# Helper functions
# =========================================================================

def _load_logo():
    """Load logo from file if it exists."""
    logo_path = Path(__file__).parent.parent / "logo.png"
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


def _render_tariff_config():
    """Render tariff rate configuration as an in-page expandable section."""
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

    current_provider = st.session_state.tariff_provider
    with st.expander(f"Tariff Rates — {current_provider}", expanded=False):
        col_provider, col_day, col_night, col_peak = st.columns([2, 1, 1, 1])

        with col_provider:
            st.selectbox(
                "Electricity Provider",
                options=provider_names,
                index=provider_names.index(st.session_state.tariff_provider),
                key='_tariff_provider_widget',
                on_change=_on_provider_change,
            )

        with col_day:
            st.number_input(
                "Day (c/kWh)",
                min_value=0.0, max_value=100.0,
                step=0.5, format="%.2f",
                key='_tariff_day_widget',
                on_change=_on_rate_change,
            )
        with col_night:
            st.number_input(
                "Night (c/kWh)",
                min_value=0.0, max_value=100.0,
                step=0.5, format="%.2f",
                key='_tariff_night_widget',
                on_change=_on_rate_change,
            )
        with col_peak:
            st.number_input(
                "Peak (c/kWh)",
                min_value=0.0, max_value=100.0,
                step=0.5, format="%.2f",
                key='_tariff_peak_widget',
                on_change=_on_rate_change,
            )

        st.caption("Rates inc. VAT. Verify against client's bill.")


def _render_filter_bar(df: pd.DataFrame):
    """Render date range and load type filters as in-page pill buttons and toggle chips.

    Returns the filtered DataFrame.
    """
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

    # Initialise filter state
    if 'date_filter_period' not in st.session_state:
        st.session_state.date_filter_period = "All Data"

    # --- Date Range pill buttons ---
    period_labels = ["All Data", "Last 7d", "Last 30d", "Last 90d", "Custom"]
    period_map = {
        "All Data": "All Data",
        "Last 7d": "Last 7 Days",
        "Last 30d": "Last 30 Days",
        "Last 90d": "Last 90 Days",
        "Custom": "Custom Range",
    }
    # Reverse lookup for current state
    reverse_map = {v: k for k, v in period_map.items()}
    current_label = reverse_map.get(st.session_state.date_filter_period, "All Data")

    # Build pill button row with load type chips
    has_tariff = 'tariff_period' in df.columns

    # Use columns: date pills on left, load type chips on right
    if has_tariff:
        col_date, col_load = st.columns([3, 2])
    else:
        col_date, _ = st.columns([3, 2])

    with col_date:
        # Use segmented control for date range
        period_choice = st.segmented_control(
            "Date Range",
            options=period_labels,
            default=current_label,
            key="_date_filter_pills",
            label_visibility="collapsed",
        )
        if period_choice is None:
            period_choice = "All Data"
        st.session_state.date_filter_period = period_map.get(period_choice, "All Data")

    # Load type toggle chips
    if has_tariff:
        with col_load:
            available_periods = sorted(df['tariff_period'].unique())
            selected_periods = st.segmented_control(
                "Load Type",
                options=available_periods,
                default=available_periods,
                selection_mode="multi",
                key="_load_type_chips",
                label_visibility="collapsed",
            )

    # Compute date range from period choice
    period = st.session_state.date_filter_period
    start_date = data_min
    end_date = data_max

    if period == "Last 7 Days":
        start_date = data_max - timedelta(days=6)
    elif period == "Last 30 Days":
        start_date = data_max - timedelta(days=29)
    elif period == "Last 90 Days":
        start_date = data_max - timedelta(days=89)
    elif period == "Custom Range":
        col1, col2, _ = st.columns([1, 1, 3])
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
        st.caption(f"{start_date.strftime('%d %b %Y')} \u2014 {end_date.strftime('%d %b %Y')}")

    # Apply date filter
    filtered = df
    if period != "All Data":
        filtered = _apply_date_filter(filtered, start_date, end_date)

    # Apply load type filter
    if selected_periods is not None and 'tariff_period' in filtered.columns:
        if selected_periods:
            filtered = filtered[filtered['tariff_period'].isin(selected_periods)].copy()
        else:
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


# =========================================================================
# File handlers
# =========================================================================

def _handle_hdf_file(file_content: bytes, filename: str):
    """Handle HDF file upload — direct to analysis (existing flow)."""
    # Cache parsed result in session_state to avoid re-parsing on rerun
    hdf_key = f"hdf_{filename}_{len(file_content)}"
    if st.session_state.get("_hdf_cache_key") != hdf_key:
        try:
            with st.spinner("Parsing HDF file..."):
                result = parse_hdf_with_result(file_content, filename)
                st.session_state._hdf_cache_key = hdf_key
                st.session_state._hdf_cached_result = result
        except Exception as e:
            st.error(f"Error parsing file: {str(e)}")
            st.info("Please ensure this is a valid ESB Networks HDF file.")
            return

    result = st.session_state._hdf_cached_result
    full_df = result.df

    # In-page tariff config and filter bar
    _render_tariff_config()
    df = _render_filter_bar(full_df)

    if len(df) == 0:
        st.warning("No data matches the current filters. Adjust the date range or load type above.")
        return

    # Recompute stats and anomalies on the filtered data
    stats = get_summary_stats(df)
    tariff_rates = _get_tariff_rates()
    anomalies = detect_anomalies(df, tariff_rates=tariff_rates)

    st.success(f"\u2713 Showing {len(df):,} readings from {stats['start_date'].strftime('%d %b %Y')} to {stats['end_date'].strftime('%d %b %Y')}")

    # Standard analysis tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "\U0001f4ca Overview",
        "\U0001f525 Heatmap",
        "\U0001f4c8 Charts",
        "\u26a0\ufe0f Insights",
        "\U0001f4e5 Export"
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

    # --- Bill Verification section (main content, below tabs) ---
    st.divider()
    _render_bill_verification_section(full_df)


def _get_extracted_bills_from_session() -> list[dict]:
    """Get successfully extracted bills from the Bill Extractor page session state."""
    bills = st.session_state.get("extracted_bills", [])
    return [b for b in bills if b.get("status") == "success" and b.get("bill")]


def _render_bill_verification_section(hdf_df: pd.DataFrame):
    """Render the bill verification section in the main content area.

    Provides:
    - Upload a new bill for verification
    - Use an already-extracted bill from Bill Extractor page
    - Graceful handling of missing MPRN (date-only matching)
    - Manual date entry when bill has no billing period
    - Color-coded pass/fail results
    """
    hdf_stats = get_summary_stats(hdf_df)
    hdf_mprn = hdf_stats.get('mprn', '')
    hdf_start = hdf_stats.get('start_date')
    hdf_end = hdf_stats.get('end_date')

    st.markdown("## Cross-Reference with a Bill")
    st.caption(
        "Upload a bill for this meter to verify charges against actual readings."
    )

    # --- Bill source selection ---
    extracted_bills = _get_extracted_bills_from_session()
    has_extracted = len(extracted_bills) > 0

    if has_extracted:
        source = st.radio(
            "Bill source",
            options=["Upload a new bill", "Use an already-extracted bill"],
            horizontal=True,
            key="_verification_source",
            label_visibility="collapsed",
        )
    else:
        source = "Upload a new bill"

    bill = None
    v_key = None

    if source == "Upload a new bill":
        col_upload, _ = st.columns([2, 1])
        with col_upload:
            verification_file = st.file_uploader(
                "Bill PDF or image",
                type=['pdf', 'jpg', 'jpeg', 'png'],
                key="verification_bill_uploader",
                label_visibility="collapsed",
            )

        if verification_file is None:
            st.session_state.pop("_verification_result", None)
            st.session_state.pop("_verification_bill", None)
            st.session_state.pop("_verification_cache_key", None)
            return

        v_content = verification_file.getvalue()
        v_key = f"verify_{verification_file.name}_{len(v_content)}"

        if st.session_state.get("_verification_cache_key") != v_key:
            try:
                with st.spinner("Extracting bill for verification..."):
                    v_name = verification_file.name.lower()
                    if v_name.endswith(('.jpg', '.jpeg', '.png')):
                        pipeline_result = extract_bill_from_image(v_content)
                    else:
                        pipeline_result = extract_bill_pipeline(v_content)
                    bill = generic_to_legacy(pipeline_result.bill)
                    st.session_state._verification_cache_key = v_key
                    st.session_state._verification_bill = bill
                    # Clear previous result so validation re-runs
                    st.session_state.pop("_verification_result", None)
            except Exception as e:
                st.error(f"Error extracting bill: {str(e)}")
                return

        bill = st.session_state.get("_verification_bill")

    else:
        # Use an already-extracted bill
        bill_options = {
            f"{b['supplier']} — {b['filename']}": b
            for b in extracted_bills
        }
        selected_label = st.selectbox(
            "Select a bill",
            options=list(bill_options.keys()),
            key="_verification_select_bill",
        )
        if selected_label:
            selected = bill_options[selected_label]
            bill = selected["bill"]
            v_key = f"verify_extracted_{selected.get('content_hash', selected['filename'])}"

            if st.session_state.get("_verification_cache_key") != v_key:
                st.session_state._verification_cache_key = v_key
                st.session_state._verification_bill = bill
                st.session_state.pop("_verification_result", None)

            bill = st.session_state.get("_verification_bill")

    if bill is None:
        return

    # --- Validate and handle gracefully ---
    # Check if we need manual dates
    override_start = st.session_state.get("_verification_manual_start")
    override_end = st.session_state.get("_verification_manual_end")

    cached_result = st.session_state.get("_verification_result")

    if cached_result is None:
        v_result = validate_cross_reference(
            hdf_df, hdf_mprn, bill,
            override_start=override_start,
            override_end=override_end,
        )

        if v_result.needs_manual_dates:
            # Show date entry UI
            st.warning("Billing period dates were not detected in this bill.")
            if hdf_start and hdf_end:
                st.caption(
                    f"Meter data covers "
                    f"{hdf_start.strftime('%d %b %Y')} — "
                    f"{hdf_end.strftime('%d %b %Y')}. "
                    f"Enter the billing period for this bill."
                )

            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                manual_start = st.date_input(
                    "Bill period start",
                    value=hdf_start,
                    min_value=hdf_start,
                    max_value=hdf_end,
                    key="_verification_date_start_input",
                )
            with col2:
                manual_end = st.date_input(
                    "Bill period end",
                    value=hdf_end,
                    min_value=hdf_start,
                    max_value=hdf_end,
                    key="_verification_date_end_input",
                )
            with col3:
                st.markdown("")
                st.markdown("")
                if st.button("Verify with these dates", type="primary"):
                    st.session_state._verification_manual_start = manual_start
                    st.session_state._verification_manual_end = manual_end
                    st.session_state.pop("_verification_result", None)
                    st.rerun()
            return

        if v_result.valid:
            v_result = compute_verification(hdf_df, bill, v_result)

        st.session_state._verification_result = v_result

    v_result = st.session_state._verification_result

    if not v_result.valid:
        st.error(v_result.block_reason)
        return

    # --- Pass/Fail Summary ---
    _render_verification_summary(v_result)

    # --- Detailed verification results ---
    show_bill_verification(hdf_df, v_result)


def _render_verification_summary(v: VerificationResult):
    """Render a color-coded pass/fail summary for the verification."""
    # Determine overall status based on consumption delta
    if v.hdf_total_kwh and v.bill_total_kwh:
        delta_pct = abs((v.bill_total_kwh - v.hdf_total_kwh) / v.hdf_total_kwh) * 100

        if delta_pct <= 5:
            color = "#22c55e"  # green
            status = "Match"
            message = "Billed consumption matches meter data within 5%."
        elif delta_pct <= 15:
            color = "#f59e0b"  # amber
            status = "Review"
            message = f"Billed consumption differs from meter data by {delta_pct:.0f}% — worth investigating."
        else:
            color = "#ef4444"  # red
            status = "Discrepancy"
            message = f"Billed consumption differs from meter data by {delta_pct:.0f}% — likely overcharge."

        st.markdown(
            f'<div style="padding: 1rem 1.5rem; border-left: 4px solid {color}; '
            f'background: {color}15; border-radius: 0 8px 8px 0; margin: 1rem 0;">'
            f'<div style="color: {color}; font-weight: 700; font-size: 1.1rem;">'
            f'{status}</div>'
            f'<div style="color: #e2e8f0; font-size: 0.95rem; margin-top: 0.3rem;">'
            f'{message}</div></div>',
            unsafe_allow_html=True,
        )

    # Show warnings
    for issue in v.issues:
        st.warning(issue)


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
        st.caption(f"{len(raw_df):,} rows \u00d7 {len(raw_df.columns)} columns")

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
                f"- **{field}** \u2192 `{candidate.original_name}` "
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
            f"Date range: {report.date_range_start.strftime('%d %b %Y')} \u2014 "
            f"{report.date_range_end.strftime('%d %b %Y')}"
        )

    # Quality issues
    if report.issues:
        st.markdown("#### Quality Issues")
        for issue in report.issues:
            icon = {"error": "\U0001f6a8", "warning": "\u26a0\ufe0f", "info": "\u2139\ufe0f"}.get(issue.severity, "\u2022")
            fixed_tag = " *(auto-fixed)*" if issue.auto_fixed else ""
            st.markdown(f"{icon} **{issue.category}**: {issue.message}{fixed_tag}")
            if issue.details:
                st.caption(f"  {issue.details}")
    else:
        st.success("\u2713 No quality issues found.")

    # Data preview
    if len(result.df) > 0:
        with st.expander("Cleaned Data Preview", expanded=False):
            st.dataframe(result.df.head(20), use_container_width=True)

    # Not usable?
    if not report.is_usable:
        st.error("Data has critical issues and cannot be analyzed. Please fix the issues above and re-upload.")
        if st.button("\u2190 Back to Mapping"):
            st.session_state.excel_step = 1
            st.rerun()
        return

    # Store result and show navigation
    st.session_state.excel_result = result

    st.markdown("")
    col1, col2, _ = st.columns([1, 1, 2])
    with col1:
        if st.button("\u2190 Back to Mapping"):
            st.session_state.excel_step = 1
            st.rerun()
    with col2:
        if st.button("Proceed to Analysis \u2192", type="primary"):
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

    # In-page tariff config and filter bar
    _render_tariff_config()
    df = _render_filter_bar(full_df)

    if len(df) == 0:
        st.warning("No data matches the current filters. Adjust the date range or load type above.")
        # Back button still available
        st.markdown("")
        if st.button("\u2190 Back to Quality Report"):
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
    st.success(f"\u2713 Showing {len(df):,} readings{date_info}")

    # Build tabs based on granularity
    _show_analysis(result, df, stats, anomalies, granularity)

    # Back button
    st.markdown("")
    if st.button("\u2190 Back to Quality Report"):
        st.session_state.excel_step = 2
        st.rerun()


def _show_analysis(result: ParseResult, df: pd.DataFrame, stats: dict, anomalies: list, granularity: DataGranularity):
    """Build tab list based on granularity and show analysis."""
    if granularity.is_interval:
        # Full 5-tab layout for interval data
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "\U0001f4ca Overview",
            "\U0001f525 Heatmap",
            "\U0001f4c8 Charts",
            "\u26a0\ufe0f Insights",
            "\U0001f4e5 Export"
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
            "\U0001f4ca Overview",
            "\U0001f4c8 Charts",
            "\u26a0\ufe0f Insights",
            "\U0001f4e5 Export"
        ])
        with tab1:
            show_overview_flexible(stats, anomalies, granularity)
        with tab3:
            show_charts_flexible(df, stats, granularity)
        with tab4:
            show_insights_flexible(df, stats, anomalies, granularity)
        with tab5:
            show_export_flexible(df, stats, granularity)


# =========================================================================
# Analysis tab functions
# =========================================================================

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
        st.subheader("\u26a0\ufe0f Quick Alerts")
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
        st.subheader("\u26a0\ufe0f Quick Alerts")
        for a in anomalies[:3]:
            severity_icon = {'info': '\u2139\ufe0f', 'warning': '\u26a0\ufe0f', 'alert': '\U0001f6a8'}.get(a['severity'], '\u2022')
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
                    f"**{night_pct:.0f}% of daytime** \u2014 this is high and may "
                    "indicate always-on loads worth investigating."
                )
            elif night_pct > 30:
                parts.append(
                    f"Night-time usage ({night_avg:.2f} kWh avg) is "
                    f"**{night_pct:.0f}% of daytime** \u2014 moderate baseload."
                )
            else:
                parts.append(
                    f"Night-time usage ({night_avg:.2f} kWh avg) is "
                    f"**{night_pct:.0f}% of daytime** \u2014 low baseload, typical "
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
    st.subheader("\U0001f4ca Daily Load Profile")
    fig_profile = create_daily_profile(df, anomalies=anomalies)
    st.plotly_chart(fig_profile, use_container_width=True)

    # Daily trend (90 days)
    st.subheader("\U0001f4c8 Daily Trend")
    fig_daily = create_daily_trend(df, last_n_days=90, anomalies=anomalies)
    st.plotly_chart(fig_daily, use_container_width=True)

    # Two columns for tariff and monthly
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("\u23f0 Tariff Breakdown")
        fig_tariff = create_tariff_breakdown(df)
        st.plotly_chart(fig_tariff, use_container_width=True)

    with col2:
        st.subheader("\U0001f4c5 Monthly Trend")
        fig_monthly = create_monthly_trend(df, anomalies=anomalies)
        st.plotly_chart(fig_monthly, use_container_width=True)

    # Solar comparison if available
    if stats['has_solar']:
        st.subheader("\u2600\ufe0f Import vs Export (Solar)")
        fig_solar = create_import_export_comparison(df)
        st.plotly_chart(fig_solar, use_container_width=True)

    # Baseload analysis
    st.subheader("\U0001f50c Baseload Analysis")
    fig_baseload = create_baseload_chart(df, anomalies=anomalies)
    st.plotly_chart(fig_baseload, use_container_width=True)


def show_charts_flexible(df: pd.DataFrame, stats: dict, granularity: DataGranularity):
    """Show charts with graceful degradation based on granularity."""
    st.header("Analysis Charts")

    if granularity == DataGranularity.DAILY:
        # Daily trend
        if 'date' in df.columns:
            st.subheader("\U0001f4c8 Daily Consumption Trend")
            fig_daily = create_daily_trend(df, last_n_days=len(df))
            st.plotly_chart(fig_daily, use_container_width=True)

        # Monthly trend
        if 'year_month' in df.columns:
            st.subheader("\U0001f4c5 Monthly Trend")
            fig_monthly = create_monthly_trend(df)
            st.plotly_chart(fig_monthly, use_container_width=True)

    elif granularity == DataGranularity.MONTHLY:
        # Monthly trend only
        if 'year_month' in df.columns:
            st.subheader("\U0001f4c5 Monthly Trend")
            fig_monthly = create_monthly_trend(df)
            st.plotly_chart(fig_monthly, use_container_width=True)
        else:
            st.info("Not enough data to generate charts at monthly granularity.")

    else:
        # Unknown granularity — try monthly trend
        if 'year_month' in df.columns:
            st.subheader("\U0001f4c5 Monthly Trend")
            fig_monthly = create_monthly_trend(df)
            st.plotly_chart(fig_monthly, use_container_width=True)

    # Note about unavailable charts
    if not granularity.is_interval:
        st.info("Load profile, tariff breakdown, heatmap, and baseload charts require interval-level (30-min/hourly) data.")


def show_insights(df: pd.DataFrame, stats: dict, anomalies: list):
    """Show anomalies and insights (interval data)."""
    st.header("Insights & Anomalies")

    if not anomalies:
        st.success("\u2713 No significant anomalies detected in the consumption pattern.")
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
        render_anomaly_cards(anomalies)

    # Tariff optimization
    st.divider()
    st.subheader("\U0001f4b0 Tariff Optimization")

    night_pct = stats['tariff_night_kwh'] / stats['total_import_kwh'] * 100
    peak_pct = stats['tariff_peak_kwh'] / stats['total_import_kwh'] * 100

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Night Usage", f"{night_pct:.1f}%")
        if night_pct < 30:
            st.caption("Consider shifting loads to night hours (23:00-08:00) for cheaper rates.")
        else:
            st.caption("\u2713 Good use of night-rate electricity.")

    with col2:
        st.metric("Peak Usage", f"{peak_pct:.1f}%")
        if peak_pct > 15:
            st.caption("\u26a0\ufe0f High peak usage (17:00-19:00). Consider shifting to avoid highest rates.")
        else:
            st.caption("\u2713 Peak period usage is reasonable.")


def show_insights_flexible(df: pd.DataFrame, stats: dict, anomalies: list, granularity: DataGranularity):
    """Show insights with graceful degradation."""
    st.header("Insights & Anomalies")

    if not anomalies:
        st.success("\u2713 No significant anomalies detected in the consumption pattern.")
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
        render_anomaly_cards(anomalies)

    # Tariff optimization only for interval data
    if stats.get('tariff_night_kwh') is not None and stats.get('tariff_peak_kwh') is not None:
        st.divider()
        st.subheader("\U0001f4b0 Tariff Optimization")

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
                    st.caption("\u2713 Good use of night-rate electricity.")

            with col2:
                st.metric("Peak Usage", f"{peak_pct:.1f}%")
                if peak_pct > 15:
                    st.caption("\u26a0\ufe0f High peak usage (17:00-19:00). Consider shifting to avoid highest rates.")
                else:
                    st.caption("\u2713 Peak period usage is reasonable.")
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

    if st.button("\U0001f4e5 Generate Excel Export", type="primary"):
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
            label="\u2b07\ufe0f Download Excel File",
            data=excel_buffer.getvalue(),
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    st.divider()
    st.subheader("\U0001f5bc\ufe0f Chart Export")
    st.caption("Right-click on any chart and select 'Download plot as PNG' to save individual charts.")


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

    if st.button("\U0001f4e5 Generate Excel Export", type="primary", key="exp_generate"):
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
            label="\u2b07\ufe0f Download Excel File",
            data=excel_buffer.getvalue(),
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="exp_download",
        )

    st.divider()
    st.subheader("\U0001f5bc\ufe0f Chart Export")
    st.caption("Right-click on any chart and select 'Download plot as PNG' to save individual charts.")


# =========================================================================
# Bill Verification tab
# =========================================================================

def show_bill_verification(hdf_df: pd.DataFrame, v: VerificationResult):
    """Display detailed bill verification results."""

    # --- 1. Match Status ---
    st.subheader("Match Status")
    col1, col2, col3 = st.columns(3)
    with col1:
        if v.mprn_skipped:
            st.metric("MPRN", "Skipped", help="Bill had no MPRN — matched by date only")
        else:
            st.metric("MPRN", v.hdf_mprn)
    with col2:
        st.metric("Data Coverage", f"{v.overlap_pct:.0f}%")
    with col3:
        st.metric("Billing Days", f"{v.overlap_days}/{v.billing_days}")

    if v.bill_start and v.bill_end:
        st.caption(
            f"Bill period: {v.bill_start.strftime('%d %b %Y')} \u2014 "
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
                delta=f"{delta_pct:+.1f}% \u2014 {status}",
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


# =========================================================================
# Excel export generators
# =========================================================================

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


# =========================================================================
# Sidebar & Main Flow
# =========================================================================

# Initialise session state for tariff (before sidebar so defaults are set)
default_rates = PROVIDER_PRESETS['Electric Ireland']
if 'tariff_provider' not in st.session_state:
    st.session_state.tariff_provider = 'Electric Ireland'
if '_tariff_day_widget' not in st.session_state:
    st.session_state._tariff_day_widget = default_rates['day']
if '_tariff_night_widget' not in st.session_state:
    st.session_state._tariff_night_widget = default_rates['night']
if '_tariff_peak_widget' not in st.session_state:
    st.session_state._tariff_peak_widget = default_rates['peak']

with st.sidebar:
    logo_path = _load_logo()
    if logo_path:
        st.image(str(logo_path), width=180)
        st.divider()

    st.markdown("### \U0001f4c1 Upload Data")
    uploaded_file = st.file_uploader(
        "Energy Data File",
        type=['csv', 'xlsx', 'xls'],
        help="Upload HDF, Excel, or CSV energy data (ESB Networks HDF 30-min CSV, .xlsx, .xls, .csv)",
        label_visibility="collapsed",
    )
    st.caption("Upload HDF, Excel, or CSV")


# --- Main content ---
st.markdown("## \U0001f4ca Meter Analysis")
st.caption("Analyze energy consumption data")

file_content = None
filename = None

if uploaded_file is not None:
    file_content = uploaded_file.getvalue()
    filename = uploaded_file.name
    st.session_state.pop("_demo_file_content", None)
    st.session_state.pop("_demo_file_name", None)
elif st.session_state.get("_demo_file_content") is not None:
    file_content = st.session_state._demo_file_content
    filename = st.session_state._demo_file_name

if file_content is not None and filename is not None:
    # Detect file type and route accordingly
    if is_hdf_file(file_content):
        _handle_hdf_file(file_content, filename)
    else:
        _handle_excel_file(file_content, filename)
else:
    # Empty state — polished card
    st.markdown(
        """
        <div class="empty-state-card">
            <div class="empty-icon">\U0001f4ca</div>
            <h3>Upload Energy Data</h3>
            <p>
                Use the sidebar to upload an ESB Networks HDF file,<br>
                Excel spreadsheet, or CSV with energy data.
            </p>
            <div class="format-tags">
                <span class="format-tag">HDF CSV</span>
                <span class="format-tag">XLSX</span>
                <span class="format-tag">XLS</span>
                <span class="format-tag">CSV</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
