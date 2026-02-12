"""
Unit tests for bill_verification module.

Tests the cross-reference validation logic between HDF smart meter data
and bill extractions.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, date

from bill_parser import BillData
from bill_verification import (
    parse_bill_date,
    validate_cross_reference,
    compute_verification,
    get_consumption_deltas,
    get_rate_comparison,
    VerificationResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_hdf_df(
    mprn: str = "10306268587",
    start_date: str = "2025-03-01",
    end_date: str = "2025-03-31",
    daily_import: float = 20.0,
) -> pd.DataFrame:
    """Create a synthetic HDF DataFrame for testing.

    Generates 30-min interval data for the specified date range.
    """
    dates = pd.date_range(start=start_date, end=end_date, freq="30min", tz="Europe/Dublin")
    n = len(dates)

    # Distribute consumption across tariff periods
    hours = dates.hour
    import_kwh = np.where(
        (hours >= 23) | (hours < 8),  # Night
        0.3,
        np.where(
            (hours >= 17) & (hours < 19),  # Peak
            0.8,
            0.5,  # Day
        ),
    )

    # Add some export during day
    export_kwh = np.where(
        (hours >= 10) & (hours < 16),
        0.1,
        0.0,
    )

    df = pd.DataFrame({
        'datetime': dates,
        'mprn': mprn,
        'import_kwh': import_kwh,
        'export_kwh': export_kwh,
        'hour': hours,
    })

    # Add tariff_period
    from hdf_parser import classify_tariff_period
    df['tariff_period'] = df['hour'].apply(classify_tariff_period)
    df['date'] = df['datetime'].dt.date

    return df


def _make_bill(
    mprn: str = "10306268587",
    billing_start: str = "01/03/2025",
    billing_end: str = "31/03/2025",
    day_kwh: float = 300.0,
    night_kwh: float = 150.0,
    peak_kwh: float = 50.0,
    day_rate: float = 0.2814,
    night_rate: float = 0.1479,
    peak_rate: float = 0.3002,
    total: float = 130.0,
    supplier: str = "Energia",
) -> BillData:
    """Create a synthetic BillData for testing."""
    bill = BillData()
    bill.mprn = mprn
    bill.supplier = supplier
    bill.billing_period_start = billing_start
    bill.billing_period_end = billing_end
    bill.day_units_kwh = day_kwh
    bill.night_units_kwh = night_kwh
    bill.peak_units_kwh = peak_kwh
    bill.total_units_kwh = day_kwh + night_kwh + peak_kwh
    bill.day_rate = day_rate
    bill.night_rate = night_rate
    bill.peak_rate = peak_rate
    bill.total_this_period = total
    bill.standing_charge_days = 31
    bill.standing_charge_total = 8.87
    return bill


# ---------------------------------------------------------------------------
# parse_bill_date tests
# ---------------------------------------------------------------------------

class TestParseBillDate:

    def test_dd_mm_yyyy_slash(self):
        assert parse_bill_date("01/03/2025") == date(2025, 3, 1)

    def test_dd_mon_yyyy(self):
        assert parse_bill_date("1 Mar 2025") == date(2025, 3, 1)

    def test_dd_month_yyyy(self):
        assert parse_bill_date("1 March 2025") == date(2025, 3, 1)

    def test_dd_mm_yyyy_dot(self):
        assert parse_bill_date("01.03.2025") == date(2025, 3, 1)

    def test_iso_format(self):
        assert parse_bill_date("2025-03-01") == date(2025, 3, 1)

    def test_dd_mm_yyyy_dash(self):
        assert parse_bill_date("01-03-2025") == date(2025, 3, 1)

    def test_none_input(self):
        assert parse_bill_date(None) is None

    def test_empty_string(self):
        assert parse_bill_date("") is None

    def test_garbage_input(self):
        assert parse_bill_date("not a date") is None

    def test_whitespace_trimmed(self):
        assert parse_bill_date("  01/03/2025  ") == date(2025, 3, 1)


# ---------------------------------------------------------------------------
# validate_cross_reference tests
# ---------------------------------------------------------------------------

class TestValidateCrossReference:

    def test_valid_full_overlap(self):
        hdf_df = _make_hdf_df()
        bill = _make_bill()
        result = validate_cross_reference(hdf_df, "10306268587", bill)

        assert result.valid is True
        assert result.mprn_match is True
        assert result.overlap_pct == 100.0
        assert result.billing_days == 30

    def test_mprn_mismatch_blocks(self):
        hdf_df = _make_hdf_df(mprn="10306268587")
        bill = _make_bill(mprn="10006002900")
        result = validate_cross_reference(hdf_df, "10306268587", bill)

        assert result.valid is False
        assert "does not match" in result.block_reason
        assert result.mprn_match is False

    def test_no_mprn_on_bill_blocks(self):
        hdf_df = _make_hdf_df()
        bill = _make_bill(mprn=None)
        result = validate_cross_reference(hdf_df, "10306268587", bill)

        assert result.valid is False
        assert "no MPRN" in result.block_reason

    def test_no_billing_dates_blocks(self):
        hdf_df = _make_hdf_df()
        bill = _make_bill(billing_start=None, billing_end=None)
        result = validate_cross_reference(hdf_df, "10306268587", bill)

        assert result.valid is False
        assert "no billing period" in result.block_reason

    def test_zero_overlap_blocks(self):
        # HDF covers March 2025, bill covers June 2025
        hdf_df = _make_hdf_df(start_date="2025-03-01", end_date="2025-03-31")
        bill = _make_bill(billing_start="01/06/2025", billing_end="30/06/2025")
        result = validate_cross_reference(hdf_df, "10306268587", bill)

        assert result.valid is False
        assert "falls outside" in result.block_reason

    def test_partial_overlap_warns(self):
        # HDF covers March 1-15, bill covers full March
        hdf_df = _make_hdf_df(start_date="2025-03-01", end_date="2025-03-15")
        bill = _make_bill(billing_start="01/03/2025", billing_end="31/03/2025")
        result = validate_cross_reference(hdf_df, "10306268587", bill)

        assert result.valid is True
        assert result.overlap_pct < 100
        assert any("may not be representative" in i for i in result.issues)


# ---------------------------------------------------------------------------
# compute_verification tests
# ---------------------------------------------------------------------------

class TestComputeVerification:

    def test_consumption_computed(self):
        hdf_df = _make_hdf_df()
        bill = _make_bill()
        v = validate_cross_reference(hdf_df, "10306268587", bill)
        v = compute_verification(hdf_df, bill, v)

        assert v.hdf_total_kwh > 0
        assert v.hdf_day_kwh > 0
        assert v.hdf_night_kwh > 0
        assert v.hdf_peak_kwh > 0

    def test_bill_fields_populated(self):
        hdf_df = _make_hdf_df()
        bill = _make_bill()
        v = validate_cross_reference(hdf_df, "10306268587", bill)
        v = compute_verification(hdf_df, bill, v)

        assert v.bill_total_kwh == bill.total_units_kwh
        assert v.bill_day_kwh == bill.day_units_kwh
        assert v.bill_day_rate == bill.day_rate

    def test_expected_cost_calculated(self):
        hdf_df = _make_hdf_df()
        bill = _make_bill()
        v = validate_cross_reference(hdf_df, "10306268587", bill)
        v = compute_verification(hdf_df, bill, v)

        assert v.expected_cost_day is not None
        assert v.expected_cost_night is not None
        assert v.expected_cost_total is not None
        assert v.expected_cost_total > 0

    def test_expected_cost_is_hdf_kwh_times_bill_rate(self):
        hdf_df = _make_hdf_df()
        bill = _make_bill()
        v = validate_cross_reference(hdf_df, "10306268587", bill)
        v = compute_verification(hdf_df, bill, v)

        # Verify the formula: expected_cost = hdf_kwh * bill_rate
        assert abs(v.expected_cost_day - (v.hdf_day_kwh * bill.day_rate)) < 0.01
        assert abs(v.expected_cost_night - (v.hdf_night_kwh * bill.night_rate)) < 0.01

    def test_export_kwh_computed(self):
        hdf_df = _make_hdf_df()
        bill = _make_bill()
        v = validate_cross_reference(hdf_df, "10306268587", bill)
        v = compute_verification(hdf_df, bill, v)

        assert v.hdf_export_kwh > 0

    def test_standing_charge_from_bill(self):
        hdf_df = _make_hdf_df()
        bill = _make_bill()
        v = validate_cross_reference(hdf_df, "10306268587", bill)
        v = compute_verification(hdf_df, bill, v)

        assert v.bill_standing_days == 31
        assert v.bill_standing_total == 8.87

    def test_invalid_result_short_circuits(self):
        hdf_df = _make_hdf_df()
        bill = _make_bill(mprn="99999999999")
        v = validate_cross_reference(hdf_df, "10306268587", bill)
        # v.valid is False due to MPRN mismatch
        v = compute_verification(hdf_df, bill, v)
        # Should not compute anything
        assert v.hdf_total_kwh == 0.0


# ---------------------------------------------------------------------------
# get_consumption_deltas tests
# ---------------------------------------------------------------------------

class TestGetConsumptionDeltas:

    def test_returns_four_rows(self):
        hdf_df = _make_hdf_df()
        bill = _make_bill()
        v = validate_cross_reference(hdf_df, "10306268587", bill)
        v = compute_verification(hdf_df, bill, v)

        deltas = get_consumption_deltas(v)
        assert len(deltas) == 4
        periods = [d['Period'] for d in deltas]
        assert periods == ['Day', 'Night', 'Peak', 'Total']

    def test_delta_calculation(self):
        hdf_df = _make_hdf_df()
        bill = _make_bill(day_kwh=100.0)  # Intentionally different from HDF
        v = validate_cross_reference(hdf_df, "10306268587", bill)
        v = compute_verification(hdf_df, bill, v)

        deltas = get_consumption_deltas(v)
        day_row = deltas[0]
        assert day_row['Meter (kWh)'] == v.hdf_day_kwh
        assert day_row['Bill (kWh)'] == 100.0
        assert day_row['Delta (kWh)'] == pytest.approx(100.0 - v.hdf_day_kwh, abs=0.1)


# ---------------------------------------------------------------------------
# get_rate_comparison tests
# ---------------------------------------------------------------------------

class TestGetRateComparison:

    def test_returns_three_rows(self):
        v = VerificationResult()
        v.bill_day_rate = 0.28
        v.bill_night_rate = 0.15
        v.bill_peak_rate = 0.30

        rows = get_rate_comparison(v, provider="Energia")
        assert len(rows) == 3
        periods = [r['Period'] for r in rows]
        assert periods == ['Day', 'Night', 'Peak']

    def test_preset_rates_populated_for_known_provider(self):
        v = VerificationResult()
        v.bill_day_rate = 0.28

        rows = get_rate_comparison(v, provider="Energia")
        day_row = rows[0]
        assert day_row['Preset Rate (EUR/kWh)'] is not None
        # Energia day rate is 27.81 c/kWh = 0.2781 EUR/kWh
        assert abs(day_row['Preset Rate (EUR/kWh)'] - 0.2781) < 0.001

    def test_preset_rates_none_for_unknown_provider(self):
        v = VerificationResult()
        v.bill_day_rate = 0.28

        rows = get_rate_comparison(v, provider="UnknownProvider")
        day_row = rows[0]
        assert day_row['Preset Rate (EUR/kWh)'] is None
