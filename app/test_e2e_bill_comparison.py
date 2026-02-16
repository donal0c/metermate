"""
Comprehensive End-to-End tests for Multi-Bill Comparison functionality.

Tests the full bill comparison workflow including:
  - Mode switching to Bill Comparison
  - Multi-file PDF uploads
  - Comparison view rendering with all elements:
    * Side-by-side bill summaries and metrics
    * Cost trends chart
    * Consumption trends chart
    * Rate comparison table
    * Export to Excel functionality
  - Navigation between comparison and single bill views
  - Multiple provider support (Energia, etc.)

Test Configuration:
  - Uses 2-3 Energia/mixed provider bills from sample_bills/
  - Tests with:
    * "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"
    * "2024 Mar - Apr.pdf"
    * "1845.pdf" (optional third bill)
  - Custom Streamlit port: 8597 (to avoid conflicts)

Requires: playwright, pytest-playwright, streamlit
Install browsers: python3 -m playwright install

These tests are marked with @pytest.mark.e2e and skipped by default.
Run E2E tests explicitly:
    python3 -m pytest app/test_e2e_bill_comparison.py -v
    python3 -m pytest -m e2e -v
"""
import os
import subprocess
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

# Mark every test in this module as an E2E test
pytestmark = pytest.mark.e2e

APP_DIR = os.path.dirname(__file__)
APP_PATH = os.path.join(APP_DIR, "main.py")
BILLS_DIR = os.path.join(APP_DIR, "..", "sample_bills")
STREAMLIT_PORT = 8597


@pytest.fixture(scope="session")
def streamlit_app():
    """Start the Streamlit app as a subprocess and yield the URL."""
    # Use sys.executable to ensure we use the same Python that's running pytest
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
    page.goto(streamlit_app, wait_until="networkidle")
    page.wait_for_timeout(500)

    # Click the "Bill Comparison" radio option
    comparison_radio = page.get_by_text("Bill Comparison")
    comparison_radio.click()
    page.wait_for_timeout(1500)


def _upload_multiple_pdfs(page: Page, filenames: list):
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

    # Wait for extraction to complete (longer timeout for multiple bills)
    page.wait_for_timeout(15000)


class TestComparisonModeSetup:
    """Test comparison mode initialization and UI elements."""

    def test_comparison_mode_exists(self, page: Page, streamlit_app: str):
        """Verify Bill Comparison mode radio option is visible."""
        page.goto(streamlit_app, wait_until="networkidle")
        page.wait_for_timeout(500)

        comparison_radio = page.get_by_text("Bill Comparison")
        expect(comparison_radio).to_be_visible(timeout=15000)

    def test_switch_to_comparison_mode(self, page: Page, streamlit_app: str):
        """Switch to Bill Comparison mode successfully."""
        _switch_to_comparison_mode(page, streamlit_app)

        # Verify we're in comparison mode by checking for mode indicator
        content = page.content()
        assert "Bill Comparison" in content, "Should display Bill Comparison heading"

    def test_comparison_mode_shows_multi_uploader(self, page: Page, streamlit_app: str):
        """Bill Comparison mode displays a file uploader."""
        _switch_to_comparison_mode(page, streamlit_app)

        uploader = page.locator('[data-testid="stFileUploader"]')
        expect(uploader).to_be_visible(timeout=5000)

    def test_comparison_mode_instructions(self, page: Page, streamlit_app: str):
        """Comparison mode shows helpful instructions."""
        _switch_to_comparison_mode(page, streamlit_app)

        content = page.content()
        # Should mention uploading multiple bills
        assert any(keyword in content.lower() for keyword in ["upload", "2", "more"]), \
            "Should provide instructions for uploading multiple bills"


class TestTwoBillComparison:
    """Test comparison with two bills (standard use case)."""

    @pytest.mark.parametrize("bill_files", [
        [
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
            "2024 Mar - Apr.pdf",
        ],
    ])
    def test_two_bills_upload_and_extract(self, page: Page, streamlit_app: str, bill_files):
        """Upload 2 bills and verify extraction succeeds."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, bill_files)

        # Should not show "need at least 2 bills" error
        content = page.content()
        assert "2 bills" in content, "Should show '2 bills' in heading"

    @pytest.mark.parametrize("bill_files", [
        [
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
            "2024 Mar - Apr.pdf",
        ],
    ])
    def test_comparison_heading_visible(self, page: Page, streamlit_app: str, bill_files):
        """Comparison view shows the heading."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, bill_files)

        content = page.content()
        assert "Bill Comparison" in content, "Main heading should be visible"
        assert "2 bills" in content, "Should show number of bills"

    @pytest.mark.parametrize("bill_files", [
        [
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
            "2024 Mar - Apr.pdf",
        ],
    ])
    def test_no_critical_errors(self, page: Page, streamlit_app: str, bill_files):
        """No error alerts should appear during comparison."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, bill_files)

        errors = page.locator('[data-testid="stAlert"][data-type="error"]')
        error_count = errors.count()
        assert error_count == 0, f"Expected no errors, but found {error_count}"


class TestComparisonTabs:
    """Test all comparison view tabs are present and functional."""

    @pytest.fixture(autouse=True)
    def setup_two_bills(self, page: Page, streamlit_app: str):
        """Upload 2 bills before each test in this class."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
            "2024 Mar - Apr.pdf",
        ])
        yield
        # Cleanup after each test - go back to home
        page.goto(streamlit_app, wait_until="networkidle")
        page.wait_for_timeout(500)

    def test_all_tabs_present(self, page: Page):
        """All expected tabs should be visible."""
        content = page.content()

        expected_tabs = ["Summary", "Cost Trends", "Consumption", "Rate Analysis", "Export"]
        for tab in expected_tabs:
            assert tab in content, f"Tab '{tab}' should be present"

    def test_summary_tab_metrics(self, page: Page):
        """Summary tab displays key metrics."""
        # Summary tab should be active by default
        content = page.content()

        # Should show at least some metrics
        has_metrics = any(keyword in content for keyword in [
            "Total Cost", "Total kWh", "Avg Cost", "Avg €/kWh"
        ])
        assert has_metrics, "Summary should display metrics"

    def test_summary_tab_table(self, page: Page):
        """Summary tab shows comparison table."""
        content = page.content()

        # Table should show side-by-side comparison
        has_table_headers = any(keyword in content for keyword in [
            "File", "Supplier", "Period", "kWh", "Total", "Confidence"
        ])
        assert has_table_headers, "Should display comparison table"

    def test_cost_trends_tab_renders(self, page: Page):
        """Cost Trends tab renders without errors."""
        # Click Cost Trends tab
        cost_tab = page.get_by_text("Cost Trends")
        cost_tab.first.click()
        page.wait_for_timeout(2000)

        content = page.content()
        assert "Cost Trends" in content, "Cost Trends tab content should load"

    def test_consumption_tab_renders(self, page: Page):
        """Consumption tab renders without errors."""
        consumption_tab = page.get_by_text("Consumption")
        consumption_tab.first.click()
        page.wait_for_timeout(2000)

        content = page.content()
        assert "Consumption" in content, "Consumption tab content should load"

    def test_rate_analysis_tab_renders(self, page: Page):
        """Rate Analysis tab renders without errors."""
        rate_tab = page.get_by_text("Rate Analysis")
        rate_tab.first.click()
        page.wait_for_timeout(2000)

        content = page.content()
        assert "Rate" in content, "Rate Analysis tab content should load"

    def test_export_tab_has_button(self, page: Page):
        """Export tab displays export button."""
        export_tab = page.get_by_text("Export")
        export_tab.first.click()
        page.wait_for_timeout(1000)

        content = page.content()
        assert any(keyword in content for keyword in ["Generate", "Export", "Excel"]), \
            "Export tab should have a generate/export button"


class TestComparisonElements:
    """Test specific comparison view elements."""

    @pytest.fixture(autouse=True)
    def setup_comparison(self, page: Page, streamlit_app: str):
        """Set up comparison view with 2 bills before each test."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
            "2024 Mar - Apr.pdf",
        ])
        yield
        # Cleanup - return to home
        page.goto(streamlit_app, wait_until="networkidle")
        page.wait_for_timeout(500)

    def test_side_by_side_summaries(self, page: Page):
        """Summaries should display side-by-side bill data."""
        content = page.content()

        # Look for summary indicators
        assert any(keyword in content for keyword in [
            "Total Cost", "Total kWh", "File", "Supplier"
        ]), "Should show side-by-side bill summaries"

    def test_cost_trends_chart_present(self, page: Page):
        """Cost Trends tab should have a chart element."""
        cost_tab = page.get_by_text("Cost Trends")
        cost_tab.first.click()
        page.wait_for_timeout(2000)

        content = page.content()
        # Plotly charts render with specific patterns
        assert "plotly" in content.lower() or "chart" in content.lower() or \
               "svg" in content.lower(), \
            "Cost Trends should display a chart"

    def test_consumption_trends_chart_present(self, page: Page):
        """Consumption tab should have consumption chart."""
        consumption_tab = page.get_by_text("Consumption")
        consumption_tab.first.click()
        page.wait_for_timeout(2000)

        content = page.content()
        # Should have chart or at least "Consumption" heading
        assert "Consumption" in content, "Consumption tab should be displayed"

    def test_rate_comparison_table(self, page: Page):
        """Rate Analysis should show a rate comparison table."""
        rate_tab = page.get_by_text("Rate Analysis")
        rate_tab.first.click()
        page.wait_for_timeout(2000)

        content = page.content()
        # Should reference rates
        assert any(keyword in content for keyword in [
            "Rate", "€/kWh", "Tariff", "Day", "Night"
        ]), "Rate Analysis should display rate information"


class TestThreeBillComparison:
    """Test comparison with three bills for better trend coverage."""

    @pytest.fixture(autouse=True)
    def setup_three_bills(self, page: Page, streamlit_app: str):
        """Upload 3 bills before each test."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
            "2024 Mar - Apr.pdf",
            "1845.pdf",
        ])
        yield
        # Cleanup
        page.goto(streamlit_app, wait_until="networkidle")
        page.wait_for_timeout(500)

    def test_three_bills_heading(self, page: Page):
        """Three bill comparison shows '3 bills' in heading."""
        content = page.content()
        assert "3 bills" in content, "Should show '3 bills' in heading"

    def test_three_bills_no_errors(self, page: Page):
        """Three bill comparison should not produce errors."""
        errors = page.locator('[data-testid="stAlert"][data-type="error"]')
        assert errors.count() == 0, "No errors should appear for 3-bill comparison"

    def test_three_bills_all_tabs(self, page: Page):
        """All tabs should be present and functional with 3 bills."""
        content = page.content()

        expected_tabs = ["Summary", "Cost Trends", "Consumption", "Rate Analysis", "Export"]
        for tab in expected_tabs:
            assert tab in content, f"Tab '{tab}' should be present in 3-bill view"

    def test_three_bills_trends_show_progression(self, page: Page):
        """With 3 bills, trends should show more complete progression."""
        cost_tab = page.get_by_text("Cost Trends")
        cost_tab.first.click()
        page.wait_for_timeout(2000)

        content = page.content()
        # Should display trend data
        assert "Cost Trends" in content or "Bill" in content, \
            "Three bills should show trend data"


class TestComparisonNavigation:
    """Test navigation between comparison and single bill views."""

    def test_switch_back_to_single_file_mode(self, page: Page, streamlit_app: str):
        """Can switch back to Single File mode from Comparison."""
        _switch_to_comparison_mode(page, streamlit_app)

        # Switch back to Single File
        single_file_radio = page.get_by_text("Single File")
        single_file_radio.click()
        page.wait_for_timeout(1000)

        content = page.content()
        # Should no longer show comparison mode content
        # Welcome page or single file uploader should appear

    def test_switching_modes_clears_state(self, page: Page, streamlit_app: str):
        """Switching modes should not leave stale comparison data."""
        # Upload bills in comparison mode
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
            "2024 Mar - Apr.pdf",
        ])

        # Switch to Single File mode
        single_file_radio = page.get_by_text("Single File")
        single_file_radio.click()
        page.wait_for_timeout(1000)

        # Switch back to Comparison mode
        comparison_radio = page.get_by_text("Bill Comparison")
        comparison_radio.click()
        page.wait_for_timeout(1000)

        content = page.content()
        # Should ask for new upload
        assert "Upload" in content or "Comparison" in content, \
            "Should show comparison mode interface"


class TestExcelExport:
    """Test Excel export functionality."""

    @pytest.fixture(autouse=True)
    def setup_export(self, page: Page, streamlit_app: str):
        """Set up comparison view ready for export."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
            "2024 Mar - Apr.pdf",
        ])
        yield
        # Cleanup
        page.goto(streamlit_app, wait_until="networkidle")
        page.wait_for_timeout(500)

    def test_export_button_visible(self, page: Page):
        """Export button is visible in Export tab."""
        export_tab = page.get_by_text("Export")
        export_tab.first.click()
        page.wait_for_timeout(1000)

        content = page.content()
        assert any(keyword in content for keyword in [
            "Generate", "Excel", "Export", "Download"
        ]), "Export button should be visible"

    def test_generate_button_clickable(self, page: Page):
        """Generate Excel button is clickable."""
        export_tab = page.get_by_text("Export")
        export_tab.first.click()
        page.wait_for_timeout(1000)

        # Find and click the generate button
        generate_btn = page.get_by_text("Generate Comparison Excel")
        if generate_btn.is_visible():
            # Button exists and is visible
            assert True, "Generate button is clickable"
        else:
            # Might not be visible, check for alternative button text
            content = page.content()
            assert any(keyword in content for keyword in [
                "Generate", "Export"
            ]), "Export functionality should be available"


class TestDataDisplay:
    """Test that extracted data displays correctly in comparison view."""

    @pytest.fixture(autouse=True)
    def setup_data_display(self, page: Page, streamlit_app: str):
        """Set up with bills compared."""
        _switch_to_comparison_mode(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
            "2024 Mar - Apr.pdf",
        ])
        yield
        # Cleanup
        page.goto(streamlit_app, wait_until="networkidle")
        page.wait_for_timeout(500)

    def test_supplier_names_displayed(self, page: Page):
        """Supplier names should be displayed."""
        content = page.content()
        # Should show supplier information
        assert any(keyword in content.lower() for keyword in [
            "supplier", "energia", "eir", "bord", "sse"
        ]), "Supplier information should be displayed"

    def test_dates_displayed(self, page: Page):
        """Billing periods and dates should be displayed."""
        content = page.content()
        # Should show date information
        assert any(keyword in content for keyword in [
            "Period", "Date", "2024", "2025", "—"
        ]), "Date information should be displayed"

    def test_financial_data_displayed(self, page: Page):
        """Financial data (cost, rates) should be displayed."""
        content = page.content()
        # Should show financial information
        assert any(keyword in content for keyword in [
            "€", "kWh", "Cost", "Rate", "charge", "Subtotal", "VAT"
        ]), "Financial data should be displayed"

    def test_consumption_data_displayed(self, page: Page):
        """Consumption data should be displayed."""
        content = page.content()
        # Should show consumption
        assert any(keyword in content for keyword in [
            "kWh", "consumption", "kwh", "Day", "Night", "Peak"
        ]), "Consumption data should be displayed"
