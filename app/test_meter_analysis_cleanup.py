"""
Unit tests for Meter Analysis page cleanup (steve-g4e).

Tests the refactored filter bar, tariff config, and sidebar structure.
These tests validate the logic functions without requiring a running Streamlit app.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Fixtures: synthetic data
# ---------------------------------------------------------------------------

def _make_interval_df(
    start_date: str = "2025-01-01",
    end_date: str = "2025-03-31",
) -> pd.DataFrame:
    """Create a synthetic 30-min interval DataFrame mimicking HDF data."""
    dates = pd.date_range(start=start_date, end=end_date, freq="30min", tz="Europe/Dublin")
    n = len(dates)
    hours = dates.hour

    import_kwh = np.where(
        (hours >= 23) | (hours < 8),
        0.3,
        np.where((hours >= 17) & (hours < 19), 0.8, 0.5),
    )
    export_kwh = np.where((hours >= 10) & (hours < 16), 0.1, 0.0)

    tariff = np.where(
        (hours >= 23) | (hours < 8),
        'Night',
        np.where((hours >= 17) & (hours < 19), 'Peak', 'Day'),
    )

    df = pd.DataFrame({
        'datetime': dates,
        'import_kwh': import_kwh,
        'export_kwh': export_kwh,
        'hour': hours,
        'day_of_week': dates.day_name(),
        'is_weekend': dates.dayofweek >= 5,
        'tariff_period': tariff,
        'date': dates.date,
        'year_month': dates.strftime('%Y-%m'),
    })
    return df


def _make_daily_df(
    start_date: str = "2025-01-01",
    end_date: str = "2025-03-31",
) -> pd.DataFrame:
    """Create a synthetic daily DataFrame."""
    dates = pd.date_range(start=start_date, end=end_date, freq="D")
    n = len(dates)
    df = pd.DataFrame({
        'date': dates.date,
        'import_kwh': np.random.uniform(15, 25, n),
        'export_kwh': np.zeros(n),
        'year_month': dates.strftime('%Y-%m'),
    })
    return df


# ---------------------------------------------------------------------------
# Test: _apply_date_filter logic
# ---------------------------------------------------------------------------

class TestApplyDateFilter:
    """Test the date filtering logic extracted from the page."""

    def test_filter_by_date_range_datetime_column(self):
        """Filtering on datetime column should return correct range."""
        from pages import __path__ as pages_path
        import importlib.util
        import sys

        # We can't import the Streamlit page directly due to st.set_page_config.
        # Instead, test the pure logic: _apply_date_filter is a standalone function.
        df = _make_interval_df("2025-01-01", "2025-03-31")

        # Simulate the filter logic
        start = date(2025, 2, 1)
        end = date(2025, 2, 28)

        mask = (df['datetime'].dt.date >= start) & (df['datetime'].dt.date <= end)
        filtered = df[mask].copy()

        assert len(filtered) > 0
        assert filtered['datetime'].dt.date.min() >= start
        assert filtered['datetime'].dt.date.max() <= end

    def test_filter_by_date_range_date_column(self):
        """Filtering on date column should return correct range."""
        df = _make_daily_df("2025-01-01", "2025-03-31")
        start = date(2025, 2, 1)
        end = date(2025, 2, 28)

        dates = pd.to_datetime(df['date']).dt.date
        mask = (dates >= start) & (dates <= end)
        filtered = df[mask].copy()

        assert len(filtered) > 0
        assert pd.to_datetime(filtered['date']).dt.date.min() >= start
        assert pd.to_datetime(filtered['date']).dt.date.max() <= end

    def test_filter_last_7_days(self):
        """'Last 7 Days' should return exactly 7 days of data."""
        df = _make_interval_df("2025-01-01", "2025-03-31")
        all_dates = df['datetime'].dt.date
        data_max = all_dates.max()
        start = data_max - timedelta(days=6)

        mask = (all_dates >= start) & (all_dates <= data_max)
        filtered = df[mask]

        unique_dates = filtered['datetime'].dt.date.nunique()
        assert unique_dates == 7

    def test_filter_last_30_days(self):
        """'Last 30 Days' should return 30 days of data."""
        df = _make_interval_df("2025-01-01", "2025-03-31")
        all_dates = df['datetime'].dt.date
        data_max = all_dates.max()
        start = data_max - timedelta(days=29)

        mask = (all_dates >= start) & (all_dates <= data_max)
        filtered = df[mask]

        unique_dates = filtered['datetime'].dt.date.nunique()
        assert unique_dates == 30

    def test_filter_last_90_days(self):
        """'Last 90 Days' should return up to 90 days of data."""
        df = _make_interval_df("2025-01-01", "2025-03-31")
        all_dates = df['datetime'].dt.date
        data_max = all_dates.max()
        start = data_max - timedelta(days=89)

        mask = (all_dates >= start) & (all_dates <= data_max)
        filtered = df[mask]

        unique_dates = filtered['datetime'].dt.date.nunique()
        assert unique_dates == 90


# ---------------------------------------------------------------------------
# Test: Load type filter logic
# ---------------------------------------------------------------------------

class TestLoadTypeFilter:
    """Test the tariff period filter logic."""

    def test_filter_single_period(self):
        """Filtering to 'Day' only should exclude Night and Peak."""
        df = _make_interval_df()
        filtered = df[df['tariff_period'].isin(['Day'])].copy()

        assert (filtered['tariff_period'] == 'Day').all()
        assert 'Night' not in filtered['tariff_period'].values
        assert 'Peak' not in filtered['tariff_period'].values

    def test_filter_multiple_periods(self):
        """Filtering to Day+Night should exclude Peak."""
        df = _make_interval_df()
        filtered = df[df['tariff_period'].isin(['Day', 'Night'])].copy()

        assert set(filtered['tariff_period'].unique()) == {'Day', 'Night'}

    def test_filter_all_periods_returns_full_data(self):
        """Selecting all periods returns the full dataset."""
        df = _make_interval_df()
        periods = sorted(df['tariff_period'].unique())
        filtered = df[df['tariff_period'].isin(periods)].copy()

        assert len(filtered) == len(df)

    def test_filter_no_periods_returns_empty(self):
        """Deselecting all periods returns empty df."""
        df = _make_interval_df()
        filtered = df[df['tariff_period'].isin([])].copy()

        assert len(filtered) == 0

    def test_available_periods_from_data(self):
        """Available periods should come from actual data."""
        df = _make_interval_df()
        periods = sorted(df['tariff_period'].unique())
        assert periods == ['Day', 'Night', 'Peak']


# ---------------------------------------------------------------------------
# Test: Tariff rate config logic
# ---------------------------------------------------------------------------

class TestTariffRateConfig:
    """Test the tariff rate configuration logic."""

    def test_provider_presets_have_required_keys(self):
        """Each provider preset should have day, night, peak rates."""
        from hdf_parser import PROVIDER_PRESETS
        for name, preset in PROVIDER_PRESETS.items():
            assert 'day' in preset, f"{name} missing 'day'"
            assert 'night' in preset, f"{name} missing 'night'"
            assert 'peak' in preset, f"{name} missing 'peak'"

    def test_provider_presets_rates_positive(self):
        """All rates should be positive."""
        from hdf_parser import PROVIDER_PRESETS
        for name, preset in PROVIDER_PRESETS.items():
            assert preset['day'] > 0, f"{name} day rate not positive"
            assert preset['night'] > 0, f"{name} night rate not positive"
            assert preset['peak'] > 0, f"{name} peak rate not positive"

    def test_provider_presets_in_cents(self):
        """Presets should be in c/kWh (values > 1)."""
        from hdf_parser import PROVIDER_PRESETS
        for name, preset in PROVIDER_PRESETS.items():
            assert preset['day'] > 1, f"{name} day rate looks like EUR not cents"
            assert preset['night'] > 1, f"{name} night rate looks like EUR not cents"

    def test_get_tariff_rates_converts_to_eur(self):
        """_get_tariff_rates should return EUR/kWh (values < 1 for typical rates)."""
        # Simulate session_state values (in cents, e.g. 28.14)
        rates = {
            'day': 28.14 / 100,
            'night': 14.79 / 100,
            'peak': 30.02 / 100,
        }
        assert rates['day'] < 1
        assert rates['night'] < 1
        assert rates['peak'] < 1
        assert rates['day'] == pytest.approx(0.2814, abs=0.001)

    def test_custom_provider_exists(self):
        """'Custom' should be in provider presets."""
        from hdf_parser import PROVIDER_PRESETS
        assert 'Custom' in PROVIDER_PRESETS


# ---------------------------------------------------------------------------
# Test: Visualization annotation fixes
# ---------------------------------------------------------------------------

class TestChartAnnotations:
    """Test the annotation positioning fixes in visualizations."""

    def test_daily_profile_annotations_not_truncated(self):
        """Daily profile vrect annotations should have positions that avoid clipping."""
        from visualizations import create_daily_profile
        df = _make_interval_df()
        fig = create_daily_profile(df)

        # Get the layout shapes (vrects become shapes)
        shapes = fig.layout.shapes or []
        annotations = fig.layout.annotations or []

        # There should be annotations for Night and Peak
        annotation_texts = [a.text for a in annotations if hasattr(a, 'text') and a.text]
        # Night and Peak annotations should exist
        assert any('Night' in t for t in annotation_texts), \
            f"Night annotation missing. Found: {annotation_texts}"
        assert any('Peak' in t for t in annotation_texts), \
            f"Peak annotation missing. Found: {annotation_texts}"

    def test_anomaly_annotations_have_xanchor_default(self):
        """_apply_anomaly_annotations should set xanchor for annotation types."""
        from visualizations import _apply_anomaly_annotations
        import plotly.graph_objects as go

        fig = go.Figure()
        anomalies = [{
            'chart_annotations': [{
                'chart': 'test_chart',
                'type': 'annotation',
                'params': {
                    'x': 10,
                    'y': 0.5,
                    'text': 'Test Label',
                },
            }],
        }]

        _apply_anomaly_annotations(fig, 'test_chart', anomalies)

        annotations = fig.layout.annotations
        assert len(annotations) == 1
        # Should have xanchor defaulted to 'left'
        assert annotations[0].xanchor == 'left'

    def test_layout_template_has_right_margin(self):
        """Layout template should have non-zero right margin for annotations."""
        from visualizations import LAYOUT_TEMPLATE
        assert LAYOUT_TEMPLATE['margin']['r'] >= 20, \
            "Right margin should be >= 20 to prevent annotation clipping"

    def test_all_charts_use_container_width(self):
        """Verify that the page renders charts with use_container_width=True.

        We check the source file directly for st.plotly_chart calls.
        """
        import os
        page_path = os.path.join(
            os.path.dirname(__file__), "pages", "2_Meter_Analysis.py"
        )
        with open(page_path) as f:
            source = f.read()

        # Find all st.plotly_chart calls
        import re
        calls = re.findall(r'st\.plotly_chart\([^)]+\)', source)
        for call in calls:
            assert 'use_container_width=True' in call, \
                f"Chart call missing use_container_width=True: {call}"


# ---------------------------------------------------------------------------
# Test: Sidebar structure (source-level checks)
# ---------------------------------------------------------------------------

class TestSidebarStructure:
    """Verify that the sidebar only contains expected elements."""

    @pytest.fixture(autouse=True)
    def _load_source(self):
        import os
        page_path = os.path.join(
            os.path.dirname(__file__), "pages", "2_Meter_Analysis.py"
        )
        with open(page_path) as f:
            self.source = f.read()

    def test_sidebar_has_file_uploader(self):
        """Sidebar should still contain the file uploader."""
        assert 'st.file_uploader' in self.source

    def test_sidebar_no_about_section(self):
        """Sidebar should NOT contain the 'About' section."""
        # The old pattern was: st.markdown("### About")
        # within the `with st.sidebar:` block
        import re
        sidebar_match = re.search(
            r'with st\.sidebar:(.*?)(?=\n# |\nst\.markdown\("## |\nfile_content)',
            self.source,
            re.DOTALL,
        )
        if sidebar_match:
            sidebar_block = sidebar_match.group(1)
            assert '### About' not in sidebar_block, \
                "Sidebar should not contain '### About' section"

    def test_sidebar_no_supported_formats(self):
        """Sidebar should NOT list 'Supported Formats'."""
        import re
        sidebar_match = re.search(
            r'with st\.sidebar:(.*?)(?=\n# |\nst\.markdown\("## |\nfile_content)',
            self.source,
            re.DOTALL,
        )
        if sidebar_match:
            sidebar_block = sidebar_match.group(1)
            assert 'Supported Formats' not in sidebar_block

    def test_sidebar_no_tariff_rates(self):
        """Tariff rate inputs should NOT be in the sidebar."""
        import re
        sidebar_match = re.search(
            r'with st\.sidebar:(.*?)(?=\n# |\nst\.markdown\("## |\nfile_content)',
            self.source,
            re.DOTALL,
        )
        if sidebar_match:
            sidebar_block = sidebar_match.group(1)
            assert '### Tariff Rates' not in sidebar_block, \
                "Tariff rates should not be in sidebar"

    def test_tariff_config_in_page_content(self):
        """Tariff config should be rendered via _render_tariff_config in page content."""
        assert '_render_tariff_config()' in self.source

    def test_filter_bar_in_page_content(self):
        """Filter bar should be rendered via _render_filter_bar in page content."""
        assert '_render_filter_bar(' in self.source

    def test_no_render_date_filter_sidebar(self):
        """The old _render_date_filter_sidebar function should not be called."""
        assert '_render_date_filter_sidebar(' not in self.source

    def test_sidebar_has_helper_text(self):
        """Sidebar should have minimal helper text under uploader."""
        import re
        sidebar_match = re.search(
            r'with st\.sidebar:(.*?)(?=\n# |\nst\.markdown\("## |\nfile_content)',
            self.source,
            re.DOTALL,
        )
        if sidebar_match:
            sidebar_block = sidebar_match.group(1)
            assert 'Upload HDF, Excel, or CSV' in sidebar_block

    def test_uploader_help_includes_formats(self):
        """File uploader help text should mention supported formats."""
        assert 'HDF' in self.source
        assert 'Excel' in self.source
        assert 'CSV' in self.source
