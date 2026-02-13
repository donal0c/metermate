"""
Playwright end-to-end tests for image bill upload.

Validates that:
  - The Streamlit app accepts JPG/PNG uploads
  - Image uploads trigger extraction and display results
  - Extracted fields and confidence are visible in the bill summary
  - Sidebar shows "Bill Extraction Mode" for image uploads

Requires: playwright, pytest-playwright
         Install browsers: python3 -m playwright install

These tests are marked with @pytest.mark.e2e and skipped by default.
Run E2E tests explicitly:
    python3 -m pytest -m e2e -v
Run this file directly:
    python3 -m pytest test_playwright_image_upload.py -v
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
IMAGE_FILE = "Steve_bill_photo.jpg"
STREAMLIT_PORT = 8599  # Same port as other E2E tests


@pytest.fixture(scope="session")
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


class TestImageUpload:
    """Test image bill upload and extraction display."""

    def _upload_image(self, page: Page, streamlit_app: str):
        """Upload a JPG image via the Streamlit file uploader."""
        image_path = os.path.join(BILLS_DIR, IMAGE_FILE)
        if not os.path.exists(image_path):
            pytest.skip(f"Image not found: {IMAGE_FILE}")

        page.goto(streamlit_app)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(5000)

        expect(page.locator('[data-testid="stSidebar"]')).to_be_visible(timeout=30000)
        expect(page.locator('[data-testid="stFileUploader"]')).to_be_visible(timeout=30000)

        file_input = page.locator('[data-testid="stFileUploader"] input[type="file"]')
        expect(file_input).to_be_attached(timeout=30000)
        file_input.set_input_files(image_path)

        # Image extraction may take longer due to OCR
        page.wait_for_timeout(15000)

    def test_image_uploader_accepts_jpg(self, page: Page, streamlit_app: str):
        """Upload Steve_bill_photo.jpg and verify extraction output appears."""
        self._upload_image(page, streamlit_app)

        content = page.content()
        has_extraction = any(
            term in content.lower()
            for term in ["confidence", "mprn", "account", "extraction"]
        )
        assert has_extraction, "Extraction output should be displayed for image upload"

    def test_image_extraction_shows_confidence(self, page: Page, streamlit_app: str):
        """Verify confidence score is displayed for image extraction."""
        self._upload_image(page, streamlit_app)

        content = page.content()
        assert "confidence" in content.lower(), \
            "Confidence score should be visible in extraction output"

    def test_image_extraction_shows_extraction_path(self, page: Page, streamlit_app: str):
        """Verify extraction path mentions spatial or LLM tier."""
        self._upload_image(page, streamlit_app)

        content = page.content().lower()
        has_path = "tier2_spatial" in content or "tier4_llm" in content or "image_input" in content
        assert has_path, "Extraction path should mention tier2_spatial, tier4_llm, or image_input"

    def test_image_shows_bill_mode_sidebar(self, page: Page, streamlit_app: str):
        """Verify sidebar shows Bill Extraction Mode for image uploads."""
        self._upload_image(page, streamlit_app)

        sidebar = page.locator('[data-testid="stSidebar"]')
        sidebar_text = sidebar.inner_text()
        assert "Bill" in sidebar_text, \
            "Sidebar should indicate bill extraction mode for image uploads"
