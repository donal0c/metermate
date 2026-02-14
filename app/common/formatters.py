"""Formatting utilities for Energy Insight.

Currency, kWh, percentage, and date formatting helpers used across pages.
"""
from __future__ import annotations

from datetime import date, datetime as dt


def format_currency(value: float | None, symbol: str = "\u20ac") -> str:
    """Format a value as EUR currency, or return a dash if None."""
    if value is None:
        return "\u2014"
    return f"{symbol}{value:,.2f}"


def format_kwh(value: float | None, precision: int = 1) -> str:
    """Format a kWh value with appropriate precision."""
    if value is None:
        return "\u2014"
    return f"{value:,.{precision}f} kWh"


def format_rate(value: float | None) -> str:
    """Format a per-kWh rate as EUR/kWh."""
    if value is None:
        return "\u2014"
    return f"\u20ac{value:.4f}/kWh"


def format_percentage(value: float | None) -> str:
    """Format a percentage value."""
    if value is None:
        return "\u2014"
    return f"{value:.1f}%"


def format_date_range(start: str | None, end: str | None) -> str:
    """Format a billing period date range."""
    if start and end:
        return f"{start} \u2192 {end}"
    if start:
        return start
    return "\u2014"


def parse_bill_date(date_str: str | None):
    """Try to parse a date string from bill extraction.

    Returns a date object or None.
    """
    if not date_str:
        return None
    formats = [
        "%d/%m/%Y", "%d %b %Y", "%d %B %Y", "%d.%m.%Y",
        "%Y-%m-%d", "%d-%m-%Y",
        "%d/%m/%y", "%d-%m-%y", "%d.%m.%y", "%d %b %y", "%d %B %y",
    ]
    for fmt in formats:
        try:
            return dt.strptime(date_str.strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def split_period_into_months(start: date, end: date) -> list[tuple[date, int]]:
    """Split a date range into calendar-month segments.

    Returns a list of (first_of_month, overlap_days) tuples.  The overlap
    days count how many days of the billing period fall within that calendar
    month.  ``end`` is treated as *exclusive* (matching how billing-period
    days are computed elsewhere: ``(end - start).days``).
    """
    if end <= start:
        return []
    segments: list[tuple[date, int]] = []
    current = start
    while current < end:
        month_start = date(current.year, current.month, 1)
        # First day of next month
        if current.month == 12:
            next_month_start = date(current.year + 1, 1, 1)
        else:
            next_month_start = date(current.year, current.month + 1, 1)
        segment_end = min(next_month_start, end)
        days = (segment_end - current).days
        if days > 0:
            segments.append((month_start, days))
        current = segment_end
    return segments


_PRORATE_FIELDS = [
    'total_cost', 'total_kwh', 'day_kwh', 'night_kwh', 'peak_kwh',
    'standing_charge', 'subtotal',
]


def build_monthly_df(df):
    """Pro-rate bill data into calendar months and aggregate.

    Accepts a comparison DataFrame (one row per bill) with ``period_start``,
    ``period_end``, and the numeric fields listed in ``_PRORATE_FIELDS``.

    Returns a pandas DataFrame with one row per calendar month (sorted
    chronologically) or ``None`` when no bills have usable date ranges.
    """
    import pandas as pd

    monthly_rows: list[dict] = []
    for _, row in df.iterrows():
        start = row.get('period_start')
        end = row.get('period_end')
        if pd.isna(start) or pd.isna(end) or start is None or end is None:
            continue
        total_days = (end - start).days
        if total_days <= 0:
            continue

        segments = split_period_into_months(start, end)
        for month_key, overlap_days in segments:
            fraction = overlap_days / total_days
            entry: dict = {
                'month_key': month_key,
                'month_label': month_key.strftime('%b %Y'),
                'days_covered': overlap_days,
            }
            for field in _PRORATE_FIELDS:
                val = row.get(field)
                if pd.notna(val) and val is not None:
                    entry[field] = float(val) * fraction
                else:
                    entry[field] = None
            monthly_rows.append(entry)

    if not monthly_rows:
        return None

    mdf = pd.DataFrame(monthly_rows)
    # Sum per calendar month (min_count=1 so all-NaN stays NaN)
    agg = {f: 'sum' for f in _PRORATE_FIELDS}
    agg['days_covered'] = 'sum'
    agg['month_label'] = 'first'
    grouped = mdf.groupby('month_key', as_index=False).agg(agg)
    # Re-apply min_count=1 for nullable columns
    for field in _PRORATE_FIELDS:
        grouped[field] = mdf.groupby('month_key')[field].apply(
            lambda s: s.sum(min_count=1)
        ).values

    grouped = grouped.sort_values('month_key').reset_index(drop=True)

    # Derived daily averages
    grouped['cost_per_day'] = grouped.apply(
        lambda r: r['total_cost'] / r['days_covered']
        if pd.notna(r['total_cost']) and r['days_covered'] > 0 else None,
        axis=1,
    )
    grouped['kwh_per_day'] = grouped.apply(
        lambda r: r['total_kwh'] / r['days_covered']
        if pd.notna(r['total_kwh']) and r['days_covered'] > 0 else None,
        axis=1,
    )

    return grouped


def compute_billing_days(start_str: str | None, end_str: str | None) -> int | None:
    """Compute the number of days in a billing period.

    Returns the day count or None if dates cannot be parsed.
    """
    start = parse_bill_date(start_str)
    end = parse_bill_date(end_str)
    if start and end:
        return (end - start).days
    return None
