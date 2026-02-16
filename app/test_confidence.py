"""
Tests for confidence scoring and cross-field validation.

Covers acceptance criteria for confidence scoring.
"""
import os
import pytest
from pipeline import (
    FieldExtractionResult,
    ValidationCheck,
    ConfidenceResult,
    validate_cross_fields,
    calculate_confidence,
    postprocess_rates_fields,
    extract_text_tier0,
    extract_with_config,
    FIELD_PROFILES,
    PROVIDER_BILL_TYPE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fr(name: str, value: str, confidence: float = 0.9) -> FieldExtractionResult:
    """Shorthand for creating a FieldExtractionResult."""
    return FieldExtractionResult(
        field_name=name, value=value, confidence=confidence, pattern_index=0,
    )


def _good_electricity_fields() -> dict[str, FieldExtractionResult]:
    """Known-good extraction with mathematically consistent values."""
    return {
        "mprn": _fr("mprn", "10306802505"),
        "account_number": _fr("account_number", "8386744600"),
        "billing_period": _fr("billing_period", "01/11/2025 - 01/01/2026"),
        "day_kwh": _fr("day_kwh", "242"),
        "day_rate": _fr("day_rate", "0.15148"),
        "standing_charge": _fr("standing_charge", "28.88"),
        "subtotal": _fr("subtotal", "244.45"),
        "vat_rate": _fr("vat_rate", "9"),
        "vat_amount": _fr("vat_amount", "22.00"),
        "total_incl_vat": _fr("total_incl_vat", "266.45"),
    }


def _bad_fields() -> dict[str, FieldExtractionResult]:
    """Known-bad extraction with inconsistent values."""
    return {
        "mprn": _fr("mprn", "12345"),  # Too short, wrong prefix
        "subtotal": _fr("subtotal", "100.00"),
        "vat_rate": _fr("vat_rate", "9"),
        "vat_amount": _fr("vat_amount", "50.00"),  # Should be 9.00
        "total_incl_vat": _fr("total_incl_vat", "200.00"),  # Should be 150.00
    }


BILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "sample_bills")


# ===================================================================
# Cross-field validation
# ===================================================================

class TestValidateCrossFields:
    def test_good_totals(self):
        fields = _good_electricity_fields()
        checks = validate_cross_fields(fields)
        totals_check = next(c for c in checks if c.name == "totals_crosscheck")
        assert totals_check.passed is True

    def test_bad_totals(self):
        fields = _bad_fields()
        checks = validate_cross_fields(fields)
        totals_check = next(c for c in checks if c.name == "totals_crosscheck")
        assert totals_check.passed is False

    def test_vat_math_good(self):
        fields = _good_electricity_fields()
        checks = validate_cross_fields(fields)
        vat_check = next(c for c in checks if c.name == "vat_math")
        assert vat_check.passed is True

    def test_vat_math_bad(self):
        fields = _bad_fields()
        checks = validate_cross_fields(fields)
        vat_check = next(c for c in checks if c.name == "vat_math")
        assert vat_check.passed is False

    def test_mprn_valid(self):
        fields = _good_electricity_fields()
        checks = validate_cross_fields(fields)
        mprn_check = next(c for c in checks if c.name == "mprn_format")
        assert mprn_check.passed is True

    def test_mprn_invalid(self):
        fields = _bad_fields()
        checks = validate_cross_fields(fields)
        mprn_check = next(c for c in checks if c.name == "mprn_format")
        assert mprn_check.passed is False

    def test_total_reasonable(self):
        fields = _good_electricity_fields()
        checks = validate_cross_fields(fields)
        total_check = next(c for c in checks if c.name == "total_reasonable")
        assert total_check.passed is True

    def test_total_unreasonable(self):
        fields = {"total_incl_vat": _fr("total_incl_vat", "150000.00")}
        checks = validate_cross_fields(fields)
        total_check = next(c for c in checks if c.name == "total_reasonable")
        assert total_check.passed is False

    def test_zero_total_is_valid(self):
        """Zero-balance statements (credit notes) should pass."""
        fields = {"total_incl_vat": _fr("total_incl_vat", "0.00")}
        checks = validate_cross_fields(fields)
        total_check = next(c for c in checks if c.name == "total_reasonable")
        assert total_check.passed is True

    def test_vat_rate_range_valid(self):
        fields = {"vat_rate": _fr("vat_rate", "13.5")}
        checks = validate_cross_fields(fields)
        rate_check = next(c for c in checks if c.name == "vat_rate_range")
        assert rate_check.passed is True

    def test_vat_rate_range_invalid(self):
        fields = {"vat_rate": _fr("vat_rate", "50")}
        checks = validate_cross_fields(fields)
        rate_check = next(c for c in checks if c.name == "vat_rate_range")
        assert rate_check.passed is False

    def test_empty_fields_no_crash(self):
        checks = validate_cross_fields({})
        assert isinstance(checks, list)

    def test_partial_fields(self):
        """Fields without enough data should still produce checks for what's available."""
        fields = {"mprn": _fr("mprn", "10306802505")}
        checks = validate_cross_fields(fields)
        assert any(c.name == "mprn_format" for c in checks)

    def test_tolerance_edge_case(self):
        """Totals off by exactly 0.02 should still pass."""
        fields = {
            "subtotal": _fr("subtotal", "100.00"),
            "vat_amount": _fr("vat_amount", "9.00"),
            "total_incl_vat": _fr("total_incl_vat", "109.02"),  # Off by 0.02
        }
        checks = validate_cross_fields(fields)
        totals_check = next(c for c in checks if c.name == "totals_crosscheck")
        assert totals_check.passed is True


# ===================================================================
# Range validation (unit rates, consumption, cost consistency)
# ===================================================================

class TestRangeValidation:
    """Tests for the plausibility checks for range validation."""

    def test_normal_day_rate_passes(self):
        fields = {"day_rate": _fr("day_rate", "0.15148")}
        checks = validate_cross_fields(fields)
        rate_check = next(c for c in checks if c.name == "day_rate_range")
        assert rate_check.passed is True

    def test_absurd_day_rate_fails(self):
        """Rate of 234 EUR/kWh is clearly an OCR error."""
        fields = {"day_rate": _fr("day_rate", "234.56")}
        checks = validate_cross_fields(fields)
        rate_check = next(c for c in checks if c.name == "day_rate_range")
        assert rate_check.passed is False

    def test_rate_in_cents_fails(self):
        """15.148 looks like cents (should be 0.15148)."""
        fields = {"day_rate": _fr("day_rate", "15.148")}
        checks = validate_cross_fields(fields)
        rate_check = next(c for c in checks if c.name == "day_rate_range")
        assert rate_check.passed is False

    def test_night_rate_boundary(self):
        """Rate at exactly 1.0 should pass (upper bound inclusive)."""
        fields = {"night_rate": _fr("night_rate", "1.0")}
        checks = validate_cross_fields(fields)
        rate_check = next(c for c in checks if c.name == "night_rate_range")
        assert rate_check.passed is True

    def test_normal_consumption_passes(self):
        fields = {"day_kwh": _fr("day_kwh", "242")}
        checks = validate_cross_fields(fields)
        kwh_check = next(c for c in checks if c.name == "day_kwh_range")
        assert kwh_check.passed is True

    def test_absurd_consumption_fails(self):
        """25,000 kWh in a billing period is implausible for residential."""
        fields = {"day_kwh": _fr("day_kwh", "25000")}
        checks = validate_cross_fields(fields)
        kwh_check = next(c for c in checks if c.name == "day_kwh_range")
        assert kwh_check.passed is False

    def test_zero_consumption_passes(self):
        """Zero consumption is valid (empty property)."""
        fields = {"day_kwh": _fr("day_kwh", "0")}
        checks = validate_cross_fields(fields)
        kwh_check = next(c for c in checks if c.name == "day_kwh_range")
        assert kwh_check.passed is True

    def test_cost_consistency_good(self):
        """rate * kwh ≈ cost should pass."""
        fields = {
            "day_rate": _fr("day_rate", "0.15"),
            "day_kwh": _fr("day_kwh", "1000"),
            "day_cost": _fr("day_cost", "150.00"),
        }
        checks = validate_cross_fields(fields)
        cost_check = next(c for c in checks if c.name == "day_cost_consistency")
        assert cost_check.passed is True

    def test_cost_consistency_bad(self):
        """rate * kwh wildly different from cost should fail."""
        fields = {
            "day_rate": _fr("day_rate", "234.56"),  # OCR error
            "day_kwh": _fr("day_kwh", "12"),         # OCR error
            "day_cost": _fr("day_cost", "1139.75"),
        }
        checks = validate_cross_fields(fields)
        cost_check = next(c for c in checks if c.name == "day_cost_consistency")
        assert cost_check.passed is False

    def test_standing_charge_normal_passes(self):
        fields = {"standing_charge": _fr("standing_charge", "28.88")}
        checks = validate_cross_fields(fields)
        sc_check = next(c for c in checks if c.name == "standing_charge_range")
        assert sc_check.passed is True

    def test_standing_charge_absurd_fails(self):
        fields = {"standing_charge": _fr("standing_charge", "5000.00")}
        checks = validate_cross_fields(fields)
        sc_check = next(c for c in checks if c.name == "standing_charge_range")
        assert sc_check.passed is False

    def test_scanned_bill_with_bad_values_lower_confidence(self):
        """Key scenario: scanned bill with OCR garbage should NOT score 'accept'."""
        fields = {
            "mprn": _fr("mprn", "10306802505"),
            "account_number": _fr("account_number", "8386744600"),
            "billing_period": _fr("billing_period", "01/11/2025 - 01/01/2026"),
            "day_kwh": _fr("day_kwh", "12"),          # OCR error (should be ~2912)
            "day_rate": _fr("day_rate", "234.56"),     # OCR error (should be ~0.234)
            "day_cost": _fr("day_cost", "1139.75"),
            "standing_charge": _fr("standing_charge", "28.88"),
            "subtotal": _fr("subtotal", "1483.66"),
            "vat_rate": _fr("vat_rate", "9"),
            "vat_amount": _fr("vat_amount", "133.53"),
            "total_incl_vat": _fr("total_incl_vat", "1617.19"),
        }
        result = calculate_confidence(fields, avg_ocr_confidence=92)
        # With the new range + consistency checks, this should NOT be "accept"
        assert result.band != "accept", (
            f"Scanned bill with garbage OCR values scored {result.score:.2f} "
            f"({result.band}) - should not be 'accept'"
        )

    def test_good_bill_still_accepts(self):
        """Ensure the new checks don't regress good bills."""
        fields = _good_electricity_fields()
        result = calculate_confidence(fields, provider="Energia")
        assert result.band == "accept", (
            f"Good bill scored {result.score:.2f} ({result.band})"
        )


class TestPostprocessRatesFields:
    """Tests for the public postprocess_rates_fields() function."""

    def test_rate_in_cents_gets_divided(self):
        fields = {"day_rate": _fr("day_rate", "15.148")}
        warnings = postprocess_rates_fields(fields)
        assert len(warnings) == 1
        assert "adjusted" in warnings[0]
        assert float(fields["day_rate"].value) == pytest.approx(0.1515, abs=0.001)

    def test_normal_rate_untouched(self):
        fields = {"day_rate": _fr("day_rate", "0.15148")}
        warnings = postprocess_rates_fields(fields)
        assert len(warnings) == 0
        assert fields["day_rate"].value == "0.15148"

    def test_multiple_rate_fields(self):
        fields = {
            "day_rate": _fr("day_rate", "23.456"),
            "night_rate": _fr("night_rate", "12.34"),
        }
        warnings = postprocess_rates_fields(fields)
        assert len(warnings) == 2


# ===================================================================
# Confidence scoring
# ===================================================================

class TestCalculateConfidence:
    def test_good_extraction_accept(self):
        """Known-good fields should score in 'accept' band."""
        fields = _good_electricity_fields()
        result = calculate_confidence(fields, provider="Energia")
        assert result.band == "accept"
        assert result.score >= 0.85

    def test_bad_extraction_low_score(self):
        """Known-bad fields should score lower."""
        fields = _bad_fields()
        result = calculate_confidence(fields, provider="Energia")
        assert result.score < 0.85
        assert result.band in ("accept_with_review", "escalate")

    def test_empty_fields_escalate(self):
        """No extracted fields should escalate."""
        result = calculate_confidence({}, provider="Energia")
        assert result.band == "escalate"
        assert result.score < 0.60

    def test_field_coverage_calculation(self):
        fields = _good_electricity_fields()
        result = calculate_confidence(fields, provider="Energia")
        expected_profile = FIELD_PROFILES["electricity"]
        expected_coverage = len(set(fields.keys()) & expected_profile) / len(expected_profile)
        assert abs(result.field_coverage - expected_coverage) < 0.01

    def test_validation_pass_rate(self):
        fields = _good_electricity_fields()
        result = calculate_confidence(fields, provider="Energia")
        assert result.validation_pass_rate > 0.8

    def test_ocr_confidence_affects_score(self):
        fields = _good_electricity_fields()
        # High OCR confidence
        result_high = calculate_confidence(fields, provider="Energia", avg_ocr_confidence=95)
        # Low OCR confidence
        result_low = calculate_confidence(fields, provider="Energia", avg_ocr_confidence=30)
        assert result_high.score > result_low.score

    def test_fuel_bill_type(self):
        fields = {
            "invoice_number": _fr("invoice_number", "039061"),
            "invoice_date": _fr("invoice_date", "06/02/24"),
            "litres": _fr("litres", "849"),
            "unit_price": _fr("unit_price", "106.21"),
            "subtotal": _fr("subtotal", "901.72"),
            "vat_rate": _fr("vat_rate", "13.5"),
            "vat_amount": _fr("vat_amount", "121.73"),
            "total_incl_vat": _fr("total_incl_vat", "1023.45"),
        }
        result = calculate_confidence(fields, provider="Kerry Petroleum")
        assert result.band in ("accept", "accept_with_review")
        assert result.fields_found >= 6

    def test_explicit_bill_type_overrides_provider(self):
        fields = {"mprn": _fr("mprn", "10306802505")}
        result = calculate_confidence(fields, provider="Kerry Petroleum", bill_type="electricity")
        expected = FIELD_PROFILES["electricity"]
        assert result.expected_fields == len(expected)

    # -- Threshold boundary tests --

    def test_score_at_085_boundary(self):
        """Score exactly at 0.85 should be 'accept'."""
        # Construct fields that give exactly 0.85
        # We need field_coverage * 0.4 + validation_pass_rate * 0.4 + ocr * 0.2 = 0.85
        # With full coverage (1.0) and full validation (1.0):
        # 1.0 * 0.4 + 1.0 * 0.4 + ocr * 0.2 = 0.85 → ocr = 0.25
        fields = _good_electricity_fields()
        result = calculate_confidence(fields, provider="Energia", avg_ocr_confidence=25)
        # This should be close to 0.85
        if result.score >= 0.85:
            assert result.band == "accept"
        else:
            assert result.band == "accept_with_review"

    def test_score_at_060_boundary(self):
        """Score just below 0.60 should be 'escalate'."""
        # Minimal fields, no validation passes
        fields = {"mprn": _fr("mprn", "12345")}  # Invalid MPRN
        result = calculate_confidence(fields, provider="Energia", avg_ocr_confidence=10)
        assert result.score < 0.60
        assert result.band == "escalate"

    # -- Field profile tests --

    def test_all_bill_types_have_profiles(self):
        for bill_type in FIELD_PROFILES:
            assert len(FIELD_PROFILES[bill_type]) > 0

    def test_all_known_providers_have_bill_type(self):
        for provider in ["Energia", "Go Power", "ESB Networks", "Kerry Petroleum"]:
            assert provider in PROVIDER_BILL_TYPE


# ===================================================================
# Integration: Tier 3 extraction → confidence scoring
# ===================================================================

class TestConfidenceIntegration:
    """End-to-end: extract from real PDF, then score confidence."""

    @pytest.mark.parametrize("pdf_name,provider", [
        ("1845.pdf", "Go Power"),
        ("2024 Mar - Apr.pdf", "ESB Networks"),
        ("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf", "Energia"),
    ])
    def test_real_pdf_confidence(self, pdf_name, provider):
        path = os.path.join(BILLS_DIR, pdf_name)
        if not os.path.exists(path):
            pytest.skip(f"PDF not found: {pdf_name}")

        tier0 = extract_text_tier0(path)
        tier3 = extract_with_config(tier0.extracted_text, provider)
        confidence = calculate_confidence(tier3.fields, provider=provider)

        print(f"\n{provider} ({pdf_name}):")
        print(f"  Score: {confidence.score:.2f}, Band: {confidence.band}")
        print(f"  Fields: {confidence.fields_found}/{confidence.expected_fields}")
        print(f"  Validation: {confidence.validation_pass_rate:.0%}")
        for check in confidence.validation_checks:
            status = "PASS" if check.passed else "FAIL"
            print(f"    [{status}] {check.name}: {check.message}")

        # All real PDFs should at least be "accept_with_review"
        assert confidence.band in ("accept", "accept_with_review"), \
            f"{provider} scored {confidence.score:.2f} ({confidence.band})"
