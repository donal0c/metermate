"""Session state and file detection helpers for Energy Insight.

Provides file type detection, content hashing, and session state utilities
used by multiple pages.
"""
from __future__ import annotations

import hashlib

from hdf_parser import (
    parse_hdf_file,
    get_summary_stats,
)
from parse_result import (
    DataGranularity,
    DataSource,
    ParseResult,
    DataQualityReport,
)


def is_hdf_file(file_content: bytes) -> bool:
    """Check if file content looks like an ESB Networks HDF CSV."""
    try:
        head = file_content[:2048].decode("utf-8", errors="ignore")
        return "MPRN" in head and "Read Type" in head and "Read Value" in head
    except Exception:
        return False


def content_hash(data: bytes) -> str:
    """Return the MD5 hex digest of raw bytes (for cache keys)."""
    return hashlib.md5(data).hexdigest()


def make_cache_key(prefix: str, filename: str, content: bytes) -> str:
    """Build a deterministic cache key from prefix + filename + content hash."""
    return f"{prefix}_{filename}_{len(content)}_{content_hash(content)}"


def parse_hdf_with_result(file_content: bytes, filename: str) -> ParseResult:
    """Wrap the existing HDF parser output in a ParseResult."""
    df = parse_hdf_file(file_content)
    stats = get_summary_stats(df)

    report = DataQualityReport(
        total_rows_raw=len(df),
        total_rows_clean=len(df),
        rows_dropped=0,
        issues=[],
        date_range_start=stats["start_date"],
        date_range_end=stats["end_date"],
        granularity=DataGranularity.HALF_HOURLY,
        completeness_pct=100.0,
    )

    return ParseResult(
        df=df,
        source=DataSource.HDF,
        granularity=DataGranularity.HALF_HOURLY,
        quality_report=report,
        original_filename=filename,
    )
