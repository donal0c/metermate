"""
Playwright end-to-end tests for the redesigned landing page.

Validates that:
  - Landing page loads with two clear, obviously-clickable workflow cards
  - Clicking the Bill Extractor card navigates to the correct page
  - Clicking the Meter Analysis card navigates to the correct page
  - No developer-facing text or old feature grid on the page
  - Cards have hover effects (border color, shadow, scale)
  - Hero section shows correct branding

Requires: playwright, pytest-playwright
         Install browsers: python3 -m playwright install

These tests are marked with @pytest.mark.e2e and skipped by default.
Run E2E tests explicitly:
    python3 -m pytest -m e2e test_playwright_landing.py -v
"""
import os
import subprocess
import sys
import time

import pytest
from playwright.sync_api import Page, expect

# Mark every test in this module as an E2E test.
pytestmark = pytest.mark.e2e

APP_DIR = os.path.dirname(__file__)
APP_PATH = os.path.join(APP_DIR, "main.py")
STREAMLIT_PORT = 8601  # Unique port to avoid conflicts


@pytest.fixture(scope="module")
def streamlit_app():
    """Start the Streamlit app as a subprocess and yield the URL."""
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


def _go_home(page: Page, streamlit_app: str):
    """Navigate to the landing page and wait for it to load."""
    page.goto(streamlit_app)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)


class TestHeroSection:
    """Tests for the hero branding section."""

    def test_title_visible(self, page: Page, streamlit_app: str):
        """Landing page shows 'Energy Insight' title."""
        _go_home(page, streamlit_app)
        expect(page.locator("text=Energy Insight").first).to_be_visible()

    def test_branding_visible(self, page: Page, streamlit_app: str):
        """Landing page shows 'Cork Energy Consultancy' branding."""
        _go_home(page, streamlit_app)
        expect(page.locator("text=Cork Energy Consultancy")).to_be_visible()

    def test_tagline_visible(self, page: Page, streamlit_app: str):
        """Landing page shows the one-line tagline."""
        _go_home(page, streamlit_app)
        expect(page.locator("text=Upload bills or meter data to get started")).to_be_visible()


class TestWorkflowCards:
    """Tests for the two workflow cards."""

    def test_both_cards_visible(self, page: Page, streamlit_app: str):
        """Two workflow cards are visible on the landing page."""
        _go_home(page, streamlit_app)
        cards = page.locator(".workflow-card")
        expect(cards).to_have_count(2)

    def test_bill_extractor_card_text(self, page: Page, streamlit_app: str):
        """Bill Extractor card shows correct title and description."""
        _go_home(page, streamlit_app)
        card = page.locator("[data-testid='card-bill-extractor']")
        expect(card).to_be_visible()
        expect(card.locator("text=Extract Bills")).to_be_visible()
        expect(card.locator("text=Upload PDF or photographed electricity bills")).to_be_visible()

    def test_meter_analysis_card_text(self, page: Page, streamlit_app: str):
        """Meter Analysis card shows correct title and description."""
        _go_home(page, streamlit_app)
        card = page.locator("[data-testid='card-meter-analysis']")
        expect(card).to_be_visible()
        expect(card.locator("text=Analyse Meter Data")).to_be_visible()
        expect(card.locator("text=Upload ESB Networks HDF or Excel files")).to_be_visible()

    def test_bill_extractor_card_navigates(self, page: Page, streamlit_app: str):
        """Clicking the Bill Extractor card navigates to the Bill Extractor page."""
        _go_home(page, streamlit_app)
        card = page.locator("[data-testid='card-bill-extractor']")
        card.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        expect(page).to_have_url(f"{streamlit_app}/Bill_Extractor", timeout=10000)

    def test_meter_analysis_card_navigates(self, page: Page, streamlit_app: str):
        """Clicking the Meter Analysis card navigates to the Meter Analysis page."""
        _go_home(page, streamlit_app)
        card = page.locator("[data-testid='card-meter-analysis']")
        card.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        expect(page).to_have_url(f"{streamlit_app}/Meter_Analysis", timeout=10000)

    def test_cards_have_arrow_indicators(self, page: Page, streamlit_app: str):
        """Each card has an arrow/chevron indicating navigation."""
        _go_home(page, streamlit_app)
        bill_arrow = page.locator("[data-testid='card-bill-extractor'] .card-arrow")
        meter_arrow = page.locator("[data-testid='card-meter-analysis'] .card-arrow")
        expect(bill_arrow).to_be_visible()
        expect(meter_arrow).to_be_visible()

    def test_cards_have_hover_effects(self, page: Page, streamlit_app: str):
        """Cards change border color on hover."""
        _go_home(page, streamlit_app)
        card = page.locator("[data-testid='card-bill-extractor']")

        # Get initial border color
        initial_border = card.evaluate(
            "el => getComputedStyle(el).borderColor"
        )

        # Hover over the card
        card.hover()
        page.wait_for_timeout(500)

        # Get hover border color
        hover_border = card.evaluate(
            "el => getComputedStyle(el).borderColor"
        )

        # Border color should change on hover
        assert initial_border != hover_border, (
            f"Card border should change on hover. "
            f"Before: {initial_border}, After: {hover_border}"
        )


class TestRemovedContent:
    """Tests that old content has been removed."""

    def test_no_feature_grid(self, page: Page, streamlit_app: str):
        """The old 2x2 feature grid (Key Metrics, Heatmap, etc.) is gone."""
        _go_home(page, streamlit_app)
        expect(page.locator("text=Key Metrics")).not_to_be_visible()
        expect(page.locator("text=Excel Export")).not_to_be_visible()

    def test_no_supported_formats_section(self, page: Page, streamlit_app: str):
        """The old Supported Formats section is gone from the landing page."""
        _go_home(page, streamlit_app)
        expect(page.locator("text=Supported Formats")).not_to_be_visible()

    def test_no_about_sidebar(self, page: Page, streamlit_app: str):
        """The old About sidebar section is gone."""
        _go_home(page, streamlit_app)
        sidebar = page.locator("section[data-testid='stSidebar']")
        expect(sidebar.locator("text=About")).not_to_be_visible()

    def test_no_welcome_heading(self, page: Page, streamlit_app: str):
        """The old 'Welcome to Energy Insight' heading is gone."""
        _go_home(page, streamlit_app)
        expect(page.locator("text=Welcome to Energy Insight")).not_to_be_visible()


