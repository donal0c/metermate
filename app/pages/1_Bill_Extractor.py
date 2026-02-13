"""Energy Insight - Bill Extractor

Upload and extract data from 1-N electricity bills in a single, fluid
workflow. Files accumulate — upload one, look at it, upload another,
compare. No mode switching required.
"""

import streamlit as st
import pandas as pd
import io
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

from bill_parser import BillData, generic_to_legacy
from orchestrator import extract_bill_pipeline, extract_bill_from_image
from common.theme import apply_theme
from common.components import fmt_value, field_html
from common.formatters import (
    parse_bill_date as parse_bill_date_util,
    compute_billing_days,
)
from common.session import content_hash
import plotly.graph_objects as go

st.set_page_config(
    page_title="Bill Extractor - Energy Insight",
    page_icon="\U0001f4c4",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()

# Alias for bill date parsing
_parse_bill_date = parse_bill_date_util


# =========================================================================
# Session state initialization
# =========================================================================

if "extracted_bills" not in st.session_state:
    st.session_state.extracted_bills = []

if "processed_hashes" not in st.session_state:
    st.session_state.processed_hashes = set()


# =========================================================================
# Functions
# =========================================================================

def _load_logo():
    """Load logo from file if it exists."""
    logo_path = Path(__file__).parent.parent / "logo.png"
    if logo_path.exists():
        return logo_path
    return None


def _extract_bill(file_content: bytes, filename: str) -> dict:
    """Extract a bill from file content, returning a result dict."""
    file_hash = content_hash(file_content)

    try:
        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            pipeline_result = extract_bill_from_image(file_content)
        else:
            pipeline_result = extract_bill_pipeline(file_content)

        bill = generic_to_legacy(pipeline_result.bill)
        return {
            "filename": filename,
            "bill": bill,
            "raw_text": pipeline_result.bill.raw_text,
            "confidence": bill.confidence_score,
            "content_hash": file_hash,
            "status": "success",
            "supplier": bill.supplier or "Unknown",
            "field_count": _count_extracted_fields(bill),
            "error": None,
        }
    except Exception as e:
        return {
            "filename": filename,
            "bill": None,
            "raw_text": None,
            "confidence": 0.0,
            "content_hash": file_hash,
            "status": "error",
            "supplier": None,
            "field_count": 0,
            "error": str(e),
        }


def _count_extracted_fields(bill: BillData) -> int:
    """Count the number of non-None extracted fields."""
    bill_dict = asdict(bill)
    skip = {'extraction_method', 'confidence_score', 'warnings'}
    return sum(
        1 for k, v in bill_dict.items()
        if k not in skip and v is not None
    )


def show_bill_summary(bill: BillData, raw_text: str | None = None,
                      key_suffix: str = ""):
    """Display extracted bill data as a clean single-page summary.

    Args:
        bill: Extracted bill data.
        raw_text: Raw text from extraction (for debug display).
        key_suffix: Suffix for widget keys to avoid duplicates when
            rendering multiple summaries on the same page.
    """

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

    section_summary = " \u00b7 ".join(section_parts)

    # Determine which fields have warnings (low confidence / missing critical)
    warn_fields = set()
    for w in bill.warnings:
        if "Critical field" in w:
            field_match = w.split("'")[1] if "'" in w else ""
            if field_match:
                warn_fields.add(field_match)

    if confidence_pct >= 80:
        st.success(
            f"**{supplier_label}** \u2014 {total_extracted}/{total_expected} fields "
            f"(confidence: {confidence_pct}%)\n\n"
            f"{section_summary}"
        )
    else:
        verify_note = (
            "Fields marked with \u26a0\ufe0f could not be extracted \u2014 please verify manually."
            if warn_fields
            else "Low extraction confidence \u2014 please verify key fields against the original bill."
        )
        st.warning(
            f"**{supplier_label}** \u2014 {total_extracted}/{total_expected} fields "
            f"(confidence: {confidence_pct}%)\n\n"
            f"{section_summary}\n\n"
            f"{verify_note}"
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

    # --- Section 1: Account Details ---
    st.subheader("\U0001f3e2 Account Details")
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
                field_html(label, value, warn=field_name in warn_fields),
                unsafe_allow_html=True,
            )

    # --- Section 2: Billing Period (hide if all empty) ---
    _has_billing = any(v is not None for v in [
        bill.bill_date, bill.billing_period_start, bill.billing_period_end,
    ])
    if _has_billing:
        st.subheader("\U0001f4c5 Billing Period")
        cols = st.columns(3)
        with cols[0]:
            st.markdown(field_html("Bill Date", bill.bill_date), unsafe_allow_html=True)
        with cols[1]:
            period = "\u2014"
            if bill.billing_period_start and bill.billing_period_end:
                period = f"{bill.billing_period_start} \u2192 {bill.billing_period_end}"
            elif bill.billing_period_start:
                period = bill.billing_period_start
            st.markdown(
                field_html("Period", period,
                            warn='billing_period_start' in warn_fields or 'billing_period_end' in warn_fields),
                unsafe_allow_html=True,
            )
        with cols[2]:
            days = compute_billing_days(bill.billing_period_start, bill.billing_period_end)
            st.markdown(
                field_html("Days", f"{days}" if days else None),
                unsafe_allow_html=True,
            )

    # --- Section 3: Consumption (hide if all empty) ---
    _has_consumption = any(v is not None for v in [
        bill.day_units_kwh, bill.night_units_kwh, bill.peak_units_kwh,
        bill.total_units_kwh, bill.day_rate, bill.night_rate, bill.peak_rate,
    ])
    if _has_consumption:
        st.subheader("\u26a1 Consumption")
        cols = st.columns(4)
        consumption_fields = [
            ("Day Units", bill.day_units_kwh, "kWh"),
            ("Night Units", bill.night_units_kwh, "kWh"),
            ("Peak Units", bill.peak_units_kwh, "kWh"),
            ("Total Units", bill.total_units_kwh, "kWh"),
        ]
        for i, (label, value, unit) in enumerate(consumption_fields):
            with cols[i]:
                display = fmt_value(value, suffix=f" {unit}", fmt_spec=",.1f") if value is not None else None
                st.markdown(field_html(label, display), unsafe_allow_html=True)

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
                    display = f"\u20ac{value:.4f}/kWh" if value is not None else None
                    st.markdown(field_html(label, display), unsafe_allow_html=True)

    # --- Section 4: Costs ---
    st.subheader("\U0001f4b0 Costs")
    cols = st.columns(4)
    cost_fields = [
        ("Day Cost", bill.day_cost),
        ("Night Cost", bill.night_cost),
        ("Peak Cost", bill.peak_cost),
        ("Subtotal", bill.subtotal_before_vat),
    ]
    for i, (label, value) in enumerate(cost_fields):
        with cols[i]:
            display = f"\u20ac{value:,.2f}" if value is not None else None
            st.markdown(field_html(label, display), unsafe_allow_html=True)

    # Additional cost line items
    line_items = []
    if bill.standing_charge_total is not None:
        detail = ""
        if bill.standing_charge_days and bill.standing_charge_rate:
            detail = f" ({bill.standing_charge_days} days at \u20ac{bill.standing_charge_rate}/day)"
        line_items.append(("Standing Charge", f"\u20ac{bill.standing_charge_total:,.2f}{detail}"))
    if bill.pso_levy is not None:
        line_items.append(("PSO Levy", f"\u20ac{bill.pso_levy:,.2f}"))
    if bill.discount is not None:
        line_items.append(("Discount", f"\u20ac{bill.discount:,.2f} CR"))
    if bill.vat_amount is not None:
        vat_detail = f" ({bill.vat_rate_pct:.0f}%)" if bill.vat_rate_pct else ""
        line_items.append(("VAT", f"\u20ac{bill.vat_amount:,.2f}{vat_detail}"))
    if bill.total_this_period is not None:
        line_items.append(("Total This Period", f"\u20ac{bill.total_this_period:,.2f}"))

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
            detail = f" ({bill.export_units:,.1f} kWh at \u20ac{bill.export_rate:.4f}/kWh)"
        if bill.export_credit is not None:
            st.markdown(
                f'<div style="border-left: 3px solid #22c55e; padding-left: 0.5rem;">'
                f'<span style="color: #22c55e; font-family: \'JetBrains Mono\', monospace;">'
                f'\u20ac{bill.export_credit:,.2f} credit{detail}</span></div>',
                unsafe_allow_html=True,
            )

    # --- Section 5: Balance (hide if all empty) ---
    _has_balance = any(v is not None for v in [
        bill.previous_balance, bill.payments_received, bill.amount_due,
    ])
    if _has_balance:
        st.subheader("\U0001f3e6 Balance")
        cols = st.columns(3)
        with cols[0]:
            display = f"\u20ac{bill.previous_balance:,.2f}" if bill.previous_balance is not None else None
            st.markdown(field_html("Previous Balance", display), unsafe_allow_html=True)
        with cols[1]:
            display = f"\u20ac{bill.payments_received:,.2f}" if bill.payments_received is not None else None
            st.markdown(field_html("Payments Received", display), unsafe_allow_html=True)
        with cols[2]:
            if bill.amount_due is not None:
                st.markdown(
                    f'<div style="border-left: 3px solid #4ade80; padding-left: 0.5rem;">'
                    f'<span style="color: #94a3b8; font-size: 0.8rem;">Amount Due</span><br>'
                    f'<span style="color: #4ade80; font-family: \'JetBrains Mono\', monospace; '
                    f'font-size: 1.3rem; font-weight: 700;">\u20ac{bill.amount_due:,.2f}</span></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(field_html("Amount Due", None), unsafe_allow_html=True)

    # --- Export ---
    st.divider()
    st.subheader("\U0001f4e5 Export")
    excel_buffer = generate_bill_excel(bill)
    mprn_part = bill.mprn or "unknown"
    date_part = (bill.bill_date or "").replace(" ", "_") or "undated"
    st.download_button(
        label="Download as Excel",
        data=excel_buffer,
        file_name=f"bill_extract_{mprn_part}_{date_part}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"bill_download{key_suffix}",
    )
    st.caption(
        f"Extraction method: {bill.extraction_method} \u00b7 "
        f"Confidence: {confidence_pct}%"
    )

    # --- Raw Text Debug (collapsed by default) ---
    if raw_text:
        with st.expander("\U0001f50d Raw Extracted Text", expanded=False):
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


# ---------------------------------------------------------------------------
# Multi-bill comparison
# ---------------------------------------------------------------------------

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


def show_bill_comparison(bills):
    """Display multi-bill comparison view with tabs."""
    st.subheader(f"Bill Comparison \u2014 {len(bills)} bills")

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
                f"{bill.billing_period_start} \u2014 {bill.billing_period_end}"
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
            f"\u20ac{total_cost:,.2f}" if pd.notna(total_cost) and total_cost > 0 else "\u2014",
        )
    with col2:
        total_kwh = df['total_kwh'].sum()
        st.metric(
            "Total kWh",
            f"{total_kwh:,.0f}" if pd.notna(total_kwh) and total_kwh > 0 else "\u2014",
        )
    with col3:
        valid_costs = df['total_cost'].dropna()
        total_bills = len(df)
        valid_count = len(valid_costs)
        avg_cost = valid_costs.mean() if valid_count > 0 else None
        label = "Avg Cost/Bill"
        if valid_count < total_bills and valid_count > 0:
            label = f"Avg Cost/Bill ({valid_count} of {total_bills})"
        st.metric(
            label,
            f"\u20ac{avg_cost:,.2f}" if avg_cost else "\u2014",
        )
    with col4:
        if (
            df['total_kwh'].notna().any()
            and df['total_cost'].notna().any()
            and df['total_kwh'].sum() > 0
        ):
            avg_rate = df['total_cost'].sum() / df['total_kwh'].sum()
            st.metric("Avg \u20ac/kWh", f"\u20ac{avg_rate:.4f}")
        else:
            st.metric("Avg \u20ac/kWh", "\u2014")

    st.divider()

    # Display table
    display_cols = {
        'filename': 'File',
        'supplier': 'Supplier',
        'billing_period': 'Period',
        'total_kwh': 'Total kWh',
        'total_cost': 'Total (\u20ac)',
        'day_kwh': 'Day kWh',
        'night_kwh': 'Night kWh',
        'standing_charge': 'Standing (\u20ac)',
        'vat': 'VAT (\u20ac)',
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
            'File': st.column_config.TextColumn(width="small"),
            'Supplier': st.column_config.TextColumn(width="small"),
            'Period': st.column_config.TextColumn(width="medium"),
            'Total kWh': st.column_config.NumberColumn(format="%.1f", width="small"),
            'Total (\u20ac)': st.column_config.NumberColumn(format="\u20ac%.2f", width="small"),
            'Day kWh': st.column_config.NumberColumn(format="%.1f", width="small"),
            'Night kWh': st.column_config.NumberColumn(format="%.1f", width="small"),
            'Standing (\u20ac)': st.column_config.NumberColumn(format="\u20ac%.2f", width="small"),
            'VAT (\u20ac)': st.column_config.NumberColumn(format="\u20ac%.2f", width="small"),
            'Confidence': st.column_config.NumberColumn(format="%.0%%", width="small"),
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
        yaxis_title="Cost (\u20ac)",
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
            st.metric("First Bill", f"\u20ac{first_cost:,.2f}")
        with col2:
            st.metric("Latest Bill", f"\u20ac{last_cost:,.2f}")
        with col3:
            st.metric("Change", f"\u20ac{change:+,.2f}", delta=f"{change_pct:+.1f}%")


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
        yaxis_title="Rate (\u20ac/kWh)",
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
                'First Bill': f"\u20ac{first:.4f}",
                'Latest Bill': f"\u20ac{last:.4f}",
                'Change': f"\u20ac{change:+.4f}",
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
            'day_rate': 'Day Rate (\u20ac/kWh)', 'night_rate': 'Night Rate (\u20ac/kWh)',
            'peak_rate': 'Peak Rate (\u20ac/kWh)',
            'standing_charge': 'Standing Charge (\u20ac)', 'subtotal': 'Subtotal (\u20ac)',
            'vat': 'VAT (\u20ac)', 'total_cost': 'Total Cost (\u20ac)',
            'amount_due': 'Amount Due (\u20ac)',
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


# =========================================================================
# Sidebar
# =========================================================================

with st.sidebar:
    logo_path = _load_logo()
    if logo_path:
        st.image(str(logo_path), width=180)
        st.divider()

    bill_count = len(st.session_state.extracted_bills)
    success_count = sum(
        1 for b in st.session_state.extracted_bills if b["status"] == "success"
    )

    st.markdown("### \U0001f4c4 Bill Extractor")
    if bill_count > 0:
        st.caption(
            f"{success_count} bill{'s' if success_count != 1 else ''} extracted"
        )
    else:
        st.caption(
            "Upload electricity bills to extract costs, consumption, and rates."
        )

    if bill_count > 0:
        st.divider()
        if st.button("Clear All Bills", use_container_width=True, key="clear_bills"):
            st.session_state.extracted_bills = []
            st.session_state.processed_hashes = set()
            st.rerun()


# =========================================================================
# Upload zone & main flow
# =========================================================================

st.markdown("## \U0001f4c4 Bill Extractor")
st.caption("Upload electricity bills to extract costs, consumption, and rates")

# Upload zone (main content area, not sidebar)
uploaded_files = st.file_uploader(
    "Upload electricity bills to extract costs, consumption, and rates",
    type=['pdf', 'jpg', 'jpeg', 'png'],
    accept_multiple_files=True,
    help="Drag and drop or browse. Supports PDF, JPG, JPEG, PNG. Upload multiple files at once.",
    key="bill_uploader",
    label_visibility="collapsed",
)

# Handle demo file from home page
_demo_content = st.session_state.pop("_demo_file_content", None)
_demo_name = st.session_state.pop("_demo_file_name", None)

if _demo_content is not None and _demo_name is not None:
    demo_hash = content_hash(_demo_content)
    if demo_hash not in st.session_state.processed_hashes:
        with st.spinner(f"Extracting {_demo_name}..."):
            result = _extract_bill(_demo_content, _demo_name)
        st.session_state.extracted_bills.append(result)
        st.session_state.processed_hashes.add(demo_hash)
        st.rerun()

# Process new uploads (deduplicate by content hash)
if uploaded_files:
    new_files = []
    for f in uploaded_files:
        file_content = f.getvalue()
        file_hash = content_hash(file_content)
        if file_hash not in st.session_state.processed_hashes:
            new_files.append((file_content, f.name, file_hash))

    if new_files:
        progress = st.progress(0, text="Processing bills...")
        for i, (file_content, filename, file_hash) in enumerate(new_files):
            progress.progress(
                (i + 1) / len(new_files),
                text=f"Extracting {filename}...",
            )
            result = _extract_bill(file_content, filename)
            st.session_state.extracted_bills.append(result)
            st.session_state.processed_hashes.add(file_hash)
        progress.empty()
        st.rerun()

# --- Status chips for processed bills ---
bills = st.session_state.extracted_bills

if bills:
    chip_html = (
        '<div style="display: flex; flex-wrap: wrap; gap: 0.5rem; '
        'margin: 0.5rem 0 1rem 0;">'
    )
    for entry in bills:
        if entry["status"] == "success":
            supplier = entry["supplier"] or "Unknown"
            conf = round(entry["confidence"] * 100)
            if conf >= 80:
                color = "#22c55e"
                icon = "\u2713"
            elif conf >= 50:
                color = "#f59e0b"
                icon = "\u26a0"
            else:
                color = "#ef4444"
                icon = "\u26a0"
            chip_html += (
                f'<div style="display: inline-flex; align-items: center; gap: 0.4rem; '
                f'padding: 0.3rem 0.8rem; background: #1e2433; border: 1px solid {color}; '
                f'border-radius: 16px; font-size: 0.85rem;">'
                f'<span style="color: {color};">{icon}</span>'
                f'<span style="color: #e2e8f0;">{entry["filename"]}</span>'
                f'<span style="color: #94a3b8;">({supplier}, {conf}%)</span>'
                f'</div>'
            )
        else:
            chip_html += (
                f'<div style="display: inline-flex; align-items: center; gap: 0.4rem; '
                f'padding: 0.3rem 0.8rem; background: #1e2433; border: 1px solid #ef4444; '
                f'border-radius: 16px; font-size: 0.85rem;">'
                f'<span style="color: #ef4444;">\u2717</span>'
                f'<span style="color: #e2e8f0;">{entry["filename"]}</span>'
                f'<span style="color: #94a3b8;">(failed)</span>'
                f'</div>'
            )
    chip_html += '</div>'
    st.markdown(chip_html, unsafe_allow_html=True)


# --- Results area ---
successful_bills = [
    (b["bill"], b["filename"]) for b in bills if b["status"] == "success"
]
error_bills = [b for b in bills if b["status"] == "error"]

# Show errors
for entry in error_bills:
    st.warning(f"Failed to extract **{entry['filename']}**: {entry['error']}")

if len(successful_bills) == 1:
    # Single bill detail view
    bill, filename = successful_bills[0]
    raw_text = next(
        (b["raw_text"] for b in bills if b["filename"] == filename), None
    )
    show_bill_summary(bill, raw_text=raw_text)

elif len(successful_bills) >= 2:
    # Comparison view at top
    show_bill_comparison(successful_bills)

    # Individual bill details below (expandable)
    st.divider()
    st.subheader("Individual Bill Details")
    for idx, (bill, filename) in enumerate(successful_bills):
        raw_text = next(
            (b["raw_text"] for b in bills if b["filename"] == filename), None
        )
        supplier_label = bill.supplier or "Unknown"
        conf_pct = round(bill.confidence_score * 100)
        with st.expander(
            f"\U0001f4c4 {filename} \u2014 {supplier_label} ({conf_pct}%)"
        ):
            show_bill_summary(bill, raw_text=raw_text, key_suffix=f"_{idx}")

else:
    # Empty state — no bills yet
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("---")
        st.markdown("### Upload Electricity Bills")
        st.markdown(
            "Upload one or more bills (PDF or photo) above to extract "
            "costs, consumption, and rates. Upload more at any time to compare."
        )
        st.markdown("")
        st.markdown("**Supported formats:**")
        st.markdown("- PDF bills (digital or scanned)")
        st.markdown("- Photographed bills (JPG, PNG)")
        st.markdown("")
        st.markdown("**What you'll get:**")
        st.markdown("- Supplier, account, and MPRN details")
        st.markdown("- Consumption breakdown (day/night/peak)")
        st.markdown("- Cost summary and balance")
        st.markdown("- Multi-bill comparison (2+ bills)")
        st.markdown("- Excel export")
        st.markdown("---")
