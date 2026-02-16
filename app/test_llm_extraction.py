"""
Tests for Tier 4 LLM Vision Extraction.

Unit tests cover:
  - Schema conversion (LLMBillSchema -> FieldExtractionResult)
  - Merge strategy (LLM + regex/spatial)
  - Graceful degradation when API key not set

Integration tests (require GEMINI_API_KEY env var):
  - Extract from photo bill (JPG)
  - Extract from PDF bill
  - Full pipeline integration via orchestrator
"""
import os
import pytest

from pipeline import FieldExtractionResult
from llm_extraction import (
    LLMBillSchema,
    LLMLineItem,
    Tier4ExtractionResult,
    _schema_to_fields,
    merge_llm_with_existing,
    _values_equivalent,
    extract_tier4_llm,
)

BILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "sample_bills")


def _bill_path(filename: str) -> str:
    return os.path.join(BILLS_DIR, filename)


def _bill_exists(filename: str) -> bool:
    return os.path.exists(_bill_path(filename))


def _has_gemini_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


# ===================================================================
# Unit tests - no API key needed
# ===================================================================


class TestValuesEquivalent:
    """Tests for the _values_equivalent helper."""

    def test_identical_strings(self):
        assert _values_equivalent("10006802505", "10006802505")

    def test_numeric_equivalence(self):
        assert _values_equivalent("266.45", "266.45")

    def test_numeric_with_currency(self):
        assert _values_equivalent("$266.45", "266.45")

    def test_numeric_with_comma(self):
        assert _values_equivalent("1,266.45", "1266.45")

    def test_case_insensitive_text(self):
        assert _values_equivalent("Energia", "energia")

    def test_different_values(self):
        assert not _values_equivalent("266.45", "300.00")

    def test_different_strings(self):
        assert not _values_equivalent("Energia", "SSE")

    def test_close_floats(self):
        assert _values_equivalent("266.45", "266.449")

    def test_not_close_floats(self):
        assert not _values_equivalent("266.45", "266.50")


class TestSchemaToFields:
    """Tests for converting LLMBillSchema to FieldExtractionResult dict."""

    def test_simple_string_fields(self):
        schema = LLMBillSchema(
            provider="Energia",
            mprn="10006802505",
            account_number="8386744600",
        )
        fields = _schema_to_fields(schema)
        assert "provider" in fields
        assert fields["provider"].value == "Energia"
        assert fields["mprn"].value == "10006802505"
        assert fields["account_number"].value == "8386744600"

    def test_numeric_fields(self):
        schema = LLMBillSchema(
            subtotal=244.45,
            vat_rate=9.0,
            vat_amount=22.0,
            total_incl_vat=266.45,
        )
        fields = _schema_to_fields(schema)
        assert fields["subtotal"].value == "244.45"
        assert fields["vat_rate"].value == "9.0"
        assert fields["vat_amount"].value == "22.0"
        assert fields["total_incl_vat"].value == "266.45"

    def test_null_fields_excluded(self):
        schema = LLMBillSchema(provider="Energia", mprn=None)
        fields = _schema_to_fields(schema)
        assert "provider" in fields
        assert "mprn" not in fields

    def test_empty_string_excluded(self):
        schema = LLMBillSchema(provider="", mprn="10006802505")
        fields = _schema_to_fields(schema)
        assert "provider" not in fields
        assert "mprn" in fields

    def test_confidence_default(self):
        schema = LLMBillSchema(provider="Energia")
        fields = _schema_to_fields(schema)
        assert fields["provider"].confidence == 0.75

    def test_custom_confidence(self):
        schema = LLMBillSchema(provider="Energia")
        fields = _schema_to_fields(schema, base_confidence=0.90)
        assert fields["provider"].confidence == 0.90

    def test_pattern_index_is_negative(self):
        schema = LLMBillSchema(provider="Energia")
        fields = _schema_to_fields(schema)
        assert fields["provider"].pattern_index == -1

    def test_line_items_day_energy(self):
        schema = LLMBillSchema(
            line_items=[
                LLMLineItem(
                    description="Day Energy",
                    quantity=242.0,
                    unit="kWh",
                    unit_price=0.15148,
                    line_total=36.66,
                ),
            ]
        )
        fields = _schema_to_fields(schema)
        assert "day_kwh" in fields
        assert fields["day_kwh"].value == "242.0"
        assert "day_rate" in fields
        assert fields["day_rate"].value == "0.15148"
        assert "day_cost" in fields
        assert fields["day_cost"].value == "36.66"

    def test_line_items_night_energy(self):
        schema = LLMBillSchema(
            line_items=[
                LLMLineItem(
                    description="Night Energy",
                    quantity=724.0,
                    unit="kWh",
                    unit_price=0.11896,
                ),
            ]
        )
        fields = _schema_to_fields(schema)
        assert "night_kwh" in fields
        assert fields["night_kwh"].value == "724.0"
        assert "night_rate" in fields

    def test_line_items_standing_charge(self):
        schema = LLMBillSchema(
            line_items=[
                LLMLineItem(
                    description="Standing Charge",
                    quantity=31.0,
                    unit_price=0.93,
                    line_total=28.88,
                ),
            ]
        )
        fields = _schema_to_fields(schema)
        assert "standing_charge" in fields
        assert "31.0" in fields["standing_charge"].value
        assert "0.93" in fields["standing_charge"].value
        assert "28.88" in fields["standing_charge"].value

    def test_line_items_pso_levy(self):
        schema = LLMBillSchema(
            line_items=[
                LLMLineItem(description="PSO Levy", line_total=12.91),
            ]
        )
        fields = _schema_to_fields(schema)
        assert "pso_levy" in fields
        assert fields["pso_levy"].value == "12.91"

    def test_line_items_fuel(self):
        schema = LLMBillSchema(
            line_items=[
                LLMLineItem(
                    description="Kerosene delivery",
                    quantity=1000.0,
                    unit="litres",
                    unit_price=0.85,
                    line_total=850.0,
                ),
            ]
        )
        fields = _schema_to_fields(schema)
        assert "litres" in fields
        assert fields["litres"].value == "1000.0"
        assert "unit_price" in fields
        assert fields["unit_price"].value == "0.85"

    def test_empty_line_items(self):
        schema = LLMBillSchema(line_items=[])
        fields = _schema_to_fields(schema)
        assert "day_kwh" not in fields


class TestMergeLlmWithExisting:
    """Tests for the merge strategy."""

    def test_only_llm_found(self):
        llm = {
            "provider": FieldExtractionResult("provider", "Energia", 0.75, -1),
        }
        existing: dict[str, FieldExtractionResult] = {}
        merged = merge_llm_with_existing(llm, existing)
        assert "provider" in merged
        assert merged["provider"].value == "Energia"

    def test_only_existing_found(self):
        llm: dict[str, FieldExtractionResult] = {}
        existing = {
            "mprn": FieldExtractionResult("mprn", "10006802505", 0.90, 0),
        }
        merged = merge_llm_with_existing(llm, existing)
        assert "mprn" in merged
        assert merged["mprn"].value == "10006802505"

    def test_both_agree_boost_confidence(self):
        llm = {
            "mprn": FieldExtractionResult("mprn", "10006802505", 0.75, -1),
        }
        existing = {
            "mprn": FieldExtractionResult("mprn", "10006802505", 0.90, 0),
        }
        merged = merge_llm_with_existing(llm, existing)
        assert merged["mprn"].confidence == 1.0  # 0.90 + 0.10, capped at 1.0
        assert merged["mprn"].value == "10006802505"
        assert merged["mprn"].pattern_index == 0  # Keep existing pattern_index

    def test_disagree_numeric_prefer_regex(self):
        llm = {
            "vat_rate": FieldExtractionResult("vat_rate", "9.5", 0.75, -1),
        }
        existing = {
            "vat_rate": FieldExtractionResult("vat_rate", "9", 0.80, 0),
        }
        merged = merge_llm_with_existing(llm, existing)
        assert merged["vat_rate"].value == "9"  # Regex preferred for numerics

    def test_disagree_text_prefer_llm(self):
        llm = {
            "provider": FieldExtractionResult("provider", "Energia", 0.75, -1),
        }
        existing = {
            "provider": FieldExtractionResult("provider", "ENRGIA", 0.60, 0),
        }
        merged = merge_llm_with_existing(llm, existing)
        assert merged["provider"].value == "Energia"  # LLM preferred for text

    def test_disagree_billing_period_prefer_llm(self):
        llm = {
            "billing_period": FieldExtractionResult(
                "billing_period", "2025-03-01 to 2025-03-31", 0.75, -1
            ),
        }
        existing = {
            "billing_period": FieldExtractionResult(
                "billing_period", "01/03/2025 - 31/03/2025", 0.70, 0
            ),
        }
        merged = merge_llm_with_existing(llm, existing)
        assert merged["billing_period"].value == "2025-03-01 to 2025-03-31"

    def test_disagree_total_prefer_regex(self):
        llm = {
            "total_incl_vat": FieldExtractionResult("total_incl_vat", "267.00", 0.75, -1),
        }
        existing = {
            "total_incl_vat": FieldExtractionResult("total_incl_vat", "266.45", 0.85, 0),
        }
        merged = merge_llm_with_existing(llm, existing)
        assert merged["total_incl_vat"].value == "266.45"

    def test_mixed_merge(self):
        llm = {
            "provider": FieldExtractionResult("provider", "Energia", 0.75, -1),
            "mprn": FieldExtractionResult("mprn", "10006802505", 0.75, -1),
            "billing_period": FieldExtractionResult("billing_period", "2025-03-01 to 2025-03-31", 0.75, -1),
        }
        existing = {
            "mprn": FieldExtractionResult("mprn", "10006802505", 0.90, 0),
            "total_incl_vat": FieldExtractionResult("total_incl_vat", "266.45", 0.85, 0),
        }
        merged = merge_llm_with_existing(llm, existing)
        assert len(merged) == 4  # provider, mprn, billing_period, total
        assert merged["mprn"].confidence == 1.0  # Boosted
        assert merged["provider"].value == "Energia"  # LLM-only
        assert merged["total_incl_vat"].value == "266.45"  # Existing-only

    def test_confidence_cap_at_one(self):
        llm = {
            "mprn": FieldExtractionResult("mprn", "10006802505", 0.95, -1),
        }
        existing = {
            "mprn": FieldExtractionResult("mprn", "10006802505", 0.95, 0),
        }
        merged = merge_llm_with_existing(llm, existing)
        assert merged["mprn"].confidence == 1.0  # 0.95 + 0.10 capped


class TestGracefulDegradation:
    """Tests that Tier 4 gracefully handles missing dependencies."""

    def test_no_api_key(self, monkeypatch):
        """extract_tier4_llm should raise RuntimeError when key not set."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            extract_tier4_llm(b"fake pdf bytes")

    def test_orchestrator_skips_without_key(self, monkeypatch):
        """Orchestrator should skip Tier 4 when no key, not crash."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        from orchestrator import _try_tier4_llm
        result = _try_tier4_llm(b"fake", [])
        assert result is None


# ===================================================================
# Integration tests - require GEMINI_API_KEY
# ===================================================================


@pytest.mark.skipif(not _has_gemini_key(), reason="GEMINI_API_KEY not set")
class TestTier4Integration:
    """Integration tests calling the actual Gemini API."""

    @pytest.mark.skipif(
        not _bill_exists("sample_bill_photo.jpg"),
        reason="Photo bill not found",
    )
    def test_extract_photo_bill(self):
        """Extract fields from a photographed bill (JPG)."""
        result = extract_tier4_llm(
            _bill_path("sample_bill_photo.jpg"), is_image=True
        )
        assert isinstance(result, Tier4ExtractionResult)
        assert result.field_count > 0
        assert result.model_used == "gemini-2.0-flash"
        assert len(result.warnings) == 0

        # Should extract at least total
        assert "total_incl_vat" in result.fields

    @pytest.mark.skipif(
        not _bill_exists("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"),
        reason="Energia PDF not found",
    )
    def test_extract_energia_pdf(self):
        """Extract fields from an Energia electricity PDF bill."""
        result = extract_tier4_llm(
            _bill_path("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")
        )
        assert isinstance(result, Tier4ExtractionResult)
        assert result.field_count >= 10  # Should get many fields

        # Verify key fields
        assert "mprn" in result.fields
        assert result.fields["mprn"].value == "10006802505"

        assert "total_incl_vat" in result.fields
        assert abs(float(result.fields["total_incl_vat"].value) - 266.45) < 0.1

        assert "provider" in result.fields

    @pytest.mark.skipif(
        not _bill_exists("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"),
        reason="Energia PDF not found",
    )
    def test_full_pipeline_with_llm(self):
        """Test the full pipeline with Tier 4 available."""
        from orchestrator import extract_bill_pipeline, PipelineResult

        result = extract_bill_pipeline(
            _bill_path("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")
        )
        assert isinstance(result, PipelineResult)
        # For native PDFs, Tier 3 should handle it without needing Tier 4
        # but it should not crash with Tier 4 available
        assert result.bill.total_incl_vat is not None
        assert abs(result.bill.total_incl_vat - 266.45) < 0.1

    @pytest.mark.skipif(
        not _bill_exists("sample_bill_photo.jpg"),
        reason="Photo bill not found",
    )
    def test_merge_with_empty_existing(self):
        """Merge LLM results with no existing fields (pure LLM path)."""
        result = extract_tier4_llm(
            _bill_path("sample_bill_photo.jpg"), is_image=True
        )
        merged = merge_llm_with_existing(result.fields, {})
        assert len(merged) == result.field_count

    @pytest.mark.skipif(
        not _bill_exists("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"),
        reason="Energia PDF not found",
    )
    def test_merge_llm_and_regex(self):
        """Merge LLM with Tier 2 regex on same bill."""
        from pipeline import extract_text_tier0, extract_tier2_universal

        pdf_path = _bill_path(
            "3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"
        )

        # Get regex results
        tier0 = extract_text_tier0(pdf_path)
        regex_result = extract_tier2_universal(tier0.extracted_text)

        # Get LLM results
        llm_result = extract_tier4_llm(pdf_path)

        # Merge
        merged = merge_llm_with_existing(llm_result.fields, regex_result.fields)

        # Merged should have at least as many fields as either source
        assert len(merged) >= len(regex_result.fields)
        assert len(merged) >= len(llm_result.fields)

        # Cross-validated fields should have boosted confidence
        for name in merged:
            if name in regex_result.fields and name in llm_result.fields:
                regex_val = regex_result.fields[name].value
                llm_val = llm_result.fields[name].value
                if _values_equivalent(regex_val, llm_val):
                    assert merged[name].confidence > max(
                        regex_result.fields[name].confidence,
                        llm_result.fields[name].confidence,
                    ) - 0.01  # Allow small float tolerance
