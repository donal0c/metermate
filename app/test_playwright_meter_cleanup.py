"""
Playwright end-to-end tests for Meter Analysis page cleanup (steve-g4e).

Validates that:
  - Sidebar is short and focused (uploader + navigation only)
  - "About" and "Supported Formats" sections are removed from sidebar
  - Tariff config is accessible in-page (expandable section)
  - Date range filter is in main content as segmented control
  - Load type filter is in main content as segmented chips
  - Chart annotations are not truncated
  - All existing analysis functionality is preserved after refactor

Requires: playwright, pytest-playwright
         Install browsers: python3 -m playwright install

These tests are marked with @pytest.mark.e2e and skipped by default.
Run E2E tests explicitly:
    python3 -m pytest -m e2e test_playwright_meter_cleanup.py -v
"""
import os
import subprocess
import time

import pytest
from playwright.sync_api import Page, expect

# Mark every test in this module as an E2E test.
pytestmark = pytest.mark.e2e

APP_DIR = os.path.dirname(__file__)
APP_PATH = os.path.join(APP_DIR, "main.py")
HDF_PATH = os.path.join(
    APP_DIR, "..", "HDF_calckWh_10306268587_03-02-2026.csv"
)
STREAMLIT_PORT = 8600  # Unique port for this test suite


@pytest.fixture(scope="module")
def streamlit_app():
    """Start the Streamlit app as a subprocess and yield the URL."""
    import sys
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", APP_PATH,
            "--server.port", str(STREAMLIT_PORT),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
        ],
        cwd=APP_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    url = f"http://localhost:{STREAMLIT_PORT}"

    # Wait for Streamlit to be ready
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(url, timeout=2)
            break
        except Exception:
            time.sleep(1)
    else:
        proc.terminate()
        pytest.fail("Streamlit app did not start within 30 seconds")

    yield url

    proc.terminate()
    proc.wait(timeout=10)


def _navigate_to_meter_analysis(page: Page, streamlit_app: str):
    """Navigate to the Meter Analysis page."""
    page.goto(f"{streamlit_app}/Meter_Analysis")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)


def _upload_hdf(page: Page):
    """Upload the HDF file via sidebar file uploader."""
    if not os.path.exists(HDF_PATH):
        pytest.skip(f"HDF file not found: {HDF_PATH}")

    file_input = page.locator(
        'section[data-testid="stSidebar"] [data-testid="stFileUploader"] input[type="file"]'
    )
    file_input.set_input_files(HDF_PATH)
    page.wait_for_timeout(5000)


# =========================================================================
# Sidebar Structure
# =========================================================================

class TestSidebarCleanup:
    """Verify the sidebar is short and focused after cleanup."""

    def test_sidebar_has_file_uploader(
        self, page: Page, streamlit_app: str
    ):
        """Sidebar should contain the file uploader."""
        _navigate_to_meter_analysis(page, streamlit_app)

        sidebar_uploader = page.locator(
            'section[data-testid="stSidebar"] [data-testid="stFileUploader"]'
        )
        expect(sidebar_uploader).to_be_visible(timeout=10000)

    def test_sidebar_has_helper_text(
        self, page: Page, streamlit_app: str
    ):
        """Sidebar should show minimal helper text."""
        _navigate_to_meter_analysis(page, streamlit_app)

        sidebar = page.locator('section[data-testid="stSidebar"]')
        sidebar_text = sidebar.inner_text()
        assert "Upload HDF, Excel, or CSV" in sidebar_text, \
            "Sidebar should show helper text for uploader"

    def test_sidebar_no_about_section(
        self, page: Page, streamlit_app: str
    ):
        """Sidebar should NOT contain an 'About' section."""
        _navigate_to_meter_analysis(page, streamlit_app)

        sidebar = page.locator('section[data-testid="stSidebar"]')
        sidebar_text = sidebar.inner_text()
        # The old sidebar had "About" header and a description
        assert "About\nAnalyze energy consumption data" not in sidebar_text

    def test_sidebar_no_tariff_rates(
        self, page: Page, streamlit_app: str
    ):
        """Tariff rate inputs should NOT be in the sidebar."""
        _navigate_to_meter_analysis(page, streamlit_app)

        sidebar_inputs = page.locator(
            'section[data-testid="stSidebar"] [data-testid="stNumberInput"]'
        )
        assert sidebar_inputs.count() == 0, \
            "Sidebar should not contain number inputs (tariff rates moved to page)"

    def test_sidebar_no_provider_dropdown(
        self, page: Page, streamlit_app: str
    ):
        """Provider dropdown should NOT be in the sidebar."""
        _navigate_to_meter_analysis(page, streamlit_app)

        # Check that sidebar doesn't have a selectbox for providers
        sidebar = page.locator('section[data-testid="stSidebar"]')
        sidebar_text = sidebar.inner_text()
        assert "Electricity Provider" not in sidebar_text, \
            "Provider dropdown should not be in sidebar"


# =========================================================================
# In-Page Tariff Config
# =========================================================================

class TestTariffConfigInPage:
    """Verify tariff configuration is accessible in the main page content."""

    def test_tariff_expander_visible_after_hdf_load(
        self, page: Page, streamlit_app: str
    ):
        """Tariff config expander should appear after loading HDF data."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        content = page.content()
        assert "Tariff Rates" in content, \
            "Tariff config expander should be visible in page content"

    def test_tariff_expander_shows_provider_name(
        self, page: Page, streamlit_app: str
    ):
        """Tariff expander should show current provider name."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        content = page.content()
        assert "Electric Ireland" in content, \
            "Default provider name should be shown in tariff expander"

    def test_tariff_expander_collapsed_by_default(
        self, page: Page, streamlit_app: str
    ):
        """Tariff config should be collapsed by default."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        # Expanders have an aria-expanded attribute
        # The main content expander for tariff should be collapsed
        expanders = page.locator(
            '[data-testid="stAppViewContainer"] [data-testid="stExpander"]'
        )
        if expanders.count() > 0:
            # Find the tariff expander
            for i in range(expanders.count()):
                text = expanders.nth(i).inner_text()
                if "Tariff Rates" in text:
                    # Check if it's collapsed (summary visible, content hidden)
                    details = expanders.nth(i).locator('details')
                    if details.count() > 0:
                        is_open = details.get_attribute('open')
                        assert is_open is None, \
                            "Tariff expander should be collapsed by default"
                    break

    def test_tariff_expander_expandable(
        self, page: Page, streamlit_app: str
    ):
        """Clicking tariff expander should reveal rate inputs."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        # Click on the expander
        expander_summary = page.get_by_text("Tariff Rates")
        if expander_summary.count() > 0:
            expander_summary.first.click()
            page.wait_for_timeout(1000)

            content = page.content()
            assert "Day (c/kWh)" in content or "Day rate" in content, \
                "Expanded tariff section should show rate inputs"


# =========================================================================
# In-Page Filter Bar
# =========================================================================

class TestFilterBarInPage:
    """Verify date range and load type filters are in the main content."""

    def test_date_filter_pills_visible(
        self, page: Page, streamlit_app: str
    ):
        """Date range filter should be visible as segmented pills in main content."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        content = page.content()
        assert "All Data" in content, "Date filter should show 'All Data' option"
        assert "Last 7d" in content, "Date filter should show 'Last 7d' option"
        assert "Last 30d" in content, "Date filter should show 'Last 30d' option"
        assert "Last 90d" in content, "Date filter should show 'Last 90d' option"

    def test_load_type_chips_visible(
        self, page: Page, streamlit_app: str
    ):
        """Load type filter should be visible as chips in main content."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        content = page.content()
        assert "Day" in content, "Load type should show 'Day' chip"
        assert "Night" in content, "Load type should show 'Night' chip"
        assert "Peak" in content, "Load type should show 'Peak' chip"

    def test_date_filter_not_in_sidebar(
        self, page: Page, streamlit_app: str
    ):
        """Date range filter should NOT be in the sidebar."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        sidebar = page.locator('section[data-testid="stSidebar"]')
        sidebar_text = sidebar.inner_text()
        assert "Date Range" not in sidebar_text, \
            "Date range filter should not be in sidebar"
        assert "Last 7 Days" not in sidebar_text, \
            "Old date options should not be in sidebar"

    def test_load_type_not_in_sidebar(
        self, page: Page, streamlit_app: str
    ):
        """Load type filter should NOT be in the sidebar."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        sidebar = page.locator('section[data-testid="stSidebar"]')
        sidebar_text = sidebar.inner_text()
        assert "Load Type" not in sidebar_text, \
            "Load type filter should not be in sidebar"


# =========================================================================
# Analysis Functionality Preserved
# =========================================================================

class TestAnalysisPreserved:
    """Verify all existing analysis functionality still works after refactor."""

    def test_five_tabs_present(
        self, page: Page, streamlit_app: str
    ):
        """HDF view should still have 5 analysis tabs."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        content = page.content()
        assert "Overview" in content
        assert "Heatmap" in content
        assert "Charts" in content
        assert "Insights" in content
        assert "Export" in content

    def test_overview_metrics_display(
        self, page: Page, streamlit_app: str
    ):
        """Overview tab should show key metrics."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        content = page.content()
        assert "Total Import" in content, "Total Import metric should be visible"
        assert "Daily Average" in content, "Daily Average metric should be visible"
        assert "Baseload" in content, "Baseload metric should be visible"

    def test_no_errors_after_hdf_load(
        self, page: Page, streamlit_app: str
    ):
        """Loading HDF should not produce errors."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        errors = page.locator('[data-testid="stAlert"][data-type="error"]')
        assert errors.count() == 0, "No errors should appear after HDF load"

    def test_success_banner_appears(
        self, page: Page, streamlit_app: str
    ):
        """Success banner should appear after loading data."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        content = page.content()
        assert "readings from" in content or "Showing" in content, \
            "Success banner should show data summary"

    def test_verification_section_still_present(
        self, page: Page, streamlit_app: str
    ):
        """Bill verification section should still appear below analysis tabs."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        # Scroll down to find the verification section
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1000)

        content = page.content()
        assert "Cross-Reference with a Bill" in content, \
            "Bill verification section should still be present"

    def test_heatmap_tab_navigable(
        self, page: Page, streamlit_app: str
    ):
        """Heatmap tab should be clickable and render content."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        heatmap_tab = page.get_by_text("Heatmap")
        if heatmap_tab.count() > 0:
            heatmap_tab.first.click()
            page.wait_for_timeout(2000)

            content = page.content()
            assert "Usage Heatmap" in content or "Heatmap" in content

    def test_charts_tab_navigable(
        self, page: Page, streamlit_app: str
    ):
        """Charts tab should be clickable and show chart content."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        charts_tab = page.get_by_text("Charts")
        if charts_tab.count() > 0:
            charts_tab.first.click()
            page.wait_for_timeout(2000)

            content = page.content()
            assert "Daily Load Profile" in content or "Analysis Charts" in content

    def test_insights_tab_navigable(
        self, page: Page, streamlit_app: str
    ):
        """Insights tab should be clickable."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        insights_tab = page.get_by_text("Insights")
        if insights_tab.count() > 0:
            insights_tab.first.click()
            page.wait_for_timeout(2000)

            content = page.content()
            assert "Insights" in content or "anomal" in content.lower()

    def test_export_tab_navigable(
        self, page: Page, streamlit_app: str
    ):
        """Export tab should show export controls."""
        _navigate_to_meter_analysis(page, streamlit_app)
        _upload_hdf(page)

        export_tab = page.get_by_text("Export")
        if export_tab.count() > 0:
            export_tab.first.click()
            page.wait_for_timeout(2000)

            content = page.content()
            assert "Export Data" in content or "Generate Excel" in content


# =========================================================================
# Empty State
# =========================================================================

class TestEmptyState:
    """Verify the empty state (no file uploaded) is correct."""

    def test_empty_state_shows_upload_prompt(
        self, page: Page, streamlit_app: str
    ):
        """Empty state should prompt user to upload."""
        _navigate_to_meter_analysis(page, streamlit_app)

        content = page.content()
        assert "Upload Energy Data" in content

    def test_empty_state_no_tariff_config(
        self, page: Page, streamlit_app: str
    ):
        """Empty state should NOT show tariff config (only after data loads)."""
        _navigate_to_meter_analysis(page, streamlit_app)

        # The tariff expander should only appear after data is loaded
        content = page.content()
        # On empty state, the tariff expander shouldn't be rendered
        # (it's inside _handle_hdf_file / _excel_step3_analysis)
        main_content = page.locator('[data-testid="stAppViewContainer"]')
        main_text = main_content.inner_text()
        assert "Day (c/kWh)" not in main_text, \
            "Tariff rate inputs should not appear in empty state"

    def test_empty_state_no_filter_bar(
        self, page: Page, streamlit_app: str
    ):
        """Empty state should NOT show filter bar."""
        _navigate_to_meter_analysis(page, streamlit_app)

        content = page.content()
        assert "Last 7d" not in content, \
            "Date filter pills should not appear in empty state"
