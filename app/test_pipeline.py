"""
Tests for pipeline Tier 0 (native text detection) and Tier 1 (provider detection).

Covers acceptance criteria for:
  steve-3gv: Tier 0 native text detection
  steve-wp1: Tier 1 provider detection
"""
import os
import pytest
from pipeline import (
    extract_text_tier0,
    TextExtractionResult,
    detect_provider,
    ProviderDetectionResult,
    PROVIDER_KEYWORDS,
)

BILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "Steve_bills")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pdf_path(filename: str) -> str:
    return os.path.join(BILLS_DIR, filename)


def _pdf_exists(filename: str) -> bool:
    return os.path.exists(_pdf_path(filename))


# Known native-text PDFs
NATIVE_PDFS = [
    "1845.pdf",                                                    # Go Power
    "2024 Mar - Apr.pdf",                                          # ESB Networks
    "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",        # Energia
]

# Known scanned / image-based PDFs
SCANNED_PDFS = [
    "094634_scan_14012026.pdf",
]


# ===================================================================
# Tier 0: Native text detection
# ===================================================================

class TestTier0NativeDetection:
    """Tests for extract_text_tier0."""

    @pytest.mark.parametrize("pdf_name", NATIVE_PDFS)
    def test_native_pdfs_detected_as_native(self, pdf_name):
        path = _pdf_path(pdf_name)
        if not os.path.exists(path):
            pytest.skip(f"PDF not found: {pdf_name}")
        result = extract_text_tier0(path)
        assert result.is_native_text is True, f"{pdf_name} should be native text"
        assert len(result.extracted_text) > 100
        assert result.page_count > 0
        assert len(result.chars_per_page) == result.page_count
        # At least one page should have substantial text (some PDFs have blank trailing pages)
        assert max(result.chars_per_page) > 50, "No page has substantial text"

    @pytest.mark.parametrize("pdf_name", SCANNED_PDFS)
    def test_scanned_pdfs_detected_as_non_native(self, pdf_name):
        path = _pdf_path(pdf_name)
        if not os.path.exists(path):
            pytest.skip(f"PDF not found: {pdf_name}")
        result = extract_text_tier0(path)
        assert result.is_native_text is False, f"{pdf_name} should NOT be native text"

    def test_accepts_bytes(self):
        """Tier 0 should accept PDF bytes in addition to file paths."""
        pdf_name = NATIVE_PDFS[0]
        path = _pdf_path(pdf_name)
        if not os.path.exists(path):
            pytest.skip(f"PDF not found: {pdf_name}")
        with open(path, "rb") as f:
            pdf_bytes = f.read()
        result = extract_text_tier0(pdf_bytes)
        assert result.is_native_text is True
        assert len(result.extracted_text) > 100

    def test_bytes_and_path_produce_same_text(self):
        """Bytes and path inputs should produce identical results."""
        pdf_name = NATIVE_PDFS[0]
        path = _pdf_path(pdf_name)
        if not os.path.exists(path):
            pytest.skip(f"PDF not found: {pdf_name}")
        with open(path, "rb") as f:
            pdf_bytes = f.read()
        result_path = extract_text_tier0(path)
        result_bytes = extract_text_tier0(pdf_bytes)
        assert result_path.is_native_text == result_bytes.is_native_text
        assert result_path.chars_per_page == result_bytes.chars_per_page

    def test_empty_bytes_raises(self):
        with pytest.raises(ValueError, match="empty"):
            extract_text_tier0(b"")

    def test_invalid_pdf_raises(self):
        with pytest.raises(RuntimeError):
            extract_text_tier0(b"not a pdf at all")

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError):
            extract_text_tier0(12345)

    def test_result_has_metadata(self):
        pdf_name = NATIVE_PDFS[0]
        path = _pdf_path(pdf_name)
        if not os.path.exists(path):
            pytest.skip(f"PDF not found: {pdf_name}")
        result = extract_text_tier0(path)
        assert "page_count" in result.metadata
        assert result.metadata["page_count"] > 0

    def test_custom_threshold(self):
        """Setting threshold very high should classify everything as non-native."""
        pdf_name = NATIVE_PDFS[0]
        path = _pdf_path(pdf_name)
        if not os.path.exists(path):
            pytest.skip(f"PDF not found: {pdf_name}")
        result = extract_text_tier0(path, native_threshold=999999)
        assert result.is_native_text is False
        # Text should still be extracted regardless of classification
        assert len(result.extracted_text) > 0


# ===================================================================
# Tier 1: Provider detection
# ===================================================================

class TestTier1ProviderDetection:
    """Tests for detect_provider."""

    # -- Known provider keyword matching --

    @pytest.mark.parametrize("text,expected_provider", [
        ("Invoice from Energia. Total: €150.00", "Energia"),
        ("Electric Ireland - your bill", "Electric Ireland"),
        ("SSE Airtricity Gas Bill", "SSE Airtricity"),
        ("Bord Gáis Energy account summary", "Bord Gais"),
        ("Kerry Petroleum delivery note", "Kerry Petroleum"),
        ("ESB Networks charges breakdown", "ESB Networks"),
        ("Go Power monthly statement", "Go Power"),
        ("Flogas delivery docket", "Flogas"),
        ("Calor Gas Ireland", "Calor Gas"),
        ("Pinergy prepay electricity", "Pinergy"),
        ("Prepay Power top-up", "Prepay Power"),
        ("Panda Power bill", "Panda Power"),
        ("Bright Energy quarterly", "Bright"),
        ("Community Power cooperative bill", "Community Power"),
        ("Iberdrola customer account", "Iberdrola"),
        ("Yuno Energy monthly", "Yuno Energy"),
    ])
    def test_known_providers(self, text, expected_provider):
        result = detect_provider(text)
        assert result.is_known is True
        assert result.provider_name == expected_provider
        assert result.matched_keyword is not None

    def test_case_insensitive(self):
        result = detect_provider("ENERGIA COMMERCIAL ELECTRICITY BILL")
        assert result.provider_name == "Energia"
        assert result.is_known is True

    def test_unknown_provider(self):
        result = detect_provider("Some random text without any provider keywords")
        assert result.provider_name == "unknown"
        assert result.is_known is False
        assert result.matched_keyword is None

    def test_empty_text(self):
        result = detect_provider("")
        assert result.provider_name == "unknown"
        assert result.is_known is False

    def test_whitespace_only(self):
        result = detect_provider("   \n\n  ")
        assert result.provider_name == "unknown"
        assert result.is_known is False

    # -- Collision / tie-breaking tests --

    def test_energia_with_esb_emergency_text(self):
        """Energia bills often mention ESB Networks for emergency contacts.
        When both providers appear once, Energia should win because it comes
        first in the priority list (dict insertion order breaks ties)."""
        text = (
            "Energia Commercial Electricity Bill\n"
            "For emergencies contact ESB Networks at 1800 372 999\n"
            "Account: 12345678\n"
        )
        result = detect_provider(text)
        # Both appear once. Tie broken by priority order: Energia is listed
        # before ESB Networks in PROVIDER_KEYWORDS.
        assert result.is_known is True
        assert result.provider_name == "Energia"

    def test_go_power_mentioning_esb(self):
        """Go Power bills mention ESB Networks in passthrough/emergency text.
        Go Power keywords appear far more often, so Go Power should win."""
        text = (
            "Go Power Electricity Bill\n"
            "Go Power is a brand of LCC Power Ltd.\n"
            "Visit gopower.ie for account details.\n"
            "Go Power pays ESB Networks on your behalf.\n"
            "For emergencies contact ESB Networks at 1800 372 999.\n"
        )
        result = detect_provider(text)
        # "go power" appears 3x, "gopower" 1x = 4 total for Go Power
        # "esb networks" appears 2x = 2 total for ESB Networks
        assert result.provider_name == "Go Power"

    def test_deterministic_results(self):
        """Same input should always produce the same output."""
        text = "Your Energia electricity bill for the period"
        results = [detect_provider(text) for _ in range(10)]
        providers = {r.provider_name for r in results}
        assert len(providers) == 1, "Detection should be deterministic"

    def test_longest_keyword_reported(self):
        """matched_keyword should report the longest keyword that matched."""
        # Both "sse airtricity" and "airtricity" match; longest is reported
        text = "SSE Airtricity gas bill summary"
        result = detect_provider(text)
        assert result.provider_name == "SSE Airtricity"
        assert result.matched_keyword == "sse airtricity"

    def test_bord_gais_fada(self):
        """Should match 'Bord Gáis' (with fada)."""
        result = detect_provider("Bord Gáis Energy electricity bill")
        assert result.provider_name == "Bord Gais"

    # -- Integration: Tier 0 text → Tier 1 provider detection --

    @pytest.mark.parametrize("pdf_name,expected_provider", [
        ("1845.pdf", "Go Power"),
        ("2024 Mar - Apr.pdf", "ESB Networks"),
        ("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf", "Energia"),
    ])
    def test_provider_from_real_pdfs(self, pdf_name, expected_provider):
        """End-to-end: extract text (Tier 0), then detect provider (Tier 1)."""
        path = _pdf_path(pdf_name)
        if not os.path.exists(path):
            pytest.skip(f"PDF not found: {pdf_name}")
        tier0 = extract_text_tier0(path)
        result = detect_provider(tier0.extracted_text)
        assert result.is_known is True
        assert result.provider_name == expected_provider

    # -- Provider keywords coverage --

    def test_all_providers_have_keywords(self):
        """Every provider in the registry should have at least one keyword."""
        for provider, keywords in PROVIDER_KEYWORDS.items():
            assert len(keywords) > 0, f"Provider '{provider}' has no keywords"
            for kw in keywords:
                assert len(kw) > 0, f"Provider '{provider}' has empty keyword"
