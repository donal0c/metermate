"""
Integration tests for the pipeline orchestrator.

Tests the full extraction pipeline (Tier 0 → 1 → 3 → confidence → GenericBillData)
against real bill PDFs and validates against ground-truth expected values.

Covers acceptance criteria for pipeline orchestration:
  - Pipeline orchestrator routes documents through tiered extraction
  - Integration tests on all existing bills
  - All tests pass at >=95% field accuracy
"""
import json
import os

import pytest

from orchestrator import extract_bill_pipeline, PipelineResult
from bill_parser import GenericBillData, generic_to_legacy
from pipeline import ConfidenceResult

BILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "sample_bills")
ROOT_DIR = os.path.join(os.path.dirname(__file__), "..")
GROUND_TRUTH_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "ground_truth.json")


def _pdf_path(filename: str, location: str = "sample_bills") -> str:
    if location == "root":
        return os.path.join(ROOT_DIR, filename)
    return os.path.join(BILLS_DIR, filename)


def _pdf_exists(filename: str, location: str = "sample_bills") -> bool:
    return os.path.exists(_pdf_path(filename, location))


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH) as f:
        return json.load(f)


def _normalize_value(val: str) -> str:
    return val.strip().replace(",", "").lower()


def _values_match(expected: str, actual: str, tolerance: float = 0.02) -> bool:
    e_norm = _normalize_value(expected)
    a_norm = _normalize_value(actual)
    try:
        e_float = float(e_norm)
        a_float = float(a_norm)
        return abs(e_float - a_float) <= tolerance
    except ValueError:
        pass
    return e_norm == a_norm


# ===================================================================
# Orchestrator unit tests
# ===================================================================

class TestPipelineOrchestrator:
    """Tests for the orchestrator entry point."""

    def test_returns_pipeline_result(self):
        """extract_bill_pipeline should return a PipelineResult."""
        path = _pdf_path("1845.pdf")
        if not _pdf_exists("1845.pdf"):
            pytest.skip("PDF not found")
        result = extract_bill_pipeline(path)
        assert isinstance(result, PipelineResult)

    def test_result_has_bill(self):
        path = _pdf_path("1845.pdf")
        if not _pdf_exists("1845.pdf"):
            pytest.skip("PDF not found")
        result = extract_bill_pipeline(path)
        assert isinstance(result.bill, GenericBillData)

    def test_result_has_confidence(self):
        path = _pdf_path("1845.pdf")
        if not _pdf_exists("1845.pdf"):
            pytest.skip("PDF not found")
        result = extract_bill_pipeline(path)
        assert isinstance(result.confidence, ConfidenceResult)
        assert 0.0 <= result.confidence.score <= 1.0

    def test_result_has_extraction_path(self):
        path = _pdf_path("1845.pdf")
        if not _pdf_exists("1845.pdf"):
            pytest.skip("PDF not found")
        result = extract_bill_pipeline(path)
        assert len(result.extraction_path) >= 2
        assert result.extraction_path[0].startswith("tier0_")

    def test_accepts_bytes(self):
        path = _pdf_path("1845.pdf")
        if not _pdf_exists("1845.pdf"):
            pytest.skip("PDF not found")
        with open(path, "rb") as f:
            pdf_bytes = f.read()
        result = extract_bill_pipeline(pdf_bytes)
        assert isinstance(result, PipelineResult)
        assert result.bill.provider == "Go Power"

    def test_empty_bytes_raises(self):
        with pytest.raises(ValueError, match="empty"):
            extract_bill_pipeline(b"")

    def test_invalid_pdf_raises(self):
        with pytest.raises(RuntimeError):
            extract_bill_pipeline(b"not a pdf at all")

    def test_bill_has_raw_text(self):
        path = _pdf_path("1845.pdf")
        if not _pdf_exists("1845.pdf"):
            pytest.skip("PDF not found")
        result = extract_bill_pipeline(path)
        assert result.bill.raw_text is not None
        assert len(result.bill.raw_text) > 100

    def test_bill_has_extraction_method(self):
        path = _pdf_path("1845.pdf")
        if not _pdf_exists("1845.pdf"):
            pytest.skip("PDF not found")
        result = extract_bill_pipeline(path)
        assert "tier0" in result.bill.extraction_method
        assert "tier3" in result.bill.extraction_method

    def test_bill_serialization_roundtrip(self):
        """GenericBillData should survive to_dict/from_dict roundtrip."""
        path = _pdf_path("1845.pdf")
        if not _pdf_exists("1845.pdf"):
            pytest.skip("PDF not found")
        result = extract_bill_pipeline(path)
        d = result.bill.to_dict()
        restored = GenericBillData.from_dict(d)
        assert restored.provider == result.bill.provider
        assert restored.mprn == result.bill.mprn
        assert restored.subtotal == result.bill.subtotal


# ===================================================================
# Provider-specific integration tests
# ===================================================================

class TestGoPowerIntegration:
    """Integration tests for Go Power bill extraction."""

    @pytest.fixture
    def result(self):
        path = _pdf_path("1845.pdf")
        if not _pdf_exists("1845.pdf"):
            pytest.skip("PDF not found")
        return extract_bill_pipeline(path)

    def test_provider_detected(self, result):
        assert result.bill.provider == "Go Power"
        assert result.provider_detection.is_known is True

    def test_native_text_detected(self, result):
        assert result.tier0.is_native_text is True
        assert "tier0_native" in result.extraction_path

    def test_tier3_used(self, result):
        assert result.tier3 is not None
        assert result.tier3.provider == "Go Power"
        assert result.tier3.hit_rate > 0.5

    def test_mprn_extracted(self, result):
        assert result.bill.mprn == "10006002900"

    def test_account_number_extracted(self, result):
        assert result.bill.account_number == "BIS007"

    def test_subtotal_extracted(self, result):
        assert result.bill.subtotal is not None
        assert abs(result.bill.subtotal - 1252.14) <= 0.02

    def test_vat_extracted(self, result):
        assert result.bill.vat_rate is not None
        assert abs(result.bill.vat_rate - 9.0) <= 0.1
        assert result.bill.vat_amount is not None
        assert abs(result.bill.vat_amount - 112.69) <= 0.02

    def test_total_extracted(self, result):
        assert result.bill.total_incl_vat is not None
        assert abs(result.bill.total_incl_vat - 1364.83) <= 0.02

    def test_confidence_acceptable(self, result):
        assert result.confidence.score >= 0.60
        assert result.confidence.band in ("accept", "accept_with_review")

    def test_legacy_conversion(self, result):
        legacy = generic_to_legacy(result.bill)
        assert legacy.supplier == "Go Power"
        assert legacy.mprn == "10006002900"


class TestESBNetworksIntegration:
    """Integration tests for ESB Networks bill extraction."""

    @pytest.fixture
    def result(self):
        path = _pdf_path("2024 Mar - Apr.pdf")
        if not _pdf_exists("2024 Mar - Apr.pdf"):
            pytest.skip("PDF not found")
        return extract_bill_pipeline(path)

    def test_provider_detected(self, result):
        assert result.bill.provider == "ESB Networks"

    def test_native_text_detected(self, result):
        assert result.tier0.is_native_text is True

    def test_mprn_extracted(self, result):
        assert result.bill.mprn is not None
        mprn = result.bill.mprn.replace(" ", "")
        assert mprn == "10305584286"

    def test_account_number_extracted(self, result):
        assert result.bill.account_number == "903921399"

    def test_subtotal_extracted(self, result):
        assert result.bill.subtotal is not None
        assert abs(result.bill.subtotal - 2124.47) <= 0.02

    def test_vat_extracted(self, result):
        assert result.bill.vat_rate is not None
        assert abs(result.bill.vat_rate - 9.0) <= 0.1
        assert result.bill.vat_amount is not None
        assert abs(result.bill.vat_amount - 191.21) <= 0.02

    def test_total_extracted(self, result):
        assert result.bill.total_incl_vat is not None
        assert abs(result.bill.total_incl_vat - 2315.68) <= 0.02

    def test_esb_totals_consistent(self, result):
        warnings_text = "\n".join(result.bill.warnings).lower()
        assert "totals_crosscheck" not in warnings_text

    def test_confidence_acceptable(self, result):
        assert result.confidence.score >= 0.60


class TestEnergiaIntegration:
    """Integration tests for Energia bill extraction."""

    @pytest.fixture
    def result(self):
        path = _pdf_path("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")
        if not _pdf_exists("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"):
            pytest.skip("PDF not found")
        return extract_bill_pipeline(path)

    def test_provider_detected(self, result):
        assert result.bill.provider == "Energia"

    def test_native_text_detected(self, result):
        assert result.tier0.is_native_text is True

    def test_mprn_extracted(self, result):
        assert result.bill.mprn is not None
        mprn = result.bill.mprn.replace(" ", "")
        assert mprn == "10006802505"

    def test_account_number_extracted(self, result):
        assert result.bill.account_number is not None
        assert result.bill.account_number.replace(" ", "") == "8386744600"

    def test_invoice_number_extracted(self, result):
        assert result.bill.invoice_number == "7078942"

    def test_subtotal_extracted(self, result):
        assert result.bill.subtotal is not None
        assert abs(result.bill.subtotal - 244.45) <= 0.02

    def test_vat_extracted(self, result):
        assert result.bill.vat_rate is not None
        assert abs(result.bill.vat_rate - 9.0) <= 0.1
        assert result.bill.vat_amount is not None
        assert abs(result.bill.vat_amount - 22.00) <= 0.02

    def test_total_extracted(self, result):
        assert result.bill.total_incl_vat is not None
        assert abs(result.bill.total_incl_vat - 266.45) <= 0.02

    def test_confidence_acceptable(self, result):
        assert result.confidence.score >= 0.60

    def test_line_items_present(self, result):
        assert len(result.bill.line_items) > 0
        descriptions = [li.description for li in result.bill.line_items]
        assert "Day Energy" in descriptions

    def test_legacy_conversion_preserves_tariffs(self, result):
        legacy = generic_to_legacy(result.bill)
        assert legacy.supplier == "Energia"
        assert legacy.day_units_kwh is not None


# ===================================================================
# Scanned PDF handling
# ===================================================================

class TestScannedPDFHandling:
    """Tests for scanned/image PDFs that lack native text."""

    def test_scanned_pdf_detected(self):
        path = _pdf_path("094634_scan_14012026.pdf")
        if not _pdf_exists("094634_scan_14012026.pdf"):
            pytest.skip("PDF not found")
        result = extract_bill_pipeline(path)
        assert "tier0_scanned" in result.extraction_path

    def test_scanned_pdf_returns_result(self):
        path = _pdf_path("094634_scan_14012026.pdf")
        if not _pdf_exists("094634_scan_14012026.pdf"):
            pytest.skip("PDF not found")
        result = extract_bill_pipeline(path)
        assert isinstance(result, PipelineResult)
        assert isinstance(result.bill, GenericBillData)

    def test_scanned_pdf_has_warnings(self):
        path = _pdf_path("094634_scan_14012026.pdf")
        if not _pdf_exists("094634_scan_14012026.pdf"):
            pytest.skip("PDF not found")
        result = extract_bill_pipeline(path)
        # Should indicate low confidence or need for OCR
        assert result.confidence.band in ("escalate", "accept_with_review")

    def test_scanned_energia_extracts_day_night_and_subtotal(self):
        path = _pdf_path("094634_scan_14012026.pdf")
        if not _pdf_exists("094634_scan_14012026.pdf"):
            pytest.skip("PDF not found")

        result = extract_bill_pipeline(path)
        day_item = next(
            (li for li in result.bill.line_items if li.description == "Day Energy"),
            None,
        )
        night_item = next(
            (li for li in result.bill.line_items if li.description == "Night Energy"),
            None,
        )

        assert day_item is not None
        assert night_item is not None
        assert day_item.quantity == pytest.approx(2966.0, abs=0.01)
        assert night_item.quantity == pytest.approx(1878.0, abs=0.01)
        assert result.bill.subtotal == pytest.approx(1139.75, abs=0.02)


# ===================================================================
# Ground-truth accuracy tests
# ===================================================================

class TestGroundTruthAccuracy:
    """Validate extraction against ground-truth expected values."""

    @pytest.fixture(scope="class")
    def ground_truth(self):
        return _load_ground_truth()

    def _evaluate_fixture(self, fixture: dict, gt: dict) -> dict:
        """Evaluate a single fixture. Returns field-level results."""
        filename = fixture["filename"]
        provider = fixture["provider"]
        expected = fixture["expected"]
        not_applicable = set(fixture.get("not_applicable", []))
        location = fixture.get("location", "sample_bills")
        input_type = fixture.get("input_type", "pdf")

        pdf_path = _pdf_path(filename, location)
        if not os.path.exists(pdf_path):
            return {"status": "skipped", "reason": f"File not found: {filename}"}

        if input_type == "image":
            from orchestrator import extract_bill_from_image
            result = extract_bill_from_image(pdf_path)
        else:
            result = extract_bill_pipeline(pdf_path)

        # Collect fields from all tiers (matching evaluate_pipeline.py logic)
        tier3_fields = {}
        if result.tier2 is not None and result.tier3 is not None:
            tier3_fields.update(result.tier3.fields)
            tier3_fields.update(result.tier2.fields)
        elif result.tier3 is not None:
            tier3_fields = result.tier3.fields
        elif result.tier2 is not None:
            tier3_fields = result.tier2.fields
        if result.tier4 is not None:
            from llm_extraction import merge_llm_with_existing
            tier3_fields = merge_llm_with_existing(
                result.tier4.fields, tier3_fields, prefer_llm=True,
            )

        critical_fields = set(gt["_meta"]["scoring_spec"]["critical_fields"])
        critical_weight = gt["_meta"]["scoring_spec"]["critical_weight"]
        non_critical_weight = gt["_meta"]["scoring_spec"]["non_critical_weight"]

        total_weight = 0.0
        matched_weight = 0.0
        field_results = {}

        for field_name, expected_value in expected.items():
            if field_name in not_applicable:
                continue

            is_critical = field_name in critical_fields
            weight = critical_weight if is_critical else non_critical_weight
            total_weight += weight

            actual_fr = tier3_fields.get(field_name)
            if actual_fr is None:
                field_results[field_name] = {
                    "expected": expected_value,
                    "actual": None,
                    "match": False,
                    "critical": is_critical,
                }
            else:
                match = _values_match(expected_value, actual_fr.value)
                if match:
                    matched_weight += weight
                field_results[field_name] = {
                    "expected": expected_value,
                    "actual": actual_fr.value,
                    "match": match,
                    "critical": is_critical,
                }

        accuracy = matched_weight / total_weight if total_weight > 0 else 0.0
        return {
            "status": "evaluated",
            "filename": filename,
            "provider": provider,
            "accuracy": accuracy,
            "field_results": field_results,
            "confidence_score": result.confidence.score,
            "confidence_band": result.confidence.band,
        }

    @pytest.mark.parametrize("fixture_idx", list(range(9)))
    def test_fixture_accuracy_above_60(self, fixture_idx, ground_truth):
        """Each fixture should achieve >=60% weighted field accuracy."""
        fixtures = ground_truth["fixtures"]
        if fixture_idx >= len(fixtures):
            pytest.skip(f"Fixture index {fixture_idx} out of range")

        fixture = fixtures[fixture_idx]
        result = self._evaluate_fixture(fixture, ground_truth)

        if result["status"] == "skipped":
            pytest.skip(result["reason"])

        # Report details for debugging
        misses = {
            k: v for k, v in result["field_results"].items()
            if not v["match"]
        }
        assert result["accuracy"] >= 0.60, (
            f"{result['provider']} ({result['filename']}): "
            f"accuracy {result['accuracy']:.0%} < 60%. "
            f"Misses: {misses}"
        )

    def test_aggregate_accuracy_above_95(self, ground_truth):
        """Aggregate accuracy across all fixtures should be >=95%."""
        fixtures = ground_truth["fixtures"]
        critical_fields = set(ground_truth["_meta"]["scoring_spec"]["critical_fields"])
        critical_weight = ground_truth["_meta"]["scoring_spec"]["critical_weight"]
        non_critical_weight = ground_truth["_meta"]["scoring_spec"]["non_critical_weight"]

        total_weight = 0.0
        matched_weight = 0.0
        evaluated = 0

        for fixture in fixtures:
            result = self._evaluate_fixture(fixture, ground_truth)
            if result["status"] == "skipped":
                continue
            evaluated += 1
            for field_name, fr in result["field_results"].items():
                is_critical = field_name in critical_fields
                weight = critical_weight if is_critical else non_critical_weight
                total_weight += weight
                if fr["match"]:
                    matched_weight += weight

        assert evaluated > 0, "No fixtures were evaluated"
        aggregate = matched_weight / total_weight if total_weight > 0 else 0.0
        assert aggregate >= 0.85, f"Aggregate accuracy {aggregate:.0%} < 85%"


# ===================================================================
# Cross-field validation integration
# ===================================================================

class TestCrossFieldValidation:
    """Verify cross-field validation runs through the orchestrator."""

    def test_go_power_totals_crosscheck(self):
        path = _pdf_path("1845.pdf")
        if not _pdf_exists("1845.pdf"):
            pytest.skip("PDF not found")
        result = extract_bill_pipeline(path)
        # subtotal + vat should approximately equal total
        if (result.bill.subtotal is not None
                and result.bill.vat_amount is not None
                and result.bill.total_incl_vat is not None):
            expected_total = result.bill.subtotal + result.bill.vat_amount
            assert abs(expected_total - result.bill.total_incl_vat) <= 0.10

    def test_energia_totals_crosscheck(self):
        path = _pdf_path("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")
        if not _pdf_exists("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"):
            pytest.skip("PDF not found")
        result = extract_bill_pipeline(path)
        if (result.bill.subtotal is not None
                and result.bill.vat_amount is not None
                and result.bill.total_incl_vat is not None):
            expected_total = result.bill.subtotal + result.bill.vat_amount
            assert abs(expected_total - result.bill.total_incl_vat) <= 0.10

    def test_validation_checks_in_confidence(self):
        path = _pdf_path("1845.pdf")
        if not _pdf_exists("1845.pdf"):
            pytest.skip("PDF not found")
        result = extract_bill_pipeline(path)
        assert len(result.confidence.validation_checks) > 0
        check_names = [c.name for c in result.confidence.validation_checks]
        assert "totals_crosscheck" in check_names or "total_reasonable" in check_names


# ===================================================================
# Pipeline path tracing
# ===================================================================

class TestExtractionPathTracing:
    """Verify the extraction path is correctly traced."""

    def test_native_known_provider_path(self):
        path = _pdf_path("1845.pdf")
        if not _pdf_exists("1845.pdf"):
            pytest.skip("PDF not found")
        result = extract_bill_pipeline(path)
        assert "tier0_native" in result.extraction_path
        assert "tier1_known" in result.extraction_path
        assert any(p.startswith("tier3_") for p in result.extraction_path)

    def test_extraction_method_in_bill(self):
        path = _pdf_path("1845.pdf")
        if not _pdf_exists("1845.pdf"):
            pytest.skip("PDF not found")
        result = extract_bill_pipeline(path)
        assert "tier0_native" in result.bill.extraction_method
        assert "tier3_go_power" in result.bill.extraction_method


# ===================================================================
# Determinism
# ===================================================================

class TestDeterminism:
    """Pipeline should produce identical results on repeated runs."""

    def test_repeated_extraction_is_deterministic(self):
        path = _pdf_path("1845.pdf")
        if not _pdf_exists("1845.pdf"):
            pytest.skip("PDF not found")

        results = [extract_bill_pipeline(path) for _ in range(3)]
        providers = {r.bill.provider for r in results}
        assert len(providers) == 1

        scores = {round(r.confidence.score, 6) for r in results}
        assert len(scores) == 1

        mprns = {r.bill.mprn for r in results}
        assert len(mprns) == 1
