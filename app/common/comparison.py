"""Helpers for comparison-table filtering."""
from __future__ import annotations

import pandas as pd

NO_MPRN_LABEL = "(No MPRN)"


def filter_dataframe_by_mprn(
    df: pd.DataFrame,
    selected_mprns: list[str],
    mprn_col: str = "mprn",
) -> pd.DataFrame:
    """Filter comparison rows by MPRN, with explicit support for blank MPRN rows."""
    if mprn_col not in df.columns:
        return df

    if not selected_mprns:
        return df.iloc[0:0].copy()

    include_blank = NO_MPRN_LABEL in selected_mprns
    selected_real = [m for m in selected_mprns if m != NO_MPRN_LABEL]

    mprn_series = df[mprn_col].fillna("").astype(str).str.strip()
    mask = mprn_series.isin(selected_real)

    if include_blank:
        mask = mask | (mprn_series == "")

    return df[mask].reset_index(drop=True)
