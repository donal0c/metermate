#!/usr/bin/env python3
"""
Pipeline Accuracy Evaluation Script
=====================================

Runs the **full end-to-end orchestrator pipeline** (``extract_bill_pipeline``)
against canonical fixture PDFs and compares results to ground-truth expected
values.  Produces per-file and aggregate accuracy metrics.

The script exercises the real pipeline path -- including Tier-0 text
extraction, scanned-PDF routing, Tier-1 provider detection, Tier-3
config-driven extraction, Tier-2 universal fallback, spatial OCR, and
field merging -- so the reported accuracy reflects true end-to-end quality.

Usage:
    python3 evaluate_pipeline.py                    # Run evaluation
    python3 evaluate_pipeline.py --json             # JSON output
    python3 -m pytest evaluate_pipeline.py -v       # As pytest test

Ground truth: app/fixtures/ground_truth.json
Fixtures:     Steve_bills/*.pdf
"""
from __future__ import annotations

import json
import os
import sys

# Ensure app/ is on the path
sys.path.insert(0, os.path.dirname(__file__))

from orchestrator import extract_bill_pipeline, extract_bill_from_image, PipelineResult


GROUND_TRUTH_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "ground_truth.json")
BILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "Steve_bills")
ROOT_DIR = os.path.join(os.path.dirname(__file__), "..")


def load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH) as f:
        return json.load(f)


def _normalize_value(val: str) -> str:
    """Normalize a value for comparison."""
    return val.strip().replace(",", "").lower()


def _normalize_date(val: str) -> str | None:
    """Try to normalise a date string to YYYY-MM-DD for comparison."""
    import re
    from datetime import datetime

    val = val.strip()
    for fmt in (
        "%d/%m/%y", "%d/%m/%Y", "%d %B %Y", "%d %b %y", "%d %b %Y",
        "%Y-%m-%d", "%Y-%d-%m",
    ):
        try:
            return datetime.strptime(val, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _values_match(expected: str, actual: str, tolerance: float = 0.02) -> bool:
    """Compare two values with optional numeric tolerance."""
    e_norm = _normalize_value(expected)
    a_norm = _normalize_value(actual)

    # Try numeric comparison first
    try:
        e_float = float(e_norm)
        a_float = float(a_norm)
        return abs(e_float - a_float) <= tolerance
    except ValueError:
        pass

    # String comparison (case-insensitive, whitespace-stripped)
    if e_norm == a_norm:
        return True

    # Date comparison: normalise both to YYYY-MM-DD
    e_date = _normalize_date(expected)
    a_date = _normalize_date(actual)
    if e_date is not None and a_date is not None:
        return e_date == a_date

    return False


def _get_extraction_fields(pipeline_result: PipelineResult) -> dict:
    """Collect the final extraction fields from a PipelineResult.

    The orchestrator may populate tier3, tier2, or both (merged).  We
    reconstruct the same merge logic the orchestrator used so evaluation
    reflects the real pipeline output.

    Merge rules (mirroring orchestrator.extract_bill_pipeline):
      - When both tier2 (spatial) and tier3 are present (scanned-PDF path):
        spatial fields take priority; tier3 only fills gaps.
      - When only tier3 is present: use tier3 fields.
      - When only tier2 is present: use tier2 fields.
    """
    fields: dict = {}

    if pipeline_result.tier2 is not None and pipeline_result.tier3 is not None:
        # Scanned-PDF merge: start with tier3, then let tier2/spatial overwrite.
        # This matches the orchestrator which starts with spatial_result.fields
        # and only adds tier3 fields where the key is absent.
        fields.update(pipeline_result.tier3.fields)
        fields.update(pipeline_result.tier2.fields)
    elif pipeline_result.tier3 is not None:
        fields.update(pipeline_result.tier3.fields)
    elif pipeline_result.tier2 is not None:
        fields.update(pipeline_result.tier2.fields)

    # Tier 4 LLM fields: the orchestrator merges these with existing fields
    # using merge_llm_with_existing(prefer_llm=True) because tier4 only
    # runs when confidence was "escalate" (existing extraction unreliable).
    if pipeline_result.tier4 is not None:
        from llm_extraction import merge_llm_with_existing
        fields = merge_llm_with_existing(
            pipeline_result.tier4.fields, fields, prefer_llm=True,
        )

    # If neither tier produced fields the pipeline still ran but found
    # nothing -- return the empty dict so every expected field shows as
    # missing.
    return fields


def evaluate_fixture(fixture: dict) -> dict:
    """Evaluate a single fixture against ground truth.

    Runs the **full orchestrator pipeline** (``extract_bill_pipeline``)
    end-to-end, then compares extracted fields to expected values.

    Returns dict with per-field results and scores.
    """
    filename = fixture["filename"]
    expected_provider = fixture["provider"]
    expected = fixture["expected"]
    not_applicable = set(fixture.get("not_applicable", []))
    input_type = fixture.get("input_type", "pdf")
    location = fixture.get("location", "Steve_bills")

    # Resolve file path based on location
    if location == "root":
        file_path = os.path.join(ROOT_DIR, filename)
    else:
        file_path = os.path.join(BILLS_DIR, filename)

    if not os.path.exists(file_path):
        return {
            "filename": filename,
            "provider": expected_provider,
            "status": "skipped",
            "reason": f"File not found: {file_path}",
        }

    # Run the FULL orchestrator pipeline end-to-end
    if input_type == "image":
        pipeline_result = extract_bill_from_image(file_path)
    else:
        pipeline_result = extract_bill_pipeline(file_path)

    # Collect the fields that the pipeline actually produced
    extraction_fields = _get_extraction_fields(pipeline_result)

    # Detected provider (from the pipeline's own Tier-1 detection)
    detected_provider = pipeline_result.provider_detection.provider_name

    # Compare fields
    gt = load_ground_truth()
    critical_fields = set(gt["_meta"]["scoring_spec"]["critical_fields"])
    critical_weight = gt["_meta"]["scoring_spec"]["critical_weight"]
    non_critical_weight = gt["_meta"]["scoring_spec"]["non_critical_weight"]

    field_results = {}
    total_weight = 0.0
    matched_weight = 0.0

    for field_name, expected_value in expected.items():
        if field_name in not_applicable:
            continue

        is_critical = field_name in critical_fields
        weight = critical_weight if is_critical else non_critical_weight
        total_weight += weight

        actual_fr = extraction_fields.get(field_name)
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
        "provider": expected_provider,
        "detected_provider": detected_provider,
        "provider_match": detected_provider == expected_provider,
        "status": "evaluated",
        "accuracy": accuracy,
        "fields_expected": len(expected),
        "fields_matched": sum(1 for f in field_results.values() if f["match"]),
        "fields_missing": sum(1 for f in field_results.values() if f["actual"] is None),
        "confidence_score": pipeline_result.confidence.score,
        "confidence_band": pipeline_result.confidence.band,
        "extraction_path": " -> ".join(pipeline_result.extraction_path),
        "field_results": field_results,
    }


def evaluate_all() -> dict:
    """Evaluate all fixtures and produce aggregate metrics."""
    gt = load_ground_truth()
    fixtures = gt["fixtures"]

    results = []
    total_weight = 0.0
    matched_weight = 0.0

    critical_fields = set(gt["_meta"]["scoring_spec"]["critical_fields"])
    critical_weight = gt["_meta"]["scoring_spec"]["critical_weight"]
    non_critical_weight = gt["_meta"]["scoring_spec"]["non_critical_weight"]

    for fixture in fixtures:
        result = evaluate_fixture(fixture)
        results.append(result)

        if result["status"] == "evaluated":
            for field_name, fr in result["field_results"].items():
                is_critical = field_name in critical_fields
                weight = critical_weight if is_critical else non_critical_weight
                total_weight += weight
                if fr["match"]:
                    matched_weight += weight

    aggregate_accuracy = matched_weight / total_weight if total_weight > 0 else 0.0

    return {
        "aggregate_accuracy": aggregate_accuracy,
        "fixtures_evaluated": sum(1 for r in results if r["status"] == "evaluated"),
        "fixtures_skipped": sum(1 for r in results if r["status"] == "skipped"),
        "results": results,
    }


def print_report(evaluation: dict) -> None:
    """Print a human-readable evaluation report."""
    print("=" * 70)
    print("  Pipeline End-to-End Accuracy Evaluation Report")
    print("=" * 70)

    for result in evaluation["results"]:
        if result["status"] == "skipped":
            print(f"\n  SKIP: {result['filename']} -- {result['reason']}")
            continue

        print(f"\n  {result['provider']} -- {result['filename']}")

        # Show extraction path to reveal which tiers actually ran
        print(f"  Extraction path: {result.get('extraction_path', 'n/a')}")

        # Show provider detection result
        detected = result.get("detected_provider", "?")
        prov_ok = result.get("provider_match", False)
        prov_tag = "OK" if prov_ok else "MISMATCH"
        print(f"  Provider detection: {detected} [{prov_tag}]")

        print(f"  Accuracy: {result['accuracy']:.0%}")
        print(f"  Confidence: {result['confidence_score']:.2f} ({result['confidence_band']})")
        print(f"  Fields: {result['fields_matched']}/{result['fields_expected']} matched, "
              f"{result['fields_missing']} missing")

        for field_name, fr in sorted(result["field_results"].items()):
            status = "MATCH" if fr["match"] else ("MISS" if fr["actual"] is None else "WRONG")
            crit = " [CRITICAL]" if fr["critical"] else ""
            actual = fr["actual"] or "--"
            expected = fr["expected"]
            if status == "MATCH":
                print(f"    [{status}] {field_name}: {actual}{crit}")
            else:
                print(f"    [{status}] {field_name}: got={actual!r}, expected={expected!r}{crit}")

    print(f"\n{'=' * 70}")
    print(f"  AGGREGATE ACCURACY: {evaluation['aggregate_accuracy']:.0%}")
    print(f"  Fixtures evaluated: {evaluation['fixtures_evaluated']}")
    print(f"  Fixtures skipped:   {evaluation['fixtures_skipped']}")
    print(f"{'=' * 70}")


# ===================================================================
# pytest integration
# ===================================================================

def test_pipeline_accuracy():
    """Pytest-compatible test that fails if aggregate accuracy < 80%."""
    evaluation = evaluate_all()
    print_report(evaluation)
    assert evaluation["aggregate_accuracy"] >= 0.80, \
        f"Aggregate accuracy {evaluation['aggregate_accuracy']:.0%} below 80% threshold"


# ===================================================================
# CLI
# ===================================================================

if __name__ == "__main__":
    evaluation = evaluate_all()

    if "--json" in sys.argv:
        # Remove field_results detail for cleaner JSON
        for r in evaluation["results"]:
            if "field_results" in r:
                r.pop("field_results")
        print(json.dumps(evaluation, indent=2, default=str))
    else:
        print_report(evaluation)

    # Exit code based on accuracy
    sys.exit(0 if evaluation["aggregate_accuracy"] >= 0.80 else 1)
