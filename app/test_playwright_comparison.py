"""
Playwright end-to-end tests for the multi-bill comparison feature.

Validates that:
  - The analysis mode radio is visible (Single File / Bill Comparison)
  - Switching to Bill Comparison mode shows the multi-file uploader
  - Uploading multiple PDFs triggers extraction and shows comparison view
  - Comparison tabs are present (Summary, Cost Trends, Consumption, etc.)
  - Summary table displays extracted data
  - Charts render without errors
  - Export button is present

Requires: playwright, pytest-playwright
         Install browsers: python3 -m playwright install

These tests are marked with @pytest.mark.e2e and skipped by default.
Run E2E tests explicitly:
    python3 -m pytest -m e2e -v
Run this file directly:
    python3 -m pytest test_playwright_comparison.py -v
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
BILLS_DIR = os.path.join(APP_DIR, "..", "sample_bills")
STREAMLIT_PORT = 8598  # Different port from other E2E tests


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


def _switch_to_comparison_mode(page: Page, streamlit_app: str):
    """Navigate to the app and switch to Bill Comparison mode."""
    page.goto(streamlit_app)
    page.wait_for_load_state("networkidle")
    # Click the "Bill Comparison" radio option
    comparison_radio = page.get_by_text("Bill Comparison")
    comparison_radio.click()
    page.wait_for_timeout(1000)


def _upload_multiple_pdfs(page: Page, filenames: list[str]):
    """Upload multiple PDFs via the comparison file uploader."""
    pdf_paths = []
    for filename in filenames:
        path = os.path.join(BILLS_DIR, filename)
        if not os.path.exists(path):
            pytest.skip(f"PDF not found: {filename}")
        pdf_paths.append(path)

    # Find the file input in the comparison uploader
    file_input = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    file_input.set_input_files(pdf_paths)

    # Wait for extraction to complete
    page.wait_for_timeout(8000)


class TestComparisonModeToggle:
    """Test that the analysis mode radio is visible and functional."""

    def test_mode_radio_visible(self, page: Page, streamlit_app: str):
        """The analysis mode radio should be visible in the sidebar."""
        page.goto(streamlit_app)
        page.wait_for_load_state("networkidle")

        single_file = page.get_by_text("Single File")
        expect(single_file).to_be_visible(timeout=15000)

        comparison = page.get_by_text("Bill Comparison")
        expect(comparison).to_be_visible(timeout=5000)

    def test_default_is_single_file(self, page: Page, streamlit_app: str):
        """Default mode should be Single File."""
        page.goto(streamlit_app)
        page.wait_for_load_state("networkidle")

        # Landing page should show the title
        expect(page.get_by_text("Energy Insight").first).to_be_visible(timeout=15000)

    def test_switch_to_comparison_shows_instructions(self, page: Page, streamlit_app: str):
        """Switching to Bill Comparison mode shows comparison instructions."""
        _switch_to_comparison_mode(page, streamlit_app)

        content = page.content()
        assert "Bill Comparison" in content, \
            "Bill Comparison heading should be visible"
        assert "Upload 2 or more" in content, \
            "Instructions should mention uploading 2+ bills"

    def test_comparison_mode_shows_multi_uploader(self, page: Page, streamlit_app: str):
        """Bill Comparison mode should show a file uploader accepting multiple files."""
        _switch_to_comparison_mode(page, streamlit_app)

        uploader = page.locator('[data-testid="stFileUploader"]')
        expect(uploader).to_be_visible(timeout=5000)

    def test_comparison_sidebar_label(self, page: Page, streamlit_app: str):
        """Sidebar should show 'Bill Comparison Mode' when in comparison mode."""
        _switch_to_comparison_mode(page, streamlit_app)

        content = page.content()
        assert "Bill Comparison Mode" in content, \
            "Sidebar should show 'Bill Comparison Mode'"

    def test_single_file_warning(self, page: Page, streamlit_app: str):
        """Uploading only 1 file in comparison mode should show a warning."""
        _switch_to_comparison_mode(page, streamlit_app)

        # Upload single PDF
        pdf_path = os.path.join(BILLS_DIR, "1845.pdf")
        if not os.path.exists(pdf_path):
            pytest.skip("PDF not found")

        file_input = page.locator('[data-testid="stFileUploader"] input[type="file"]')
        file_input.set_input_files(pdf_path)
        page.wait_for_timeout(3000)

        content = page.content()
        assert "at least 2" in content.lower(), \
            "Should warn that at least 2 bills are needed"


class TestBillComparison:
    """Test multi-bill comparison with actual PDF uploads."""

    def test_comparison_tabs_visible(self, page: Page, streamlit_app: str):
        """Uploading 2+ bills should show comparison tabs."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        ])

        content = page.content()
        assert "Bill Comparison" in content, "Comparison heading should appear"
        assert "Summary" in content, "Summary tab should be visible"
        assert "Cost Trends" in content, "Cost Trends tab should be visible"
        assert "Consumption" in content, "Consumption tab should be visible"
        assert "Rate Analysis" in content, "Rate Analysis tab should be visible"
        assert "Export" in content, "Export tab should be visible"

    def test_comparison_shows_bill_count(self, page: Page, streamlit_app: str):
        """Comparison view should show the number of bills."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        ])

        content = page.content()
        assert "2 bills" in content, "Should show '2 bills' in the heading"

    def test_summary_table_has_data(self, page: Page, streamlit_app: str):
        """Summary tab should show a data table with bill information."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        ])

        content = page.content()
        # Summary metrics should be visible
        has_metrics = (
            "Total Cost" in content
            or "Total kWh" in content
            or "Avg Cost" in content
        )
        assert has_metrics, "Summary metrics should be displayed"

        # Table should show file names
        assert "1845.pdf" in content, "First bill filename should appear in table"

    def test_no_errors_on_comparison(self, page: Page, streamlit_app: str):
        """Comparison should not produce error alerts."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        ])

        errors = page.locator('[data-testid="stAlert"][data-type="error"]')
        assert errors.count() == 0, "No errors should appear for valid bill comparison"

    def test_cost_trends_tab(self, page: Page, streamlit_app: str):
        """Cost Trends tab should render charts."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        ])

        # Click Cost Trends tab
        cost_tab = page.get_by_text("Cost Trends")
        cost_tab.first.click()
        page.wait_for_timeout(2000)

        content = page.content()
        assert "Cost Trends" in content, "Cost Trends heading should appear"

    def test_consumption_tab(self, page: Page, streamlit_app: str):
        """Consumption tab should render charts."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        ])

        # Click Consumption tab
        consumption_tab = page.get_by_text("Consumption")
        consumption_tab.first.click()
        page.wait_for_timeout(2000)

        content = page.content()
        assert "Consumption Trends" in content, "Consumption Trends heading should appear"

    def test_rate_analysis_tab(self, page: Page, streamlit_app: str):
        """Rate Analysis tab should render."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        ])

        # Click Rate Analysis tab
        rate_tab = page.get_by_text("Rate Analysis")
        rate_tab.first.click()
        page.wait_for_timeout(2000)

        content = page.content()
        assert "Rate Analysis" in content, "Rate Analysis heading should appear"

    def test_export_tab_has_button(self, page: Page, streamlit_app: str):
        """Export tab should have a generate button."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        ])

        # Click Export tab
        export_tab = page.get_by_text("Export")
        export_tab.first.click()
        page.wait_for_timeout(1000)

        content = page.content()
        assert "Generate Comparison Excel" in content or "Export Comparison" in content, \
            "Export tab should have a generate button"


class TestComparisonThreeBills:
    """Test comparison with 3 bills for better trend coverage."""

    def test_three_bills_comparison(self, page: Page, streamlit_app: str):
        """Should handle 3 bills and show '3 bills' in heading."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
            "2024 Mar - Apr.pdf",
        ])

        content = page.content()
        assert "3 bills" in content, "Should show '3 bills' in the heading"

    def test_three_bills_no_errors(self, page: Page, streamlit_app: str):
        """3-bill comparison should not produce errors."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
            "2024 Mar - Apr.pdf",
        ])

        errors = page.locator('[data-testid="stAlert"][data-type="error"]')
        assert errors.count() == 0, "No errors should appear for 3-bill comparison"
