"""
Bill Verification — Cross-reference HDF smart meter data with bill extractions.

Compares actual meter readings (HDF 30-min interval data) against billed
consumption and costs. Identifies billing errors, overcharging, and
metering discrepancies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import pandas as pd

from bill_parser import BillData
from hdf_parser import PROVIDER_PRESETS, CEG_RATE_EUR


# ---------------------------------------------------------------------------
# Date parsing (reuses the formats from main._parse_bill_date)
# ---------------------------------------------------------------------------

_DATE_FORMATS = [
    "%d/%m/%Y", "%d %b %Y", "%d %B %Y", "%d.%m.%Y",
    "%Y-%m-%d", "%d-%m-%Y",
]


def parse_bill_date(date_str: str | None) -> date | None:
    """Parse a date string from bill extraction. Returns date or None."""
    if not date_str:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass
class VerificationResult:
    """Result of cross-referencing HDF data with a bill."""

    # MPRN check
    valid: bool = True
    hdf_mprn: str = ""
    bill_mprn: str = ""
    mprn_match: bool = False

    # Date overlap
    bill_start: Optional[date] = None
    bill_end: Optional[date] = None
    hdf_start: Optional[date] = None
    hdf_end: Optional[date] = None
    overlap_days: int = 0
    billing_days: int = 0
    overlap_pct: float = 0.0

    # Issues / warnings
    issues: list[str] = field(default_factory=list)
    block_reason: str = ""

    # Consumption comparison
    hdf_total_kwh: float = 0.0
    hdf_day_kwh: float = 0.0
    hdf_night_kwh: float = 0.0
    hdf_peak_kwh: float = 0.0
    hdf_export_kwh: float = 0.0

    bill_total_kwh: Optional[float] = None
    bill_day_kwh: Optional[float] = None
    bill_night_kwh: Optional[float] = None
    bill_peak_kwh: Optional[float] = None

    # Cost verification
    expected_cost_day: Optional[float] = None
    expected_cost_night: Optional[float] = None
    expected_cost_peak: Optional[float] = None
    expected_cost_total: Optional[float] = None
    bill_cost_total: Optional[float] = None

    # Rate comparison
    bill_day_rate: Optional[float] = None
    bill_night_rate: Optional[float] = None
    bill_peak_rate: Optional[float] = None

    # Standing charge
    bill_standing_days: Optional[int] = None
    bill_standing_total: Optional[float] = None

    # Export
    bill_export_units: Optional[float] = None
    bill_export_credit: Optional[float] = None


def validate_cross_reference(
    hdf_df: pd.DataFrame,
    hdf_mprn: str,
    bill: BillData,
) -> VerificationResult:
    """Validate that HDF data and bill can be cross-referenced.

    Checks MPRN match and date overlap. Does NOT compute consumption
    comparisons — that's done by compute_verification() after validation.
    """
    result = VerificationResult()
    result.hdf_mprn = hdf_mprn

    # --- MPRN check ---
    result.bill_mprn = bill.mprn or ""
    if not bill.mprn:
        result.valid = False
        result.block_reason = "Bill has no MPRN — cannot verify against meter data."
        return result

    result.mprn_match = result.hdf_mprn.strip() == result.bill_mprn.strip()
    if not result.mprn_match:
        result.valid = False
        result.block_reason = (
            f"Bill MPRN ({result.bill_mprn}) does not match "
            f"meter data MPRN ({result.hdf_mprn}). "
            f"Cannot compare data from different meters."
        )
        return result

    # --- Date overlap check ---
    result.bill_start = parse_bill_date(bill.billing_period_start)
    result.bill_end = parse_bill_date(bill.billing_period_end)

    if not result.bill_start or not result.bill_end:
        result.valid = False
        result.block_reason = "Bill has no billing period dates — cannot filter meter data."
        return result

    # HDF date range
    if 'datetime' in hdf_df.columns:
        result.hdf_start = hdf_df['datetime'].min().date()
        result.hdf_end = hdf_df['datetime'].max().date()
    else:
        result.valid = False
        result.block_reason = "HDF data has no datetime column."
        return result

    result.billing_days = (result.bill_end - result.bill_start).days
    if result.billing_days <= 0:
        result.valid = False
        result.block_reason = "Bill period end is before or equal to start date."
        return result

    # Calculate overlap
    overlap_start = max(result.bill_start, result.hdf_start)
    overlap_end = min(result.bill_end, result.hdf_end)
    result.overlap_days = max(0, (overlap_end - overlap_start).days)
    result.overlap_pct = (result.overlap_days / result.billing_days) * 100

    if result.overlap_days == 0:
        result.valid = False
        result.block_reason = (
            f"Bill period ({result.bill_start.strftime('%d %b %Y')} — "
            f"{result.bill_end.strftime('%d %b %Y')}) falls outside "
            f"HDF data range ({result.hdf_start.strftime('%d %b %Y')} — "
            f"{result.hdf_end.strftime('%d %b %Y')})."
        )
        return result

    if result.overlap_pct < 50:
        result.issues.append(
            f"Only {result.overlap_days} of {result.billing_days} billing days "
            f"covered by meter data ({result.overlap_pct:.0f}%). "
            f"Results may not be representative."
        )

    if result.overlap_pct < 100:
        result.issues.append(
            f"Meter data covers {result.overlap_pct:.0f}% of the billing period "
            f"({result.overlap_days}/{result.billing_days} days)."
        )

    return result


def compute_verification(
    hdf_df: pd.DataFrame,
    bill: BillData,
    verification: VerificationResult,
) -> VerificationResult:
    """Compute consumption and cost comparisons between HDF data and bill.

    Must be called after validate_cross_reference() returns valid=True.
    Modifies and returns the same VerificationResult with populated
    comparison fields.
    """
    if not verification.valid:
        return verification

    # Filter HDF to billing period
    bill_start = verification.bill_start
    bill_end = verification.bill_end
    mask = (
        (hdf_df['datetime'].dt.date >= bill_start)
        & (hdf_df['datetime'].dt.date <= bill_end)
    )
    filtered = hdf_df[mask].copy()

    if len(filtered) == 0:
        verification.issues.append("No HDF readings found within the billing period.")
        return verification

    # --- Consumption from HDF ---
    verification.hdf_total_kwh = filtered['import_kwh'].sum()

    if 'tariff_period' in filtered.columns:
        tariff_sums = filtered.groupby('tariff_period')['import_kwh'].sum()
        verification.hdf_day_kwh = tariff_sums.get('Day', 0.0)
        verification.hdf_night_kwh = tariff_sums.get('Night', 0.0)
        verification.hdf_peak_kwh = tariff_sums.get('Peak', 0.0)

    if 'export_kwh' in filtered.columns:
        verification.hdf_export_kwh = filtered['export_kwh'].sum()

    # --- Consumption from bill ---
    verification.bill_total_kwh = bill.total_units_kwh
    verification.bill_day_kwh = bill.day_units_kwh
    verification.bill_night_kwh = bill.night_units_kwh
    verification.bill_peak_kwh = bill.peak_units_kwh

    # --- Rates from bill ---
    verification.bill_day_rate = bill.day_rate
    verification.bill_night_rate = bill.night_rate
    verification.bill_peak_rate = bill.peak_rate

    # --- Cost verification: HDF consumption x bill rates ---
    if bill.day_rate is not None:
        verification.expected_cost_day = verification.hdf_day_kwh * bill.day_rate
    if bill.night_rate is not None:
        verification.expected_cost_night = verification.hdf_night_kwh * bill.night_rate
    if bill.peak_rate is not None:
        verification.expected_cost_peak = verification.hdf_peak_kwh * bill.peak_rate

    cost_parts = [
        verification.expected_cost_day,
        verification.expected_cost_night,
        verification.expected_cost_peak,
    ]
    if any(c is not None for c in cost_parts):
        verification.expected_cost_total = sum(c for c in cost_parts if c is not None)

    verification.bill_cost_total = bill.total_this_period

    # --- Standing charge ---
    verification.bill_standing_days = bill.standing_charge_days
    verification.bill_standing_total = bill.standing_charge_total

    # --- Export ---
    verification.bill_export_units = bill.export_units
    verification.bill_export_credit = bill.export_credit

    return verification


def _pct_diff(a: float | None, b: float | None) -> float | None:
    """Calculate percentage difference between two values. Returns None if either is None."""
    if a is None or b is None or a == 0:
        return None
    return ((b - a) / a) * 100


def get_consumption_deltas(v: VerificationResult) -> list[dict]:
    """Build comparison rows for the consumption table."""
    rows = []

    def _row(label, hdf_val, bill_val):
        delta = None
        pct = None
        if hdf_val is not None and bill_val is not None:
            delta = bill_val - hdf_val
            pct = _pct_diff(hdf_val, bill_val)
        rows.append({
            'Period': label,
            'Meter (kWh)': hdf_val,
            'Bill (kWh)': bill_val,
            'Delta (kWh)': delta,
            'Delta (%)': pct,
        })

    _row('Day', v.hdf_day_kwh, v.bill_day_kwh)
    _row('Night', v.hdf_night_kwh, v.bill_night_kwh)
    _row('Peak', v.hdf_peak_kwh, v.bill_peak_kwh)
    _row('Total', v.hdf_total_kwh, v.bill_total_kwh)

    return rows


def get_rate_comparison(v: VerificationResult, provider: str | None = None) -> list[dict]:
    """Build comparison rows for rate analysis."""
    preset = PROVIDER_PRESETS.get(provider or '', None)
    rows = []

    def _row(label, bill_rate, preset_key):
        preset_rate = None
        if preset and preset_key in preset:
            preset_rate = preset[preset_key] / 100  # c/kWh -> EUR/kWh
        rows.append({
            'Period': label,
            'Bill Rate (EUR/kWh)': bill_rate,
            'Preset Rate (EUR/kWh)': preset_rate,
        })

    _row('Day', v.bill_day_rate, 'day')
    _row('Night', v.bill_night_rate, 'night')
    _row('Peak', v.bill_peak_rate, 'peak')

    return rows
