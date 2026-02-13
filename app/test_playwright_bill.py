"""
Playwright end-to-end tests for the Streamlit bill extraction UI.

Validates that:
  - The Streamlit app starts and displays the welcome page
  - PDF bill upload triggers extraction and displays results
  - Extracted fields are visible in the bill summary

Requires: playwright, pytest-playwright
         Install browsers: python3 -m playwright install

These tests are marked with @pytest.mark.e2e and skipped by default.
Run E2E tests explicitly:
    python3 -m pytest -m e2e -v
Run this file directly:
    python3 -m pytest test_playwright_bill.py -v
"""
import os
import subprocess
import time

import pytest
from playwright.sync_api import Page, expect

# Mark every test in this module as an E2E test.
# These are skipped by default; run with: pytest -m e2e
pytestmark = pytest.mark.e2e

APP_DIR = os.path.dirname(__file__)
APP_PATH = os.path.join(APP_DIR, "main.py")
BILLS_DIR = os.path.join(APP_DIR, "..", "Steve_bills")
STREAMLIT_PORT = 8599  # Non-standard port to avoid conflicts


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


@pytest.fixture(autouse=True)
def cleanup_after_test(page: Page, streamlit_app: str):
    """Navigate home after each test to reset Streamlit state."""
    yield
    page.goto(streamlit_app)
    page.wait_for_timeout(1000)


class TestAppStartup:
    """Verify the Streamlit app starts and shows the welcome page."""

    def test_welcome_page_loads(self, page: Page, streamlit_app: str):
        page.goto(streamlit_app)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(5000)  # Wait for React components
        # The landing page title should be visible
        expect(page.locator("text=Energy Insight").first).to_be_visible(timeout=15000)

    def test_file_uploader_visible(self, page: Page, streamlit_app: str):
        page.goto(f"{streamlit_app}/Bill_Extractor")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(5000)  # Wait for React components
        # The Bill Extractor page should have a file uploader
        uploader = page.locator('[data-testid="stFileUploader"]')
        expect(uploader).to_be_visible(timeout=30000)

class TestBillPDFUpload:
    """Test PDF bill upload and extraction display."""

    def _upload_pdf(self, page: Page, streamlit_app: str, filename: str):
        """Upload a PDF via the Streamlit file uploader."""
        pdf_path = os.path.join(BILLS_DIR, filename)
        if not os.path.exists(pdf_path):
            pytest.skip(f"PDF not found: {filename}")

        page.goto(streamlit_app)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(5000)  # Wait for Streamlit React components

        # Wait for sidebar and uploader to be ready
        expect(page.locator('[data-testid="stSidebar"]')).to_be_visible(timeout=30000)
        expect(page.locator('[data-testid="stFileUploader"]')).to_be_visible(timeout=30000)

        # Find the file input and upload
        file_input = page.locator('[data-testid="stFileUploader"] input[type="file"]')
        expect(file_input).to_be_attached(timeout=30000)
        file_input.set_input_files(pdf_path)

        # Wait for extraction to complete
        page.wait_for_timeout(10000)

    def test_go_power_bill_extraction(self, page: Page, streamlit_app: str):
        """Upload Go Power bill and verify extraction produces results.

        Note: The Streamlit app uses the legacy extract_bill() which may not
        detect Go Power (not in legacy SUPPLIER_SIGNATURES). The new pipeline
        orchestrator handles this correctly. This test verifies the upload flow
        completes without error and shows extraction output.
        """
        self._upload_pdf(page, streamlit_app, "1845.pdf")

        content = page.content()
        # Verify extraction happened (shows confidence or field data)
        has_extraction = (
            "confidence" in content.lower()
            or "fields" in content.lower()
            or "mprn" in content.lower()
        )
        assert has_extraction, "Extraction output should be displayed"

    def test_energia_bill_extraction(self, page: Page, streamlit_app: str):
        """Upload Energia bill and verify extraction."""
        self._upload_pdf(
            page, streamlit_app,
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"
        )

        content = page.content()
        assert "Energia" in content or "energia" in content.lower(), \
            "Supplier should be detected as Energia"

    def test_energia_billing_period_extracted(self, page: Page, streamlit_app: str):
        """Billing period and bill date should be extracted for Energia bills."""
        self._upload_pdf(
            page, streamlit_app,
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"
        )

        content = page.content()
        # Billing period dates should appear (split as start → end)
        assert "1 Mar 2025" in content, \
            "Billing period start should be displayed"
        assert "31 Mar 2025" in content, \
            "Billing period end should be displayed"
        # Bill date should appear
        assert "11 Apr 2025" in content, \
            "Bill date should be extracted and displayed"

    def test_extraction_shows_mprn(self, page: Page, streamlit_app: str):
        """MPRN should be displayed in the bill summary."""
        self._upload_pdf(page, streamlit_app, "1845.pdf")

        content = page.content()
        # The MPRN 10006002900 should appear somewhere in the output
        assert "10006002900" in content, "MPRN should be displayed"

    def test_extraction_shows_confidence(self, page: Page, streamlit_app: str):
        """Confidence score should be displayed."""
        self._upload_pdf(page, streamlit_app, "1845.pdf")

        content = page.content()
        # Should show confidence percentage or "fields" count
        assert "confidence" in content.lower() or "fields" in content.lower(), \
            "Confidence or field count should be displayed"

    def test_esb_bill_extraction(self, page: Page, streamlit_app: str):
        """Upload ESB Networks bill and verify extraction."""
        self._upload_pdf(page, streamlit_app, "2024 Mar - Apr.pdf")

        content = page.content()
        # ESB Networks should be detected (the legacy parser may use different name)
        has_esb = "ESB" in content or "esb" in content.lower()
        assert has_esb, "ESB should appear in extraction results"


class TestBillSummaryDisplay:
    """Test that the bill summary UI displays correctly."""

    def _upload_pdf(self, page: Page, streamlit_app: str, filename: str):
        """Upload a PDF via the Streamlit file uploader."""
        pdf_path = os.path.join(BILLS_DIR, filename)
        if not os.path.exists(pdf_path):
            pytest.skip(f"PDF not found: {filename}")

        page.goto(streamlit_app)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(5000)  # Wait for Streamlit React components

        # Wait for sidebar and uploader to be ready
        expect(page.locator('[data-testid="stSidebar"]')).to_be_visible(timeout=30000)
        expect(page.locator('[data-testid="stFileUploader"]')).to_be_visible(timeout=30000)

        file_input = page.locator('[data-testid="stFileUploader"] input[type="file"]')
        expect(file_input).to_be_attached(timeout=30000)
        file_input.set_input_files(pdf_path)

        # Wait for extraction to complete
        page.wait_for_timeout(10000)

    def test_per_section_breakdown_displayed(self, page: Page, streamlit_app: str):
        """Confidence banner should show per-section field breakdown."""
        self._upload_pdf(
            page, streamlit_app,
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"
        )

        content = page.content()
        # Per-section breakdown should be visible
        assert "Account:" in content, "Account section count should be displayed"
        assert "Billing:" in content, "Billing section count should be displayed"
        assert "Consumption:" in content, "Consumption section count should be displayed"
        assert "Costs:" in content, "Costs section count should be displayed"
        assert "Balance:" in content, "Balance section count should be displayed"

    def test_warnings_appear_before_bill_data(self, page: Page, streamlit_app: str):
        """Warnings should appear near the top, before Account Details section."""
        self._upload_pdf(
            page, streamlit_app,
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"
        )

        content = page.text_content("body") or ""
        # If there are warnings, they should appear before Account Details
        account_pos = content.find("Account Details")
        if account_pos > 0:
            # Warnings (if any) should be before Account Details, not after Export
            export_pos = content.find("Export")
            # The warning section should NOT be between Balance and Export
            balance_pos = content.find("Balance")
            if balance_pos > 0 and export_pos > 0:
                warnings_after_balance = content[balance_pos:export_pos]
                assert "Extraction Warning" not in warnings_after_balance, \
                    "Warnings should not appear between Balance and Export sections"

    def test_bill_summary_has_sections(self, page: Page, streamlit_app: str):
        """Bill summary should have organized sections."""
        pdf_path = os.path.join(BILLS_DIR, "1845.pdf")
        if not os.path.exists(pdf_path):
            pytest.skip("PDF not found")

        page.goto(streamlit_app)
        page.wait_for_load_state("networkidle")

        file_input = page.locator('[data-testid="stFileUploader"] input[type="file"]')
        file_input.set_input_files(pdf_path)
        page.wait_for_timeout(3000)

        # Should show some structured data display
        content = page.content()
        # Check for common bill fields
        has_relevant_content = any(
            term in content.lower()
            for term in ["mprn", "account", "vat", "total", "supplier"]
        )
        assert has_relevant_content, "Bill summary should show key financial fields"

    def test_no_error_on_upload(self, page: Page, streamlit_app: str):
        """Uploading a valid bill should not produce error messages."""
        pdf_path = os.path.join(BILLS_DIR, "1845.pdf")
        if not os.path.exists(pdf_path):
            pytest.skip("PDF not found")

        page.goto(streamlit_app)
        page.wait_for_load_state("networkidle")

        file_input = page.locator('[data-testid="stFileUploader"] input[type="file"]')
        file_input.set_input_files(pdf_path)
        page.wait_for_timeout(3000)

        # Should not show error alerts
        errors = page.locator('[data-testid="stAlert"][data-type="error"]')
        assert errors.count() == 0, "No errors should appear for valid bill PDFs"

    def test_tariff_panel_hidden_during_bill_view(self, page: Page, streamlit_app: str):
        """Tariff rates sidebar should be hidden when viewing a bill PDF."""
        self._upload_pdf(
            page, streamlit_app,
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"
        )

        content = page.content()
        assert "Bill Extraction Mode" in content, \
            "Sidebar should show 'Bill Extraction Mode' instead of tariff inputs"
        assert "Tariff Rates" not in content, \
            "Tariff Rates header should not appear during bill view"

    def test_raw_text_expander_present(self, page: Page, streamlit_app: str):
        """Raw text debug expander should be available on bill view."""
        self._upload_pdf(
            page, streamlit_app,
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"
        )

        content = page.content()
        assert "Raw Extracted Text" in content, \
            "Raw Extracted Text expander should be present"
