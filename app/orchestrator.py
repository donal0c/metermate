"""
Pipeline Orchestrator
======================

Wires together Tier 0 → Tier 1 → Tier 2 / Tier 3 into a single entry point.
Takes a PDF path or bytes, returns structured GenericBillData with
confidence scoring and extraction metadata.

Usage:
    from orchestrator import extract_bill_pipeline
    result = extract_bill_pipeline("path/to/bill.pdf")
    print(result.bill.to_json(indent=2))
"""
from __future__ import annotations

import logging
import os
import re
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
    postprocess_vat_and_totals,
    postprocess_computed_costs,
    PROVIDER_BILL_TYPE,
)
from provider_configs import get_provider_config
from spatial_extraction import extract_tier2_spatial, get_ocr_text
from llm_extraction import extract_tier4_llm, merge_llm_with_existing, Tier4ExtractionResult

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
    tier4: Optional[Tier4ExtractionResult] = None
    extraction_path: list[str] = field(default_factory=list)


def _safe_float(value: str | None) -> float | None:
    """Parse a string as float, returning None on failure."""
    if value is None:
        return None
    try:
        cleaned = str(value).strip()
        if not cleaned:
            return None
        cleaned = cleaned.split("(", 1)[0].strip()
        cleaned = re.sub(r"[^\d.\-]", "", cleaned.replace(",", ""))
        if cleaned in {"", "-", ".", "-."}:
            return None
        return float(cleaned)
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
        gprn=get_val("gprn"),
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
    if day_kwh is not None or day_rate is not None or day_cost is not None:
        day_total = day_cost
        if day_total is None and day_kwh is not None and day_rate is not None:
            day_total = round(day_kwh * day_rate, 2)
        if day_total is not None:
            line_items.append(LineItem(
                description="Day Energy",
                line_total=day_total,
                quantity=day_kwh,
                unit="kWh",
                unit_price=day_rate,
            ))

    # Night energy
    night_kwh = _safe_float(get_val("night_kwh"))
    night_rate = _safe_float(get_val("night_rate"))
    night_cost = _safe_float(get_val("night_cost"))
    if night_kwh is not None or night_rate is not None or night_cost is not None:
        night_total = night_cost
        if night_total is None and night_kwh is not None and night_rate is not None:
            night_total = round(night_kwh * night_rate, 2)
        if night_total is not None:
            line_items.append(LineItem(
                description="Night Energy",
                line_total=night_total,
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
            if sc_total is None and sc_days is not None and sc_rate is not None:
                sc_total = round(sc_days * sc_rate, 2)
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
        subtotal = bill.subtotal
        if subtotal is not None:
            line_items.append(LineItem(
                description="Kerosene",
                line_total=subtotal,
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


def _is_low_quality_text(text: str) -> bool:
    """Determine whether extracted text is too low-quality to rely on.

    Scanned PDFs sometimes produce >50 characters of junk from embedded
    metadata, font names, or partial OCR layers. A raw length check is
    insufficient -- we need to assess *text quality* to decide whether
    spatial OCR should run.

    Heuristics (any True means low quality):
      1. Very short text (< 50 chars stripped) -- obviously insufficient.
      2. Low substantive word count -- fewer than 5 words of 3+ alpha chars.
         Two-letter fragments are common OCR noise (Il, lI, iI, etc.) so
         they are not counted as substantive.
      3. Low alpha ratio -- less than 40% of non-whitespace characters are
         alphabetic, suggesting binary/metadata noise.

    Returns:
        True if the text is low quality and spatial OCR should be attempted.
    """
    stripped = text.strip()

    # Trivially short text is always low quality
    if len(stripped) < 50:
        return True

    # Count substantive words: sequences of 3+ alphabetic characters.
    # Two-letter combos (Il, lI, Tf, gs, etc.) are common in OCR noise
    # and PDF operator fragments, so require at least 3 alpha chars.
    substantive_words = re.findall(r"[a-zA-Z]{3,}", stripped)
    if len(substantive_words) < 5:
        log.debug(
            "Low quality: only %d substantive words (3+ alpha chars) "
            "in %d chars of text",
            len(substantive_words), len(stripped),
        )
        return True

    # Check ratio of alphabetic characters to total non-whitespace chars
    non_ws = re.sub(r"\s", "", stripped)
    if non_ws:
        alpha_count = sum(1 for c in non_ws if c.isalpha())
        alpha_ratio = alpha_count / len(non_ws)
        if alpha_ratio < 0.40:
            log.debug(
                "Low quality: alpha ratio %.2f in %d non-whitespace chars",
                alpha_ratio, len(non_ws),
            )
            return True

    return False


def _try_tier4_llm(
    source: bytes | str,
    extraction_path: list[str],
    is_image: bool = False,
) -> Tier4ExtractionResult | None:
    """Attempt Tier 4 LLM extraction, returning None if unavailable.

    Gracefully handles missing API key or google-genai package.
    """
    if not os.environ.get("GEMINI_API_KEY"):
        log.debug("Tier 4 skipped: GEMINI_API_KEY not set")
        return None

    try:
        extraction_path.append("tier4_llm")
        result = extract_tier4_llm(source, is_image=is_image)
        return result
    except RuntimeError as e:
        log.warning("Tier 4 LLM unavailable: %s", e)
        return None
    except Exception as e:
        log.warning("Tier 4 LLM failed: %s", e, exc_info=True)
        return None


def _detect_provider_from_fields(
    fields: dict[str, FieldExtractionResult],
) -> str:
    """Infer provider name from LLM-extracted fields."""
    provider_field = fields.get("provider")
    if provider_field and provider_field.value.strip():
        # Normalize to match known provider names
        raw = provider_field.value.strip()
        # Try case-insensitive match against known providers
        for known in PROVIDER_BILL_TYPE:
            if raw.lower() == known.lower():
                return known
        # Return as-is if not in known list
        return raw
    return "unknown"


def extract_bill_pipeline(source: bytes | str) -> PipelineResult:
    """Extract structured bill data from a PDF using the tiered pipeline.

    Pipeline flow:
      1. Tier 0: Extract text + classify (native vs scanned)
      2. Tier 1: Detect provider from extracted text
      3. If known provider with config → Tier 3 extraction
         If unknown provider → Tier 2 universal regex fallback
         If scanned PDF with little text → Tier 2 spatial OCR extraction
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

    # If scanned PDF with low-quality text, attempt spatial OCR extraction.
    # Use a quality heuristic rather than a raw length check because scanned
    # PDFs can produce >50 chars of junk from embedded metadata or partial
    # OCR layers while still lacking usable content.
    if not tier0.is_native_text and _is_low_quality_text(text):
        extraction_path.append("tier2_spatial")
        try:
            spatial_result, avg_ocr_conf, _ocr_df, ocr_text = extract_tier2_spatial(source)
        except Exception as e:
            log.warning(
                "Spatial extraction failed for scanned PDF: %s", e, exc_info=True
            )
            spatial_result = None
            avg_ocr_conf = None
            ocr_text = None

        if spatial_result is not None and spatial_result.field_count > 0:
            extraction_fields = spatial_result.fields

            # Detect provider from OCR text already obtained by extract_tier2_spatial
            # (reuses OCR results to avoid a redundant expensive OCR pass)
            try:
                provider_result = detect_provider(ocr_text)
                text = ocr_text  # Use OCR text for downstream
            except Exception as e:
                log.error(
                    "OCR provider detection failed during spatial flow: %s",
                    e,
                    exc_info=True,
                )
                provider_result = ProviderDetectionResult(
                    provider_name="unknown", is_known=False
                )

            extraction_path.append(
                f"tier1_{'known' if provider_result.is_known else 'unknown'}"
            )
            provider_name = provider_result.provider_name

            # Also try Tier 3 config extraction on OCR text if provider known
            config = get_provider_config(provider_name) if provider_result.is_known else None
            tier3 = None
            if config is not None:
                tier3 = extract_with_config(text, provider_name)
                extraction_path.append(f"tier3_{provider_name.lower().replace(' ', '_')}")
                # Merge: Tier 3 fills gaps spatial missed
                for fname, fval in tier3.fields.items():
                    if fname not in extraction_fields:
                        extraction_fields[fname] = fval

            # Self-heal VAT/total fields using cross-field math
            computed_cost_corrections = postprocess_computed_costs(extraction_fields)
            vat_corrections = postprocess_vat_and_totals(extraction_fields)

            bill_type = PROVIDER_BILL_TYPE.get(provider_name)
            confidence = calculate_confidence(
                extraction_fields,
                provider=provider_name,
                bill_type=bill_type,
                avg_ocr_confidence=avg_ocr_conf,
            )

            # ---- Tier 4 LLM escalation for scanned PDFs ----
            tier4 = None
            if confidence.band == "escalate":
                tier4 = _try_tier4_llm(source, extraction_path)
                if tier4 is not None and tier4.field_count > 0:
                    extraction_fields = merge_llm_with_existing(
                        tier4.fields, extraction_fields, prefer_llm=True,
                    )
                    if provider_name == "unknown":
                        provider_name = _detect_provider_from_fields(tier4.fields)
                        provider_result = ProviderDetectionResult(
                            provider_name=provider_name,
                            is_known=provider_name != "unknown",
                        )
                    bill_type = PROVIDER_BILL_TYPE.get(provider_name)
                    computed_cost_corrections.extend(
                        postprocess_computed_costs(extraction_fields)
                    )
                    confidence = calculate_confidence(
                        extraction_fields,
                        provider=provider_name,
                        bill_type=bill_type,
                        avg_ocr_confidence=avg_ocr_conf,
                    )

            build_result = Tier3ExtractionResult(
                provider=provider_name,
                fields=extraction_fields,
                field_count=len(extraction_fields),
                hit_rate=spatial_result.hit_rate,
                warnings=spatial_result.warnings + computed_cost_corrections + vat_corrections,
            )

            extraction_method = " → ".join(extraction_path)
            bill = _build_bill(build_result, provider_name, confidence, extraction_method, text)

            return PipelineResult(
                bill=bill,
                confidence=confidence,
                tier0=tier0,
                provider_detection=provider_result,
                tier3=tier3,
                tier2=spatial_result,
                tier4=tier4,
                extraction_path=extraction_path,
            )

        # Spatial extraction failed or produced no results - try Tier 4 LLM
        tier4 = _try_tier4_llm(source, extraction_path)
        if tier4 is not None and tier4.field_count > 0:
            extraction_fields = tier4.fields
            provider_name = _detect_provider_from_fields(tier4.fields)
            provider_result = ProviderDetectionResult(
                provider_name=provider_name,
                is_known=provider_name != "unknown",
            )
            extraction_path.append(
                f"tier1_{'known' if provider_result.is_known else 'unknown'}"
            )

            bill_type = PROVIDER_BILL_TYPE.get(provider_name)
            confidence = calculate_confidence(
                extraction_fields,
                provider=provider_name,
                bill_type=bill_type,
            )

            build_result = Tier3ExtractionResult(
                provider=provider_name,
                fields=extraction_fields,
                field_count=len(extraction_fields),
                hit_rate=tier4.hit_rate,
                warnings=tier4.warnings,
            )

            extraction_method = " \u2192 ".join(extraction_path)
            bill = _build_bill(build_result, provider_name, confidence, extraction_method, text)

            return PipelineResult(
                bill=bill,
                confidence=confidence,
                tier0=tier0,
                provider_detection=provider_result,
                tier4=tier4,
                extraction_path=extraction_path,
            )

        extraction_path.append("insufficient_text")
        empty_provider = ProviderDetectionResult(
            provider_name="unknown", is_known=False
        )
        empty_fields: dict[str, FieldExtractionResult] = {}
        empty_confidence = calculate_confidence(empty_fields)
        bill = GenericBillData(
            extraction_method="tier0_insufficient_text",
            confidence_score=empty_confidence.score,
            raw_text=text,
            warnings=["Insufficient text extracted - OCR and spatial extraction failed"],
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

    # ---- Self-heal VAT/total fields using cross-field math ----
    computed_cost_corrections = postprocess_computed_costs(extraction_fields)
    vat_corrections = postprocess_vat_and_totals(extraction_fields)

    # ---- Confidence scoring ----
    bill_type = PROVIDER_BILL_TYPE.get(provider_name)
    confidence = calculate_confidence(
        extraction_fields,
        provider=provider_name,
        bill_type=bill_type,
    )

    # ---- Tier 4 LLM escalation ----
    # If confidence is in the "escalate" band, try LLM to fill gaps
    tier4 = None
    if confidence.band == "escalate":
        tier4 = _try_tier4_llm(source, extraction_path)
        if tier4 is not None and tier4.field_count > 0:
            extraction_fields = merge_llm_with_existing(
                tier4.fields, extraction_fields, prefer_llm=True,
            )
            # Recalculate confidence with merged fields
            computed_cost_corrections.extend(postprocess_computed_costs(extraction_fields))
            confidence = calculate_confidence(
                extraction_fields,
                provider=provider_name,
                bill_type=bill_type,
            )

    # ---- Build GenericBillData ----
    # Build a Tier3-shaped result for _build_bill compatibility
    if tier3 is not None:
        build_result = tier3
        build_result.warnings.extend(computed_cost_corrections + vat_corrections)
    else:
        build_result = Tier3ExtractionResult(
            provider=provider_name,
            fields=extraction_fields,
            field_count=len(extraction_fields),
            hit_rate=tier2.hit_rate if tier2 else 0.0,
            warnings=tier2.warnings if tier2 else [],
        )
        build_result.warnings.extend(computed_cost_corrections + vat_corrections)

    extraction_method = " → ".join(extraction_path)
    bill = _build_bill(build_result, provider_name, confidence, extraction_method, text)

    return PipelineResult(
        bill=bill,
        confidence=confidence,
        tier0=tier0,
        provider_detection=provider_result,
        tier3=tier3,
        tier2=tier2,
        tier4=tier4,
        extraction_path=extraction_path,
    )


def extract_bill_from_image(source: bytes | str) -> PipelineResult:
    """Extract structured bill data from a JPG/PNG image.

    Skips Tier 0 (PyMuPDF) since there is no PDF. Instead goes directly
    to spatial OCR on the image, falling back to Tier 4 LLM vision.

    Args:
        source: Image file path (str) or raw image bytes.

    Returns:
        PipelineResult with bill data, confidence, and extraction metadata.
    """
    extraction_path: list[str] = ["image_input"]

    # Synthetic Tier 0 result — no PDF text extraction
    tier0 = TextExtractionResult(
        extracted_text="",
        page_count=1,
        is_native_text=False,
        chars_per_page=[0],
        metadata={},
    )

    # ---- Spatial OCR directly on the image ----
    extraction_path.append("tier2_spatial")
    try:
        spatial_result, avg_ocr_conf, ocr_df, ocr_text = extract_tier2_spatial(
            source, is_image=True,
        )
    except Exception as e:
        log.warning("Spatial extraction failed for image: %s", e, exc_info=True)
        spatial_result = None
        avg_ocr_conf = None
        ocr_text = ""

    text = ocr_text or ""

    if spatial_result is not None and spatial_result.field_count > 0:
        extraction_fields = spatial_result.fields

        try:
            provider_result = detect_provider(text)
        except Exception:
            provider_result = ProviderDetectionResult(
                provider_name="unknown", is_known=False,
            )

        extraction_path.append(
            f"tier1_{'known' if provider_result.is_known else 'unknown'}"
        )
        provider_name = provider_result.provider_name

        # Try Tier 3 config on OCR text if provider is known
        config = get_provider_config(provider_name) if provider_result.is_known else None
        tier3 = None
        if config is not None:
            tier3 = extract_with_config(text, provider_name)
            extraction_path.append(f"tier3_{provider_name.lower().replace(' ', '_')}")
            for fname, fval in tier3.fields.items():
                if fname not in extraction_fields:
                    extraction_fields[fname] = fval

        # Self-heal VAT/total fields using cross-field math
        computed_cost_corrections = postprocess_computed_costs(extraction_fields)
        vat_corrections = postprocess_vat_and_totals(extraction_fields)

        bill_type = PROVIDER_BILL_TYPE.get(provider_name)
        confidence = calculate_confidence(
            extraction_fields,
            provider=provider_name,
            bill_type=bill_type,
            avg_ocr_confidence=avg_ocr_conf,
        )

        # ---- Tier 4 LLM escalation for images (same as PDF path) ----
        tier4 = None
        if confidence.band == "escalate":
            tier4 = _try_tier4_llm(source, extraction_path, is_image=True)
            if tier4 is not None and tier4.field_count > 0:
                extraction_fields = merge_llm_with_existing(
                    tier4.fields, extraction_fields,
                    prefer_llm=True,
                )
                # Detect provider from LLM if still unknown
                if provider_name == "unknown":
                    provider_name = _detect_provider_from_fields(tier4.fields)
                    provider_result = ProviderDetectionResult(
                        provider_name=provider_name,
                        is_known=provider_name != "unknown",
                    )
                # Recalculate confidence with merged fields
                bill_type = PROVIDER_BILL_TYPE.get(provider_name)
                computed_cost_corrections.extend(
                    postprocess_computed_costs(extraction_fields)
                )
                confidence = calculate_confidence(
                    extraction_fields,
                    provider=provider_name,
                    bill_type=bill_type,
                    avg_ocr_confidence=avg_ocr_conf,
                )

        build_result = Tier3ExtractionResult(
            provider=provider_name,
            fields=extraction_fields,
            field_count=len(extraction_fields),
            hit_rate=spatial_result.hit_rate,
            warnings=spatial_result.warnings + computed_cost_corrections + vat_corrections,
        )

        extraction_method = " → ".join(extraction_path)
        bill = _build_bill(build_result, provider_name, confidence, extraction_method, text)

        return PipelineResult(
            bill=bill,
            confidence=confidence,
            tier0=tier0,
            provider_detection=provider_result,
            tier3=tier3,
            tier2=spatial_result,
            tier4=tier4,
            extraction_path=extraction_path,
        )

    # ---- Fallback: Tier 4 LLM vision ----
    tier4 = _try_tier4_llm(source, extraction_path, is_image=True)
    if tier4 is not None and tier4.field_count > 0:
        extraction_fields = tier4.fields
        provider_name = _detect_provider_from_fields(tier4.fields)
        provider_result = ProviderDetectionResult(
            provider_name=provider_name,
            is_known=provider_name != "unknown",
        )
        extraction_path.append(
            f"tier1_{'known' if provider_result.is_known else 'unknown'}"
        )

        bill_type = PROVIDER_BILL_TYPE.get(provider_name)
        confidence = calculate_confidence(
            extraction_fields,
            provider=provider_name,
            bill_type=bill_type,
        )

        build_result = Tier3ExtractionResult(
            provider=provider_name,
            fields=extraction_fields,
            field_count=len(extraction_fields),
            hit_rate=tier4.hit_rate,
            warnings=tier4.warnings,
        )

        extraction_method = " → ".join(extraction_path)
        bill = _build_bill(build_result, provider_name, confidence, extraction_method, text)

        return PipelineResult(
            bill=bill,
            confidence=confidence,
            tier0=tier0,
            provider_detection=provider_result,
            tier4=tier4,
            extraction_path=extraction_path,
        )

    # ---- Nothing worked ----
    extraction_path.append("insufficient_text")
    empty_provider = ProviderDetectionResult(
        provider_name="unknown", is_known=False,
    )
    empty_fields: dict[str, FieldExtractionResult] = {}
    empty_confidence = calculate_confidence(empty_fields)
    bill = GenericBillData(
        extraction_method="image_extraction_failed",
        confidence_score=empty_confidence.score,
        raw_text=text,
        warnings=["Image extraction failed - OCR and LLM vision produced no results"],
    )
    return PipelineResult(
        bill=bill,
        confidence=empty_confidence,
        tier0=tier0,
        provider_detection=empty_provider,
        extraction_path=extraction_path,
    )
