"""Formatting utilities for Energy Insight.

Currency, kWh, percentage, and date formatting helpers used across pages.
"""
from __future__ import annotations

from datetime import datetime as dt


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


def compute_billing_days(start_str: str | None, end_str: str | None) -> int | None:
    """Compute the number of days in a billing period.

    Returns the day count or None if dates cannot be parsed.
    """
    start = parse_bill_date(start_str)
    end = parse_bill_date(end_str)
    if start and end:
        return (end - start).days
    return None
