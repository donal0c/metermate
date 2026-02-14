"""Unit tests for comparison filtering helpers."""

import pandas as pd

from common.comparison import NO_MPRN_LABEL, filter_dataframe_by_mprn


def test_filter_dataframe_by_mprn_includes_blank_rows_when_selected():
    df = pd.DataFrame(
        [
            {"filename": "a.pdf", "mprn": "10000000001"},
            {"filename": "b.pdf", "mprn": "10000000002"},
            {"filename": "photo.jpg", "mprn": ""},
        ]
    )

    filtered = filter_dataframe_by_mprn(
        df, ["10000000001", "10000000002", NO_MPRN_LABEL]
    )

    assert set(filtered["filename"]) == {"a.pdf", "b.pdf", "photo.jpg"}


def test_filter_dataframe_by_mprn_excludes_blank_rows_when_not_selected():
    df = pd.DataFrame(
        [
            {"filename": "a.pdf", "mprn": "10000000001"},
            {"filename": "photo.jpg", "mprn": ""},
        ]
    )

    filtered = filter_dataframe_by_mprn(df, ["10000000001"])

    assert set(filtered["filename"]) == {"a.pdf"}
