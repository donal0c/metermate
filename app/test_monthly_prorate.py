"""Unit tests for calendar-month pro-rating logic.

Tests split_period_into_months (date range → monthly segments)
and build_monthly_df (comparison DataFrame → monthly aggregation).
"""

from datetime import date

import pandas as pd
import pytest

from common.formatters import split_period_into_months, build_monthly_df


# ---------------------------------------------------------------------------
# split_period_into_months
# ---------------------------------------------------------------------------

class TestSplitPeriodIntoMonths:
    """Test splitting a date range into per-month segments."""

    def test_single_month(self):
        """Period entirely within one month."""
        segments = split_period_into_months(date(2025, 3, 5), date(2025, 3, 20))
        assert segments == [(date(2025, 3, 1), 15)]

    def test_full_single_month(self):
        """Period covering an entire month."""
        segments = split_period_into_months(date(2025, 3, 1), date(2025, 4, 1))
        assert segments == [(date(2025, 3, 1), 31)]

    def test_two_months(self):
        """Period spanning two months (end is exclusive)."""
        # Jan 15 to Feb 10 = 26 total days
        # Jan 15 to Feb 1 = 17 days in Jan
        # Feb 1 to Feb 10 = 9 days in Feb
        segments = split_period_into_months(date(2025, 1, 15), date(2025, 2, 10))
        assert len(segments) == 2
        assert segments[0] == (date(2025, 1, 1), 17)  # Jan 15–31
        assert segments[1] == (date(2025, 2, 1), 9)   # Feb 1–9 (end exclusive)

    def test_three_months(self):
        """Period spanning three months."""
        # Jan 15 to Mar 14 = 58 total days
        # Jan: 17, Feb: 28, Mar: 13
        segments = split_period_into_months(date(2025, 1, 15), date(2025, 3, 14))
        assert len(segments) == 3
        assert segments[0] == (date(2025, 1, 1), 17)   # Jan 15–31
        assert segments[1] == (date(2025, 2, 1), 28)   # All of Feb 2025
        assert segments[2] == (date(2025, 3, 1), 13)   # Mar 1–13 (end exclusive)

    def test_year_boundary(self):
        """Period crossing a year boundary."""
        # Dec 15 to Jan 10 = 26 total days
        # Dec: 17, Jan: 9
        segments = split_period_into_months(date(2024, 12, 15), date(2025, 1, 10))
        assert len(segments) == 2
        assert segments[0] == (date(2024, 12, 1), 17)  # Dec 15–31
        assert segments[1] == (date(2025, 1, 1), 9)    # Jan 1–9 (end exclusive)

    def test_leap_year_february(self):
        """Period through February in a leap year."""
        segments = split_period_into_months(date(2024, 2, 1), date(2024, 3, 1))
        assert segments == [(date(2024, 2, 1), 29)]

    def test_non_leap_year_february(self):
        """Period through February in a non-leap year."""
        segments = split_period_into_months(date(2025, 2, 1), date(2025, 3, 1))
        assert segments == [(date(2025, 2, 1), 28)]

    def test_single_day(self):
        """Period of exactly one day."""
        segments = split_period_into_months(date(2025, 6, 15), date(2025, 6, 16))
        assert segments == [(date(2025, 6, 1), 1)]

    def test_empty_period(self):
        """Start equals end (zero-day period)."""
        segments = split_period_into_months(date(2025, 3, 1), date(2025, 3, 1))
        assert segments == []

    def test_reversed_dates(self):
        """End before start should return empty."""
        segments = split_period_into_months(date(2025, 3, 10), date(2025, 3, 5))
        assert segments == []

    def test_twelve_months(self):
        """Period spanning a full year."""
        segments = split_period_into_months(date(2024, 1, 1), date(2025, 1, 1))
        assert len(segments) == 12
        total_days = sum(d for _, d in segments)
        assert total_days == 366  # 2024 is a leap year

    def test_days_sum_equals_total(self):
        """Overlap days should sum to (end - start).days."""
        start, end = date(2025, 1, 15), date(2025, 4, 20)
        segments = split_period_into_months(start, end)
        assert sum(d for _, d in segments) == (end - start).days


# ---------------------------------------------------------------------------
# build_monthly_df
# ---------------------------------------------------------------------------

def _make_df(rows):
    """Helper to create a comparison-like DataFrame."""
    defaults = {
        'period_start': None, 'period_end': None,
        'total_cost': None, 'total_kwh': None,
        'day_kwh': None, 'night_kwh': None, 'peak_kwh': None,
        'standing_charge': None, 'subtotal': None,
    }
    full_rows = []
    for r in rows:
        row = {**defaults, **r}
        full_rows.append(row)
    return pd.DataFrame(full_rows)


class TestBuildMonthlyDf:
    """Test the build_monthly_df aggregation function."""

    def test_single_bill_single_month(self):
        """Bill entirely within one month produces one row."""
        df = _make_df([{
            'period_start': date(2025, 3, 1),
            'period_end': date(2025, 4, 1),
            'total_cost': 100.0,
            'total_kwh': 500.0,
        }])
        mdf = build_monthly_df(df)
        assert mdf is not None
        assert len(mdf) == 1
        assert mdf.iloc[0]['month_label'] == 'Mar 2025'
        assert mdf.iloc[0]['total_cost'] == pytest.approx(100.0)
        assert mdf.iloc[0]['total_kwh'] == pytest.approx(500.0)

    def test_two_month_proration(self):
        """Bill spanning two months is pro-rated by day count."""
        # Jan 15 to Feb 15 = 31 total days
        # Jan 15 to Feb 1 = 17 days, Feb 1 to Feb 15 = 14 days
        start, end = date(2025, 1, 15), date(2025, 2, 15)
        total_days = (end - start).days  # 31
        df = _make_df([{
            'period_start': start,
            'period_end': end,
            'total_cost': 310.0,
            'total_kwh': 620.0,
        }])
        mdf = build_monthly_df(df)
        assert mdf is not None
        assert len(mdf) == 2

        jan = mdf[mdf['month_label'] == 'Jan 2025'].iloc[0]
        feb = mdf[mdf['month_label'] == 'Feb 2025'].iloc[0]

        # Jan: 17 days out of 31
        assert jan['total_cost'] == pytest.approx(310.0 * 17 / 31)
        assert jan['total_kwh'] == pytest.approx(620.0 * 17 / 31)

        # Feb: 14 days out of 31
        assert feb['total_cost'] == pytest.approx(310.0 * 14 / 31)

        # Sum should equal original
        assert jan['total_cost'] + feb['total_cost'] == pytest.approx(310.0)

    def test_overlapping_bills_sum(self):
        """Two bills contributing to the same month should sum."""
        df = _make_df([
            {
                'period_start': date(2025, 3, 1),
                'period_end': date(2025, 4, 1),
                'total_cost': 100.0,
                'total_kwh': 400.0,
            },
            {
                'period_start': date(2025, 3, 1),
                'period_end': date(2025, 4, 1),
                'total_cost': 50.0,
                'total_kwh': 200.0,
            },
        ])
        mdf = build_monthly_df(df)
        assert len(mdf) == 1
        assert mdf.iloc[0]['total_cost'] == pytest.approx(150.0)
        assert mdf.iloc[0]['total_kwh'] == pytest.approx(600.0)
        # days_covered should be 31 + 31 = 62
        assert mdf.iloc[0]['days_covered'] == 62

    def test_missing_dates_excluded(self):
        """Bills without valid date ranges are excluded."""
        df = _make_df([
            {
                'period_start': None,
                'period_end': None,
                'total_cost': 100.0,
            },
            {
                'period_start': date(2025, 3, 1),
                'period_end': date(2025, 4, 1),
                'total_cost': 200.0,
            },
        ])
        mdf = build_monthly_df(df)
        assert mdf is not None
        assert len(mdf) == 1
        assert mdf.iloc[0]['total_cost'] == pytest.approx(200.0)

    def test_all_missing_dates_returns_none(self):
        """All bills without dates should return None."""
        df = _make_df([
            {'period_start': None, 'period_end': None, 'total_cost': 100.0},
        ])
        assert build_monthly_df(df) is None

    def test_nan_fields_preserved(self):
        """NaN fields should stay NaN through pro-rating."""
        df = _make_df([{
            'period_start': date(2025, 3, 1),
            'period_end': date(2025, 4, 1),
            'total_cost': 100.0,
            'total_kwh': None,  # no consumption data
        }])
        mdf = build_monthly_df(df)
        assert mdf is not None
        assert mdf.iloc[0]['total_cost'] == pytest.approx(100.0)
        assert pd.isna(mdf.iloc[0]['total_kwh'])

    def test_daily_averages_computed(self):
        """cost_per_day and kwh_per_day should be derived from totals."""
        df = _make_df([{
            'period_start': date(2025, 3, 1),
            'period_end': date(2025, 4, 1),
            'total_cost': 310.0,
            'total_kwh': 620.0,
        }])
        mdf = build_monthly_df(df)
        assert mdf.iloc[0]['cost_per_day'] == pytest.approx(10.0)
        assert mdf.iloc[0]['kwh_per_day'] == pytest.approx(20.0)

    def test_sorted_chronologically(self):
        """Output should be sorted by month."""
        df = _make_df([
            {
                'period_start': date(2025, 5, 1),
                'period_end': date(2025, 6, 1),
                'total_cost': 200.0,
            },
            {
                'period_start': date(2025, 3, 1),
                'period_end': date(2025, 4, 1),
                'total_cost': 100.0,
            },
        ])
        mdf = build_monthly_df(df)
        labels = mdf['month_label'].tolist()
        assert labels == ['Mar 2025', 'May 2025']

    def test_breakdown_fields_prorated(self):
        """day_kwh, night_kwh, peak_kwh should be pro-rated."""
        # Jan 15 to Feb 15 = 31 days, 17 in Jan, 14 in Feb
        df = _make_df([{
            'period_start': date(2025, 1, 15),
            'period_end': date(2025, 2, 15),
            'total_kwh': 310.0,
            'day_kwh': 200.0,
            'night_kwh': 100.0,
            'peak_kwh': 10.0,
        }])
        mdf = build_monthly_df(df)
        assert len(mdf) == 2
        total_days = 31
        jan_frac = 17 / total_days
        jan = mdf[mdf['month_label'] == 'Jan 2025'].iloc[0]
        assert jan['day_kwh'] == pytest.approx(200.0 * jan_frac)
        assert jan['night_kwh'] == pytest.approx(100.0 * jan_frac)
        assert jan['peak_kwh'] == pytest.approx(10.0 * jan_frac)
