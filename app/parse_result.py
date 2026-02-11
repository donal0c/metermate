"""
Shared data structures for energy data parsing.

Used by both HDF and Excel parsers to provide a consistent interface
for the analysis pipeline.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import pandas as pd


class DataGranularity(Enum):
    """Granularity of time-series energy data."""
    HALF_HOURLY = "30min"
    HOURLY = "1h"
    DAILY = "daily"
    MONTHLY = "monthly"
    UNKNOWN = "unknown"

    @property
    def is_interval(self) -> bool:
        return self in (DataGranularity.HALF_HOURLY, DataGranularity.HOURLY)

    @property
    def has_hourly_detail(self) -> bool:
        return self.is_interval

    @property
    def has_daily_detail(self) -> bool:
        return self in (DataGranularity.HALF_HOURLY, DataGranularity.HOURLY, DataGranularity.DAILY)


class DataSource(Enum):
    """Origin of the parsed data."""
    HDF = "hdf"
    EXCEL = "excel"
    MANUAL = "manual"


@dataclass
class ColumnMapping:
    """Maps detected columns to standard field names."""
    datetime_col: Optional[str] = None
    import_kwh_col: Optional[str] = None
    export_kwh_col: Optional[str] = None
    mprn_col: Optional[str] = None
    cost_col: Optional[str] = None
    detection_tier: int = 0  # 1=exact, 2=fuzzy, 3=content
    confidence: float = 0.0


@dataclass
class DataQualityIssue:
    """A single data quality finding."""
    category: str          # e.g. "missing_values", "duplicates", "date_parse"
    severity: str          # "info", "warning", "error"
    message: str
    affected_rows: int = 0
    auto_fixed: bool = False
    details: Optional[str] = None


@dataclass
class DataQualityReport:
    """Summary of data quality after cleaning."""
    total_rows_raw: int = 0
    total_rows_clean: int = 0
    rows_dropped: int = 0
    issues: list[DataQualityIssue] = field(default_factory=list)
    date_range_start: Optional[pd.Timestamp] = None
    date_range_end: Optional[pd.Timestamp] = None
    granularity: DataGranularity = DataGranularity.UNKNOWN
    completeness_pct: float = 0.0
    column_mapping: Optional[ColumnMapping] = None

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def is_usable(self) -> bool:
        return self.error_count == 0 and self.total_rows_clean > 0


@dataclass
class ParseResult:
    """Unified output from any parser."""
    df: pd.DataFrame
    source: DataSource
    granularity: DataGranularity
    quality_report: DataQualityReport
    original_filename: str = ""

    @property
    def is_interval_data(self) -> bool:
        return self.granularity.is_interval

    @property
    def available_columns(self) -> list[str]:
        return list(self.df.columns)
