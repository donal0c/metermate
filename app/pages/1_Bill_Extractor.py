"""Energy Insight - Bill Extractor

Upload and extract data from 1-N electricity bills in a single, fluid
workflow. Files accumulate — upload one, look at it, upload another,
compare. No mode switching required.
"""

import os
import streamlit as st
import pandas as pd
import io
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

# Bridge Streamlit Cloud secrets into env vars for pipeline code
for _key in ("GEMINI_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI"):
    if _key not in os.environ:
        try:
            os.environ[_key] = st.secrets[_key]
            print(f"[LLM] Loaded {_key} from st.secrets (Streamlit Cloud)")
        except (KeyError, FileNotFoundError):
            pass

# Log LLM readiness at page load
_gemini_key = os.environ.get("GEMINI_API_KEY", "")
if _gemini_key:
    print(f"[LLM] GEMINI_API_KEY is set (length={len(_gemini_key)})")
else:
    print("[LLM] WARNING: GEMINI_API_KEY is NOT set - Tier 4 LLM will be unavailable")

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
import streamlit.components.v1 as components


def _browser_log(*messages: str) -> None:
    """Emit console.log() messages visible in the browser DevTools console."""
    js_lines = []
    for msg in messages:
        escaped = msg.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
        js_lines.append(f"console.log(`{escaped}`);")
    components.html(f"<script>{' '.join(js_lines)}</script>", height=0)

st.set_page_config(
    page_title="Bill Extractor - Energy Insight",
    page_icon="\U0001f4c4",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()

# Browser console: LLM readiness
if _gemini_key:
    _browser_log(
        f"[LLM] GEMINI_API_KEY is set (length={len(_gemini_key)})",
    )
else:
    _browser_log("[LLM] WARNING: GEMINI_API_KEY is NOT set - Tier 4 LLM unavailable")

# Alias for bill date parsing
_parse_bill_date = parse_bill_date_util


# =========================================================================
# Session state initialization
# =========================================================================

if "extracted_bills" not in st.session_state:
    st.session_state.extracted_bills = []

if "processed_hashes" not in st.session_state:
    st.session_state.processed_hashes = set()

if "bill_edits" not in st.session_state:
    st.session_state.bill_edits = {}

if "excluded_bills" not in st.session_state:
    st.session_state.excluded_bills = set()


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
        is_image = filename.lower().endswith(('.jpg', '.jpeg', '.png'))
        print(f"[EXTRACT] Starting extraction: {filename} ({'image' if is_image else 'pdf'}, {len(file_content):,} bytes)")

        if is_image:
            pipeline_result = extract_bill_from_image(file_content)
        else:
            pipeline_result = extract_bill_pipeline(file_content)

        path = " -> ".join(pipeline_result.extraction_path)
        provider = pipeline_result.provider_detection.provider_name
        conf = pipeline_result.confidence
        tier4_fired = pipeline_result.tier4 is not None
        tier4_fields = len(pipeline_result.tier4.fields) if tier4_fired else 0

        print(f"[EXTRACT] Provider: {provider}")
        print(f"[EXTRACT] Path: {path}")
        print(f"[EXTRACT] Confidence: {conf.score:.2f} ({conf.band})")
        if tier4_fired:
            print(f"[EXTRACT] Tier 4 LLM fired: YES ({tier4_fields} fields extracted)")
        else:
            print(f"[EXTRACT] Tier 4 LLM fired: NO (confidence was '{conf.band}', not 'escalate')")

        bill = generic_to_legacy(pipeline_result.bill)
        field_count = _count_extracted_fields(bill)

        print(f"[EXTRACT] Result: {field_count} fields extracted for {filename}")

        # Browser console logs (visible in DevTools F12)
        llm_msg = (
            f"[EXTRACT] Tier 4 LLM: YES ({tier4_fields} fields)"
            if tier4_fired
            else f"[EXTRACT] Tier 4 LLM: NO (confidence='{conf.band}')"
        )
        _browser_log(
            f"[EXTRACT] {filename} | {provider} | {field_count} fields",
            f"[EXTRACT] Path: {path}",
            f"[EXTRACT] Confidence: {conf.score:.2f} ({conf.band})",
            llm_msg,
        )

        return {
            "filename": filename,
            "bill": bill,
            "raw_text": pipeline_result.bill.raw_text,
            "confidence": bill.confidence_score,
            "content_hash": file_hash,
            "status": "success",
            "supplier": bill.supplier or "Unknown",
            "field_count": field_count,
            "error": None,
        }
    except Exception as e:
        print(f"[EXTRACT] ERROR extracting {filename}: {e}")
        _browser_log(f"[EXTRACT] ERROR: {filename} - {e}")
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


def _confidence_level(pct: int):
    """Return (level, color, bg, label, suggestion) for a confidence percentage."""
    if pct >= 80:
        return ("high", "#22c55e", "rgba(34,197,94,0.1)",
                "High confidence", None)
    elif pct >= 60:
        return ("partial", "#f59e0b", "rgba(245,158,11,0.1)",
                "Partial extraction",
                "Review highlighted values against the original bill.")
    else:
        return ("low", "#ef4444", "rgba(239,68,68,0.1)",
                "Low confidence",
                "Consider uploading a clearer scan or the PDF version if available.")


def _get_edit(key_suffix: str, field_name: str):
    """Retrieve an edited value from session state, or None if not edited."""
    return st.session_state.bill_edits.get(f"{key_suffix}_{field_name}")


def _display_value(bill, field_name: str, key_suffix: str, format_fn=None):
    """Return (display_value, is_edited, original) for a field, checking edits."""
    original = getattr(bill, field_name, None)
    edited_val = _get_edit(key_suffix, field_name)
    if edited_val is not None:
        display = format_fn(edited_val) if format_fn else edited_val
        orig_str = format_fn(original) if format_fn and original is not None else str(original)
        return display, True, orig_str
    display = format_fn(original) if format_fn and original is not None else original
    return display, False, None


def _edited_or_original(bill, field_name: str, key_suffix: str):
    """Return edited value if present, otherwise the original bill attribute."""
    edited = _get_edit(key_suffix, field_name)
    if edited is not None:
        return edited
    return getattr(bill, field_name, None)


def show_bill_summary(bill: BillData, raw_text: str | None = None,
                      key_suffix: str = ""):
    """Display extracted bill data as a clean single-page summary.

    Args:
        bill: Extracted bill data.
        raw_text: Raw text from extraction (for debug display).
        key_suffix: Suffix for widget keys to avoid duplicates when
            rendering multiple summaries on the same page.
    """

    # --- Traffic Light Confidence Badge ---
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

    level, color, bg, level_label, suggestion = _confidence_level(confidence_pct)

    badge_html = (
        f'<div data-testid="confidence-badge" data-level="{level}" '
        f'style="display: flex; align-items: center; gap: 0.75rem; '
        f'padding: 0.6rem 1rem; background: {bg}; border: 1px solid {color}30; '
        f'border-radius: 8px; margin-bottom: 0.5rem;">'
        f'<span style="width: 12px; height: 12px; border-radius: 50%; '
        f'background: {color}; flex-shrink: 0;"></span>'
        f'<div>'
        f'<span style="color: {color}; font-weight: 600;">{level_label}</span>'
        f'<span style="color: #94a3b8; margin-left: 0.5rem;">'
        f'\u2014 {total_extracted}/{total_expected} fields extracted</span>'
        f'<br><span style="color: #e2e8f0; font-weight: 500;">{supplier_label}</span>'
        f'</div></div>'
    )
    st.markdown(badge_html, unsafe_allow_html=True)

    # Section breakdown (muted detail)
    st.caption(section_summary)

    # Actionable suggestion for partial/low confidence
    if suggestion:
        st.markdown(
            f'<div data-testid="confidence-suggestion" '
            f'style="padding: 0.5rem 0.8rem; border-left: 3px solid {color}; '
            f'background: #1e2433; border-radius: 0 4px 4px 0; margin-bottom: 0.8rem; '
            f'color: #e2e8f0; font-size: 0.85rem;">{suggestion}</div>',
            unsafe_allow_html=True,
        )

    # --- Very low confidence: show extraction-failed card ---
    if confidence_pct < 40:
        st.markdown(
            '<div class="extraction-failed-card">'
            '<h4>Extraction largely failed</h4>'
            '<p style="color: #94a3b8; font-size: 0.9rem; margin-bottom: 0.75rem;">'
            'Most fields could not be extracted from this bill.</p>'
            '<p style="color: #cbd5e1; font-size: 0.85rem; font-weight: 600; '
            'margin-bottom: 0.25rem;">Try:</p>'
            '<ol class="suggestion-list">'
            '<li>Upload a clearer scan or the original PDF version</li>'
            '<li>Check the file is not password-protected or corrupted</li>'
            '<li>Use the edit form below to enter values manually</li>'
            '</ol></div>',
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
        ("Supplier", 'supplier'),
        ("Customer", 'customer_name'),
        ("MPRN", 'mprn'),
        ("Account No.", 'account_number'),
        ("Meter No.", 'meter_number'),
        ("Invoice No.", 'invoice_number'),
    ]
    for i, (label, field_name) in enumerate(account_fields):
        with cols[i % 4]:
            display, is_edited, orig = _display_value(bill, field_name, key_suffix)
            st.markdown(
                field_html(label, display,
                           warn=field_name in warn_fields and not is_edited,
                           edited=is_edited, original=orig),
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
            ("Day Units", "day_units_kwh", "kWh"),
            ("Night Units", "night_units_kwh", "kWh"),
            ("Peak Units", "peak_units_kwh", "kWh"),
            ("Total Units", "total_units_kwh", "kWh"),
        ]
        for i, (label, fname, unit) in enumerate(consumption_fields):
            with cols[i]:
                def _fmt_kwh(v, u=unit):
                    return fmt_value(v, suffix=f" {u}", fmt_spec=",.1f")
                display, is_edited, orig = _display_value(bill, fname, key_suffix, format_fn=_fmt_kwh)
                st.markdown(
                    field_html(label, display, edited=is_edited, original=orig),
                    unsafe_allow_html=True,
                )

        # Rates row
        if any(v is not None for v in [bill.day_rate, bill.night_rate, bill.peak_rate]):
            cols = st.columns(4)
            rate_fields = [
                ("Day Rate", "day_rate"),
                ("Night Rate", "night_rate"),
                ("Peak Rate", "peak_rate"),
            ]
            for i, (label, fname) in enumerate(rate_fields):
                with cols[i]:
                    def _fmt_rate(v):
                        return f"\u20ac{v:.4f}/kWh" if v is not None else None
                    display, is_edited, orig = _display_value(bill, fname, key_suffix, format_fn=_fmt_rate)
                    st.markdown(
                        field_html(label, display, edited=is_edited, original=orig),
                        unsafe_allow_html=True,
                    )

    # --- Section 4: Costs ---
    st.subheader("\U0001f4b0 Costs")
    cols = st.columns(4)
    cost_field_names = [
        ("Day Cost", "day_cost"),
        ("Night Cost", "night_cost"),
        ("Peak Cost", "peak_cost"),
        ("Subtotal", "subtotal_before_vat"),
    ]
    for i, (label, fname) in enumerate(cost_field_names):
        with cols[i]:
            def _fmt_eur(v):
                return f"\u20ac{v:,.2f}" if v is not None else None
            display, is_edited, orig = _display_value(bill, fname, key_suffix, format_fn=_fmt_eur)
            st.markdown(
                field_html(label, display, edited=is_edited, original=orig),
                unsafe_allow_html=True,
            )

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

    # --- Inline Editing ---
    st.divider()
    with st.expander("\u270f\ufe0f Edit Extracted Values", expanded=False):
        st.caption(
            "Correct any misidentified values. Edits are marked blue and "
            "included in exports."
        )
        with st.form(key=f"edit_form{key_suffix}"):
            col1, col2 = st.columns(2)
            _edits = st.session_state.bill_edits

            with col1:
                st.markdown("**Identity & Dates**")
                ef_supplier = st.text_input(
                    "Supplier",
                    value=_edits.get(f"{key_suffix}_supplier", bill.supplier or ""),
                    key=f"ef_supplier{key_suffix}",
                )
                ef_mprn = st.text_input(
                    "MPRN",
                    value=_edits.get(f"{key_suffix}_mprn", bill.mprn or ""),
                    key=f"ef_mprn{key_suffix}",
                )
                ef_bill_date = st.text_input(
                    "Bill Date",
                    value=_edits.get(f"{key_suffix}_bill_date", bill.bill_date or ""),
                    key=f"ef_bill_date{key_suffix}",
                )
                ef_period_start = st.text_input(
                    "Period Start",
                    value=_edits.get(f"{key_suffix}_billing_period_start",
                                     bill.billing_period_start or ""),
                    key=f"ef_period_start{key_suffix}",
                )
                ef_period_end = st.text_input(
                    "Period End",
                    value=_edits.get(f"{key_suffix}_billing_period_end",
                                     bill.billing_period_end or ""),
                    key=f"ef_period_end{key_suffix}",
                )

            with col2:
                st.markdown("**Consumption & Costs**")
                ef_day_rate = st.text_input(
                    "Day Rate (\u20ac/kWh)",
                    value=str(_edits.get(f"{key_suffix}_day_rate",
                                          bill.day_rate or "")),
                    key=f"ef_day_rate{key_suffix}",
                )
                ef_night_rate = st.text_input(
                    "Night Rate (\u20ac/kWh)",
                    value=str(_edits.get(f"{key_suffix}_night_rate",
                                          bill.night_rate or "")),
                    key=f"ef_night_rate{key_suffix}",
                )
                ef_standing = st.text_input(
                    "Standing Charge (\u20ac)",
                    value=str(_edits.get(f"{key_suffix}_standing_charge_total",
                                          bill.standing_charge_total or "")),
                    key=f"ef_standing{key_suffix}",
                )
                ef_total_cost = st.text_input(
                    "Total Cost (\u20ac)",
                    value=str(_edits.get(f"{key_suffix}_total_this_period",
                                          bill.total_this_period or "")),
                    key=f"ef_total_cost{key_suffix}",
                )
                ef_amount_due = st.text_input(
                    "Amount Due (\u20ac)",
                    value=str(_edits.get(f"{key_suffix}_amount_due",
                                          bill.amount_due or "")),
                    key=f"ef_amount_due{key_suffix}",
                )

            submitted = st.form_submit_button("Save Changes", type="primary")
            if submitted:
                _edit_map = {
                    f"{key_suffix}_supplier": (ef_supplier, bill.supplier),
                    f"{key_suffix}_mprn": (ef_mprn, bill.mprn),
                    f"{key_suffix}_bill_date": (ef_bill_date, bill.bill_date),
                    f"{key_suffix}_billing_period_start": (ef_period_start, bill.billing_period_start),
                    f"{key_suffix}_billing_period_end": (ef_period_end, bill.billing_period_end),
                    f"{key_suffix}_day_rate": (ef_day_rate, bill.day_rate),
                    f"{key_suffix}_night_rate": (ef_night_rate, bill.night_rate),
                    f"{key_suffix}_standing_charge_total": (ef_standing, bill.standing_charge_total),
                    f"{key_suffix}_total_this_period": (ef_total_cost, bill.total_this_period),
                    f"{key_suffix}_amount_due": (ef_amount_due, bill.amount_due),
                }
                for edit_key, (new_val, orig_val) in _edit_map.items():
                    new_str = str(new_val).strip()
                    orig_str = str(orig_val or "").strip()
                    if new_str and new_str != orig_str:
                        # Try numeric conversion for cost/rate fields
                        try:
                            st.session_state.bill_edits[edit_key] = float(new_str)
                        except ValueError:
                            st.session_state.bill_edits[edit_key] = new_str
                    elif not new_str and edit_key in st.session_state.bill_edits:
                        del st.session_state.bill_edits[edit_key]
                st.rerun()

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
    st.caption(f"Confidence: {confidence_pct}%")

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


def show_bill_comparison(bills, edit_indices=None):
    """Display multi-bill comparison view with tabs.

    Args:
        bills: List of (bill, filename) tuples.
        edit_indices: Optional dict mapping filename -> original index for edit
            key lookup. If None, uses enumerate order.
    """
    st.subheader(f"Bill Comparison \u2014 {len(bills)} bills")

    # Build comparison DataFrame with edits applied and computed columns
    rows = []
    for i, (bill, filename) in enumerate(bills):
        # Resolve edit key_suffix from the original index (stable across filtering)
        orig_idx = (edit_indices or {}).get(filename, i)
        ks = f"_{orig_idx}"

        # Apply edits where available (10 editable fields)
        supplier = _edited_or_original(bill, 'supplier', ks) or 'Unknown'
        mprn = _edited_or_original(bill, 'mprn', ks) or ''
        bill_date_str = _edited_or_original(bill, 'bill_date', ks) or ''
        period_start_str = _edited_or_original(bill, 'billing_period_start', ks)
        period_end_str = _edited_or_original(bill, 'billing_period_end', ks)
        day_rate = _edited_or_original(bill, 'day_rate', ks)
        night_rate = _edited_or_original(bill, 'night_rate', ks)
        standing_total = _edited_or_original(bill, 'standing_charge_total', ks)
        total_cost = _edited_or_original(bill, 'total_this_period', ks)
        amount_due = _edited_or_original(bill, 'amount_due', ks)

        period_start = _parse_bill_date(period_start_str)
        period_end = _parse_bill_date(period_end_str)
        bill_date_parsed = _parse_bill_date(bill_date_str)
        sort_date = period_start or bill_date_parsed

        total_kwh = bill.total_units_kwh

        # Computed: billing days and normalised metrics
        billing_days = compute_billing_days(
            period_start_str, period_end_str
        )
        cost_per_day = (
            total_cost / billing_days
            if total_cost and billing_days and billing_days > 0
            else None
        )
        kwh_per_day = (
            total_kwh / billing_days
            if total_kwh and billing_days and billing_days > 0
            else None
        )
        effective_rate = (
            total_cost / total_kwh
            if total_cost and total_kwh and total_kwh > 0
            else None
        )
        annualised_cost = cost_per_day * 365 if cost_per_day else None
        sc_daily_rate = bill.standing_charge_rate

        rows.append({
            'filename': filename,
            'supplier': supplier,
            'mprn': mprn,
            'bill_date': bill_date_str,
            'billing_period': (
                f"{period_start_str} \u2014 {period_end_str}"
                if period_start_str and period_end_str
                else ''
            ),
            'sort_date': sort_date,
            'period_start': period_start,
            'period_end': period_end,
            'billing_days': billing_days,
            'total_kwh': total_kwh,
            'day_kwh': bill.day_units_kwh,
            'night_kwh': bill.night_units_kwh,
            'peak_kwh': bill.peak_units_kwh,
            'day_rate': day_rate,
            'night_rate': night_rate,
            'peak_rate': bill.peak_rate,
            'standing_charge': standing_total,
            'standing_charge_rate': sc_daily_rate,
            'subtotal': bill.subtotal_before_vat,
            'vat': bill.vat_amount,
            'total_cost': total_cost,
            'amount_due': amount_due,
            'confidence': bill.confidence_score,
            'cost_per_day': cost_per_day,
            'kwh_per_day': kwh_per_day,
            'effective_rate': effective_rate,
            'annualised_cost': annualised_cost,
        })

    df = pd.DataFrame(rows)

    # Sort by date if available
    if df['sort_date'].notna().any():
        df = df.sort_values('sort_date').reset_index(drop=True)

    # MPRN filter (only when multiple distinct MPRNs present)
    unique_mprns = sorted(set(m for m in df['mprn'] if m))
    if len(unique_mprns) > 1:
        import hashlib as _hl
        _mprn_hash = _hl.md5(",".join(unique_mprns).encode()).hexdigest()[:6]
        selected_mprns = st.multiselect(
            "Filter by MPRN (property)",
            options=unique_mprns,
            default=unique_mprns,
            key=f"mprn_filter_{_mprn_hash}",
        )
        if selected_mprns:
            df = df[df['mprn'].isin(selected_mprns)].reset_index(drop=True)
        if len(df) < 2:
            st.info("Select at least 2 bills for comparison.")
            return

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

    # Key metrics row 1: totals
    col1, col2, col3, col4 = st.columns(4)
    valid_costs = df['total_cost'].dropna()
    valid_kwh = df['total_kwh'].dropna()
    total_bills = len(df)
    cost_count = len(valid_costs)
    kwh_count = len(valid_kwh)

    with col1:
        total_cost = valid_costs.sum() if cost_count > 0 else 0
        cost_label = "Total Cost"
        if cost_count < total_bills:
            cost_label = f"Total Cost ({cost_count}/{total_bills} bills)"
        st.metric(
            cost_label,
            f"\u20ac{total_cost:,.2f}" if total_cost > 0 else "\u2014",
        )
    with col2:
        total_kwh = valid_kwh.sum() if kwh_count > 0 else 0
        kwh_label = "Total kWh"
        if kwh_count < total_bills:
            kwh_label = f"Total kWh ({kwh_count}/{total_bills} bills)"
        st.metric(
            kwh_label,
            f"{total_kwh:,.0f}" if total_kwh > 0 else "\u2014",
        )
    with col3:
        # Effective blended rate (total cost / total kWh across all bills)
        if total_kwh > 0 and total_cost > 0:
            blended_rate = total_cost / total_kwh
            st.metric("Effective \u20ac/kWh", f"\u20ac{blended_rate:.4f}")
        else:
            st.metric("Effective \u20ac/kWh", "\u2014")
    with col4:
        # Annualised cost projection from average cost/day
        valid_annualised = df['annualised_cost'].dropna()
        if len(valid_annualised) > 0:
            avg_annual = valid_annualised.mean()
            st.metric("Annualised Cost", f"\u20ac{avg_annual:,.0f}")
        else:
            st.metric("Annualised Cost", "\u2014")

    # Key metrics row 2: daily averages
    valid_cpd = df['cost_per_day'].dropna()
    valid_kpd = df['kwh_per_day'].dropna()
    if len(valid_cpd) > 0 or len(valid_kpd) > 0:
        col5, col6, col7, col8 = st.columns(4)
        with col5:
            if len(valid_cpd) > 0:
                st.metric("Avg Cost/Day", f"\u20ac{valid_cpd.mean():.2f}")
            else:
                st.metric("Avg Cost/Day", "\u2014")
        with col6:
            if len(valid_kpd) > 0:
                st.metric("Avg kWh/Day", f"{valid_kpd.mean():.1f}")
            else:
                st.metric("Avg kWh/Day", "\u2014")
        with col7:
            avg_cost_bill = valid_costs.mean() if cost_count > 0 else None
            label = "Avg Cost/Bill"
            if cost_count < total_bills and cost_count > 0:
                label = f"Avg Cost/Bill ({cost_count} of {total_bills})"
            st.metric(
                label,
                f"\u20ac{avg_cost_bill:,.2f}" if avg_cost_bill else "\u2014",
            )
        with col8:
            # Total billing days covered
            valid_days = df['billing_days'].dropna()
            if len(valid_days) > 0:
                st.metric("Total Days Covered", f"{int(valid_days.sum())}")
            else:
                st.metric("Total Days Covered", "\u2014")

    # Exclusion note
    excluded = total_bills - cost_count
    if excluded > 0:
        st.caption(
            f"{excluded} bill{'s' if excluded != 1 else ''} excluded from "
            f"cost aggregates (incomplete extraction)."
        )

    st.divider()

    # Add traffic-light confidence level to DataFrame
    def _conf_label(score):
        pct = round(score * 100)
        level, color, _, label, _ = _confidence_level(pct)
        return f"{label} ({pct}%)"

    df_display = df.copy()
    df_display['conf_label'] = df_display['confidence'].apply(_conf_label)

    # Display table
    display_cols = {
        'supplier': 'Supplier',
        'billing_period': 'Period',
        'billing_days': 'Days',
        'total_kwh': 'Total kWh',
        'total_cost': 'Total (\u20ac)',
        'cost_per_day': '\u20ac/Day',
        'kwh_per_day': 'kWh/Day',
        'effective_rate': 'Eff. \u20ac/kWh',
        'standing_charge': 'Standing (\u20ac)',
        'conf_label': 'Confidence',
    }

    available_cols = [c for c in display_cols if c in df_display.columns]
    display_df = df_display[available_cols].copy()

    # Format computed columns before renaming
    for col in ['cost_per_day', 'effective_rate']:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(
                lambda v: f"{v:.4f}" if pd.notna(v) else None
            )
    if 'kwh_per_day' in display_df.columns:
        display_df['kwh_per_day'] = display_df['kwh_per_day'].apply(
            lambda v: f"{v:.1f}" if pd.notna(v) else None
        )
    if 'billing_days' in display_df.columns:
        display_df['billing_days'] = display_df['billing_days'].apply(
            lambda v: str(int(v)) if pd.notna(v) else None
        )

    display_df = display_df.rename(
        columns={k: v for k, v in display_cols.items() if k in available_cols}
    )

    # Replace NaN/None with dash for display
    display_df = display_df.fillna("\u2014")

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )


def _comparison_cost_trends(df: pd.DataFrame):
    """Show cost trend chart across bills."""
    st.markdown("### Cost Trends Over Time")

    labels = df['label'].tolist()
    has_cost = df['total_cost'].notna().any()

    if not has_cost:
        st.info("No cost data available in the extracted bills.")
        return

    # Normalisation toggle
    has_daily = df['cost_per_day'].notna().any()
    normalise = False
    if has_daily:
        normalise = st.toggle(
            "Normalise by billing period (cost per day)",
            value=False,
            key="cost_normalise",
        )

    fig = go.Figure()

    if normalise:
        fig.add_trace(go.Scatter(
            x=labels,
            y=df['cost_per_day'],
            mode='lines+markers',
            name='Cost/Day',
            line=dict(color='#4ade80', width=3),
            marker=dict(size=10),
        ))
        y_title = "Cost per Day (\u20ac)"
    else:
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
        y_title = "Cost (\u20ac)"

    fig.update_layout(
        xaxis_title="Billing Period",
        yaxis_title=y_title,
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="DM Sans", color="#e2e8f0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )

    st.plotly_chart(fig, use_container_width=True)

    # Cost change summary (uses normalised values when toggle is on)
    cost_col = 'cost_per_day' if normalise else 'total_cost'
    unit = "/day" if normalise else ""
    valid = df.dropna(subset=[cost_col])
    if len(valid) >= 2:
        first_cost = valid.iloc[0][cost_col]
        last_cost = valid.iloc[-1][cost_col]
        change = last_cost - first_cost
        change_pct = (change / first_cost * 100) if first_cost else 0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("First Bill", f"\u20ac{first_cost:,.2f}{unit}")
        with col2:
            st.metric("Latest Bill", f"\u20ac{last_cost:,.2f}{unit}")
        with col3:
            st.metric("Change", f"\u20ac{change:+,.2f}{unit}", delta=f"{change_pct:+.1f}%")


def _comparison_consumption(df: pd.DataFrame):
    """Show consumption trend charts."""
    st.markdown("### Consumption Trends")

    labels = df['label'].tolist()
    has_kwh = df['total_kwh'].notna().any()

    if not has_kwh:
        st.info("No consumption data available in the extracted bills.")
        return

    # Normalisation toggle
    has_daily = df['kwh_per_day'].notna().any()
    normalise = False
    if has_daily:
        normalise = st.toggle(
            "Normalise by billing period (kWh per day)",
            value=False,
            key="consumption_normalise",
        )

    # Total consumption bar chart
    fig = go.Figure()
    if normalise:
        y_vals = df['kwh_per_day']
        y_title = "Consumption (kWh/day)"
        fmt_fn = lambda v: f"{v:.1f}" if pd.notna(v) else ""
    else:
        y_vals = df['total_kwh']
        y_title = "Consumption (kWh)"
        fmt_fn = lambda v: f"{v:,.0f}" if pd.notna(v) else ""

    fig.add_trace(go.Bar(
        x=labels,
        y=y_vals,
        name='kWh/day' if normalise else 'Total kWh',
        marker_color='#4ade80',
        text=[fmt_fn(v) for v in y_vals],
        textposition='auto',
    ))
    fig.update_layout(
        xaxis_title="Billing Period",
        yaxis_title=y_title,
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="DM Sans", color="#e2e8f0"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Day/Night/Peak breakdown (raw only — normalising breakdown per day
    # would require per-component billing days which we don't have)
    if not normalise:
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
    kwh_col = 'kwh_per_day' if normalise else 'total_kwh'
    unit = " kWh/day" if normalise else " kWh"
    valid = df.dropna(subset=[kwh_col])
    if len(valid) >= 2:
        st.divider()
        first = valid.iloc[0][kwh_col]
        last = valid.iloc[-1][kwh_col]
        change = last - first
        change_pct = (change / first * 100) if first else 0

        fmt = ".1f" if normalise else ",.0f"
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("First Bill", f"{first:{fmt}}{unit}")
        with col2:
            st.metric("Latest Bill", f"{last:{fmt}}{unit}")
        with col3:
            st.metric("Change", f"{change:+{fmt}}{unit}", delta=f"{change_pct:+.1f}%")


def _comparison_rates(df: pd.DataFrame):
    """Show rate comparison across bills."""
    st.markdown("### Rate Analysis")

    has_rates = (
        df['day_rate'].notna().any()
        or df['night_rate'].notna().any()
        or df['peak_rate'].notna().any()
    )
    has_effective = df['effective_rate'].notna().any()

    if not has_rates and not has_effective:
        st.info("No unit rate data available in the extracted bills.")
        return

    labels = df['label'].tolist()

    # --- Tariff rates chart ---
    if has_rates:
        st.markdown("#### Unit Tariff Rates")
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

    # --- Effective blended rate chart ---
    if has_effective:
        st.markdown("#### Effective Blended Rate")
        st.caption(
            "Total cost \u00f7 total kWh per bill \u2014 captures the real cost "
            "including standing charges, PSO, VAT, and tariff mix."
        )
        fig_eff = go.Figure()
        fig_eff.add_trace(go.Scatter(
            x=labels, y=df['effective_rate'],
            mode='lines+markers', name='Effective \u20ac/kWh',
            line=dict(color='#4ade80', width=3),
            marker=dict(size=10),
        ))
        fig_eff.update_layout(
            xaxis_title="Billing Period",
            yaxis_title="Effective Rate (\u20ac/kWh)",
            template="plotly_dark",
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(family="DM Sans", color="#e2e8f0"),
            hovermode="x unified",
        )
        st.plotly_chart(fig_eff, use_container_width=True)

    # --- Standing charge daily rate ---
    if df['standing_charge_rate'].notna().any():
        st.markdown("#### Standing Charge Daily Rate")
        fig_sc = go.Figure()
        fig_sc.add_trace(go.Scatter(
            x=labels, y=df['standing_charge_rate'],
            mode='lines+markers', name='Standing \u20ac/day',
            line=dict(color='#f59e0b', width=2),
            marker=dict(size=8),
        ))
        fig_sc.update_layout(
            xaxis_title="Billing Period",
            yaxis_title="Standing Charge (\u20ac/day)",
            template="plotly_dark",
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(family="DM Sans", color="#e2e8f0"),
            hovermode="x unified",
        )
        st.plotly_chart(fig_sc, use_container_width=True)

    # Rate change table
    st.markdown("#### Rate Changes")
    rate_data = []
    rate_items = [
        ('Day', 'day_rate'), ('Night', 'night_rate'), ('Peak', 'peak_rate'),
        ('Effective (blended)', 'effective_rate'),
        ('Standing (\u20ac/day)', 'standing_charge_rate'),
    ]
    for rate_name, rate_col in rate_items:
        if rate_col not in df.columns:
            continue
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
    """Generate Excel comparison workbook with computed columns and totals."""
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        # Summary sheet — includes computed columns
        summary_cols = [
            'filename', 'supplier', 'mprn', 'bill_date', 'billing_period',
            'billing_days', 'total_kwh', 'day_kwh', 'night_kwh', 'peak_kwh',
            'day_rate', 'night_rate', 'peak_rate',
            'standing_charge', 'standing_charge_rate',
            'subtotal', 'vat', 'total_cost', 'amount_due',
            'cost_per_day', 'kwh_per_day', 'effective_rate', 'annualised_cost',
        ]
        summary_labels = {
            'filename': 'File', 'supplier': 'Supplier', 'mprn': 'MPRN',
            'bill_date': 'Bill Date', 'billing_period': 'Billing Period',
            'billing_days': 'Billing Days',
            'total_kwh': 'Total kWh', 'day_kwh': 'Day kWh',
            'night_kwh': 'Night kWh', 'peak_kwh': 'Peak kWh',
            'day_rate': 'Day Rate (\u20ac/kWh)', 'night_rate': 'Night Rate (\u20ac/kWh)',
            'peak_rate': 'Peak Rate (\u20ac/kWh)',
            'standing_charge': 'Standing Charge (\u20ac)',
            'standing_charge_rate': 'Standing \u20ac/day',
            'subtotal': 'Subtotal (\u20ac)',
            'vat': 'VAT (\u20ac)', 'total_cost': 'Total Cost (\u20ac)',
            'amount_due': 'Amount Due (\u20ac)',
            'cost_per_day': 'Cost/Day (\u20ac)',
            'kwh_per_day': 'kWh/Day',
            'effective_rate': 'Effective \u20ac/kWh',
            'annualised_cost': 'Annualised Cost (\u20ac)',
        }

        available = [c for c in summary_cols if c in df.columns]
        export_df = df[available].copy()

        # Build totals/averages row
        totals = {}
        for col in available:
            if col in ('filename',):
                totals[col] = 'TOTAL / AVG'
            elif col in ('supplier', 'mprn', 'bill_date', 'billing_period'):
                totals[col] = ''
            elif col in ('total_kwh', 'day_kwh', 'night_kwh', 'peak_kwh',
                         'standing_charge', 'subtotal', 'vat', 'total_cost',
                         'amount_due', 'billing_days'):
                totals[col] = df[col].sum() if df[col].notna().any() else None
            elif col in ('day_rate', 'night_rate', 'peak_rate',
                         'standing_charge_rate', 'cost_per_day', 'kwh_per_day',
                         'effective_rate', 'annualised_cost'):
                totals[col] = df[col].mean() if df[col].notna().any() else None

        totals_row = pd.DataFrame([totals])
        export_df = pd.concat([export_df, totals_row], ignore_index=True)

        export_df = export_df.rename(
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

# Process new uploads (deduplicate by content hash)
if uploaded_files:
    new_files = []
    for f in uploaded_files:
        file_content = f.getvalue()
        file_hash = content_hash(file_content)
        if file_hash not in st.session_state.processed_hashes:
            new_files.append((file_content, f.name, file_hash))

    if new_files:
        total = len(new_files)
        with st.status(
            f"Processing {total} bill{'s' if total > 1 else ''}...",
            expanded=True,
        ) as status:
            for i, (file_content, filename, file_hash) in enumerate(new_files):
                st.write(f"Extracting **{filename}** ({i + 1}/{total})")
                result = _extract_bill(file_content, filename)
                st.session_state.extracted_bills.append(result)
                st.session_state.processed_hashes.add(file_hash)
                if result["status"] == "success":
                    supplier = result["supplier"] or "Unknown"
                    conf = round(result["confidence"] * 100)
                    st.write(f"  {supplier} \u2014 {conf}% confidence")
                else:
                    st.write(f"  Failed: {result['error']}")
            status.update(
                label=f"Extracted {total} bill{'s' if total > 1 else ''}",
                state="complete",
            )
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
# Stable index mapping: filename -> original position (for edit key lookup)
_edit_indices = {fn: idx for idx, (_, fn) in enumerate(successful_bills)}
error_bills = [b for b in bills if b["status"] == "error"]

# Show errors with actionable guidance
for entry in error_bills:
    fname = entry["filename"]
    is_image = fname.lower().endswith(('.jpg', '.jpeg', '.png'))
    if is_image:
        suggestions = (
            '<ol class="suggestion-list">'
            '<li>Ensure the photo has good lighting and is in focus</li>'
            '<li>Flatten the bill before photographing (avoid creases)</li>'
            '<li>Use the PDF version of the bill if available</li>'
            '</ol>'
        )
    else:
        suggestions = (
            '<ol class="suggestion-list">'
            '<li>Check the file is not password-protected</li>'
            '<li>Ensure it is a valid electricity bill PDF</li>'
            '<li>If scanned, ensure the text is legible</li>'
            '</ol>'
        )
    st.markdown(
        f'<div class="extraction-failed-card">'
        f'<h4>Could not extract {fname}</h4>'
        f'<p style="color: #94a3b8; font-size: 0.9rem; margin-bottom: 0.75rem;">'
        f'{entry["error"]}</p>'
        f'<p style="color: #cbd5e1; font-size: 0.85rem; font-weight: 600; '
        f'margin-bottom: 0.25rem;">Suggestions:</p>'
        f'{suggestions}'
        f'</div>',
        unsafe_allow_html=True,
    )

if len(successful_bills) == 1:
    # Single bill detail view
    bill, filename = successful_bills[0]
    raw_text = next(
        (b["raw_text"] for b in bills if b["filename"] == filename), None
    )
    show_bill_summary(bill, raw_text=raw_text)

elif len(successful_bills) >= 2:
    # Bill inclusion filter — allows excluding individual bills from comparison
    all_fns = [fn for _, fn in successful_bills]
    import hashlib as _hl_filter
    _fns_hash = _hl_filter.md5(",".join(all_fns).encode()).hexdigest()[:6]
    included_fns = st.multiselect(
        "Bills included in comparison",
        options=all_fns,
        default=all_fns,
        key=f"bill_include_filter_{_fns_hash}",
    )
    filtered_bills = [
        (b, fn) for b, fn in successful_bills if fn in included_fns
    ]

    if len(filtered_bills) >= 2:
        # Comparison view at top (pass stable edit indices)
        show_bill_comparison(filtered_bills, edit_indices=_edit_indices)
    elif len(filtered_bills) == 1:
        bill, filename = filtered_bills[0]
        idx = _edit_indices[filename]
        raw_text = next(
            (b["raw_text"] for b in bills if b["filename"] == filename), None
        )
        show_bill_summary(bill, raw_text=raw_text, key_suffix=f"_{idx}")

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
    # Empty state — polished card
    st.markdown(
        """
        <div class="empty-state-card">
            <div class="empty-icon">\U0001f4c4</div>
            <h3>Upload Electricity Bills</h3>
            <p>
                Drag and drop PDF or photographed bills above.<br>
                Upload more at any time to compare across periods.
            </p>
            <div class="format-tags">
                <span class="format-tag">PDF</span>
                <span class="format-tag">JPG</span>
                <span class="format-tag">PNG</span>
                <span class="format-tag">Scanned</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
