"""
Playwright end-to-end tests for Tier 4 LLM vision extraction.

Validates that:
  - PDF bill upload still works with Tier 4 available
  - Extraction results display correctly when LLM supplements existing tiers
  - The pipeline handles the photo bill upload path (JPG)

Requires: playwright, pytest-playwright, GEMINI_API_KEY env var
         Install browsers: python3 -m playwright install

These tests are marked with @pytest.mark.e2e and skipped by default.
Run E2E tests explicitly:
    GEMINI_API_KEY=<key> GOOGLE_GENAI_USE_VERTEXAI=false pytest -m e2e test_playwright_llm.py -v
"""
import os
import subprocess
import time

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

APP_DIR = os.path.dirname(__file__)
APP_PATH = os.path.join(APP_DIR, "main.py")
BILLS_DIR = os.path.join(APP_DIR, "..", "sample_bills")
STREAMLIT_PORT = 8601  # Different port to avoid conflicts


def _bill_path(filename: str) -> str:
    return os.path.join(BILLS_DIR, filename)


def _bill_exists(filename: str) -> bool:
    return os.path.exists(_bill_path(filename))


def _has_gemini_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


@pytest.fixture(scope="session")
def streamlit_app():
    """Start the Streamlit app with GEMINI_API_KEY set."""
    import sys
    env = os.environ.copy()
    # Ensure Gemini API key is available to the app
    if not env.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set")

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
        env=env,
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


def _upload_file(page: Page, streamlit_app: str, filepath: str):
    """Upload a file via the Streamlit file uploader."""
    page.goto(streamlit_app)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    file_input = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    file_input.set_input_files(filepath)

    # Wait for extraction to complete
    page.wait_for_timeout(5000)


class TestLLMPipelineE2E:
    """E2E tests verifying Tier 4 LLM integration in the Streamlit app."""

    @pytest.mark.skipif(
        not _bill_exists("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"),
        reason="Energia PDF not found",
    )
    def test_energia_pdf_extraction_with_tier4_available(
        self, page: Page, streamlit_app: str
    ):
        """PDF extraction should still work correctly with Tier 4 available.

        Tier 3 handles Energia natively so Tier 4 shouldn't be needed,
        but having it available shouldn't cause regressions.
        """
        _upload_file(
            page, streamlit_app,
            _bill_path("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"),
        )

        content = page.content()
        # Provider should be detected
        assert "energia" in content.lower(), \
            "Energia should be detected as provider"

        # Key fields should be visible
        has_mprn = "10006802505" in content
        has_total = "266.45" in content
        assert has_mprn or has_total, \
            "MPRN or total should be visible in extraction results"

    @pytest.mark.skipif(
        not _bill_exists("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"),
        reason="Energia PDF not found",
    )
    def test_confidence_score_displayed(
        self, page: Page, streamlit_app: str
    ):
        """Confidence score should be displayed after extraction."""
        _upload_file(
            page, streamlit_app,
            _bill_path("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"),
        )

        content = page.content()
        # Confidence percentage should appear
        assert "confidence" in content.lower() or "%" in content, \
            "Confidence score should be visible"

    @pytest.mark.skipif(
        not _bill_exists("1845.pdf"),
        reason="Go Power PDF not found",
    )
    def test_go_power_extraction_no_regression(
        self, page: Page, streamlit_app: str
    ):
        """Go Power extraction should still work with Tier 4 present."""
        _upload_file(page, streamlit_app, _bill_path("1845.pdf"))

        content = page.content()
        has_extraction = (
            "confidence" in content.lower()
            or "mprn" in content.lower()
            or "fields" in content.lower()
        )
        assert has_extraction, \
            "Extraction output should be displayed for Go Power bill"


class TestTier4DirectExtraction:
    """Direct tests of Tier 4 LLM extraction (not through UI).

    These are E2E-marked because they call the real Gemini API
    but don't need Streamlit.
    """

    @pytest.mark.skipif(not _has_gemini_key(), reason="GEMINI_API_KEY not set")
    @pytest.mark.skipif(
        not _bill_exists("sample_bill_photo.jpg"),
        reason="Photo bill not found",
    )
    def test_photo_bill_extraction_quality(self):
        """Verify LLM extracts meaningful data from a photographed bill."""
        from llm_extraction import extract_tier4_llm

        result = extract_tier4_llm(
            _bill_path("sample_bill_photo.jpg"), is_image=True
        )

        # Should extract at least some fields from the photo
        assert result.field_count >= 1, \
            f"Expected at least 1 field from photo, got {result.field_count}"

        # Some monetary field should be extractable from the photo
        has_monetary = (
            "total_incl_vat" in result.fields
            or "subtotal" in result.fields
        )
        assert has_monetary, \
            "At least subtotal or total should be extracted from photo bill"

        # Value should be reasonable
        monetary_field = result.fields.get("total_incl_vat") or result.fields.get("subtotal")
        amount = float(monetary_field.value)
        assert amount > 0, "Monetary amount should be positive"

    @pytest.mark.skipif(not _has_gemini_key(), reason="GEMINI_API_KEY not set")
    @pytest.mark.skipif(
        not _bill_exists("094634_scan_14012026.pdf"),
        reason="Scanned PDF not found",
    )
    def test_scanned_pdf_extraction(self):
        """Verify LLM can extract from a scanned/degraded PDF."""
        from llm_extraction import extract_tier4_llm

        result = extract_tier4_llm(
            _bill_path("094634_scan_14012026.pdf")
        )

        # Should extract at least some fields
        assert result.field_count >= 1, \
            f"Expected fields from scanned PDF, got {result.field_count}"

    @pytest.mark.skipif(not _has_gemini_key(), reason="GEMINI_API_KEY not set")
    @pytest.mark.skipif(
        not _bill_exists("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"),
        reason="Energia PDF not found",
    )
    def test_llm_agrees_with_regex_on_known_bill(self):
        """LLM should agree with regex extraction on a well-formatted bill.

        This is a quality check: for known bills where regex works well,
        LLM should produce matching results.
        """
        from llm_extraction import extract_tier4_llm, _values_equivalent
        from pipeline import extract_text_tier0, extract_tier2_universal

        pdf_path = _bill_path(
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"
        )

        # Get regex results
        tier0 = extract_text_tier0(pdf_path)
        regex_result = extract_tier2_universal(tier0.extracted_text)

        # Get LLM results
        llm_result = extract_tier4_llm(pdf_path)

        # Check agreement on common fields
        common_fields = set(regex_result.fields.keys()) & set(llm_result.fields.keys())
        agreements = 0
        total = len(common_fields)

        for field_name in common_fields:
            regex_val = regex_result.fields[field_name].value
            llm_val = llm_result.fields[field_name].value
            if _values_equivalent(regex_val, llm_val):
                agreements += 1

        # Expect at least 70% agreement on common fields
        if total > 0:
            agreement_rate = agreements / total
            assert agreement_rate >= 0.70, \
                f"LLM/regex agreement rate {agreement_rate:.0%} below 70% threshold. " \
                f"Agreed on {agreements}/{total} fields."
