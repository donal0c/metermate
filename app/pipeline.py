"""
Generic Bill Extraction Pipeline
=================================

Tiered extraction pipeline for Irish utility bills (electricity, gas, heating oil).
Each tier handles progressively harder cases:

  Tier 0: Native text detection via PyMuPDF (this module)
  Tier 1: Provider detection via keyword matching (this module)
  Tier 2: Generic regex + anchor-based extraction (future)
  Tier 3: Config-driven provider-specific regex (this module)
  Tier 4: LLM vision fallback (future)

  Cross-cutting: Confidence scoring and cross-field validation (this module)

See research_generic_pipeline_output.txt for design rationale.
"""
from __future__ import annotations

import re
import pymupdf
from dataclasses import dataclass, field
from typing import Optional

from provider_configs import get_provider_config, PROVIDER_CONFIGS


# ---------------------------------------------------------------------------
# Tier 0: Native text detection
# ---------------------------------------------------------------------------

@dataclass
class TextExtractionResult:
    """Result of Tier 0 text extraction."""
    is_native_text: bool
    extracted_text: str
    chars_per_page: list[int]
    page_count: int
    metadata: dict


def extract_text_tier0(
    source: bytes | str,
    *,
    native_threshold: int = 100,
) -> TextExtractionResult:
    """Detect whether a PDF has native/embedded text and extract it.

    Args:
        source: PDF file path (str) or raw PDF bytes.
        native_threshold: Minimum average chars per page to classify as native
            text. Default 100 (proven on Go Power, ESB Networks, Energia).

    Returns:
        TextExtractionResult with classification and extracted text.

    Raises:
        ValueError: If source is empty or not a valid PDF.
        RuntimeError: If PyMuPDF cannot open the document.
    """
    doc = _open_document(source)

    try:
        if doc.page_count == 0:
            return TextExtractionResult(
                is_native_text=False,
                extracted_text="",
                chars_per_page=[],
                page_count=0,
                metadata=_extract_metadata(doc),
            )

        page_texts: list[str] = []
        chars_per_page: list[int] = []

        for page in doc:
            text = page.get_text()
            page_texts.append(text)
            chars_per_page.append(len(text.strip()))

        full_text = "\n\n".join(page_texts)
        avg_chars = sum(chars_per_page) / len(chars_per_page)
        is_native = avg_chars >= native_threshold

        return TextExtractionResult(
            is_native_text=is_native,
            extracted_text=full_text,
            chars_per_page=chars_per_page,
            page_count=doc.page_count,
            metadata=_extract_metadata(doc),
        )
    finally:
        doc.close()


def _open_document(source: bytes | str) -> pymupdf.Document:
    """Open a PDF from path or bytes, with validation."""
    if isinstance(source, str):
        try:
            return pymupdf.open(source)
        except Exception as e:
            raise RuntimeError(f"Cannot open PDF file '{source}': {e}") from e
    elif isinstance(source, (bytes, bytearray)):
        if not source:
            raise ValueError("PDF bytes are empty")
        try:
            return pymupdf.open(stream=source, filetype="pdf")
        except Exception as e:
            raise RuntimeError(f"Cannot open PDF from bytes: {e}") from e
    else:
        raise TypeError(f"source must be str (path) or bytes, got {type(source).__name__}")


def _extract_metadata(doc: pymupdf.Document) -> dict:
    """Extract PDF metadata for diagnostics."""
    return {
        "creator": doc.metadata.get("creator", ""),
        "producer": doc.metadata.get("producer", ""),
        "page_count": doc.page_count,
    }


# ---------------------------------------------------------------------------
# Tier 1: Provider detection via keyword matching
# ---------------------------------------------------------------------------

# Ordered by specificity (longer/more-specific keywords first within each provider).
# Provider order matters for tie-breaking: more common Irish providers first.
PROVIDER_KEYWORDS: dict[str, list[str]] = {
    "Electric Ireland": ["electric ireland", "electricireland.ie"],
    "SSE Airtricity": ["sse airtricity", "airtricity", "sseairtricity.com"],
    "Bord Gais": ["bord gáis", "bord gais", "bordgais", "bordgaisenergy.ie"],
    "Kerry Petroleum": ["kerry petroleum"],
    "Energia": ["energia", "energia.ie"],
    "ESB Networks": ["esb networks", "esb network"],
    "Go Power": ["go power", "gopower", "gopower.ie"],
    "Flogas": ["flogas", "flogas.ie"],
    "Calor Gas": ["calor gas", "calor"],
    "Pinergy": ["pinergy", "pinergy.ie"],
    "Prepay Power": ["prepay power", "prepaypower"],
    "Panda Power": ["panda power", "pandapower.ie"],
    "Bright": ["bright energy"],
    "Community Power": ["community power"],
    "Iberdrola": ["iberdrola"],
    "Yuno Energy": ["yuno", "yunoenergy.ie"],
}


@dataclass
class ProviderDetectionResult:
    """Result of Tier 1 provider detection."""
    provider_name: str
    is_known: bool
    matched_keyword: Optional[str] = None


def detect_provider(text: str) -> ProviderDetectionResult:
    """Detect which utility provider issued a bill from extracted text.

    Algorithm:
      1. Lowercase the full text.
      2. For each provider, count total keyword occurrences in the text.
      3. The provider with the highest total occurrence count wins.
      4. Ties are broken by provider priority order (position in PROVIDER_KEYWORDS).
      5. If no keyword matches at all: return ('unknown', False).

    This frequency-based approach correctly handles bills where provider X
    legitimately mentions provider Y (e.g., Go Power bills say "ESB Networks"
    in emergency contact info, but mention "Go Power" far more often).

    Args:
        text: Extracted text from the bill PDF.

    Returns:
        ProviderDetectionResult with provider name and known flag.
    """
    if not text or not text.strip():
        return ProviderDetectionResult(
            provider_name="unknown",
            is_known=False,
        )

    text_lower = text.lower()

    # Score each provider by total keyword occurrences.
    # To avoid double-counting substring pairs (e.g. "esb network" within
    # "esb networks"), we skip a keyword if a longer keyword for the same
    # provider is also a substring match AND actually appears in the text.
    best_provider: str | None = None
    best_score: int = 0
    best_keyword: str | None = None

    for provider, keywords in PROVIDER_KEYWORDS.items():
        kws_lower = [kw.lower() for kw in keywords]

        # First pass: find which keywords actually match
        matched_kws = [(kw, kws_lower[i]) for i, kw in enumerate(keywords)
                       if kws_lower[i] in text_lower]
        if not matched_kws:
            continue

        # Second pass: remove keywords that are substrings of another
        # matched keyword (only suppress if the longer one is also matched)
        filtered: list[tuple[str, str]] = []
        for orig, kw_low in matched_kws:
            suppressed = any(
                kw_low in other_low and kw_low != other_low
                for _, other_low in matched_kws
            )
            if not suppressed:
                filtered.append((orig, kw_low))

        # If filtering removed everything (all are substrings of each other),
        # keep the longest
        if not filtered:
            filtered = [max(matched_kws, key=lambda x: len(x[1]))]

        provider_score = sum(text_lower.count(kw_low) for _, kw_low in filtered)
        longest_orig = max(filtered, key=lambda x: len(x[0]))[0]

        # Strictly greater — ties broken by dict insertion order (priority)
        if provider_score > best_score:
            best_score = provider_score
            best_provider = provider
            best_keyword = longest_orig

    if best_provider is not None:
        return ProviderDetectionResult(
            provider_name=best_provider,
            is_known=True,
            matched_keyword=best_keyword,
        )

    return ProviderDetectionResult(
        provider_name="unknown",
        is_known=False,
    )


# ---------------------------------------------------------------------------
# Tier 3: Config-driven provider-specific regex extraction
# ---------------------------------------------------------------------------

@dataclass
class FieldExtractionResult:
    """Result for a single extracted field."""
    field_name: str
    value: str
    confidence: float
    pattern_index: int  # which pattern matched (0-based)


@dataclass
class Tier3ExtractionResult:
    """Result of Tier 3 config-driven extraction."""
    provider: str
    fields: dict[str, FieldExtractionResult]
    field_count: int
    hit_rate: float  # fraction of config fields that matched
    warnings: list[str] = field(default_factory=list)


# ---- Preprocessing hooks ----

_PREPROCESS_HOOKS: dict[str, object] = {}


def register_preprocess(name: str):
    """Decorator to register a text preprocessing hook."""
    def decorator(fn):
        _PREPROCESS_HOOKS[name] = fn
        return fn
    return decorator


@register_preprocess("energia_normalize")
def _preprocess_energia(text: str) -> str:
    """Normalize OCR artifacts common in scanned Energia bills."""
    t = text
    # Replace euro-word OCR artifacts with euro sign
    t = re.sub(r'\b[eEc][uU][rR][oO]\b', '€', t)
    # Clean up @ sign artifacts
    t = re.sub(r'@[\s_~=]+', '@ ', t)
    # Replace colon with period in monetary contexts
    t = re.sub(r'(€[\d,]+):(\d{2})', r'\1.\2', t)
    t = re.sub(r'(\d,\d+):(\d{2})\b', r'\1.\2', t)
    # Handle OCR typos
    t = re.sub(r'\bTatal\b', 'Total', t)
    t = re.sub(r'\bXWh\b', 'kWh', t)
    t = re.sub(r'\bxWh\b', 'kWh', t)
    # Normalize multiple spaces
    t = re.sub(r'  +', ' ', t)
    return t


@register_preprocess("kerry_normalize")
def _preprocess_kerry(text: str) -> str:
    """Normalize OCR artifacts common in scanned Kerry Petroleum invoices."""
    t = text
    # Replace pipe/dash table separators with spaces
    t = re.sub(r'\s*[|—]\s*', ' ', t)
    # Remove thousand separators in numbers
    t = re.sub(r'(\d),(\d)', r'\1\2', t)
    # Normalize multiple spaces
    t = re.sub(r'  +', ' ', t)
    return t


# ---- Value transforms ----

def _apply_transform(value: str, transform: str | None) -> str:
    """Apply a post-extraction transform to a captured value."""
    if transform is None:
        return value
    if transform == "strip_commas":
        return value.replace(",", "")
    if transform == "strip_spaces":
        return value.replace(" ", "")
    return value


# ---- Core extraction engine ----

def extract_with_config(text: str, provider_name: str) -> Tier3ExtractionResult:
    """Extract fields from text using a provider's config-driven regex patterns.

    Args:
        text: Full extracted text from the bill.
        provider_name: Provider name (must have a config in PROVIDER_CONFIGS).

    Returns:
        Tier3ExtractionResult with extracted fields and hit rate.

    Raises:
        ValueError: If no config found for the provider.
    """
    config = get_provider_config(provider_name)
    if config is None:
        raise ValueError(f"No Tier 3 config for provider: {provider_name}")

    # Apply preprocessing if configured
    preprocess_name = config.get("preprocess")
    if preprocess_name and preprocess_name in _PREPROCESS_HOOKS:
        text = _PREPROCESS_HOOKS[preprocess_name](text)

    fields_config = config["fields"]
    extracted: dict[str, FieldExtractionResult] = {}
    warnings: list[str] = []

    for field_name, field_cfg in fields_config.items():
        patterns = field_cfg["patterns"]
        confidence = field_cfg.get("confidence", 0.5)
        transform = field_cfg.get("transform")
        multi_match = field_cfg.get("multi_match", False)

        for pat_idx, (anchor_re, value_re) in enumerate(patterns):
            search_text = text

            # If anchor regex is provided, narrow the search region
            if anchor_re:
                anchor_match = re.search(anchor_re, text, re.IGNORECASE | re.DOTALL)
                if not anchor_match:
                    continue
                # Search from anchor position onward (up to 500 chars)
                start = anchor_match.start()
                search_text = text[start:start + 500]

            if multi_match:
                # For multi-match fields (e.g. ESB standing charge periods)
                all_matches = re.findall(value_re, search_text, re.IGNORECASE)
                if all_matches:
                    capture_groups = field_cfg.get("capture_groups", {})

                    # If capture_groups defines "days" and "rate",
                    # aggregate the multiple periods into a single
                    # "days - rate - total" string that the orchestrator
                    # can parse like a single-match standing charge.
                    # When "total" is also in capture_groups, sum the
                    # explicit totals; otherwise compute from days*rate.
                    if "days" in capture_groups and "rate" in capture_groups:
                        days_idx = capture_groups["days"] - 1
                        rate_idx = capture_groups["rate"] - 1
                        total_idx = (capture_groups["total"] - 1
                                     if "total" in capture_groups else None)
                        total_days = 0.0
                        total_charge = 0.0
                        valid = True
                        for m in all_matches:
                            parts = m if isinstance(m, tuple) else (m,)
                            try:
                                d = float(parts[days_idx])
                                r = float(parts[rate_idx])
                                total_days += d
                                if total_idx is not None:
                                    total_charge += float(parts[total_idx])
                                else:
                                    total_charge += d * r
                            except (ValueError, IndexError):
                                valid = False
                                break
                        if valid and total_days > 0:
                            avg_rate = total_charge / total_days
                            value = (
                                f"{int(total_days)} - "
                                f"{avg_rate:.4f} - "
                                f"{total_charge:.2f}"
                            )
                            extracted[field_name] = FieldExtractionResult(
                                field_name=field_name,
                                value=value,
                                confidence=confidence,
                                pattern_index=pat_idx,
                            )
                            break

                    # Default multi_match: semicolon-joined raw values
                    joined = "; ".join(
                        _apply_transform(
                            " ".join(m) if isinstance(m, tuple) else m,
                            transform,
                        )
                        for m in all_matches
                    )
                    extracted[field_name] = FieldExtractionResult(
                        field_name=field_name,
                        value=joined,
                        confidence=confidence,
                        pattern_index=pat_idx,
                    )
                    break
            else:
                m = re.search(value_re, search_text, re.IGNORECASE | re.MULTILINE)
                if m:
                    # Guard: pattern must have at least one capture group
                    if m.lastindex is None or m.lastindex < 1:
                        continue

                    # Use all captured groups
                    if m.lastindex > 1:
                        # Multiple capture groups → join with " - "
                        value = " - ".join(
                            _apply_transform(g, transform)
                            for g in m.groups() if g is not None
                        )
                    else:
                        value = _apply_transform(m.group(1), transform)

                    extracted[field_name] = FieldExtractionResult(
                        field_name=field_name,
                        value=value,
                        confidence=confidence,
                        pattern_index=pat_idx,
                    )
                    break

    total_fields = len(fields_config)
    hit_count = len(extracted)
    hit_rate = hit_count / total_fields if total_fields > 0 else 0.0

    return Tier3ExtractionResult(
        provider=provider_name,
        fields=extracted,
        field_count=hit_count,
        hit_rate=hit_rate,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Tier 2: Universal regex extraction for unknown providers
# ---------------------------------------------------------------------------

# Universal patterns that work across any Irish utility/fuel bill.
# Each entry: field_name -> list of (regex_pattern, confidence, transform)
# Patterns are tried in order; first match wins.

TIER2_UNIVERSAL_PATTERNS: dict[str, list[tuple[str, float, str | None]]] = {
    "mprn": [
        (r"(?:MPRN|Meter\s*Point\s*Ref(?:erence)?)\s*(?:No\.?|Number)?\s*[:\-]?\s*(10\d{9})", 0.90, None),
        # ESB-style MPRN with spaces: "10 305 584 286"
        (r"(10[\s]*\d[\s]*\d[\s]*\d[\s]*\d[\s]*\d[\s]*\d[\s]*\d[\s]*\d[\s]*\d)", 0.75, "strip_spaces"),
        (r"\b(10\d{9})\b", 0.70, None),
    ],
    "gprn": [
        (r"(?:GPRN|Gas\s*Point\s*Reg(?:istration)?)\s*(?:No\.?|Number)?\s*[:\-]?\s*(\d{7})\b", 0.85, None),
    ],
    "account_number": [
        (r"(?:Account|Acct|A/C)\s*(?:Number|No\.?|Code|Num)\s*[:\-]?\s*([\w\-/]{4,20})", 0.80, "strip_spaces"),
        (r"Customer\s*(?:Number|No\.?)\s*[:\-]?\s*([\w\-/]{4,20})", 0.75, "strip_spaces"),
        (r"Client\s*(?:Number|No\.?)\s*[:\-]?\s*([\w\-/]{4,20})", 0.70, "strip_spaces"),
        # ESB multiline: "Your account number\n...\n903921399"
        (r"(?:Your\s+)?account\s*number\s*\n[^\n]*\n\s*(\d{6,10})", 0.70, None),
    ],
    "invoice_number": [
        (r"(?:Invoice|Bill)\s*(?:No\.?|Number|Num)\s*[:\-]?\s*(\d[\w\-/]{3,20})", 0.80, None),
        (r"(?:Reference|Document)\s*(?:No\.?|Number)\s*[:\-]?\s*(\d[\w\-/]{3,20})", 0.70, None),
    ],
    "billing_period": [
        (r"(?:Billing|Bill|Usage|Accounting)\s*[Pp]eriod\s*[:\s]*(\d{1,2}\s+\w+\s+\d{2,4}\s*(?:to|-)\s*\d{1,2}\s+\w+\s+\d{2,4})", 0.85, None),
        (r"(?:Billing|Bill)\s*[Pp]eriod\s*[:\s]*(\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/\d{2}/\d{4})", 0.85, None),
        # ESB multiline: "Billing period\n---\n29 Feb 24 to 30 Apr 24"
        (r"Billing\s*period\s*\n[^\n]*\n\s*(\d{1,2}\s+\w+\s+\d{2,4}\s+to\s+\d{1,2}\s+\w+\s+\d{2,4})", 0.80, None),
    ],
    "invoice_date": [
        (r"(?:Invoice|Bill)\s*Date\s*[:\-]?\s*(\d{1,2}\s+\w+\s+\d{4})", 0.80, None),
        (r"(?:Invoice|Bill)\s*Date\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{2,4})", 0.80, None),
        (r"Date\s*(?:of\s*(?:this\s*)?(?:Invoice|Bill))?\s*[:\-]?\s*(\d{1,2}\s+\w+\s+\d{4})", 0.70, None),
    ],
    "subtotal": [
        (r"Total\s+Excl(?:uding)?\s*VAT\s*[:\s]*[€\u20ac]?\s*([\d,]+\.\d{2})", 0.85, "strip_commas"),
        (r"Sub\s*[Tt]otal\s*(?:before\s*VAT)?\s*[:\s]*[€\u20ac]?\s*([\d,]+\.\d{2})", 0.85, "strip_commas"),
        (r"Net\s+(?:Total|Amount)\s*[:\s]*[€\u20ac]?\s*([\d,]+\.\d{2})", 0.80, "strip_commas"),
        (r"(?:Total|Amount)\s+(?:Ex|Before)\s*VAT\s*[:\s]*[€\u20ac]?\s*([\d,]+\.\d{2})", 0.80, "strip_commas"),
        (r"Total\s+electricity\s+charges\s+([\d,.]+)", 0.75, "strip_commas"),
    ],
    "vat_rate": [
        (r"(?:VAT|V\.A\.T\.?)\s*(?:@|at)?\s*(\d{1,2}(?:\.\d{1,2})?)\s*%", 0.85, None),
        # ESB multiline: "VAT\n780.83\n9% on ..."
        (r"VAT\s+\d+\.\d+\s+(\d+)%", 0.80, None),
    ],
    "vat_amount": [
        (r"(?:VAT|V\.A\.T\.?)\s*(?:@|at)?\s*\d{1,2}(?:\.\d{1,2})?\s*%\s*[^\d]*?[€\u20ac]?\s*([\d,]+\.\d{2})", 0.85, "strip_commas"),
        # ESB multiline: "VAT\n780.83\n9%"
        (r"VAT\s+(\d+\.\d{2})\s+\d+%", 0.80, "strip_commas"),
    ],
    "total_incl_vat": [
        (r"Total\s+(?:Charges?\s+)?(?:[Ff]or\s+)?(?:[Tt]h(?:is|e)\s+[Pp]eriod)\s*[:\s]*[€\u20ac]?\s*([\d,]+\.\d{2})", 0.85, "strip_commas"),
        (r"(?:Amount|Balance)\s+Due\s*[:\s]*[€\u20ac]?\s*([\d,]+\.\d{2})", 0.80, "strip_commas"),
        (r"(?:Grand|Invoice)\s+Total\s*[:\s]*[€\u20ac]?\s*([\d,]+\.\d{2})", 0.80, "strip_commas"),
        (r"Total\s+(?:Inc(?:luding|l\.?)\s*VAT)\s*[:\s]*[€\u20ac]?\s*([\d,]+\.\d{2})", 0.80, "strip_commas"),
        (r"NEW\s+BALANCE\s+DUE\s*[:\s]*[€\u20ac]?\s*([\d,]+\.\d{2})", 0.75, "strip_commas"),
        (r"Total\s+(?:due|balance\s+due)\s*[:\s]*[€\u20ac]?\s*([\d,]+\.\d{2})", 0.75, "strip_commas"),
    ],
    "day_kwh": [
        (r"Day\s+(?:Energy|Rate)\s+(\d[\d,]*)\s*(?:kWh|xWh)", 0.80, "strip_commas"),
        (r"Energy\s+(\d[\d,]*)\s*kWh\s+\d+\.\d+", 0.70, "strip_commas"),
    ],
    "day_rate": [
        (r"Day\s+(?:Energy|Rate)\s+\d[\d,]*\s*(?:kWh|xWh)\s*@\s*[€\u20ac]?\s*(\d+\.\d+)", 0.80, None),
        (r"Energy\s+\d[\d,]*\s*kWh\s+(\d+\.\d+)\s*[€\u20ac]", 0.70, None),
    ],
    "night_kwh": [
        (r"Night\s+(?:Energy|Rate)\s+(\d[\d,]*)\s*(?:kWh|xWh)", 0.80, "strip_commas"),
    ],
    "night_rate": [
        (r"Night\s+(?:Energy|Rate)\s+\d[\d,]*\s*(?:kWh|xWh)\s*@\s*[€\u20ac]?\s*(\d+\.\d+)", 0.80, None),
    ],
    "standing_charge": [
        (r"Standing\s*Charge\s*.*?[€\u20ac]\s*(\d+[\d,.]*\.\d{2})", 0.75, "strip_commas"),
    ],
    "pso_levy": [
        (r"PSO\s+Levy.*?[€\u20ac]?\s*(\d+[\d,.]*\.\d{2})", 0.75, None),
        (r"Public\s*Service\s*Obligation\s*Levy.*?[€\u20ac](\d+\.\d+)", 0.70, None),
    ],
    "litres": [
        (r"(?:KEROSENE|[Hh]eating\s*[Oo]il|[Gg]as\s*[Oo]il)\s+(\d{2,5})\s+\d+\.\d{2}", 0.75, None),
    ],
    "unit_price": [
        (r"(?:KEROSENE|[Hh]eating\s*[Oo]il|[Gg]as\s*[Oo]il)\s+\d{2,5}\s+(\d+\.\d{2})\s+\d+\.\d{2}", 0.70, None),
    ],
    "mcc_code": [
        (r"MCC\s*(\d+)", 0.85, None),
    ],
    "dg_code": [
        (r"(DG\d+)", 0.85, None),
    ],
}


@dataclass
class Tier2ExtractionResult:
    """Result of Tier 2 universal regex extraction."""
    fields: dict[str, FieldExtractionResult]
    field_count: int
    hit_rate: float  # fraction of universal fields that matched
    warnings: list[str] = field(default_factory=list)


def extract_tier2_universal(text: str) -> Tier2ExtractionResult:
    """Extract fields using universal regex patterns (provider-agnostic).

    Tries generic patterns that work across any Irish utility/fuel bill.
    Designed for unknown providers or as a supplement to Tier 3.

    Args:
        text: Extracted text from the bill.

    Returns:
        Tier2ExtractionResult with extracted fields and hit rate.
    """
    extracted: dict[str, FieldExtractionResult] = {}
    warnings: list[str] = []

    for field_name, patterns in TIER2_UNIVERSAL_PATTERNS.items():
        for pat_idx, (pattern, confidence, transform) in enumerate(patterns):
            m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if m:
                if m.lastindex is None or m.lastindex < 1:
                    continue
                value = m.group(1)
                if transform:
                    value = _apply_transform(value, transform)
                extracted[field_name] = FieldExtractionResult(
                    field_name=field_name,
                    value=value,
                    confidence=confidence,
                    pattern_index=pat_idx,
                )
                break

    total_fields = len(TIER2_UNIVERSAL_PATTERNS)
    hit_count = len(extracted)
    hit_rate = hit_count / total_fields if total_fields > 0 else 0.0

    return Tier2ExtractionResult(
        fields=extracted,
        field_count=hit_count,
        hit_rate=hit_rate,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Confidence scoring and cross-field validation
# ---------------------------------------------------------------------------

# -- Expected field profiles by bill type --

FIELD_PROFILES: dict[str, set[str]] = {
    "electricity": {
        "mprn", "account_number", "billing_period",
        "day_kwh", "day_rate", "standing_charge",
        "subtotal", "vat_rate", "vat_amount", "total_incl_vat",
    },
    "gas": {
        "gprn", "account_number", "billing_period",
        "subtotal", "vat_rate", "vat_amount", "total_incl_vat",
    },
    "fuel": {
        "invoice_number", "invoice_date", "litres", "unit_price",
        "subtotal", "vat_rate", "vat_amount", "total_incl_vat",
    },
}

# Map providers to their bill type
PROVIDER_BILL_TYPE: dict[str, str] = {
    "Energia": "electricity",
    "Go Power": "electricity",
    "ESB Networks": "electricity",
    "Electric Ireland": "electricity",
    "SSE Airtricity": "electricity",
    "Bord Gais": "gas",
    "Flogas": "fuel",
    "Kerry Petroleum": "fuel",
    "Calor Gas": "fuel",
    "Pinergy": "electricity",
    "Prepay Power": "electricity",
    "Panda Power": "electricity",
    "Bright": "electricity",
    "Community Power": "electricity",
    "Iberdrola": "electricity",
    "Yuno Energy": "electricity",
}


@dataclass
class ValidationCheck:
    """Result of a single cross-field validation check."""
    name: str
    passed: bool
    message: str


@dataclass
class ConfidenceResult:
    """Document-level confidence assessment."""
    score: float
    band: str  # "accept", "accept_with_review", "escalate"
    fields_found: int
    expected_fields: int
    validation_checks: list[ValidationCheck]
    validation_pass_rate: float
    field_coverage: float


def _safe_float(value: str | None) -> float | None:
    """Try to parse a string as a float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(value.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def validate_cross_fields(
    fields: dict[str, FieldExtractionResult],
) -> list[ValidationCheck]:
    """Run cross-field validation checks on extracted fields.

    Checks:
      1. subtotal + vat_amount ≈ total_incl_vat (tolerance 0.02)
      2. vat_amount ≈ subtotal * vat_rate / 100 (tolerance 5%)
      3. MPRN format (11 digits, starts with 10)
      4. Total is positive and reasonable (< 100,000)
      5. VAT rate is in expected range (0-23%)
    """
    checks: list[ValidationCheck] = []

    # 1. Totals cross-check: subtotal + vat = total
    subtotal = _safe_float(fields.get("subtotal", FieldExtractionResult("", "", 0, 0)).value)
    vat_amount = _safe_float(fields.get("vat_amount", FieldExtractionResult("", "", 0, 0)).value)
    total = _safe_float(fields.get("total_incl_vat", FieldExtractionResult("", "", 0, 0)).value)

    if subtotal is not None and vat_amount is not None and total is not None:
        expected_total = subtotal + vat_amount
        diff = abs(expected_total - total)
        passed = diff <= 0.02
        checks.append(ValidationCheck(
            name="totals_crosscheck",
            passed=passed,
            message=f"subtotal({subtotal}) + vat({vat_amount}) = {expected_total}, total={total}, diff={diff:.2f}",
        ))
    elif total is not None:
        checks.append(ValidationCheck(
            name="totals_crosscheck",
            passed=False,
            message="Missing subtotal or vat_amount for cross-check",
        ))

    # 2. VAT math: vat_amount ≈ subtotal * vat_rate / 100
    vat_rate = _safe_float(fields.get("vat_rate", FieldExtractionResult("", "", 0, 0)).value)
    if subtotal is not None and vat_rate is not None and vat_amount is not None:
        expected_vat = subtotal * vat_rate / 100.0
        diff = abs(expected_vat - vat_amount)
        tolerance = max(0.05, subtotal * 0.01)  # 1% of subtotal or 5 cent
        passed = diff <= tolerance
        checks.append(ValidationCheck(
            name="vat_math",
            passed=passed,
            message=f"subtotal({subtotal}) * {vat_rate}% = {expected_vat:.2f}, actual vat={vat_amount}, diff={diff:.2f}",
        ))

    # 3. MPRN format
    mprn_val = fields.get("mprn")
    if mprn_val is not None:
        mprn = mprn_val.value.replace(" ", "")
        valid = len(mprn) == 11 and mprn.isdigit() and mprn.startswith("10")
        checks.append(ValidationCheck(
            name="mprn_format",
            passed=valid,
            message=f"MPRN '{mprn}' {'valid' if valid else 'invalid'} (expect 11 digits starting with 10)",
        ))

    # 4. Total is positive and reasonable
    if total is not None:
        reasonable = 0 <= total < 100_000
        checks.append(ValidationCheck(
            name="total_reasonable",
            passed=reasonable,
            message=f"Total {total} {'reasonable' if reasonable else 'out of range (0, 100000)'}",
        ))

    # 5. VAT rate in expected range
    if vat_rate is not None:
        valid_rate = 0 <= vat_rate <= 23
        checks.append(ValidationCheck(
            name="vat_rate_range",
            passed=valid_rate,
            message=f"VAT rate {vat_rate}% {'in range' if valid_rate else 'out of range [0, 23]'}",
        ))

    return checks


def _infer_bill_type_from_fields(fields: dict[str, FieldExtractionResult]) -> str | None:
    """Infer bill type from extracted field names when provider is unknown.

    Uses type-specific 'signature' fields to determine the most likely bill type.
    Returns None if no clear signal is found (caller should use best-match logic).
    """
    field_names = set(fields.keys())

    # Signature fields unique to each bill type
    electricity_signals = {"mprn", "day_kwh", "day_rate", "night_kwh", "night_rate"}
    gas_signals = {"gprn"}
    fuel_signals = {"litres", "unit_price", "invoice_number"}

    elec_hits = len(field_names & electricity_signals)
    gas_hits = len(field_names & gas_signals)
    fuel_hits = len(field_names & fuel_signals)

    # Require at least one signal hit; pick the type with the most hits
    best_hits = max(elec_hits, gas_hits, fuel_hits)
    if best_hits == 0:
        return None

    # Resolve ties by returning None (will fall through to best-match)
    candidates = []
    if elec_hits == best_hits:
        candidates.append("electricity")
    if gas_hits == best_hits:
        candidates.append("gas")
    if fuel_hits == best_hits:
        candidates.append("fuel")

    if len(candidates) == 1:
        return candidates[0]
    return None  # Ambiguous -- use best-match logic


def _best_match_bill_type(fields: dict[str, FieldExtractionResult]) -> str:
    """Pick the bill type profile with the highest field coverage.

    Used as a last resort when neither the provider nor field signatures
    give a clear answer.  This avoids defaulting to electricity and biasing
    confidence for unknown gas/fuel bills.
    """
    field_names = set(fields.keys())
    best_type = "electricity"
    best_coverage = -1.0

    for btype, expected in FIELD_PROFILES.items():
        if not expected:
            continue
        coverage = len(field_names & expected) / len(expected)
        if coverage > best_coverage:
            best_coverage = coverage
            best_type = btype

    return best_type


def calculate_confidence(
    fields: dict[str, FieldExtractionResult],
    provider: str | None = None,
    bill_type: str | None = None,
    avg_ocr_confidence: float | None = None,
) -> ConfidenceResult:
    """Calculate document-level confidence score.

    Score formula:
      score = field_coverage * 0.4
            + validation_pass_rate * 0.4
            + ocr_confidence * 0.2

    Thresholds:
      score >= 0.85 → "accept"
      score >= 0.60 → "accept_with_review"
      score < 0.60  → "escalate"

    Args:
        fields: Extracted field results from Tier 3.
        provider: Provider name (used to determine bill type).
        bill_type: Explicit bill type ("electricity", "gas", "fuel").
            If not given, inferred from provider or from extracted fields.
        avg_ocr_confidence: Average OCR word confidence (0-100 scale).
            If None, OCR component gets 0.5 (neutral).
    """
    # Determine expected fields
    if bill_type is None and provider is not None:
        bill_type = PROVIDER_BILL_TYPE.get(provider)
    if bill_type is None:
        # Provider unknown or not in PROVIDER_BILL_TYPE -- infer from fields
        bill_type = _infer_bill_type_from_fields(fields)
    if bill_type is None:
        # Still unknown -- pick profile with best field overlap
        bill_type = _best_match_bill_type(fields)

    expected = FIELD_PROFILES.get(bill_type, FIELD_PROFILES["electricity"])
    fields_found = len(set(fields.keys()) & expected)
    expected_count = len(expected)
    field_coverage = fields_found / expected_count if expected_count > 0 else 0.0

    # Cross-field validation
    validation_checks = validate_cross_fields(fields)
    if validation_checks:
        passes = sum(1 for c in validation_checks if c.passed)
        validation_pass_rate = passes / len(validation_checks)
    else:
        validation_pass_rate = 0.5  # Neutral if no checks possible

    # OCR confidence (0-1 scale)
    if avg_ocr_confidence is not None:
        ocr_score = min(avg_ocr_confidence / 100.0, 1.0)
    else:
        ocr_score = 0.5  # Neutral for native text (no OCR)

    # Weighted score
    score = field_coverage * 0.4 + validation_pass_rate * 0.4 + ocr_score * 0.2

    # Decision band
    if score >= 0.85:
        band = "accept"
    elif score >= 0.60:
        band = "accept_with_review"
    else:
        band = "escalate"

    return ConfidenceResult(
        score=score,
        band=band,
        fields_found=fields_found,
        expected_fields=expected_count,
        validation_checks=validation_checks,
        validation_pass_rate=validation_pass_rate,
        field_coverage=field_coverage,
    )
