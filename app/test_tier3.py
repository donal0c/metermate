"""
Tests for Tier 3: Config-driven provider-specific regex extraction.

Covers acceptance criteria for steve-8vw:
  (1) Config-driven extractor for Energia, Kerry Petroleum, Go Power, ESB Networks
  (2) Provider configs with schema: provider, version, fields{patterns, confidence}
  (3) Preprocessing hooks
  (4) Per-provider field hit rate against real fixtures
  (5) >=95% critical field extraction across known-provider fixtures
"""
import os
import pytest
from pipeline import (
    extract_text_tier0,
    detect_provider,
    extract_with_config,
    Tier3ExtractionResult,
    FieldExtractionResult,
)
from provider_configs import (
    PROVIDER_CONFIGS,
    get_provider_config,
    ENERGIA_CONFIG,
    GO_POWER_CONFIG,
    ESB_NETWORKS_CONFIG,
    KERRY_PETROLEUM_CONFIG,
    ELECTRIC_IRELAND_CONFIG,
    SSE_AIRTRICITY_CONFIG,
)

BILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "Steve_bills")
ROOT_DIR = os.path.join(os.path.dirname(__file__), "..")


def _pdf_path(filename: str) -> str:
    return os.path.join(BILLS_DIR, filename)


def _root_pdf_path(filename: str) -> str:
    return os.path.join(ROOT_DIR, filename)


# ===================================================================
# Config schema validation
# ===================================================================

class TestProviderConfigSchema:
    """Validate that all provider configs conform to the expected schema."""

    @pytest.mark.parametrize("provider_name", list(PROVIDER_CONFIGS.keys()))
    def test_required_keys(self, provider_name):
        config = PROVIDER_CONFIGS[provider_name]
        assert "provider" in config
        assert "version" in config
        assert "detection_keywords" in config
        assert "fields" in config
        assert config["provider"] == provider_name
        assert isinstance(config["version"], int)
        assert isinstance(config["detection_keywords"], list)
        assert len(config["detection_keywords"]) > 0

    @pytest.mark.parametrize("provider_name", list(PROVIDER_CONFIGS.keys()))
    def test_field_schema(self, provider_name):
        config = PROVIDER_CONFIGS[provider_name]
        for field_name, field_cfg in config["fields"].items():
            assert "patterns" in field_cfg, f"{provider_name}.{field_name} missing 'patterns'"
            assert "confidence" in field_cfg, f"{provider_name}.{field_name} missing 'confidence'"
            assert isinstance(field_cfg["patterns"], list)
            assert len(field_cfg["patterns"]) > 0
            assert 0.0 <= field_cfg["confidence"] <= 1.0
            # Each pattern is a tuple of (anchor_regex, value_regex)
            for pat in field_cfg["patterns"]:
                assert len(pat) == 2, f"{provider_name}.{field_name} pattern should be (anchor, value)"

    def test_get_provider_config_returns_config(self):
        assert get_provider_config("Energia") is not None
        assert get_provider_config("Go Power") is not None

    def test_get_provider_config_unknown(self):
        assert get_provider_config("NonExistent") is None


# ===================================================================
# Extraction engine unit tests
# ===================================================================

class TestExtractWithConfig:
    def test_raises_on_unknown_provider(self):
        with pytest.raises(ValueError, match="No Tier 3 config"):
            extract_with_config("some text", "FakeProvider")

    def test_returns_result_dataclass(self):
        result = extract_with_config("Invoice No. 123456 energia", "Energia")
        assert isinstance(result, Tier3ExtractionResult)
        assert result.provider == "Energia"
        assert isinstance(result.fields, dict)
        assert isinstance(result.hit_rate, float)

    def test_simple_energia_extraction(self):
        text = (
            "MPRN Number: 10306802505\n"
            "Account Number: 8386744600\n"
            "VAT @ 9% €22.79\n"
            "Total Charges For This Period €176.59\n"
        )
        result = extract_with_config(text, "Energia")
        assert "mprn" in result.fields
        assert result.fields["mprn"].value == "10306802505"
        assert "account_number" in result.fields
        assert "vat_rate" in result.fields
        assert "total_incl_vat" in result.fields
        assert result.fields["total_incl_vat"].value == "176.59"


# ===================================================================
# Real PDF fixture tests — per-provider
# ===================================================================

# Critical fields that must be extracted (per acceptance criteria: >=95%)
CRITICAL_FIELDS = {"mprn", "account_number", "vat_rate", "vat_amount", "total_incl_vat", "subtotal"}
# Kerry Petroleum doesn't have MPRN — use its own critical set
KERRY_CRITICAL_FIELDS = {"invoice_number", "vat_rate", "total_incl_vat", "subtotal"}


class TestTier3GoPower:
    PDF = "1845.pdf"

    @pytest.fixture
    def extraction(self):
        path = _pdf_path(self.PDF)
        if not os.path.exists(path):
            pytest.skip(f"PDF not found: {self.PDF}")
        tier0 = extract_text_tier0(path)
        return extract_with_config(tier0.extracted_text, "Go Power")

    def test_provider_identified(self, extraction):
        assert extraction.provider == "Go Power"

    def test_mprn_extracted(self, extraction):
        assert "mprn" in extraction.fields
        mprn = extraction.fields["mprn"].value
        assert len(mprn) == 11
        assert mprn.startswith("10")

    def test_critical_fields(self, extraction):
        available = CRITICAL_FIELDS & set(extraction.fields.keys())
        assert len(available) >= 4, f"Only found {len(available)}/6: {available}"

    def test_hit_rate(self, extraction):
        print(f"\nGo Power hit rate: {extraction.hit_rate:.0%} ({extraction.field_count} fields)")
        for name, fr in sorted(extraction.fields.items()):
            print(f"  {name}: {fr.value}")


class TestTier3ESBNetworks:
    PDF = "2024 Mar - Apr.pdf"

    @pytest.fixture
    def extraction(self):
        path = _pdf_path(self.PDF)
        if not os.path.exists(path):
            pytest.skip(f"PDF not found: {self.PDF}")
        tier0 = extract_text_tier0(path)
        return extract_with_config(tier0.extracted_text, "ESB Networks")

    def test_provider_identified(self, extraction):
        assert extraction.provider == "ESB Networks"

    def test_mprn_extracted(self, extraction):
        assert "mprn" in extraction.fields
        mprn = extraction.fields["mprn"].value
        assert len(mprn) == 11
        assert mprn.startswith("10")

    def test_vat_fields(self, extraction):
        # ESB should have VAT amount and rate
        assert "vat_amount" in extraction.fields or "vat_rate" in extraction.fields

    def test_hit_rate(self, extraction):
        print(f"\nESB Networks hit rate: {extraction.hit_rate:.0%} ({extraction.field_count} fields)")
        for name, fr in sorted(extraction.fields.items()):
            print(f"  {name}: {fr.value}")


class TestTier3Energia:
    PDF = "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"

    @pytest.fixture
    def extraction(self):
        path = _pdf_path(self.PDF)
        if not os.path.exists(path):
            pytest.skip(f"PDF not found: {self.PDF}")
        tier0 = extract_text_tier0(path)
        return extract_with_config(tier0.extracted_text, "Energia")

    def test_provider_identified(self, extraction):
        assert extraction.provider == "Energia"

    def test_mprn_extracted(self, extraction):
        assert "mprn" in extraction.fields
        mprn = extraction.fields["mprn"].value
        assert len(mprn) == 11
        assert mprn.startswith("10")

    def test_account_number(self, extraction):
        assert "account_number" in extraction.fields
        acct = extraction.fields["account_number"].value
        assert len(acct) >= 7

    def test_critical_fields(self, extraction):
        available = CRITICAL_FIELDS & set(extraction.fields.keys())
        assert len(available) >= 5, f"Only found {len(available)}/6: {available}"

    def test_hit_rate(self, extraction):
        print(f"\nEnergia hit rate: {extraction.hit_rate:.0%} ({extraction.field_count} fields)")
        for name, fr in sorted(extraction.fields.items()):
            print(f"  {name}: {fr.value}")


class TestTier3ElectricIreland:
    """Test Electric Ireland Tier 3 extraction against two bill formats."""

    # New format (smart meter, 2025)
    PDF_NEW = "download.pdf"
    # Old format (single tariff, 2023)
    PDF_OLD = "Bill_310148750 (1).pdf"

    @pytest.fixture
    def extraction_new(self):
        path = _root_pdf_path(self.PDF_NEW)
        if not os.path.exists(path):
            pytest.skip(f"PDF not found: {self.PDF_NEW}")
        tier0 = extract_text_tier0(path)
        return extract_with_config(tier0.extracted_text, "Electric Ireland")

    @pytest.fixture
    def extraction_old(self):
        path = _root_pdf_path(self.PDF_OLD)
        if not os.path.exists(path):
            pytest.skip(f"PDF not found: {self.PDF_OLD}")
        tier0 = extract_text_tier0(path)
        return extract_with_config(tier0.extracted_text, "Electric Ireland")

    def test_provider_identified(self, extraction_new):
        assert extraction_new.provider == "Electric Ireland"

    def test_mprn_extracted_new(self, extraction_new):
        assert "mprn" in extraction_new.fields
        mprn = extraction_new.fields["mprn"].value
        assert len(mprn) == 11
        assert mprn.startswith("10")

    def test_mprn_extracted_old(self, extraction_old):
        assert "mprn" in extraction_old.fields
        mprn = extraction_old.fields["mprn"].value
        assert len(mprn) == 11
        assert mprn.startswith("10")

    def test_account_number_new(self, extraction_new):
        assert "account_number" in extraction_new.fields
        assert extraction_new.fields["account_number"].value == "2298483377"

    def test_account_number_old(self, extraction_old):
        assert "account_number" in extraction_old.fields
        assert extraction_old.fields["account_number"].value == "950960495"

    def test_critical_fields_new(self, extraction_new):
        available = CRITICAL_FIELDS & set(extraction_new.fields.keys())
        assert len(available) >= 5, f"Only found {len(available)}/6: {available}"

    def test_critical_fields_old(self, extraction_old):
        available = CRITICAL_FIELDS & set(extraction_old.fields.keys())
        assert len(available) >= 5, f"Only found {len(available)}/6: {available}"

    def test_smart_meter_fields(self, extraction_new):
        """New format bills should extract day/night/peak usage."""
        assert "day_kwh" in extraction_new.fields
        assert "night_kwh" in extraction_new.fields
        assert "peak_kwh" in extraction_new.fields

    def test_hit_rate_new(self, extraction_new):
        print(f"\nElectric Ireland (new) hit rate: {extraction_new.hit_rate:.0%} ({extraction_new.field_count} fields)")
        for name, fr in sorted(extraction_new.fields.items()):
            print(f"  {name}: {fr.value}")

    def test_hit_rate_old(self, extraction_old):
        print(f"\nElectric Ireland (old) hit rate: {extraction_old.hit_rate:.0%} ({extraction_old.field_count} fields)")
        for name, fr in sorted(extraction_old.fields.items()):
            print(f"  {name}: {fr.value}")


class TestTier3SSEAirtricity:
    """Test SSE Airtricity Tier 3 extraction.

    Note: The fixture is an illustrative example with blank MPRN/account fields.
    """

    PDF = "SSE_Airtricity_example.pdf"

    @pytest.fixture
    def extraction(self):
        path = _root_pdf_path(self.PDF)
        if not os.path.exists(path):
            pytest.skip(f"PDF not found: {self.PDF}")
        tier0 = extract_text_tier0(path)
        return extract_with_config(tier0.extracted_text, "SSE Airtricity")

    def test_provider_identified(self, extraction):
        assert extraction.provider == "SSE Airtricity"

    def test_billing_period(self, extraction):
        assert "billing_period" in extraction.fields
        assert "22/12/2017" in extraction.fields["billing_period"].value

    def test_day_night_kwh(self, extraction):
        assert "day_kwh" in extraction.fields
        assert "night_kwh" in extraction.fields
        assert extraction.fields["day_kwh"].value == "247.00"
        assert extraction.fields["night_kwh"].value == "49.00"

    def test_standing_charge(self, extraction):
        assert "standing_charge" in extraction.fields
        val = extraction.fields["standing_charge"].value
        # Should be "31.00 - 0.6037 - 18.72" (days - rate - total)
        parts = val.split(" - ")
        assert len(parts) == 3

    def test_total_and_vat(self, extraction):
        assert "subtotal" in extraction.fields
        assert "vat_rate" in extraction.fields
        assert "vat_amount" in extraction.fields
        assert "total_incl_vat" in extraction.fields
        assert extraction.fields["subtotal"].value == "72.85"
        assert extraction.fields["total_incl_vat"].value == "82.68"

    def test_hit_rate(self, extraction):
        print(f"\nSSE Airtricity hit rate: {extraction.hit_rate:.0%} ({extraction.field_count} fields)")
        for name, fr in sorted(extraction.fields.items()):
            print(f"  {name}: {fr.value}")


# ===================================================================
# Cross-provider critical field extraction rate
# ===================================================================

class TestCriticalFieldRate:
    """Acceptance: >=95% critical field extraction across known-provider fixtures."""

    FIXTURE_MAP = {
        "Go Power": "1845.pdf",
        "ESB Networks": "2024 Mar - Apr.pdf",
        "Energia": "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf",
    }

    def test_overall_critical_rate(self):
        total_critical = 0
        total_extracted = 0

        for provider, pdf_name in self.FIXTURE_MAP.items():
            path = _pdf_path(pdf_name)
            if not os.path.exists(path):
                pytest.skip(f"PDF not found: {pdf_name}")

            tier0 = extract_text_tier0(path)
            result = extract_with_config(tier0.extracted_text, provider)

            # Determine which critical fields this provider should have
            provider_fields = set(result.fields.keys())
            config_fields = set(PROVIDER_CONFIGS[provider]["fields"].keys())
            applicable_critical = CRITICAL_FIELDS & config_fields

            for cf in applicable_critical:
                total_critical += 1
                if cf in result.fields:
                    total_extracted += 1

        if total_critical == 0:
            pytest.skip("No critical fields to check")

        rate = total_extracted / total_critical
        print(f"\nOverall critical field rate: {rate:.0%} ({total_extracted}/{total_critical})")
        assert rate >= 0.95, f"Critical field rate too low: {rate:.0%}"


# ===================================================================
# Preprocessing hooks
# ===================================================================

class TestPreprocessHooks:
    def test_energia_normalize_euro_word(self):
        # OCR typically outputs "euro 123.45" (with space) as a word boundary
        text = "Total euro 123.45"
        from pipeline import _preprocess_energia
        result = _preprocess_energia(text)
        assert "€ 123.45" in result or "€123.45" in result

    def test_energia_normalize_xwh(self):
        text = "Day Energy 242 XWh"
        from pipeline import _preprocess_energia
        result = _preprocess_energia(text)
        assert "kWh" in result

    def test_energia_normalize_synthesizes_scanned_summary_lines(self):
        text = (
            "Gas. Total Carbon Night Day Standing Electricity EEOS EEOS Rate Charge "
            "Excluding Rate Credit Charge Charge Tax VAT . "
            "4,844 4,344 4,844 2422 4,844 2,966 1,878 31 Days kWh kWh "
            "€371.09 €946.45 €170.68 €20.43 €10.90 €1,139.75"
        )
        from pipeline import _preprocess_energia
        result = _preprocess_energia(text)
        assert "Day Energy 2,966 kWh" in result
        assert "Night Energy 1,878 kWh" in result
        assert "Total Excluding VAT €1,139.75" in result

    def test_kerry_normalize_pipes(self):
        text = "KEROSENE | 849 | 106.21"
        from pipeline import _preprocess_kerry
        result = _preprocess_kerry(text)
        assert "|" not in result
        assert "KEROSENE" in result

    def test_kerry_normalize_commas(self):
        text = "1,023.45"
        from pipeline import _preprocess_kerry
        result = _preprocess_kerry(text)
        assert result.strip() == "1023.45"
