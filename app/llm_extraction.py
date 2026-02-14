"""
Tier 4: LLM Vision Extraction
===============================

Uses Gemini 2.0 Flash to extract structured bill data from page images.
Activated when regex/anchor extraction fails or confidence is below threshold.

Trigger conditions:
  - Unknown provider AND generic regex < 0.85 confidence
  - Photo/image input (not PDF)
  - Cross-field validation fails after all regex tiers
  - Heavily degraded scan quality (spatial extraction produces 0 fields)

Cost: ~$0.0002/page (Gemini 2.0 Flash)
"""
from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel

from pipeline import FieldExtractionResult, Tier2ExtractionResult

log = logging.getLogger(__name__)

# Fields where LLM text extraction is preferred over regex in merge conflicts
_LLM_PREFERRED_FIELDS = frozenset({
    "provider", "customer_name", "supply_address", "billing_period",
    "invoice_date",
})

# Fields where regex numeric extraction is preferred over LLM in merge conflicts
_REGEX_PREFERRED_FIELDS = frozenset({
    "subtotal", "vat_rate", "vat_amount", "total_incl_vat",
    "day_kwh", "day_rate", "night_kwh", "night_rate",
    "standing_charge", "pso_levy", "litres", "unit_price",
})

# Prompt template for structured extraction
_EXTRACTION_PROMPT = (
    "You are extracting structured data from an Irish utility/fuel bill.\n"
    "Extract the following fields as JSON. If a field is not present, use null.\n"
    "All monetary values in euros as decimal numbers. Dates in YYYY-MM-DD format.\n"
    "For MPRN: exactly 11 digits starting with 10.\n"
    "For GPRN: exactly 7 digits.\n"
    "For billing_period: use format 'YYYY-MM-DD to YYYY-MM-DD'.\n"
    "Transcribe numbers exactly as they appear - do not correct or round them."
)


# ---------------------------------------------------------------------------
# Pydantic schema for Gemini structured output
# ---------------------------------------------------------------------------

class LLMLineItem(BaseModel):
    """A single line item extracted by the LLM."""
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    line_total: Optional[float] = None


class LLMBillSchema(BaseModel):
    """Schema sent to Gemini for structured JSON output."""
    provider: Optional[str] = None
    invoice_number: Optional[str] = None
    account_number: Optional[str] = None
    mprn: Optional[str] = None
    gprn: Optional[str] = None
    invoice_date: Optional[str] = None
    billing_period: Optional[str] = None
    line_items: Optional[list[LLMLineItem]] = None
    subtotal: Optional[float] = None
    vat_rate: Optional[float] = None
    vat_amount: Optional[float] = None
    total_incl_vat: Optional[float] = None
    customer_name: Optional[str] = None
    supply_address: Optional[str] = None


# ---------------------------------------------------------------------------
# Tier 4 result
# ---------------------------------------------------------------------------

@dataclass
class Tier4ExtractionResult:
    """Result of Tier 4 LLM vision extraction."""
    fields: dict[str, FieldExtractionResult]
    field_count: int
    hit_rate: float
    warnings: list[str] = field(default_factory=list)
    llm_raw: Optional[LLMBillSchema] = None
    model_used: str = ""


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def _get_gemini_client():
    """Create a Gemini client. Requires GEMINI_API_KEY env var."""
    try:
        from google import genai
    except ImportError:
        raise RuntimeError(
            "google-genai package not installed. Run: pip install google-genai"
        )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable not set. "
            "Set it to your Google AI Studio API key."
        )

    return genai.Client(api_key=api_key)


def _get_genai_types():
    """Import google.genai types with graceful fallback error."""
    try:
        from google.genai import types
    except ImportError:
        raise RuntimeError(
            "google-genai package not installed. Run: pip install google-genai"
        )
    return types


def _image_bytes_from_pdf(source: bytes | str, page_num: int = 0) -> bytes:
    """Convert a single PDF page to JPEG bytes for vision API."""
    from pdf2image import convert_from_path, convert_from_bytes

    if isinstance(source, str):
        images = convert_from_path(
            source, first_page=page_num + 1, last_page=page_num + 1, dpi=200
        )
    else:
        images = convert_from_bytes(
            source, first_page=page_num + 1, last_page=page_num + 1, dpi=200
        )

    if not images:
        raise ValueError(f"No image generated for page {page_num}")

    buf = io.BytesIO()
    images[0].save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _image_bytes_from_file(source: bytes | str) -> tuple[bytes, str]:
    """Read image bytes and determine MIME type from a file path or bytes."""
    if isinstance(source, str):
        ext = os.path.splitext(source)[1].lower()
        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp",
            ".heic": "image/heic", ".heif": "image/heif",
        }
        mime_type = mime_map.get(ext, "image/jpeg")
        with open(source, "rb") as f:
            return f.read(), mime_type
    else:
        # Raw bytes - assume JPEG
        return source, "image/jpeg"


def _schema_to_fields(
    schema: LLMBillSchema,
    base_confidence: float = 0.75,
) -> dict[str, FieldExtractionResult]:
    """Convert LLMBillSchema to dict of FieldExtractionResult."""
    fields: dict[str, FieldExtractionResult] = {}

    # Simple string/numeric fields
    field_map = {
        "provider": schema.provider,
        "invoice_number": schema.invoice_number,
        "account_number": schema.account_number,
        "mprn": schema.mprn,
        "gprn": schema.gprn,
        "invoice_date": schema.invoice_date,
        "billing_period": schema.billing_period,
        "customer_name": schema.customer_name,
        "supply_address": schema.supply_address,
    }

    for name, value in field_map.items():
        if value is not None and str(value).strip():
            fields[name] = FieldExtractionResult(
                field_name=name,
                value=str(value).strip(),
                confidence=base_confidence,
                pattern_index=-1,  # -1 indicates LLM extraction
            )

    # Numeric fields
    numeric_map = {
        "subtotal": schema.subtotal,
        "vat_rate": schema.vat_rate,
        "vat_amount": schema.vat_amount,
        "total_incl_vat": schema.total_incl_vat,
    }

    for name, value in numeric_map.items():
        if value is not None:
            fields[name] = FieldExtractionResult(
                field_name=name,
                value=str(value),
                confidence=base_confidence,
                pattern_index=-1,
            )

    # Extract energy fields from line items
    if schema.line_items:
        for item in schema.line_items:
            if item.description is None:
                continue
            desc_lower = item.description.lower()

            if "day" in desc_lower and "energy" in desc_lower:
                if item.quantity is not None:
                    fields["day_kwh"] = FieldExtractionResult(
                        field_name="day_kwh", value=str(item.quantity),
                        confidence=base_confidence, pattern_index=-1,
                    )
                if item.unit_price is not None:
                    fields["day_rate"] = FieldExtractionResult(
                        field_name="day_rate", value=str(item.unit_price),
                        confidence=base_confidence, pattern_index=-1,
                    )
                if item.line_total is not None:
                    fields["day_cost"] = FieldExtractionResult(
                        field_name="day_cost", value=str(item.line_total),
                        confidence=base_confidence, pattern_index=-1,
                    )

            elif "night" in desc_lower and "energy" in desc_lower:
                if item.quantity is not None:
                    fields["night_kwh"] = FieldExtractionResult(
                        field_name="night_kwh", value=str(item.quantity),
                        confidence=base_confidence, pattern_index=-1,
                    )
                if item.unit_price is not None:
                    fields["night_rate"] = FieldExtractionResult(
                        field_name="night_rate", value=str(item.unit_price),
                        confidence=base_confidence, pattern_index=-1,
                    )

            elif "standing" in desc_lower:
                parts = []
                if item.quantity is not None:
                    parts.append(str(item.quantity))
                else:
                    parts.append("")
                if item.unit_price is not None:
                    parts.append(str(item.unit_price))
                else:
                    parts.append("")
                if item.line_total is not None:
                    parts.append(str(item.line_total))
                else:
                    parts.append("")
                # Format as "days - rate - total" for compatibility
                if any(parts):
                    fields["standing_charge"] = FieldExtractionResult(
                        field_name="standing_charge",
                        value=" - ".join(parts),
                        confidence=base_confidence, pattern_index=-1,
                    )

            elif "pso" in desc_lower:
                if item.line_total is not None:
                    fields["pso_levy"] = FieldExtractionResult(
                        field_name="pso_levy", value=str(item.line_total),
                        confidence=base_confidence, pattern_index=-1,
                    )

            elif any(k in desc_lower for k in ("kerosene", "oil", "fuel", "litre")):
                if item.quantity is not None:
                    fields["litres"] = FieldExtractionResult(
                        field_name="litres", value=str(item.quantity),
                        confidence=base_confidence, pattern_index=-1,
                    )
                if item.unit_price is not None:
                    fields["unit_price"] = FieldExtractionResult(
                        field_name="unit_price", value=str(item.unit_price),
                        confidence=base_confidence, pattern_index=-1,
                    )

    return fields


def extract_tier4_llm(
    source: bytes | str,
    is_image: bool = False,
    model: str = "gemini-2.0-flash",
) -> Tier4ExtractionResult:
    """Extract bill data using Gemini vision.

    Args:
        source: PDF file path/bytes, or image file path/bytes.
        is_image: If True, treat source as a direct image (not PDF).
        model: Gemini model to use.

    Returns:
        Tier4ExtractionResult with extracted fields.

    Raises:
        RuntimeError: If API key not set or google-genai not installed.
    """
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError(
            "GEMINI_API_KEY environment variable not set. "
            "Set it to your Google AI Studio API key."
        )

    types = _get_genai_types()
    client = _get_gemini_client()
    warnings: list[str] = []

    # Get image bytes
    if is_image:
        image_bytes, mime_type = _image_bytes_from_file(source)
    else:
        try:
            max_pages_raw = os.environ.get("LLM_MAX_PDF_PAGES", "3").strip()
            try:
                max_pages = max(1, int(max_pages_raw))
            except ValueError:
                max_pages = 3

            page_count = 1
            try:
                import pymupdf
                if isinstance(source, str):
                    with pymupdf.open(source) as doc:
                        page_count = max(1, doc.page_count)
                else:
                    with pymupdf.open(stream=source, filetype="pdf") as doc:
                        page_count = max(1, doc.page_count)
            except Exception:
                page_count = 1

            page_limit = min(page_count, max_pages)
            image_bytes_list = [
                _image_bytes_from_pdf(source, page_num=i)
                for i in range(page_limit)
            ]
            image_bytes = image_bytes_list[0]
            mime_type = "image/jpeg"
            if page_count > page_limit:
                warnings.append(
                    f"LLM PDF context truncated to first {page_limit} of {page_count} pages"
                )
        except Exception as e:
            log.warning("PDF to image conversion failed: %s", e)
            return Tier4ExtractionResult(
                fields={}, field_count=0, hit_rate=0.0,
                warnings=[f"PDF conversion failed: {e}"],
                model_used=model,
            )

    # Call Gemini with structured output
    try:
        content_parts = []
        if is_image:
            content_parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
        else:
            for page_img in image_bytes_list:
                content_parts.append(types.Part.from_bytes(data=page_img, mime_type=mime_type))

        if not is_image and len(content_parts) > 1:
            _EXTRACTION_PROMPT_MULTI = _EXTRACTION_PROMPT + (
                "\nThe bill spans multiple pages. Combine fields across all pages; "
                "prefer totals from final summary sections when duplicates exist."
            )
            prompt = _EXTRACTION_PROMPT_MULTI
        else:
            prompt = _EXTRACTION_PROMPT

        response = client.models.generate_content(
            model=model,
            contents=[*content_parts, prompt],
            config={
                "response_mime_type": "application/json",
                "response_schema": LLMBillSchema,
            },
        )

        response_text = response.text
        if not response_text:
            response_text = "{}"
        parsed = LLMBillSchema.model_validate_json(response_text)
    except Exception as e:
        log.warning("Gemini extraction failed: %s", e)
        return Tier4ExtractionResult(
            fields={}, field_count=0, hit_rate=0.0,
            warnings=[f"LLM extraction failed: {e}"],
            model_used=model,
        )

    # Convert schema to FieldExtractionResult dict
    fields = _schema_to_fields(parsed)

    # Count against a reasonable total (20 possible fields)
    total_possible = 20
    hit_rate = len(fields) / total_possible if total_possible > 0 else 0.0

    return Tier4ExtractionResult(
        fields=fields,
        field_count=len(fields),
        hit_rate=hit_rate,
        warnings=warnings,
        llm_raw=parsed,
        model_used=model,
    )


# ---------------------------------------------------------------------------
# Merge strategy: combine regex/spatial results with LLM results
# ---------------------------------------------------------------------------

def _values_equivalent(val1: str, val2: str) -> bool:
    """Check if two extracted values are equivalent."""
    v1 = val1.strip().replace(",", "").lstrip("$").strip()
    v2 = val2.strip().replace(",", "").lstrip("$").strip()

    if v1 == v2:
        return True

    try:
        return abs(float(v1) - float(v2)) < 0.01
    except (ValueError, TypeError):
        return v1.lower() == v2.lower()


def merge_llm_with_existing(
    llm_fields: dict[str, FieldExtractionResult],
    existing_fields: dict[str, FieldExtractionResult],
    prefer_llm: bool = False,
) -> dict[str, FieldExtractionResult]:
    """Merge LLM extraction results with existing regex/spatial results.

    Strategy:
      - If only one source found it: use that source
      - If both agree: boost confidence (+0.1, capped at 1.0)
      - If they disagree:
          - When prefer_llm=False (default): prefer regex for numeric fields
          - When prefer_llm=True (escalation): prefer LLM for all fields
            since we're in the escalation path because existing extraction
            was unreliable.

    Args:
        llm_fields: Fields from Tier 4 LLM extraction.
        existing_fields: Fields from Tier 2/3 regex/spatial extraction.
        prefer_llm: When True, prefer LLM for ALL disagreements (used in
            escalation path where existing extraction has low confidence).

    Returns:
        Merged dict of FieldExtractionResult.
    """
    merged = dict(existing_fields)

    for field_name, llm_field in llm_fields.items():
        if field_name not in merged:
            # Only LLM found it - use LLM
            merged[field_name] = llm_field
        else:
            existing = merged[field_name]
            if _values_equivalent(existing.value, llm_field.value):
                # Both agree: boost confidence (cross-validated)
                merged[field_name] = FieldExtractionResult(
                    field_name=field_name,
                    value=existing.value,
                    confidence=min(
                        max(existing.confidence, llm_field.confidence) + 0.1,
                        1.0,
                    ),
                    pattern_index=existing.pattern_index,
                )
            else:
                # Disagree: choose based on context
                if prefer_llm or field_name in _LLM_PREFERRED_FIELDS:
                    merged[field_name] = llm_field
                else:
                    # Keep existing (regex/spatial) for numeric and other fields
                    pass

    return merged
