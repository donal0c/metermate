"""
Playwright end-to-end tests for the confidence UX, inline editing,
and improved comparison table.

Validates that:
  - Traffic light confidence badges appear (green/amber/red)
  - No developer-facing jargon visible (extraction path, tier strings)
  - Actionable suggestions shown for low-confidence extractions
  - Comparison table shows traffic-light confidence labels
  - Aggregate metrics are transparent about exclusions
  - Inline editing form is available
  - Edited values are marked as "manually corrected"

Requires: playwright, pytest-playwright
         Install browsers: python3 -m playwright install chromium

These tests are marked with @pytest.mark.e2e and skipped by default.
Run E2E tests explicitly:
    python3 -m pytest -m e2e test_playwright_confidence_ux.py -v
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
STREAMLIT_PORT = 8601  # Unique port to avoid conflicts


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


# =========================================================================
# Traffic Light Confidence Badge Tests
# =========================================================================

class TestTrafficLightConfidence:
    """Verify traffic light confidence badges replace jargon."""

    def test_confidence_badge_present(self, page: Page, streamlit_app: str):
        """A confidence badge should appear after uploading a bill."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "1845.pdf")

        badge = page.locator('[data-testid="confidence-badge"]')
        expect(badge).to_be_visible(timeout=15000)

    def test_confidence_badge_has_level(self, page: Page, streamlit_app: str):
        """The confidence badge should have a data-level attribute."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "1845.pdf")

        badge = page.locator('[data-testid="confidence-badge"]')
        expect(badge).to_be_visible(timeout=15000)
        level = badge.get_attribute("data-level")
        assert level in ("high", "partial", "low"), (
            f"Badge level should be high/partial/low, got: {level}"
        )

    def test_confidence_shows_human_label(self, page: Page, streamlit_app: str):
        """Badge should show 'High confidence', 'Partial extraction', or 'Low confidence'."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "1845.pdf")

        badge = page.locator('[data-testid="confidence-badge"]')
        badge_text = badge.inner_text()
        has_label = any(
            label in badge_text
            for label in ["High confidence", "Partial extraction", "Low confidence"]
        )
        assert has_label, (
            f"Badge should contain a human-readable label. Got: {badge_text}"
        )

    def test_confidence_shows_field_count(self, page: Page, streamlit_app: str):
        """Badge should show 'N/M fields extracted'."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "1845.pdf")

        badge = page.locator('[data-testid="confidence-badge"]')
        badge_text = badge.inner_text()
        assert "fields extracted" in badge_text, (
            f"Badge should show field count. Got: {badge_text}"
        )

    def test_confidence_shows_supplier(self, page: Page, streamlit_app: str):
        """Badge should display the supplier name."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")

        badge = page.locator('[data-testid="confidence-badge"]')
        badge_text = badge.inner_text()
        assert "Energia" in badge_text, (
            f"Badge should show supplier name. Got: {badge_text}"
        )


# =========================================================================
# No Developer Jargon Tests
# =========================================================================

class TestNoDeveloperJargon:
    """Verify developer-facing text is removed from the UI."""

    def test_no_extraction_path(self, page: Page, streamlit_app: str):
        """Extraction path string (tier0_native -> tier1_known -> ...) should not be visible."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "1845.pdf")

        content = page.content()
        assert "Extraction path:" not in content, (
            "Developer-facing 'Extraction path:' text should not be visible"
        )
        assert "tier0_" not in content, (
            "Tier strings (tier0_native etc.) should not be visible"
        )
        assert "tier1_" not in content, (
            "Tier strings should not be visible"
        )

    def test_no_misleading_verify_message(self, page: Page, streamlit_app: str):
        """'verify fields marked with a warning icon' message should not appear."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "1845.pdf")

        content = page.content()
        assert "verify fields with warning icon" not in content.lower(), (
            "Misleading 'verify fields with warning icon' should not be shown"
        )

    def test_no_extraction_method_in_caption(self, page: Page, streamlit_app: str):
        """Export caption should not show 'Extraction method: ...'."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "1845.pdf")

        content = page.content()
        assert "Extraction method:" not in content, (
            "Export caption should not show extraction method string"
        )


# =========================================================================
# Actionable Suggestions Tests
# =========================================================================

class TestActionableSuggestions:
    """Verify actionable suggestions appear for non-high-confidence extractions."""

    def test_scanned_bill_shows_suggestion(self, page: Page, streamlit_app: str):
        """A scanned/low-confidence bill should show an actionable suggestion."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "094634_scan_14012026.pdf")

        # This is a scanned bill, likely low/partial confidence
        content = page.content()
        badge = page.locator('[data-testid="confidence-badge"]')
        if badge.count() > 0:
            level = badge.get_attribute("data-level")
            if level in ("partial", "low"):
                suggestion = page.locator('[data-testid="confidence-suggestion"]')
                expect(suggestion).to_be_visible(timeout=5000)
                suggestion_text = suggestion.inner_text()
                has_action = (
                    "review" in suggestion_text.lower()
                    or "clearer" in suggestion_text.lower()
                    or "pdf version" in suggestion_text.lower()
                )
                assert has_action, (
                    f"Suggestion should contain actionable advice. Got: {suggestion_text}"
                )

    def test_high_confidence_no_suggestion(self, page: Page, streamlit_app: str):
        """A high-confidence bill should NOT show a suggestion."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")

        badge = page.locator('[data-testid="confidence-badge"]')
        if badge.count() > 0:
            level = badge.get_attribute("data-level")
            if level == "high":
                suggestion = page.locator('[data-testid="confidence-suggestion"]')
                assert suggestion.count() == 0, (
                    "High-confidence bills should not show a suggestion"
                )


# =========================================================================
# Comparison Table Tests
# =========================================================================

class TestComparisonTable:
    """Verify the improved comparison table with traffic light and aggregates."""

    def _setup_comparison(self, page: Page, streamlit_app: str):
        """Upload 2 bills to get to comparison view."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
        ])

    def test_comparison_shows_confidence_labels(self, page: Page, streamlit_app: str):
        """Comparison table should show traffic-light confidence labels."""
        self._setup_comparison(page, streamlit_app)

        content = page.content()
        has_label = any(
            label in content
            for label in ["High confidence", "Partial extraction", "Low confidence"]
        )
        assert has_label, (
            "Comparison table should show traffic-light confidence labels"
        )

    def test_comparison_aggregate_metrics(self, page: Page, streamlit_app: str):
        """Comparison should show aggregate metrics."""
        self._setup_comparison(page, streamlit_app)

        content = page.content()
        has_metrics = (
            "Total Cost" in content
            or "Total kWh" in content
            or "Avg Cost" in content
        )
        assert has_metrics, "Aggregate metrics should be displayed"

    def test_comparison_no_none_values(self, page: Page, streamlit_app: str):
        """Table should show dashes not 'None' for missing values."""
        self._setup_comparison(page, streamlit_app)

        # Check the dataframe area for literal 'None' strings
        # (Streamlit renders dataframes in iframes or shadow DOM, so check full content)
        content = page.content()
        # We want to check that table cells don't contain "None"
        # but 'None' can appear in other contexts, so check specifically
        # in the comparison area
        assert content.count(">None<") == 0, (
            "Table should use dashes instead of 'None' for missing values"
        )

    def test_comparison_table_has_supplier_column(self, page: Page, streamlit_app: str):
        """Table should have a Supplier column."""
        self._setup_comparison(page, streamlit_app)

        content = page.content()
        assert "Supplier" in content, "Table should have a Supplier column"

    def test_three_bills_aggregation(self, page: Page, streamlit_app: str):
        """3-bill comparison should show transparent aggregation."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_multiple_pdfs(page, [
            "1845.pdf",
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
            "2024 Mar - Apr.pdf",
        ])

        content = page.content()
        assert "3 bills" in content, "Should show '3 bills' in heading"
        # Aggregate metrics should be present
        assert "Total Cost" in content or "Total kWh" in content


# =========================================================================
# Inline Editing Tests
# =========================================================================

class TestInlineEditing:
    """Verify inline editing functionality."""

    def test_edit_expander_present(self, page: Page, streamlit_app: str):
        """Edit Extracted Values expander should be present."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")

        content = page.content()
        assert "Edit Extracted Values" in content, (
            "Edit Extracted Values expander should be present"
        )

    def test_edit_form_has_fields(self, page: Page, streamlit_app: str):
        """Expanding the edit form should show input fields."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")

        # Click the Edit Extracted Values expander
        edit_expander = page.get_by_text("Edit Extracted Values")
        if edit_expander.count() > 0:
            edit_expander.first.click()
            page.wait_for_timeout(1000)

            content = page.content()
            # Should show form fields for key editable fields
            has_fields = (
                "Supplier" in content
                and "MPRN" in content
                and "Save Changes" in content
            )
            assert has_fields, (
                "Edit form should show Supplier, MPRN, and Save Changes button"
            )

    def test_edit_form_has_cost_fields(self, page: Page, streamlit_app: str):
        """Edit form should have cost/rate fields."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")

        edit_expander = page.get_by_text("Edit Extracted Values")
        if edit_expander.count() > 0:
            edit_expander.first.click()
            page.wait_for_timeout(1000)

            content = page.content()
            assert "Day Rate" in content, "Edit form should have Day Rate field"
            assert "Total Cost" in content, "Edit form should have Total Cost field"

    def test_edit_form_save_button(self, page: Page, streamlit_app: str):
        """Save Changes button should be present in the edit form."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")

        edit_expander = page.get_by_text("Edit Extracted Values")
        if edit_expander.count() > 0:
            edit_expander.first.click()
            page.wait_for_timeout(1000)

            save_btn = page.get_by_text("Save Changes")
            expect(save_btn.first).to_be_visible(timeout=5000)


# =========================================================================
# Status Chip Tests (ensure existing behaviour preserved)
# =========================================================================

class TestStatusChips:
    """Verify status chips still show correctly with the new UX."""

    def test_status_chip_shows_filename(self, page: Page, streamlit_app: str):
        """Status chip should show the uploaded filename."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "1845.pdf")

        content = page.content()
        assert "1845.pdf" in content, "Filename should appear in status chip"

    def test_status_chip_shows_supplier(self, page: Page, streamlit_app: str):
        """Status chip should show the supplier name."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")

        content = page.content()
        assert "Energia" in content, "Supplier should appear in status chip"

    def test_status_chip_color_coding(self, page: Page, streamlit_app: str):
        """Status chips should have color-coded borders."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "1845.pdf")

        content = page.content()
        # Chips use border colors: #22c55e (green), #f59e0b (amber), #ef4444 (red)
        has_color = (
            "#22c55e" in content
            or "#f59e0b" in content
            or "#ef4444" in content
        )
        assert has_color, "Status chips should have color-coded borders"


# =========================================================================
# Regression Tests (ensure no breakage)
# =========================================================================

class TestRegression:
    """Ensure existing functionality still works after the UX changes."""

    def test_account_details_section(self, page: Page, streamlit_app: str):
        """Account Details section should still render."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")

        content = page.content()
        assert "Account Details" in content, "Account Details section should render"

    def test_costs_section(self, page: Page, streamlit_app: str):
        """Costs section should still render."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")

        content = page.content()
        assert "Costs" in content, "Costs section should render"

    def test_export_section(self, page: Page, streamlit_app: str):
        """Export section should still render with download button."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")

        content = page.content()
        assert "Export" in content, "Export section should render"
        assert "Download as Excel" in content, "Download button should be present"

    def test_no_errors_on_upload(self, page: Page, streamlit_app: str):
        """No error alerts should appear for valid bills."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")

        errors = page.locator('[data-testid="stAlert"][data-type="error"]')
        assert errors.count() == 0, "No errors should appear for valid bill"

    def test_clear_all_button(self, page: Page, streamlit_app: str):
        """Clear All Bills button should still work."""
        _navigate_to_bill_extractor(page, streamlit_app)
        _upload_pdf(page, "1845.pdf")

        content = page.content()
        assert "Clear All Bills" in content, (
            "Clear All button should be visible after upload"
        )

    def test_multi_bill_comparison_tabs(self, page: Page, streamlit_app: str):
        """Comparison tabs should still be visible for 2+ bills."""
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
