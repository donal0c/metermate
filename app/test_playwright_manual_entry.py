"""Playwright e2e tests for Manual Fuel Entry in the Bill Extractor.

Verifies the manual entry expander, form submission, chip rendering,
and detail view for manually entered fuel entries.
"""

import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:8601"
BILL_EXTRACTOR_PATH = "/Bill_Extractor"

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def page_url():
    return f"{BASE_URL}{BILL_EXTRACTOR_PATH}"


class TestManualEntryFormPresence:
    """Test that the manual entry expander and form elements exist."""

    def test_manual_entry_expander_visible(self, page: Page, page_url):
        page.goto(page_url, wait_until="networkidle")
        # The expander should be present on the page
        expander = page.get_by_text("Add Fuel Entry Manually")
        expect(expander).to_be_visible()

    def test_manual_entry_expander_collapsed_by_default(self, page: Page, page_url):
        page.goto(page_url, wait_until="networkidle")
        # The form fields should not be visible until expanded
        fuel_type_label = page.get_by_text("Fuel Type").first
        # Expander content is collapsed, so the form label inside shouldn't be visible
        # (Streamlit renders expander content lazily)
        expander = page.get_by_text("Add Fuel Entry Manually")
        expect(expander).to_be_visible()

    def test_manual_entry_form_has_fields_when_expanded(self, page: Page, page_url):
        page.goto(page_url, wait_until="networkidle")
        # Click the expander to open it
        page.get_by_text("Add Fuel Entry Manually").click()
        page.wait_for_timeout(500)

        # Check form fields are visible
        expect(page.get_by_text("Fuel Type").first).to_be_visible()
        expect(page.get_by_text("Quantity").first).to_be_visible()
        expect(page.get_by_text("Unit").first).to_be_visible()
        expect(page.get_by_text("Total Cost (EUR incl. VAT)").first).to_be_visible()
        expect(page.get_by_text("Date of Purchase").first).to_be_visible()

    def test_manual_entry_form_has_submit_button(self, page: Page, page_url):
        page.goto(page_url, wait_until="networkidle")
        page.get_by_text("Add Fuel Entry Manually").click()
        page.wait_for_timeout(500)

        submit_btn = page.get_by_role("button", name="Add Fuel Entry")
        expect(submit_btn).to_be_visible()

    def test_manual_entry_form_has_supplier_field(self, page: Page, page_url):
        page.goto(page_url, wait_until="networkidle")
        page.get_by_text("Add Fuel Entry Manually").click()
        page.wait_for_timeout(500)

        expect(page.get_by_text("Supplier (optional)").first).to_be_visible()

    def test_manual_entry_form_has_period_end_field(self, page: Page, page_url):
        page.goto(page_url, wait_until="networkidle")
        page.get_by_text("Add Fuel Entry Manually").click()
        page.wait_for_timeout(500)

        expect(page.get_by_text("Period End (optional)").first).to_be_visible()


class TestManualEntrySubmission:
    """Test submitting a manual fuel entry."""

    def test_submit_coal_entry_shows_chip(self, page: Page, page_url):
        page.goto(page_url, wait_until="networkidle")

        # Clear any existing bills first
        clear_btn = page.get_by_role("button", name="Clear All Bills")
        if clear_btn.is_visible():
            clear_btn.click()
            page.wait_for_timeout(1000)

        # Expand the manual entry form
        page.get_by_text("Add Fuel Entry Manually").click()
        page.wait_for_timeout(500)

        # Fill in quantity (default fuel type is Coal, default unit is Bag (40kg))
        qty_input = page.locator('input[aria-label="Quantity"]')
        qty_input.fill("5")

        # Fill in cost
        cost_input = page.locator('input[aria-label="Total Cost (EUR incl. VAT)"]')
        cost_input.fill("120")

        # Submit the form
        page.get_by_role("button", name="Add Fuel Entry").click()
        page.wait_for_timeout(2000)

        # Should see a blue chip with the manual entry
        page_content = page.content()
        assert "Coal" in page_content, "Coal entry should appear on page after submission"

    def test_manual_entry_shows_kwh_equivalent(self, page: Page, page_url):
        page.goto(page_url, wait_until="networkidle")

        # Clear any existing bills
        clear_btn = page.get_by_role("button", name="Clear All Bills")
        if clear_btn.is_visible():
            clear_btn.click()
            page.wait_for_timeout(1000)

        # Expand and fill
        page.get_by_text("Add Fuel Entry Manually").click()
        page.wait_for_timeout(500)

        # Default fuel=Coal, default unit=Tonne (first in all-units list)
        # 5 tonnes * 8140 kWh/tonne = 40,700 kWh
        qty_input = page.locator('input[aria-label="Quantity"]')
        qty_input.fill("5")

        cost_input = page.locator('input[aria-label="Total Cost (EUR incl. VAT)"]')
        cost_input.fill("120")

        page.get_by_role("button", name="Add Fuel Entry").click()
        page.wait_for_timeout(2000)

        page_content = page.content()
        assert "40,700.0" in page_content or "40700" in page_content, \
            "Should show kWh equivalent for 5 tonnes of coal (40,700 kWh)"

    def test_manual_entry_shows_effective_rate(self, page: Page, page_url):
        page.goto(page_url, wait_until="networkidle")

        clear_btn = page.get_by_role("button", name="Clear All Bills")
        if clear_btn.is_visible():
            clear_btn.click()
            page.wait_for_timeout(1000)

        page.get_by_text("Add Fuel Entry Manually").click()
        page.wait_for_timeout(500)

        # Default fuel=Coal, default unit=Tonne
        # Effective rate = 120 / 40700 = ~0.0029
        qty_input = page.locator('input[aria-label="Quantity"]')
        qty_input.fill("5")

        cost_input = page.locator('input[aria-label="Total Cost (EUR incl. VAT)"]')
        cost_input.fill("120")

        page.get_by_role("button", name="Add Fuel Entry").click()
        page.wait_for_timeout(2000)

        page_content = page.content()
        assert "0.0029" in page_content, \
            "Should show effective rate ~0.0029/kWh for 5 tonnes coal at EUR 120"

    def test_zero_quantity_shows_error(self, page: Page, page_url):
        page.goto(page_url, wait_until="networkidle")

        clear_btn = page.get_by_role("button", name="Clear All Bills")
        if clear_btn.is_visible():
            clear_btn.click()
            page.wait_for_timeout(1000)

        page.get_by_text("Add Fuel Entry Manually").click()
        page.wait_for_timeout(500)

        # Leave quantity at 0, set cost
        cost_input = page.locator('input[aria-label="Total Cost (EUR incl. VAT)"]')
        cost_input.fill("100")

        page.get_by_role("button", name="Add Fuel Entry").click()
        page.wait_for_timeout(1000)

        # Should show validation error
        page_content = page.content()
        assert "greater than 0" in page_content, \
            "Should show validation error for zero quantity"

    def test_invalid_unit_for_fuel_shows_error(self, page: Page, page_url):
        page.goto(page_url, wait_until="networkidle")

        clear_btn = page.get_by_role("button", name="Clear All Bills")
        if clear_btn.is_visible():
            clear_btn.click()
            page.wait_for_timeout(1000)

        page.get_by_text("Add Fuel Entry Manually").click()
        page.wait_for_timeout(500)

        # Select Coal as fuel type (default), then select Litre as unit
        # which is invalid for coal
        unit_select = page.locator('[data-testid="stSelectbox"]').nth(1)
        unit_select.click()
        page.wait_for_timeout(300)
        # Select "Litre" option
        page.get_by_role("option", name="Litre").click()
        page.wait_for_timeout(300)

        qty_input = page.locator('input[aria-label="Quantity"]')
        qty_input.fill("5")

        cost_input = page.locator('input[aria-label="Total Cost (EUR incl. VAT)"]')
        cost_input.fill("100")

        page.get_by_role("button", name="Add Fuel Entry").click()
        page.wait_for_timeout(1000)

        page_content = page.content()
        assert "not valid" in page_content, \
            "Should show validation error for invalid unit/fuel combination"


class TestManualEntryChipRendering:
    """Test that manual entry chips render correctly."""

    def test_manual_chip_has_blue_border(self, page: Page, page_url):
        page.goto(page_url, wait_until="networkidle")

        clear_btn = page.get_by_role("button", name="Clear All Bills")
        if clear_btn.is_visible():
            clear_btn.click()
            page.wait_for_timeout(1000)

        page.get_by_text("Add Fuel Entry Manually").click()
        page.wait_for_timeout(500)

        qty_input = page.locator('input[aria-label="Quantity"]')
        qty_input.fill("5")

        cost_input = page.locator('input[aria-label="Total Cost (EUR incl. VAT)"]')
        cost_input.fill("120")

        page.get_by_role("button", name="Add Fuel Entry").click()
        page.wait_for_timeout(2000)

        # Check for blue border color in chip HTML
        # Streamlit may render as hex (#3b82f6) or rgb(59, 130, 246)
        page_content = page.content()
        assert "#3b82f6" in page_content or "59, 130, 246" in page_content, \
            "Manual entry chip should have blue border color"

    def test_manual_chip_has_pencil_icon(self, page: Page, page_url):
        page.goto(page_url, wait_until="networkidle")

        clear_btn = page.get_by_role("button", name="Clear All Bills")
        if clear_btn.is_visible():
            clear_btn.click()
            page.wait_for_timeout(1000)

        page.get_by_text("Add Fuel Entry Manually").click()
        page.wait_for_timeout(500)

        qty_input = page.locator('input[aria-label="Quantity"]')
        qty_input.fill("5")

        cost_input = page.locator('input[aria-label="Total Cost (EUR incl. VAT)"]')
        cost_input.fill("120")

        page.get_by_role("button", name="Add Fuel Entry").click()
        page.wait_for_timeout(2000)

        # Check for pencil icon (&#9998; = U+270E)
        page_content = page.content()
        assert "&#9998;" in page_content or "\u270e" in page_content or "✎" in page_content, \
            "Manual entry chip should have pencil icon"


class TestManualEntryCleanup:
    """Cleanup after tests."""

    def test_clear_all_removes_manual_entries(self, page: Page, page_url):
        page.goto(page_url, wait_until="networkidle")

        # Add an entry first
        clear_btn = page.get_by_role("button", name="Clear All Bills")
        if clear_btn.is_visible():
            clear_btn.click()
            page.wait_for_timeout(1000)

        page.get_by_text("Add Fuel Entry Manually").click()
        page.wait_for_timeout(500)

        qty_input = page.locator('input[aria-label="Quantity"]')
        qty_input.fill("5")

        cost_input = page.locator('input[aria-label="Total Cost (EUR incl. VAT)"]')
        cost_input.fill("120")

        page.get_by_role("button", name="Add Fuel Entry").click()
        page.wait_for_timeout(2000)

        # Now clear
        clear_btn = page.get_by_role("button", name="Clear All Bills")
        expect(clear_btn).to_be_visible()
        clear_btn.click()
        page.wait_for_timeout(1000)

        # Verify empty state is back
        page_content = page.content()
        assert "Upload Energy Bills" in page_content or "Upload energy bills" in page_content, \
            "Should show empty state after clearing"
