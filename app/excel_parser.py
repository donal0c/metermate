"""
Excel/CSV parsing pipeline for energy data.

Handles messy client spreadsheets with auto-detection of columns,
data cleaning, validation, and normalization to the standard schema.
"""

import io
from typing import Optional

import pandas as pd
import numpy as np

from parse_result import (
    DataGranularity,
    DataSource,
    ColumnMapping,
    DataQualityIssue,
    DataQualityReport,
    ParseResult,
)
from column_mapping import detect_columns, build_column_mapping, validate_mapping


def get_sheet_names(file_content: bytes, filename: str) -> list[str]:
    """Get sheet names from an Excel file. Returns empty list for CSV."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("xlsx", "xls"):
        return []
    try:
        xlsx = pd.ExcelFile(io.BytesIO(file_content), engine="openpyxl")
        return xlsx.sheet_names
    except Exception:
        try:
            xlsx = pd.ExcelFile(io.BytesIO(file_content))
            return xlsx.sheet_names
        except Exception:
            return []


def read_upload(file_content: bytes, filename: str, sheet_name: str | None = None) -> pd.DataFrame:
    """
    Read an uploaded file into a raw DataFrame.

    Handles .xlsx, .xls, .csv with encoding detection and header row skipping.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext in ("xlsx", "xls"):
        # Try reading Excel - openpyxl for xlsx, xlrd for xls
        try:
            df = pd.read_excel(io.BytesIO(file_content), engine="openpyxl", sheet_name=sheet_name or 0)
        except Exception:
            df = pd.read_excel(io.BytesIO(file_content), sheet_name=sheet_name or 0)
    elif ext == "csv":
        # Try UTF-8 first, then latin-1 fallback
        try:
            df = pd.read_csv(io.BytesIO(file_content), encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(file_content), encoding="latin-1")
    else:
        raise ValueError(f"Unsupported file format: .{ext}")

    # Detect and skip logo/junk rows before actual header
    df = _skip_to_header(df)

    return df


def _skip_to_header(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect and skip junk rows above the actual header.

    Some client exports have company logos, titles, or blank rows before
    the actual data header. We look for the first row where most cells
    are non-null strings that look like column names.
    """
    if len(df) < 2:
        return df

    # Check if current columns look like real headers (not Unnamed)
    unnamed_count = sum(1 for c in df.columns if str(c).startswith("Unnamed"))
    if unnamed_count <= len(df.columns) * 0.3:
        # Headers look reasonable
        return df

    # Scan first 10 rows for a better header row
    best_row = None
    best_score = 0

    for i in range(min(10, len(df))):
        row = df.iloc[i]
        non_null = row.notna().sum()
        str_count = sum(1 for v in row if isinstance(v, str) and len(v.strip()) > 0)
        score = non_null + str_count

        if score > best_score:
            best_score = score
            best_row = i

    if best_row is not None and best_row > 0:
        # Use this row as the header
        new_headers = df.iloc[best_row].astype(str).str.strip()
        df = df.iloc[best_row + 1:].reset_index(drop=True)
        df.columns = new_headers
    elif best_row == 0:
        # First data row might be the header - check if current headers are all Unnamed
        if unnamed_count > len(df.columns) * 0.5:
            new_headers = df.iloc[0].astype(str).str.strip()
            df = df.iloc[1:].reset_index(drop=True)
            df.columns = new_headers

    return df


def detect_granularity(dt_series: pd.Series) -> DataGranularity:
    """
    Detect data granularity from a datetime series by analyzing intervals.
    """
    if len(dt_series) < 2:
        return DataGranularity.UNKNOWN

    sorted_dt = dt_series.sort_values().reset_index(drop=True)
    diffs = sorted_dt.diff().dropna()

    if len(diffs) == 0:
        return DataGranularity.UNKNOWN

    median_diff = diffs.median()
    minutes = median_diff.total_seconds() / 60

    if minutes <= 35:
        return DataGranularity.HALF_HOURLY
    elif minutes <= 65:
        return DataGranularity.HOURLY
    elif minutes <= 1500:  # up to ~25 hours
        return DataGranularity.DAILY
    elif minutes <= 45000:  # up to ~31 days
        return DataGranularity.MONTHLY
    else:
        return DataGranularity.UNKNOWN


def parse_dates(series: pd.Series, dayfirst: bool = True) -> tuple[pd.Series, list[DataQualityIssue]]:
    """
    Parse a series of date strings to datetime, defaulting to DD/MM (Irish format).

    Returns (parsed_series, list_of_issues).
    """
    issues = []

    # First try with dayfirst preference
    parsed = pd.to_datetime(series, errors="coerce", dayfirst=dayfirst)
    failed_count = parsed.isna().sum() - series.isna().sum()  # Only count newly-failed

    if failed_count > 0:
        # Try the opposite format for failed rows
        mask = parsed.isna() & series.notna()
        alt = pd.to_datetime(series[mask], errors="coerce", dayfirst=not dayfirst)
        recovered = alt.notna().sum()
        parsed[mask] = alt

        still_failed = parsed.isna().sum() - series.isna().sum()
        if still_failed > 0:
            issues.append(DataQualityIssue(
                category="date_parse",
                severity="warning",
                message=f"{still_failed} date values could not be parsed",
                affected_rows=int(still_failed),
                auto_fixed=False,
            ))

        if recovered > 0:
            issues.append(DataQualityIssue(
                category="date_format_mixed",
                severity="info",
                message=f"Mixed date formats detected. {recovered} dates parsed with alternate format.",
                affected_rows=int(recovered),
                auto_fixed=True,
            ))

    return parsed, issues


def clean_data(
    df: pd.DataFrame,
    mapping: ColumnMapping,
) -> tuple[pd.DataFrame, list[DataQualityIssue]]:
    """
    Clean and normalize data using the column mapping.

    Steps: rename columns, drop empty rows, remove duplicates,
    parse dates, coerce numerics, handle negatives, sort, dedup timestamps.
    """
    issues = []
    original_len = len(df)

    # Build rename map
    rename_map = {}
    if mapping.datetime_col:
        rename_map[mapping.datetime_col] = "datetime"
    if mapping.import_kwh_col:
        rename_map[mapping.import_kwh_col] = "import_kwh"
    if mapping.export_kwh_col:
        rename_map[mapping.export_kwh_col] = "export_kwh"
    if mapping.mprn_col:
        rename_map[mapping.mprn_col] = "mprn"
    if mapping.cost_col:
        rename_map[mapping.cost_col] = "cost"

    df = df.rename(columns=rename_map)

    # Drop rows where both datetime and import_kwh are null
    required_cols = [c for c in ["datetime", "import_kwh"] if c in df.columns]
    if required_cols:
        before = len(df)
        df = df.dropna(subset=required_cols, how="all")
        dropped = before - len(df)
        if dropped > 0:
            issues.append(DataQualityIssue(
                category="empty_rows",
                severity="info",
                message=f"Removed {dropped} empty rows",
                affected_rows=dropped,
                auto_fixed=True,
            ))

    # Parse dates
    if "datetime" in df.columns:
        parsed_dates, date_issues = parse_dates(df["datetime"])
        df["datetime"] = parsed_dates
        issues.extend(date_issues)

        # Drop rows where date parsing failed
        before = len(df)
        df = df.dropna(subset=["datetime"])
        dropped = before - len(df)
        if dropped > 0:
            issues.append(DataQualityIssue(
                category="invalid_dates",
                severity="warning",
                message=f"Dropped {dropped} rows with unparseable dates",
                affected_rows=dropped,
                auto_fixed=True,
            ))

    # Coerce numeric columns
    for col in ["import_kwh", "export_kwh", "cost"]:
        if col in df.columns:
            # Strip currency symbols and whitespace
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace(r"[€$£,\s]", "", regex=True)
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Handle negative import values (some exports use negative for export)
    if "import_kwh" in df.columns:
        neg_count = (df["import_kwh"] < 0).sum()
        if neg_count > 0:
            # If we don't have export column and there are negatives,
            # the negatives might represent export
            if "export_kwh" not in df.columns or df.get("export_kwh") is None:
                df["export_kwh"] = df["import_kwh"].clip(upper=0).abs()
                df["import_kwh"] = df["import_kwh"].clip(lower=0)
                issues.append(DataQualityIssue(
                    category="negative_values",
                    severity="info",
                    message=f"Converted {neg_count} negative import values to export column",
                    affected_rows=int(neg_count),
                    auto_fixed=True,
                ))
            else:
                df["import_kwh"] = df["import_kwh"].abs()
                issues.append(DataQualityIssue(
                    category="negative_values",
                    severity="info",
                    message=f"Converted {neg_count} negative import values to absolute",
                    affected_rows=int(neg_count),
                    auto_fixed=True,
                ))

    # Ensure export_kwh column exists
    if "export_kwh" not in df.columns:
        df["export_kwh"] = 0.0

    # Sort by datetime
    if "datetime" in df.columns:
        df = df.sort_values("datetime").reset_index(drop=True)

        # Remove duplicate timestamps (keep first)
        before = len(df)
        df = df.drop_duplicates(subset=["datetime"], keep="first")
        duped = before - len(df)
        if duped > 0:
            issues.append(DataQualityIssue(
                category="duplicates",
                severity="info",
                message=f"Removed {duped} duplicate timestamps",
                affected_rows=duped,
                auto_fixed=True,
            ))

    # Ensure MPRN column exists
    if "mprn" not in df.columns:
        df["mprn"] = "Unknown"
    else:
        df["mprn"] = df["mprn"].astype(str).str.strip()

    total_dropped = original_len - len(df)
    return df, issues


def validate_data(
    df: pd.DataFrame,
    granularity: DataGranularity,
) -> list[DataQualityIssue]:
    """
    Validate cleaned data and flag quality issues.
    """
    issues = []

    if "datetime" not in df.columns or len(df) < 2:
        return issues

    # Check for gaps
    sorted_dt = df["datetime"].sort_values()
    diffs = sorted_dt.diff().dropna()

    if len(diffs) > 0:
        expected_minutes = {
            DataGranularity.HALF_HOURLY: 30,
            DataGranularity.HOURLY: 60,
            DataGranularity.DAILY: 1440,
        }

        if granularity in expected_minutes:
            expected = pd.Timedelta(minutes=expected_minutes[granularity])
            gaps = diffs[diffs > expected * 1.5]
            if len(gaps) > 0:
                issues.append(DataQualityIssue(
                    category="gaps",
                    severity="warning",
                    message=f"Found {len(gaps)} gaps in the time series",
                    affected_rows=len(gaps),
                    details=f"Largest gap: {gaps.max()}",
                ))

    # Check for spikes (>5 std from mean)
    if "import_kwh" in df.columns:
        mean = df["import_kwh"].mean()
        std = df["import_kwh"].std()
        if std > 0:
            spikes = df[df["import_kwh"] > mean + 5 * std]
            if len(spikes) > 0:
                issues.append(DataQualityIssue(
                    category="spikes",
                    severity="info",
                    message=f"Found {len(spikes)} readings >5 standard deviations above mean",
                    affected_rows=len(spikes),
                ))

    # Check for constant data (all same value)
    if "import_kwh" in df.columns and len(df) > 10:
        unique_count = df["import_kwh"].nunique()
        if unique_count <= 3:
            issues.append(DataQualityIssue(
                category="constant_data",
                severity="warning",
                message=f"Only {unique_count} unique consumption values found - data may be aggregated or placeholder",
                affected_rows=len(df),
            ))

    # Completeness
    if "datetime" in df.columns and granularity != DataGranularity.UNKNOWN:
        date_range = df["datetime"].max() - df["datetime"].min()
        expected_intervals = {
            DataGranularity.HALF_HOURLY: date_range.total_seconds() / 1800,
            DataGranularity.HOURLY: date_range.total_seconds() / 3600,
            DataGranularity.DAILY: date_range.days + 1,
            DataGranularity.MONTHLY: date_range.days / 30,
        }
        if granularity in expected_intervals:
            expected = expected_intervals[granularity]
            if expected > 0:
                completeness = len(df) / expected * 100
                if completeness < 90:
                    issues.append(DataQualityIssue(
                        category="completeness",
                        severity="warning" if completeness > 50 else "error",
                        message=f"Data completeness is {completeness:.0f}% ({len(df)} of ~{expected:.0f} expected readings)",
                        affected_rows=int(expected - len(df)),
                    ))

    return issues


def add_derived_columns(df: pd.DataFrame, granularity: DataGranularity) -> pd.DataFrame:
    """
    Add temporal feature columns based on data granularity.

    Interval data (30min/hourly): all columns including hour, tariff_period
    Daily data: date-level columns (day_of_week, is_weekend, month, etc.)
    Monthly data: month/year_month only
    """
    if "datetime" not in df.columns:
        return df

    # Always add month and year_month
    df["month"] = df["datetime"].dt.month_name()
    df["year_month"] = df["datetime"].dt.strftime("%Y-%m")

    if granularity.has_daily_detail:
        # Daily or finer
        df["day_of_week"] = df["datetime"].dt.day_name()
        df["day_of_week_num"] = df["datetime"].dt.dayofweek
        df["is_weekend"] = df["day_of_week_num"] >= 5
        df["date"] = df["datetime"].dt.date

    if granularity.has_hourly_detail:
        # Interval data only
        df["hour"] = df["datetime"].dt.hour
        df["tariff_period"] = df["hour"].apply(_classify_tariff)

    return df


def _classify_tariff(hour: int) -> str:
    """Irish tariff period classification."""
    if hour >= 23 or hour < 8:
        return "Night"
    elif 17 <= hour < 19:
        return "Peak"
    else:
        return "Day"


def parse_excel_file(
    file_content: bytes,
    filename: str,
    column_mapping: Optional[ColumnMapping] = None,
    mprn_override: Optional[str] = None,
    sheet_name: Optional[str] = None,
) -> ParseResult:
    """
    Main entry point: parse an Excel/CSV file into a ParseResult.

    Args:
        file_content: Raw file bytes
        filename: Original filename (for format detection)
        column_mapping: User-edited mapping, or None for auto-detection
        mprn_override: Override MPRN value if user provides one

    Returns:
        ParseResult with cleaned DataFrame, quality report, and metadata
    """
    # Step 1: Read raw data
    raw_df = read_upload(file_content, filename, sheet_name=sheet_name)
    total_rows_raw = len(raw_df)

    # Step 2: Detect or use provided column mapping
    if column_mapping is None:
        candidates = detect_columns(raw_df)
        column_mapping = build_column_mapping(candidates)

    # Validate mapping
    errors = validate_mapping(column_mapping, raw_df)
    if errors:
        # Build a report with errors
        report = DataQualityReport(
            total_rows_raw=total_rows_raw,
            total_rows_clean=0,
            rows_dropped=total_rows_raw,
            issues=[
                DataQualityIssue(
                    category="mapping",
                    severity="error",
                    message=e,
                ) for e in errors
            ],
            granularity=DataGranularity.UNKNOWN,
            column_mapping=column_mapping,
        )
        return ParseResult(
            df=pd.DataFrame(),
            source=DataSource.EXCEL,
            granularity=DataGranularity.UNKNOWN,
            quality_report=report,
            original_filename=filename,
        )

    # Step 3: Clean data
    cleaned_df, clean_issues = clean_data(raw_df, column_mapping)

    # Step 4: Apply MPRN override
    if mprn_override and mprn_override.strip():
        cleaned_df["mprn"] = mprn_override.strip()

    # Step 5: Detect granularity
    granularity = DataGranularity.UNKNOWN
    if "datetime" in cleaned_df.columns and len(cleaned_df) > 1:
        granularity = detect_granularity(cleaned_df["datetime"])

    # Step 6: Validate
    validation_issues = validate_data(cleaned_df, granularity)

    # Step 7: Add derived columns
    cleaned_df = add_derived_columns(cleaned_df, granularity)

    # Step 8: Compute completeness
    completeness = 0.0
    if "datetime" in cleaned_df.columns and len(cleaned_df) > 0:
        date_range = cleaned_df["datetime"].max() - cleaned_df["datetime"].min()
        expected_map = {
            DataGranularity.HALF_HOURLY: date_range.total_seconds() / 1800,
            DataGranularity.HOURLY: date_range.total_seconds() / 3600,
            DataGranularity.DAILY: date_range.days + 1,
            DataGranularity.MONTHLY: max(date_range.days / 30, 1),
        }
        expected = expected_map.get(granularity, len(cleaned_df))
        if expected > 0:
            completeness = min(len(cleaned_df) / expected * 100, 100.0)

    # Build quality report
    all_issues = clean_issues + validation_issues
    report = DataQualityReport(
        total_rows_raw=total_rows_raw,
        total_rows_clean=len(cleaned_df),
        rows_dropped=total_rows_raw - len(cleaned_df),
        issues=all_issues,
        date_range_start=cleaned_df["datetime"].min() if "datetime" in cleaned_df.columns and len(cleaned_df) > 0 else None,
        date_range_end=cleaned_df["datetime"].max() if "datetime" in cleaned_df.columns and len(cleaned_df) > 0 else None,
        granularity=granularity,
        completeness_pct=completeness,
        column_mapping=column_mapping,
    )

    return ParseResult(
        df=cleaned_df,
        source=DataSource.EXCEL,
        granularity=granularity,
        quality_report=report,
        original_filename=filename,
    )
