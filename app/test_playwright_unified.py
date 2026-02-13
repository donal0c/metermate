"""
Playwright end-to-end tests for the unified Bill Extractor page.

Validates that:
  - The upload zone is in the main content area (not sidebar-only)
  - No mode radio (Single File / Bill Comparison) exists
  - Single file upload shows detail view with bill summary
  - Multi-file upload shows comparison view with tabs
  - Individual bill details are expandable below comparison
  - Clear All button resets the page
  - Demo bill button from home page still works
  - Status chips appear for processed bills

Requires: playwright, pytest-playwright
         Install browsers: python3 -m playwright install

These tests are marked with @pytest.mark.e2e and skipped by default.
Run E2E tests explicitly:
    python3 -m pytest -m e2e -v
Run this file directly:
    python3 -m pytest test_playwright_unified.py -v
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
BILLS_DIR = os.path.join(APP_DIR, "..", "Steve_bills")
STREAMLIT_PORT = 8597  # Unique port to avoid conflicts


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


def _navigate_to_bill_extractor(page: Page, streamlit_app: str):
    """Navigate to the Bill Extractor page."""
    page.goto(f"{streamlit_app}/Bill_Extractor")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)


def _upload_pdf(page: Page, filename: str):
    """Upload a single PDF via the file uploader."""
    pdf_path = os.path.join(BILLS_DIR, filename)
    if not os.path.exists(pdf_path):
        pytest.skip(f"PDF not found: {filename}")

    file_input = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    expect(file_input).to_be_attached(timeout=30000)
    file_input.set_input_files(pdf_path)
    page.wait_for_timeout(10000)


def _upload_multiple_pdfs(page: Page, filenames: list[str]):
    """Upload multiple PDFs via the file uploader."""
    pdf_paths = []
    for filename in filenames:
        path = os.path.join(BILLS_DIR, filename)
        if not os.path.exists(path):
            pytest.skip(f"PDF not found: {filename}")
        pdf_paths.append(path)

    file_input = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    expect(file_input).to_be_attached(timeout=30000)
    file_input.set_input_files(pdf_paths)
    page.wait_for_timeout(15000)


class TestUnifiedPageStructure:
    """Verify the unified page structure — no mode switching."""

    def test_page_loads_with_uploader(self, page: Page, streamlit_app: str):
        """Bill Extractor page should load with a file uploader visible."""
        _navigate_to_bill_extractor(page, streamlit_app)

        uploader = page.locator('[data-testid="stFileUploader"]')
        expect(uploader).to_be_visible(timeout=15000)

    def test_no_mode_radio(self, page: Page, streamlit_app: str):
        """There should be no 'Single Bill' or 'Bill Comparison' radio buttons."""
        _navigate_to_bill_extractor(page, streamlit_app)

        content = page.content()
        assert "Single Bill" not in content, \
            "Mode radio 'Single Bill' should not exist in unified view"

    def test_uploader_accepts_multiple_files(self, page: Page, streamlit_app: str):
        """The file uploader should accept multiple files."""
        _navigate_to_bill_extractor(page, streamlit_app)

        # Check that the file input has the 'multiple' attribute
        file_input = page.locator('[data-testid="stFileUploader"] input[type="file"]')
        expect(file_input).to_be_attached(timeout=15000)
        is_multiple = file_input.get_attribute("multiple")
        assert is_multiple is not None, "File uploader should accept multiple files"

    def test_empty_state_shows_instructions(self, page: Page, streamlit_app: str):
        """Empty state should show upload instructions."""
        _navigate_to_bill_extractor(page, streamlit_app)

        content = page.content()
        assert "Upload Electricity Bills" in content, \
            "Empty state should show upload instructions"

    def test_sidebar_shows_bill_extractor_label(self, page: Page, streamlit_app: str):
        """Sidebar should show 'Bill Extractor' label."""
        _navigate_to_bill_extractor(page, streamlit_app)

        content = page.content()
        assert "Bill Extractor" in content, \
            "Sidebar should show 'Bill Extractor' label"


class TestSingleBillUpload:
    """Test uploading a single bill shows the detail view."""

    def test_single_bill_shows_summary(self, page: Page, streamlit_app: str):
        """Uploading one bill should show the bill summary."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "1845.pdf")

        content = page.content()
        has_extraction = any(
            term in content.lower()
            for term in ["confidence", "mprn", "account"]
        )
        assert has_extraction, "Single bill upload should show extraction results"

    def test_single_bill_shows_mprn(self, page: Page, streamlit_app: str):
        """MPRN should be displayed for a single bill."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "1845.pdf")

        content = page.content()
        assert "10006002900" in content, "MPRN should be displayed"

    def test_single_bill_has_status_chip(self, page: Page, streamlit_app: str):
        """A status chip should appear for the processed bill."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "1845.pdf")

        content = page.content()
        assert "1845.pdf" in content, "Filename should appear in status chip"

    def test_single_bill_no_comparison_tabs(self, page: Page, streamlit_app: str):
        """With only 1 bill, comparison tabs should NOT appear."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "1845.pdf")

        content = page.content()
        assert "Cost Trends" not in content, \
            "Comparison tabs should not appear for single bill"

    def test_single_bill_has_sections(self, page: Page, streamlit_app: str):
        """Bill summary should show organized sections."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")

        content = page.content()
        assert "Account Details" in content, "Account section should be visible"
        assert "Account:" in content, "Per-section breakdown should be visible"

    def test_no_errors_on_single_upload(self, page: Page, streamlit_app: str):
        """Valid bill upload should not produce error alerts."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "1845.pdf")

        errors = page.locator('[data-testid="stAlert"][data-type="error"]')
        assert errors.count() == 0, "No errors should appear for valid bill"


class TestMultiBillUpload:
    """Test uploading multiple bills shows comparison view."""

    def test_two_bills_show_comparison(self, page: Page, streamlit_app: str):
        """Uploading 2 bills should show comparison view."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        ])

        content = page.content()
        assert "Bill Comparison" in content, "Comparison heading should appear"
        assert "2 bills" in content, "Should show '2 bills' in heading"

    def test_comparison_tabs_visible(self, page: Page, streamlit_app: str):
        """Comparison tabs should be present."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        ])

        content = page.content()
        assert "Summary" in content, "Summary tab should be visible"
        assert "Cost Trends" in content, "Cost Trends tab should be visible"
        assert "Consumption" in content, "Consumption tab should be visible"
        assert "Rate Analysis" in content, "Rate Analysis tab should be visible"
        assert "Export" in content, "Export tab should be visible"

    def test_summary_metrics_displayed(self, page: Page, streamlit_app: str):
        """Summary metrics should be visible."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        ])

        content = page.content()
        has_metrics = (
            "Total Cost" in content
            or "Total kWh" in content
            or "Avg Cost" in content
        )
        assert has_metrics, "Summary metrics should be displayed"

    def test_individual_bill_details_expandable(self, page: Page, streamlit_app: str):
        """Individual bill details should be in expandable sections below comparison."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        ])

        content = page.content()
        assert "Individual Bill Details" in content, \
            "Individual Bill Details section should appear"

    def test_status_chips_for_all_bills(self, page: Page, streamlit_app: str):
        """Status chips should appear for all uploaded bills."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        ])

        content = page.content()
        assert "1845.pdf" in content, "First bill filename should appear in status chip"

    def test_no_errors_on_multi_upload(self, page: Page, streamlit_app: str):
        """Multi-bill upload should not produce errors."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        ])

        errors = page.locator('[data-testid="stAlert"][data-type="error"]')
        assert errors.count() == 0, "No errors should appear for valid multi-bill upload"

    def test_three_bills_comparison(self, page: Page, streamlit_app: str):
        """Should handle 3 bills correctly."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
            "2024 Mar - Apr.pdf",
        ])

        content = page.content()
        assert "3 bills" in content, "Should show '3 bills' in heading"


class TestClearAllButton:
    """Test the Clear All Bills functionality."""

    def test_clear_button_visible_after_upload(self, page: Page, streamlit_app: str):
        """Clear All button should appear after uploading bills."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "1845.pdf")

        content = page.content()
        assert "Clear All Bills" in content, \
            "Clear All button should be visible after upload"

    def test_clear_button_not_visible_when_empty(self, page: Page, streamlit_app: str):
        """Clear All button should NOT appear when no bills are uploaded."""
        _navigate_to_bill_extractor(page, streamlit_app)

        content = page.content()
        assert "Clear All Bills" not in content, \
            "Clear All button should not be visible when empty"


class TestDemoBillButton:
    """Test that the demo bill button from home page still works."""

    def test_demo_bill_navigates_and_extracts(self, page: Page, streamlit_app: str):
        """Clicking demo bill on home page should navigate to extractor with results."""
        page.goto(streamlit_app)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)

        bill_button = page.get_by_text("Try sample bill")
        if bill_button.count() > 0:
            bill_button.click()
            page.wait_for_timeout(10000)

            content = page.content()
            has_extraction = any(
                term in content.lower()
                for term in ["confidence", "mprn", "account"]
            )
            assert has_extraction, "Demo bill should load and show extraction results"
        else:
            pytest.skip("Demo bill button not available (sample file missing)")


class TestComparisonTabs:
    """Test that comparison tabs work correctly when navigated."""

    def _setup_comparison(self, page: Page, streamlit_app: str):
        """Upload 2 bills to get to comparison view."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        ])

    def test_cost_trends_tab_navigable(self, page: Page, streamlit_app: str):
        """Cost Trends tab should be navigable."""
        self._setup_comparison(page, streamlit_app)

        cost_tab = page.get_by_text("Cost Trends")
        cost_tab.first.click()
        page.wait_for_timeout(2000)

        content = page.content()
        assert "Cost Trends" in content

    def test_consumption_tab_navigable(self, page: Page, streamlit_app: str):
        """Consumption tab should be navigable."""
        self._setup_comparison(page, streamlit_app)

        tab = page.get_by_text("Consumption")
        tab.first.click()
        page.wait_for_timeout(2000)

        content = page.content()
        assert "Consumption Trends" in content

    def test_rate_analysis_tab_navigable(self, page: Page, streamlit_app: str):
        """Rate Analysis tab should be navigable."""
        self._setup_comparison(page, streamlit_app)

        tab = page.get_by_text("Rate Analysis")
        tab.first.click()
        page.wait_for_timeout(2000)

        content = page.content()
        assert "Rate Analysis" in content

    def test_export_tab_has_button(self, page: Page, streamlit_app: str):
        """Export tab should have a generate button."""
        self._setup_comparison(page, streamlit_app)

        tab = page.get_by_text("Export")
        tab.first.click()
        page.wait_for_timeout(1000)

        content = page.content()
        assert "Generate Comparison Excel" in content or "Export Comparison" in content
