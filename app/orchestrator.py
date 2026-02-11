"""
Pipeline Orchestrator
======================

Wires together Tier 0 → Tier 1 → Tier 3 into a single entry point.
Takes a PDF path or bytes, returns structured GenericBillData with
confidence scoring and extraction metadata.

Usage:
    from orchestrator import extract_bill_pipeline
    result = extract_bill_pipeline("path/to/bill.pdf")
    print(result.bill.to_json(indent=2))
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from bill_parser import GenericBillData, LineItem
from pipeline import (
    TextExtractionResult,
    ProviderDetectionResult,
    Tier3ExtractionResult,
    Tier2ExtractionResult,
    ConfidenceResult,
    FieldExtractionResult,
    extract_text_tier0,
    detect_provider,
    extract_with_config,
    extract_tier2_universal,
    calculate_confidence,
    PROVIDER_BILL_TYPE,
)
from provider_configs import get_provider_config

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Full result of the extraction pipeline."""
    bill: GenericBillData
    confidence: ConfidenceResult
    tier0: TextExtractionResult
    provider_detection: ProviderDetectionResult
    tier3: Optional[Tier3ExtractionResult] = None
    tier2: Optional[Tier2ExtractionResult] = None
    extraction_path: list[str] = field(default_factory=list)


def _safe_float(value: str | None) -> float | None:
    """Parse a string as float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _build_bill(
    tier3: Tier3ExtractionResult,
    provider: str,
    confidence: ConfidenceResult,
    extraction_method: str,
    raw_text: str,
) -> GenericBillData:
    """Build a GenericBillData from Tier 3 extraction results."""
    fields = tier3.fields

    def get_val(name: str) -> str | None:
        fr = fields.get(name)
        return fr.value if fr else None

    bill = GenericBillData(
        provider=provider,
        mprn=get_val("mprn"),
        account_number=get_val("account_number"),
        invoice_number=get_val("invoice_number"),
        invoice_date=get_val("invoice_date"),
        billing_period=get_val("billing_period"),
        subtotal=_safe_float(get_val("subtotal")),
        vat_rate=_safe_float(get_val("vat_rate")),
        vat_amount=_safe_float(get_val("vat_amount")),
        total_incl_vat=_safe_float(get_val("total_incl_vat")),
        extraction_method=extraction_method,
        confidence_score=confidence.score,
        raw_text=raw_text,
    )

    # Build line items from extracted fields
    line_items: list[LineItem] = []

    # Day energy
    day_kwh = _safe_float(get_val("day_kwh"))
    day_rate = _safe_float(get_val("day_rate"))
    day_cost = _safe_float(get_val("day_cost"))
    if day_kwh is not None or day_cost is not None:
        line_items.append(LineItem(
            description="Day Energy",
            line_total=day_cost or 0.0,
            quantity=day_kwh,
            unit="kWh",
            unit_price=day_rate,
        ))

    # Night energy
    night_kwh = _safe_float(get_val("night_kwh"))
    night_rate = _safe_float(get_val("night_rate"))
    night_cost = _safe_float(get_val("night_cost"))
    if night_kwh is not None or night_cost is not None:
        line_items.append(LineItem(
            description="Night Energy",
            line_total=night_cost or 0.0,
            quantity=night_kwh,
            unit="kWh",
            unit_price=night_rate,
        ))

    # Standing charge
    standing_val = get_val("standing_charge")
    if standing_val is not None:
        # Standing charge might have multi-group values: "days - rate - total"
        parts = standing_val.split(" - ")
        if len(parts) == 3:
            sc_days = _safe_float(parts[0])
            sc_rate = _safe_float(parts[1])
            sc_total = _safe_float(parts[2])
        else:
            sc_days = None
            sc_rate = None
            sc_total = _safe_float(standing_val)
        if sc_total is not None:
            line_items.append(LineItem(
                description="Standing Charge",
                line_total=sc_total,
                quantity=sc_days,
                unit="days",
                unit_price=sc_rate,
            ))

    # PSO Levy
    pso_val = _safe_float(get_val("pso_levy"))
    if pso_val is not None:
        line_items.append(LineItem(
            description="PSO Levy",
            line_total=pso_val,
        ))

    # Fuel-specific: litres + unit_price
    litres = _safe_float(get_val("litres"))
    unit_price = _safe_float(get_val("unit_price"))
    if litres is not None:
        line_items.append(LineItem(
            description="Kerosene",
            line_total=bill.subtotal or 0.0,
            quantity=litres,
            unit="litres",
            unit_price=unit_price,
        ))

    bill.line_items = line_items

    # Warnings from tier3 and confidence
    warnings: list[str] = list(tier3.warnings)
    for check in confidence.validation_checks:
        if not check.passed:
            warnings.append(f"Validation failed: {check.name} - {check.message}")
    if confidence.band == "escalate":
        warnings.append("Low confidence - manual review recommended")
    bill.warnings = warnings

    return bill


def extract_bill_pipeline(source: bytes | str) -> PipelineResult:
    """Extract structured bill data from a PDF using the tiered pipeline.

    Pipeline flow:
      1. Tier 0: Extract text + classify (native vs scanned)
      2. Tier 1: Detect provider from extracted text
      3. If known provider with config → Tier 3 extraction
         If unknown provider → escalate (Tier 2/4 not yet implemented)
      4. Confidence scoring + cross-field validation
      5. Build GenericBillData from extracted fields
      6. Return PipelineResult

    Args:
        source: PDF file path (str) or raw PDF bytes.

    Returns:
        PipelineResult with bill data, confidence, and extraction metadata.

    Raises:
        ValueError: If source is empty or not a valid PDF.
        RuntimeError: If PyMuPDF cannot open the document.
    """
    extraction_path: list[str] = []

    # ---- Tier 0: Text extraction ----
    tier0 = extract_text_tier0(source)

    if tier0.is_native_text:
        extraction_path.append("tier0_native")
    else:
        extraction_path.append("tier0_scanned")

    text = tier0.extracted_text

    # If scanned PDF with very little text, note the limitation
    if not tier0.is_native_text and len(text.strip()) < 50:
        extraction_path.append("insufficient_text")
        # Build a minimal result with escalation
        empty_provider = ProviderDetectionResult(
            provider_name="unknown", is_known=False
        )
        empty_fields: dict[str, FieldExtractionResult] = {}
        empty_confidence = calculate_confidence(empty_fields)
        bill = GenericBillData(
            extraction_method="tier0_insufficient_text",
            confidence_score=empty_confidence.score,
            raw_text=text,
            warnings=["Insufficient text extracted - OCR or Tier 4 LLM required"],
        )
        return PipelineResult(
            bill=bill,
            confidence=empty_confidence,
            tier0=tier0,
            provider_detection=empty_provider,
            extraction_path=extraction_path,
        )

    # ---- Tier 1: Provider detection ----
    provider_result = detect_provider(text)
    extraction_path.append(
        f"tier1_{'known' if provider_result.is_known else 'unknown'}"
    )

    provider_name = provider_result.provider_name

    # ---- Tier 3: Config-driven extraction (if config exists) ----
    config = get_provider_config(provider_name) if provider_result.is_known else None
    tier2 = None

    if config is not None:
        tier3 = extract_with_config(text, provider_name)
        extraction_path.append(f"tier3_{provider_name.lower().replace(' ', '_')}")
        extraction_fields = tier3.fields
    else:
        tier3 = None

        # ---- Tier 2: Universal regex fallback ----
        tier2 = extract_tier2_universal(text)
        extraction_path.append("tier2_universal")

        # Wrap Tier 2 fields into a Tier3-shaped result for downstream compat
        extraction_fields = tier2.fields

    # ---- Confidence scoring ----
    bill_type = PROVIDER_BILL_TYPE.get(provider_name)
    confidence = calculate_confidence(
        extraction_fields,
        provider=provider_name,
        bill_type=bill_type,
    )

    # ---- Build GenericBillData ----
    # Build a Tier3-shaped result for _build_bill compatibility
    if tier3 is not None:
        build_result = tier3
    else:
        build_result = Tier3ExtractionResult(
            provider=provider_name,
            fields=extraction_fields,
            field_count=len(extraction_fields),
            hit_rate=tier2.hit_rate if tier2 else 0.0,
            warnings=tier2.warnings if tier2 else [],
        )

    extraction_method = " → ".join(extraction_path)
    bill = _build_bill(build_result, provider_name, confidence, extraction_method, text)

    return PipelineResult(
        bill=bill,
        confidence=confidence,
        tier0=tier0,
        provider_detection=provider_result,
        tier3=tier3,
        tier2=tier2,
        extraction_path=extraction_path,
    )
