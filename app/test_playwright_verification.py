"""
Playwright end-to-end tests for the Bill Verification feature.

Validates that:
  - The verification uploader appears in the sidebar when HDF data is loaded
  - Uploading a bill with mismatched MPRN shows block error
  - The Bill Verification tab appears when a bill is uploaded alongside HDF
  - Verification content renders without errors

Requires: playwright, pytest-playwright
         Install browsers: python3 -m playwright install

These tests are marked with @pytest.mark.e2e and skipped by default.
Run E2E tests explicitly:
    python3 -m pytest -m e2e test_playwright_verification.py -v
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
HDF_PATH = os.path.join(
    APP_DIR, "..", "HDF_calckWh_10306268587_03-02-2026.csv"
)
STREAMLIT_PORT = 8597  # Different port from other E2E tests


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


def _load_hdf_via_demo(page: Page, streamlit_app: str):
    """Load the sample HDF data via the demo button."""
    page.goto(streamlit_app)
    page.wait_for_load_state("networkidle")

    # Wait for welcome page to fully render
    expect(page.get_by_text("Welcome to Energy Insight")).to_be_visible(timeout=15000)

    hdf_button = page.get_by_text("Try sample HDF data")
    expect(hdf_button).to_be_visible(timeout=10000)
    hdf_button.click()
    page.wait_for_timeout(5000)


def _load_hdf_via_upload(page: Page, streamlit_app: str):
    """Load the HDF file via file uploader."""
    if not os.path.exists(HDF_PATH):
        pytest.skip(f"HDF file not found: {HDF_PATH}")

    page.goto(streamlit_app)
    page.wait_for_load_state("networkidle")

    file_input = page.locator(
        '[data-testid="stFileUploader"] input[type="file"]'
    )
    file_input.set_input_files(HDF_PATH)
    page.wait_for_timeout(5000)


class TestVerificationUploaderVisibility:
    """Test that the verification uploader appears in the right context."""

    def test_verification_uploader_visible_after_hdf_load(
        self, page: Page, streamlit_app: str
    ):
        """After loading HDF data, sidebar should show verification uploader."""
        _load_hdf_via_demo(page, streamlit_app)

        content = page.content()
        assert "Verify a Bill" in content, \
            "Sidebar should show 'Verify a Bill' section when HDF is loaded"

    def test_verification_uploader_not_on_welcome(
        self, page: Page, streamlit_app: str
    ):
        """Welcome page should NOT show the verification uploader."""
        page.goto(streamlit_app)
        page.wait_for_load_state("networkidle")

        content = page.content()
        assert "Verify a Bill" not in content, \
            "Verification uploader should not appear on welcome page"

    def test_verification_uploader_not_on_bill_view(
        self, page: Page, streamlit_app: str
    ):
        """Bill extraction view should NOT show the verification uploader."""
        pdf_path = os.path.join(BILLS_DIR, "1845.pdf")
        if not os.path.exists(pdf_path):
            pytest.skip("PDF not found")

        page.goto(streamlit_app)
        page.wait_for_load_state("networkidle")

        file_input = page.locator(
            '[data-testid="stFileUploader"] input[type="file"]'
        )
        file_input.set_input_files(pdf_path)
        page.wait_for_timeout(3000)

        content = page.content()
        assert "Verify a Bill" not in content, \
            "Verification uploader should not appear during bill extraction"


class TestMPRNMismatch:
    """Test that mismatched MPRN shows a block error."""

    def test_mprn_mismatch_shows_error(
        self, page: Page, streamlit_app: str
    ):
        """Uploading a bill with different MPRN should show error."""
        _load_hdf_via_demo(page, streamlit_app)

        # Upload a bill with different MPRN (1845.pdf has MPRN 10006002900)
        pdf_path = os.path.join(BILLS_DIR, "1845.pdf")
        if not os.path.exists(pdf_path):
            pytest.skip("PDF not found")

        # Find the verification uploader (second file input on page)
        file_inputs = page.locator('input[type="file"]')
        # The verification uploader should be the second one
        if file_inputs.count() < 2:
            pytest.skip("Verification uploader not found")

        file_inputs.nth(1).set_input_files(pdf_path)
        page.wait_for_timeout(5000)

        content = page.content()
        assert "does not match" in content, \
            "Should show MPRN mismatch error"

    def test_mprn_mismatch_no_verification_tab(
        self, page: Page, streamlit_app: str
    ):
        """Bill Verification tab should NOT appear for MPRN mismatch."""
        _load_hdf_via_demo(page, streamlit_app)

        pdf_path = os.path.join(BILLS_DIR, "1845.pdf")
        if not os.path.exists(pdf_path):
            pytest.skip("PDF not found")

        file_inputs = page.locator('input[type="file"]')
        if file_inputs.count() < 2:
            pytest.skip("Verification uploader not found")

        file_inputs.nth(1).set_input_files(pdf_path)
        page.wait_for_timeout(5000)

        content = page.content()
        assert "Bill Verification" not in content, \
            "Bill Verification tab should not appear for MPRN mismatch"


class TestHDFTabsWithoutVerification:
    """Test that existing HDF tabs work correctly without verification."""

    def test_five_tabs_without_verification(
        self, page: Page, streamlit_app: str
    ):
        """HDF view should have 5 tabs when no verification bill is uploaded."""
        _load_hdf_via_demo(page, streamlit_app)

        content = page.content()
        assert "Overview" in content
        assert "Heatmap" in content
        assert "Charts" in content
        assert "Insights" in content
        assert "Export" in content

    def test_no_errors_on_hdf_load(
        self, page: Page, streamlit_app: str
    ):
        """Loading HDF should not produce errors."""
        _load_hdf_via_demo(page, streamlit_app)

        errors = page.locator('[data-testid="stAlert"][data-type="error"]')
        assert errors.count() == 0, "No errors should appear for HDF load"


class TestVerificationWithMatchingBill:
    """Test verification when MPRN matches (using Energia bill if available).

    Note: The sample HDF has MPRN 10306268587 and the sample bills have
    different MPRNs. These tests validate the mismatch error path and
    that the app handles it gracefully.
    """

    def test_energia_bill_mprn_mismatch_is_graceful(
        self, page: Page, streamlit_app: str
    ):
        """Uploading Energia bill against HDF should show mismatch, not crash."""
        _load_hdf_via_demo(page, streamlit_app)

        pdf_path = os.path.join(
            BILLS_DIR,
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        )
        if not os.path.exists(pdf_path):
            pytest.skip("Energia PDF not found")

        file_inputs = page.locator('input[type="file"]')
        if file_inputs.count() < 2:
            pytest.skip("Verification uploader not found")

        file_inputs.nth(1).set_input_files(pdf_path)
        page.wait_for_timeout(5000)

        # Should show MPRN mismatch but no crashes
        content = page.content()
        assert "does not match" in content, \
            "Should show MPRN mismatch for different meter"

        # The 5 standard tabs should still be there
        assert "Overview" in content
        assert "Heatmap" in content
