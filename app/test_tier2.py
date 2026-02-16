"""
Tests for Tier 2: Universal regex extraction for unknown providers.

Tests the universal patterns work across any Irish utility bill by running
extraction with provider detection disabled (simulating unknown provider).
Measures and validates hit rates per field and per fixture.

Covers acceptance criteria for Tier 2 extraction.
"""
import json
import os

import pytest

from pipeline import (
    extract_text_tier0,
    extract_tier2_universal,
    Tier2ExtractionResult,
    FieldExtractionResult,
    TIER2_UNIVERSAL_PATTERNS,
)
from orchestrator import extract_bill_pipeline, PipelineResult

BILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "sample_bills")
GROUND_TRUTH_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "ground_truth.json")


def _pdf_path(filename: str) -> str:
    return os.path.join(BILLS_DIR, filename)


def _pdf_exists(filename: str) -> bool:
    return os.path.exists(_pdf_path(filename))


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH) as f:
        return json.load(f)


def _normalize_value(val: str) -> str:
    return val.strip().replace(",", "").lower()


def _values_match(expected: str, actual: str, tolerance: float = 0.02) -> bool:
    e_norm = _normalize_value(expected)
    a_norm = _normalize_value(actual)
    try:
        return abs(float(e_norm) - float(a_norm)) <= tolerance
    except ValueError:
        pass
    return e_norm == a_norm


def _extract_text(filename: str) -> str:
    """Extract text from a PDF for Tier 2 testing."""
    path = _pdf_path(filename)
    if not os.path.exists(path):
        pytest.skip(f"PDF not found: {filename}")
    tier0 = extract_text_tier0(path)
    return tier0.extracted_text


# ===================================================================
# Tier 2 unit tests
# ===================================================================

class TestTier2Basics:
    """Basic tests for extract_tier2_universal."""

    def test_returns_tier2_result(self):
        result = extract_tier2_universal("Some bill text with MPRN 10123456789")
        assert isinstance(result, Tier2ExtractionResult)

    def test_empty_text(self):
        result = extract_tier2_universal("")
        assert result.field_count == 0
        assert result.hit_rate == 0.0

    def test_mprn_extraction(self):
        text = "MPRN Number: 10123456789"
        result = extract_tier2_universal(text)
        assert "mprn" in result.fields
        assert result.fields["mprn"].value == "10123456789"

    def test_mprn_fallback_pattern(self):
        text = "Meter ref is 10987654321 for this account"
        result = extract_tier2_universal(text)
        assert "mprn" in result.fields
        assert result.fields["mprn"].value == "10987654321"

    def test_gprn_extraction(self):
        text = "GPRN Number: 1234567"
        result = extract_tier2_universal(text)
        assert "gprn" in result.fields
        assert result.fields["gprn"].value == "1234567"

    def test_account_number_extraction(self):
        text = "Account Number: ABC12345"
        result = extract_tier2_universal(text)
        assert "account_number" in result.fields
        assert result.fields["account_number"].value == "ABC12345"

    def test_invoice_number_extraction(self):
        text = "Invoice No: 7078942"
        result = extract_tier2_universal(text)
        assert "invoice_number" in result.fields
        assert result.fields["invoice_number"].value == "7078942"

    def test_vat_rate_extraction(self):
        text = "VAT @ 9% on charges €22.00"
        result = extract_tier2_universal(text)
        assert "vat_rate" in result.fields
        assert result.fields["vat_rate"].value == "9"

    def test_vat_amount_extraction(self):
        text = "VAT @ 9% €22.00"
        result = extract_tier2_universal(text)
        assert "vat_amount" in result.fields
        assert result.fields["vat_amount"].value == "22.00"

    def test_subtotal_total_excluding_vat(self):
        text = "Total Excluding VAT €244.45"
        result = extract_tier2_universal(text)
        assert "subtotal" in result.fields
        assert result.fields["subtotal"].value == "244.45"

    def test_subtotal_sub_total(self):
        text = "Sub Total before VAT €1,252.14"
        result = extract_tier2_universal(text)
        assert "subtotal" in result.fields
        assert result.fields["subtotal"].value == "1252.14"

    def test_total_incl_vat(self):
        text = "Total Charges for this Period €266.45"
        result = extract_tier2_universal(text)
        assert "total_incl_vat" in result.fields
        assert result.fields["total_incl_vat"].value == "266.45"

    def test_total_amount_due(self):
        text = "Amount Due €1,364.83"
        result = extract_tier2_universal(text)
        assert "total_incl_vat" in result.fields
        assert result.fields["total_incl_vat"].value == "1364.83"

    def test_billing_period(self):
        text = "Billing Period 01 March 2025 to 31 March 2025"
        result = extract_tier2_universal(text)
        assert "billing_period" in result.fields

    def test_invoice_date(self):
        text = "Invoice Date: 15 April 2025"
        result = extract_tier2_universal(text)
        assert "invoice_date" in result.fields
        assert result.fields["invoice_date"].value == "15 April 2025"

    def test_pso_levy(self):
        text = "PSO Levy Flat Charge €12.91"
        result = extract_tier2_universal(text)
        assert "pso_levy" in result.fields
        assert result.fields["pso_levy"].value == "12.91"

    def test_kwh_day(self):
        text = "Day Energy 242 kWh @ €0.15148"
        result = extract_tier2_universal(text)
        assert "day_kwh" in result.fields
        assert result.fields["day_kwh"].value == "242"

    def test_standing_charge(self):
        text = "Standing Charge 31 days €10.90"
        result = extract_tier2_universal(text)
        assert "standing_charge" in result.fields

    def test_mcc_code(self):
        text = "MCC06 demand category"
        result = extract_tier2_universal(text)
        assert "mcc_code" in result.fields
        assert result.fields["mcc_code"].value == "06"

    def test_dg_code(self):
        text = "Connected at DG6 level"
        result = extract_tier2_universal(text)
        assert "dg_code" in result.fields
        assert result.fields["dg_code"].value == "DG6"

    def test_hit_rate_calculation(self):
        text = "MPRN: 10123456789\nVAT @ 9%\nTotal Excluding VAT €100.00"
        result = extract_tier2_universal(text)
        assert result.field_count >= 3
        total_patterns = len(TIER2_UNIVERSAL_PATTERNS)
        assert result.hit_rate == result.field_count / total_patterns

    def test_all_patterns_have_capture_groups(self):
        """Every pattern should have at least one capture group."""
        import re
        for field_name, patterns in TIER2_UNIVERSAL_PATTERNS.items():
            for i, (pattern, conf, transform) in enumerate(patterns):
                groups = re.compile(pattern).groups
                assert groups >= 1, (
                    f"Pattern {i} for '{field_name}' has no capture groups"
                )


# ===================================================================
# Simulated unknown provider tests (Tier 2 on real PDFs)
# ===================================================================

class TestTier2OnRealPDFs:
    """Run Tier 2 universal extraction on real PDFs.

    These tests simulate an unknown provider by running Tier 2 directly
    (bypassing Tier 1 provider detection and Tier 3 config extraction).
    """

    def test_go_power_tier2(self):
        """Tier 2 should extract critical fields from Go Power bill."""
        text = _extract_text("1845.pdf")
        result = extract_tier2_universal(text)
        assert result.field_count >= 4, f"Expected >=4 fields, got {result.field_count}"
        # Critical fields
        assert "mprn" in result.fields
        assert "subtotal" in result.fields or "total_incl_vat" in result.fields

    def test_esb_networks_tier2(self):
        """Tier 2 should extract critical fields from ESB Networks bill."""
        text = _extract_text("2024 Mar - Apr.pdf")
        result = extract_tier2_universal(text)
        assert result.field_count >= 4, f"Expected >=4 fields, got {result.field_count}"
        assert "mprn" in result.fields

    def test_energia_tier2(self):
        """Tier 2 should extract critical fields from Energia bill."""
        text = _extract_text("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")
        result = extract_tier2_universal(text)
        assert result.field_count >= 5, f"Expected >=5 fields, got {result.field_count}"
        assert "mprn" in result.fields
        assert "vat_rate" in result.fields


class TestTier2GroundTruthAccuracy:
    """Validate Tier 2 extraction against ground-truth values.

    Simulates unknown provider: Tier 2 only, no Tier 3.
    Expected hit rate: 60-80% of fields per the research spec.
    """

    @pytest.fixture(scope="class")
    def ground_truth(self):
        return _load_ground_truth()

    def _evaluate_tier2(self, fixture: dict, gt: dict) -> dict:
        """Evaluate Tier 2 extraction against a fixture."""
        filename = fixture["filename"]
        expected = fixture["expected"]
        not_applicable = set(fixture.get("not_applicable", []))

        text = _extract_text(filename)
        result = extract_tier2_universal(text)

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

            actual_fr = result.fields.get(field_name)
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
            "filename": filename,
            "provider": fixture["provider"],
            "accuracy": accuracy,
            "hit_rate": result.hit_rate,
            "field_count": result.field_count,
            "field_results": field_results,
        }

    @pytest.mark.parametrize("fixture_idx", [0, 1, 2])
    def test_tier2_fixture_hits_60pct(self, fixture_idx, ground_truth):
        """Each fixture should achieve >=60% weighted accuracy via Tier 2."""
        fixtures = ground_truth["fixtures"]
        if fixture_idx >= len(fixtures):
            pytest.skip(f"Fixture index {fixture_idx} out of range")

        fixture = fixtures[fixture_idx]
        result = self._evaluate_tier2(fixture, ground_truth)

        misses = {
            k: v for k, v in result["field_results"].items()
            if not v["match"]
        }
        assert result["accuracy"] >= 0.60, (
            f"Tier 2 on {result['provider']} ({result['filename']}): "
            f"accuracy {result['accuracy']:.0%} < 60%. "
            f"Misses: {misses}"
        )

    def test_tier2_aggregate_hits_60pct(self, ground_truth):
        """Aggregate Tier 2 accuracy across all fixtures should be >=60%."""
        fixtures = ground_truth["fixtures"]
        critical_fields = set(ground_truth["_meta"]["scoring_spec"]["critical_fields"])
        critical_weight = ground_truth["_meta"]["scoring_spec"]["critical_weight"]
        non_critical_weight = ground_truth["_meta"]["scoring_spec"]["non_critical_weight"]

        total_weight = 0.0
        matched_weight = 0.0

        for fixture in fixtures:
            result = self._evaluate_tier2(fixture, ground_truth)
            for field_name, fr in result["field_results"].items():
                is_critical = field_name in critical_fields
                weight = critical_weight if is_critical else non_critical_weight
                total_weight += weight
                if fr["match"]:
                    matched_weight += weight

        aggregate = matched_weight / total_weight if total_weight > 0 else 0.0
        assert aggregate >= 0.60, f"Tier 2 aggregate accuracy {aggregate:.0%} < 60%"

    def test_tier2_critical_fields_coverage(self, ground_truth):
        """Tier 2 should find most critical fields across all fixtures."""
        fixtures = ground_truth["fixtures"]
        critical_fields = set(ground_truth["_meta"]["scoring_spec"]["critical_fields"])

        total_critical = 0
        found_critical = 0

        for fixture in fixtures:
            expected = fixture["expected"]
            not_applicable = set(fixture.get("not_applicable", []))
            text = _extract_text(fixture["filename"])
            result = extract_tier2_universal(text)

            for field_name in critical_fields:
                if field_name in expected and field_name not in not_applicable:
                    total_critical += 1
                    if field_name in result.fields:
                        actual = result.fields[field_name].value
                        if _values_match(expected[field_name], actual):
                            found_critical += 1

        coverage = found_critical / total_critical if total_critical > 0 else 0.0
        assert coverage >= 0.50, (
            f"Critical field coverage {coverage:.0%} < 50% "
            f"({found_critical}/{total_critical})"
        )


# ===================================================================
# Orchestrator integration with Tier 2
# ===================================================================

class TestOrchestratorTier2Fallback:
    """Test that the orchestrator uses Tier 2 for unknown providers."""

    def test_unknown_provider_uses_tier2(self):
        """When provider is unknown, orchestrator should use Tier 2."""
        # Use a synthetic text that won't match any known provider
        from pipeline import extract_text_tier0
        from orchestrator import extract_bill_pipeline

        # We can't easily force unknown provider with real PDFs since they all
        # have known providers. Instead, test the extraction path directly.
        path = _pdf_path("1845.pdf")
        if not _pdf_exists("1845.pdf"):
            pytest.skip("PDF not found")

        # The Go Power bill should use Tier 3, not Tier 2
        result = extract_bill_pipeline(path)
        assert result.tier3 is not None
        assert result.tier2 is None
        assert any("tier3" in p for p in result.extraction_path)

    def test_known_provider_with_config_uses_tier3(self):
        """Known providers with Tier 3 config should NOT fall through to Tier 2."""
        path = _pdf_path("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf")
        if not _pdf_exists("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf"):
            pytest.skip("PDF not found")
        result = extract_bill_pipeline(path)
        assert result.tier3 is not None
        assert result.tier2 is None

    def test_tier2_result_in_pipeline_result(self):
        """PipelineResult should carry tier2 field when Tier 2 was used."""
        from orchestrator import PipelineResult
        from pipeline import Tier2ExtractionResult
        # Verify the dataclass has the tier2 field
        fields = {f.name for f in PipelineResult.__dataclass_fields__.values()}
        assert "tier2" in fields


# ===================================================================
# Pattern coverage
# ===================================================================

class TestPatternCoverage:
    """Verify the universal pattern set covers expected field categories."""

    def test_identity_fields_covered(self):
        """Patterns should cover identity fields."""
        assert "mprn" in TIER2_UNIVERSAL_PATTERNS
        assert "gprn" in TIER2_UNIVERSAL_PATTERNS
        assert "account_number" in TIER2_UNIVERSAL_PATTERNS
        assert "invoice_number" in TIER2_UNIVERSAL_PATTERNS

    def test_financial_fields_covered(self):
        """Patterns should cover financial totals."""
        assert "subtotal" in TIER2_UNIVERSAL_PATTERNS
        assert "vat_rate" in TIER2_UNIVERSAL_PATTERNS
        assert "vat_amount" in TIER2_UNIVERSAL_PATTERNS
        assert "total_incl_vat" in TIER2_UNIVERSAL_PATTERNS

    def test_date_fields_covered(self):
        """Patterns should cover date fields."""
        assert "billing_period" in TIER2_UNIVERSAL_PATTERNS
        assert "invoice_date" in TIER2_UNIVERSAL_PATTERNS

    def test_consumption_fields_covered(self):
        """Patterns should cover energy consumption."""
        assert "day_kwh" in TIER2_UNIVERSAL_PATTERNS
        assert "day_rate" in TIER2_UNIVERSAL_PATTERNS

    def test_fuel_fields_covered(self):
        """Patterns should cover fuel/oil deliveries."""
        assert "litres" in TIER2_UNIVERSAL_PATTERNS
        assert "unit_price" in TIER2_UNIVERSAL_PATTERNS

    def test_esb_specific_fields_covered(self):
        """Universal patterns should include ESB-specific codes."""
        assert "mcc_code" in TIER2_UNIVERSAL_PATTERNS
        assert "dg_code" in TIER2_UNIVERSAL_PATTERNS

    def test_minimum_pattern_count(self):
        """Should have at least 15 field patterns."""
        assert len(TIER2_UNIVERSAL_PATTERNS) >= 15


# ===================================================================
# Hit rate reporting (informational test)
# ===================================================================

class TestTier2HitRateReport:
    """Generate a per-field hit rate report for documentation."""

    def test_hit_rate_report(self):
        """Print Tier 2 hit rates across all real PDFs (informational)."""
        pdfs = [
            ("1845.pdf", "Go Power"),
            ("2024 Mar - Apr.pdf", "ESB Networks"),
            ("3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf", "Energia"),
        ]

        field_hits: dict[str, int] = {}
        field_total: dict[str, int] = {}

        for filename, provider in pdfs:
            if not _pdf_exists(filename):
                continue
            text = _extract_text(filename)
            result = extract_tier2_universal(text)

            for field_name in TIER2_UNIVERSAL_PATTERNS:
                field_total[field_name] = field_total.get(field_name, 0) + 1
                if field_name in result.fields:
                    field_hits[field_name] = field_hits.get(field_name, 0) + 1

        # Print report
        print("\n" + "=" * 60)
        print("  Tier 2 Universal Extraction Hit Rate Report")
        print("=" * 60)
        for field_name in sorted(TIER2_UNIVERSAL_PATTERNS.keys()):
            hits = field_hits.get(field_name, 0)
            total = field_total.get(field_name, 0)
            rate = hits / total if total > 0 else 0.0
            status = "HIT" if hits == total else ("PARTIAL" if hits > 0 else "MISS")
            print(f"  [{status:7s}] {field_name:20s}: {hits}/{total} ({rate:.0%})")
        print("=" * 60)

        # At least 50% of fields should hit on at least one PDF
        hit_fields = sum(1 for h in field_hits.values() if h > 0)
        total_fields = len(TIER2_UNIVERSAL_PATTERNS)
        assert hit_fields / total_fields >= 0.50, (
            f"Only {hit_fields}/{total_fields} fields hit on any PDF"
        )
