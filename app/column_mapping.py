"""
3-tier column detection engine for energy data spreadsheets.

Detects standard columns (datetime, import_kwh, export_kwh, mprn, cost)
from messy client spreadsheets using:
  Tier 1 - Exact match against known column name dictionaries
  Tier 2 - Fuzzy match using rapidfuzz
  Tier 3 - Content inference by sampling column values
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd
from rapidfuzz import fuzz

from parse_result import ColumnMapping


# Known column names from Irish energy supplier exports
# (ESB Networks, Electric Ireland, SSE Airtricity, Flogas, Energia, Bord Gáis)
KNOWN_COLUMNS: dict[str, list[str]] = {
    "datetime": [
        "datetime", "date time", "date/time", "date_time",
        "read date and end time", "read date", "timestamp",
        "interval end time", "interval end", "end time",
        "period end", "period", "time", "date",
        "billing date", "bill date", "usage date",
        "meter read date", "reading date",
        "interval date", "start date", "start time",
        "date and time", "reading timestamp",
    ],
    "import_kwh": [
        "import_kwh", "import kwh", "import (kwh)", "active import",
        "active import interval (kwh)", "active import interval (kw)",
        "consumption", "consumption (kwh)", "usage", "usage (kwh)",
        "kwh", "units", "units consumed", "energy (kwh)",
        "grid import", "grid import (kwh)", "import",
        "total kwh", "total consumption", "total usage",
        "read value", "meter reading", "reading",
        "day units", "night units", "peak units",
        "electricity usage", "electricity consumed",
    ],
    "export_kwh": [
        "export_kwh", "export kwh", "export (kwh)", "active export",
        "active export interval (kwh)", "active export interval (kw)",
        "generation", "generation (kwh)", "solar export",
        "grid export", "grid export (kwh)", "export",
        "feed-in", "feed in", "exported",
        "solar generation", "pv export",
    ],
    "mprn": [
        "mprn", "meter point reference", "meter point ref",
        "meter reference", "meter ref", "meter number",
        "meter point reference number", "mpan", "supply number",
        "account number", "meter id", "meter serial number",
        "gprn",  # gas - sometimes in combined files
    ],
    "cost": [
        "cost", "cost (eur)", "cost (€)", "amount", "charge",
        "total cost", "total charge", "total amount",
        "net amount", "gross amount", "bill amount",
        "energy cost", "energy charge", "unit cost",
        "standing charge", "price", "value (€)",
        "value (eur)", "euro", "eur",
    ],
}


@dataclass
class ColumnCandidate:
    """A candidate mapping for a standard field."""
    original_name: str
    standard_field: str
    tier: int           # 1=exact, 2=fuzzy, 3=content
    confidence: float   # 0.0-1.0
    reason: str


def _normalize(name: str) -> str:
    """Normalize a column name for comparison."""
    return name.strip().lower().replace("_", " ").replace("-", " ")


def _tier1_exact(columns: list[str]) -> dict[str, ColumnCandidate]:
    """Tier 1: Exact match against known column name dictionaries."""
    candidates: dict[str, ColumnCandidate] = {}
    normalized_cols = {_normalize(c): c for c in columns}

    for field_name, known_names in KNOWN_COLUMNS.items():
        for known in known_names:
            norm_known = _normalize(known)
            if norm_known in normalized_cols:
                original = normalized_cols[norm_known]
                # Only keep the highest-priority match (first in list)
                if field_name not in candidates:
                    candidates[field_name] = ColumnCandidate(
                        original_name=original,
                        standard_field=field_name,
                        tier=1,
                        confidence=1.0,
                        reason=f"Exact match: '{original}' = '{known}'"
                    )
                break

    return candidates


def _tier2_fuzzy(columns: list[str], already_matched: set[str]) -> dict[str, ColumnCandidate]:
    """Tier 2: Fuzzy match using rapidfuzz token_sort_ratio."""
    candidates: dict[str, ColumnCandidate] = {}
    threshold = 80

    for col in columns:
        if col in already_matched:
            continue

        norm_col = _normalize(col)
        best_score = 0.0
        best_field = None
        best_known = None

        for field_name, known_names in KNOWN_COLUMNS.items():
            if field_name in candidates:
                continue
            for known in known_names:
                score = fuzz.token_sort_ratio(norm_col, _normalize(known))
                if score > best_score:
                    best_score = score
                    best_field = field_name
                    best_known = known

        if best_field and best_score >= threshold:
            candidates[best_field] = ColumnCandidate(
                original_name=col,
                standard_field=best_field,
                tier=2,
                confidence=best_score / 100.0,
                reason=f"Fuzzy match ({best_score:.0f}%): '{col}' ~ '{best_known}'"
            )

    return candidates


def _tier3_content(df: pd.DataFrame, already_matched: set[str]) -> dict[str, ColumnCandidate]:
    """Tier 3: Content inference by sampling column values."""
    candidates: dict[str, ColumnCandidate] = {}
    sample_size = min(50, len(df))
    unmatched_fields = set(KNOWN_COLUMNS.keys()) - set()

    for col in df.columns:
        if col in already_matched:
            continue

        sample = df[col].dropna().head(sample_size)
        if len(sample) == 0:
            continue

        # Check for datetime
        if "datetime" not in candidates and "datetime" not in already_matched:
            if _looks_like_datetime(sample):
                candidates["datetime"] = ColumnCandidate(
                    original_name=col,
                    standard_field="datetime",
                    tier=3,
                    confidence=0.7,
                    reason=f"Content inference: column '{col}' contains parseable dates"
                )
                continue

        # Check for MPRN (10-11 digit numbers starting with "10")
        if "mprn" not in candidates and "mprn" not in already_matched:
            if _looks_like_mprn(sample):
                candidates["mprn"] = ColumnCandidate(
                    original_name=col,
                    standard_field="mprn",
                    tier=3,
                    confidence=0.8,
                    reason=f"Content inference: column '{col}' contains MPRN-like values"
                )
                continue

        # Check for kWh values (positive floats in reasonable range)
        if "import_kwh" not in candidates and "import_kwh" not in already_matched:
            if _looks_like_kwh(sample):
                candidates["import_kwh"] = ColumnCandidate(
                    original_name=col,
                    standard_field="import_kwh",
                    tier=3,
                    confidence=0.6,
                    reason=f"Content inference: column '{col}' contains kWh-like values"
                )
                continue

        # Check for cost values
        if "cost" not in candidates and "cost" not in already_matched:
            if _looks_like_cost(sample):
                candidates["cost"] = ColumnCandidate(
                    original_name=col,
                    standard_field="cost",
                    tier=3,
                    confidence=0.5,
                    reason=f"Content inference: column '{col}' contains currency-like values"
                )
                continue

    return candidates


def _looks_like_datetime(series: pd.Series) -> bool:
    """Check if a series contains parseable date values."""
    str_vals = series.astype(str)
    parsed = pd.to_datetime(str_vals, errors="coerce", dayfirst=True)
    success_rate = parsed.notna().sum() / len(str_vals)
    return success_rate > 0.8


def _looks_like_mprn(series: pd.Series) -> bool:
    """Check if a series contains MPRN-like values (10-11 digit, starts with 10)."""
    str_vals = series.astype(str).str.strip()
    matches = str_vals.str.match(r"^10\d{8,9}$")
    return matches.sum() / len(str_vals) > 0.8


def _looks_like_kwh(series: pd.Series) -> bool:
    """Check if a series contains kWh-like values (positive floats, reasonable range)."""
    try:
        numeric = pd.to_numeric(series, errors="coerce")
        valid = numeric.dropna()
        if len(valid) < len(series) * 0.5:
            return False
        # Reasonable kWh range: 0 to 500 (single interval or daily)
        in_range = (valid >= 0) & (valid <= 500)
        return in_range.sum() / len(valid) > 0.8
    except Exception:
        return False


def _looks_like_cost(series: pd.Series) -> bool:
    """Check if a series contains currency-like values."""
    try:
        # Strip currency symbols
        cleaned = series.astype(str).str.replace(r"[€$£,]", "", regex=True)
        numeric = pd.to_numeric(cleaned, errors="coerce")
        valid = numeric.dropna()
        if len(valid) < len(series) * 0.5:
            return False
        # Positive values, reasonable cost range
        in_range = (valid >= 0) & (valid <= 10000)
        return in_range.sum() / len(valid) > 0.8
    except Exception:
        return False


def detect_columns(df: pd.DataFrame) -> dict[str, ColumnCandidate]:
    """
    Orchestrate 3-tier column detection.

    Returns a dict mapping standard field names to their best ColumnCandidate.
    """
    columns = list(df.columns)

    # Tier 1: Exact matches
    candidates = _tier1_exact(columns)
    matched_originals = {c.original_name for c in candidates.values()}

    # Tier 2: Fuzzy matches for remaining fields
    fuzzy = _tier2_fuzzy(columns, matched_originals)
    for field_name, candidate in fuzzy.items():
        if field_name not in candidates:
            candidates[field_name] = candidate
            matched_originals.add(candidate.original_name)

    # Tier 3: Content inference for still-missing fields
    content = _tier3_content(df, matched_originals)
    for field_name, candidate in content.items():
        if field_name not in candidates:
            candidates[field_name] = candidate

    return candidates


def build_column_mapping(candidates: dict[str, ColumnCandidate]) -> ColumnMapping:
    """Convert detected candidates into a ColumnMapping."""
    max_tier = max((c.tier for c in candidates.values()), default=0)
    avg_confidence = (
        sum(c.confidence for c in candidates.values()) / len(candidates)
        if candidates else 0.0
    )

    return ColumnMapping(
        datetime_col=candidates["datetime"].original_name if "datetime" in candidates else None,
        import_kwh_col=candidates["import_kwh"].original_name if "import_kwh" in candidates else None,
        export_kwh_col=candidates["export_kwh"].original_name if "export_kwh" in candidates else None,
        mprn_col=candidates["mprn"].original_name if "mprn" in candidates else None,
        cost_col=candidates["cost"].original_name if "cost" in candidates else None,
        detection_tier=max_tier,
        confidence=avg_confidence,
    )


def validate_mapping(mapping: ColumnMapping, df: pd.DataFrame) -> list[str]:
    """
    Validate that a column mapping is usable.

    Returns a list of error messages (empty = valid).
    """
    errors = []
    columns = set(df.columns)

    if not mapping.datetime_col:
        errors.append("No datetime column mapped. A date/time column is required.")
    elif mapping.datetime_col not in columns:
        errors.append(f"Datetime column '{mapping.datetime_col}' not found in data.")

    if not mapping.import_kwh_col:
        errors.append("No import/consumption column mapped. An energy usage column is required.")
    elif mapping.import_kwh_col not in columns:
        errors.append(f"Import column '{mapping.import_kwh_col}' not found in data.")

    # Export and MPRN are optional
    if mapping.export_kwh_col and mapping.export_kwh_col not in columns:
        errors.append(f"Export column '{mapping.export_kwh_col}' not found in data.")

    if mapping.mprn_col and mapping.mprn_col not in columns:
        errors.append(f"MPRN column '{mapping.mprn_col}' not found in data.")

    if mapping.cost_col and mapping.cost_col not in columns:
        errors.append(f"Cost column '{mapping.cost_col}' not found in data.")

    return errors
