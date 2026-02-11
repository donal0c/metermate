#!/usr/bin/env python3
"""
Pipeline Accuracy Evaluation Script
=====================================

Runs the extraction pipeline against canonical fixture PDFs and compares
results to ground-truth expected values. Produces per-file and aggregate
accuracy metrics.

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

from pipeline import extract_text_tier0, extract_with_config, calculate_confidence


GROUND_TRUTH_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "ground_truth.json")
BILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "Steve_bills")


def load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH) as f:
        return json.load(f)


def _normalize_value(val: str) -> str:
    """Normalize a value for comparison."""
    return val.strip().replace(",", "").lower()


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
    return e_norm == a_norm


def evaluate_fixture(fixture: dict) -> dict:
    """Evaluate a single fixture against ground truth.

    Returns dict with per-field results and scores.
    """
    filename = fixture["filename"]
    provider = fixture["provider"]
    expected = fixture["expected"]
    not_applicable = set(fixture.get("not_applicable", []))

    pdf_path = os.path.join(BILLS_DIR, filename)
    if not os.path.exists(pdf_path):
        return {
            "filename": filename,
            "provider": provider,
            "status": "skipped",
            "reason": f"PDF not found: {pdf_path}",
        }

    # Run pipeline
    tier0 = extract_text_tier0(pdf_path)
    tier3 = extract_with_config(tier0.extracted_text, provider)
    confidence = calculate_confidence(tier3.fields, provider=provider)

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

        actual_fr = tier3.fields.get(field_name)
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
        "provider": provider,
        "status": "evaluated",
        "accuracy": accuracy,
        "fields_expected": len(expected),
        "fields_matched": sum(1 for f in field_results.values() if f["match"]),
        "fields_missing": sum(1 for f in field_results.values() if f["actual"] is None),
        "confidence_score": confidence.score,
        "confidence_band": confidence.band,
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
    print("  Pipeline Accuracy Evaluation Report")
    print("=" * 70)

    for result in evaluation["results"]:
        if result["status"] == "skipped":
            print(f"\n  SKIP: {result['filename']} — {result['reason']}")
            continue

        print(f"\n  {result['provider']} — {result['filename']}")
        print(f"  Accuracy: {result['accuracy']:.0%}")
        print(f"  Confidence: {result['confidence_score']:.2f} ({result['confidence_band']})")
        print(f"  Fields: {result['fields_matched']}/{result['fields_expected']} matched, "
              f"{result['fields_missing']} missing")

        for field_name, fr in sorted(result["field_results"].items()):
            status = "MATCH" if fr["match"] else ("MISS" if fr["actual"] is None else "WRONG")
            crit = " [CRITICAL]" if fr["critical"] else ""
            actual = fr["actual"] or "—"
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
