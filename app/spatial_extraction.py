"""
Anchor-Based Spatial Extraction
================================

Layout-independent extraction module that uses OCR bounding box data to find
anchor labels and extract nearby values via spatial proximity. Enables extraction
from scanned bills where native text is unavailable.

Flow:
  1. Convert PDF pages to images (pdf2image)
  2. Run pytesseract.image_to_data() for word-level bounding boxes
  3. Find anchor labels via n-gram sliding window
  4. For each anchor, find nearest value by spatial proximity (right-of, below)
  5. Return Tier2ExtractionResult compatible with the existing pipeline
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from pipeline import (
    Tier2ExtractionResult,
    FieldExtractionResult,
    _PREPROCESS_HOOKS,
    detect_provider,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Anchor dictionary: field_name -> list of label phrases (most specific first)
# ---------------------------------------------------------------------------

ANCHOR_LABELS: dict[str, list[str]] = {
    "total_incl_vat": [
        "Total Charges For This Period",
        "Total Charges for the Period",
        "Total transactions for this period",
        "Total Including VAT",
        "Total incl VAT",
        "Amount Due",
        "Grand Total",
        "Total due",
        "NEW BALANCE DUE",
    ],
    "subtotal": [
        "Total Excluding VAT",
        "Total Excl VAT",
        "Sub Total before VAT",
        "SubTotal",
        "Sub Total",
        "Net Total",
        "Net Amount",
        "Total electricity charges",
    ],
    "vat_rate": [
        "VAT @",
        "VAT at",
        "V.A.T.",
        "VAT",
    ],
    "vat_amount": [
        "VAT on",
        "VAT @",
        "VAT at",
        "V.A.T.",
        "VAT",
    ],
    "mprn": [
        "Meter Point Reference Number",
        "Meter Point Reference",
        "MPRN Number",
        "MPRN No",
        "MPRN",
    ],
    "gprn": [
        "Gas Point Registration",
        "GPRN Number",
        "GPRN No",
        "GPRN",
    ],
    "account_number": [
        "Account Number",
        "Account No",
        "Account Code",
        "Acct No",
        "A/C No",
    ],
    "invoice_number": [
        "Invoice Number",
        "Invoice No",
        "Bill Number",
        "Bill No",
    ],
    "billing_period": [
        "Billing Period",
        "Bill Period",
        "Usage Period",
        "Accounting Period",
    ],
    "invoice_date": [
        "Date of this Bill",
        "Invoice Date",
        "Bill Date",
    ],
    "day_kwh": [
        "Day Energy",
        "Day Rate",
    ],
    "day_rate": [
        "Day Energy",
        "Day Rate",
    ],
    "night_kwh": [
        "Night Energy",
        "Night Rate",
    ],
    "night_rate": [
        "Night Energy",
        "Night Rate",
    ],
    "standing_charge": [
        "Standing Charge",
    ],
    "pso_levy": [
        "PSO Levy",
        "Public Service Obligation Levy",
    ],
    "litres": [
        "KEROSENE",
        "Heating Oil",
        "Gas Oil",
    ],
    "unit_price": [
        "KEROSENE",
        "Heating Oil",
        "Gas Oil",
    ],
    "mcc_code": [
        "MCC",
    ],
    "dg_code": [
        "DG",
    ],
}


# ---------------------------------------------------------------------------
# Value type patterns: regex to identify candidate values by type
# ---------------------------------------------------------------------------

VALUE_TYPE_PATTERNS: dict[str, str] = {
    "monetary": r"[€]?\d[\d,]*\.\d{2}$",
    "integer": r"\d{3,}$",
    "percentage": r"\d{1,2}(?:\.\d+)?%$",
    "date": r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}$",
    "alphanumeric": r"[\w\-/]{4,20}$",
}

# Map field names to expected value types
FIELD_VALUE_TYPES: dict[str, list[str]] = {
    "total_incl_vat": ["monetary"],
    "subtotal": ["monetary"],
    "vat_rate": ["percentage", "integer"],
    "vat_amount": ["monetary"],
    "mprn": ["integer"],
    "gprn": ["integer"],
    "account_number": ["integer", "alphanumeric"],
    "invoice_number": ["integer", "alphanumeric"],
    "billing_period": ["date", "alphanumeric"],
    "invoice_date": ["date", "alphanumeric"],
    "day_kwh": ["integer"],
    "day_rate": ["monetary"],
    "night_kwh": ["integer"],
    "night_rate": ["monetary"],
    "standing_charge": ["monetary"],
    "pso_levy": ["monetary"],
    "litres": ["integer"],
    "unit_price": ["monetary"],
    "mcc_code": ["integer", "alphanumeric"],
    "dg_code": ["alphanumeric"],
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AnchorMatch:
    """A matched anchor label in OCR output."""
    field_name: str
    label: str
    bbox: tuple[int, int, int, int]  # (left, top, width, height)
    specificity: int  # index in anchor list (0 = most specific)
    word_indices: list[int]  # indices into the OCR dataframe


@dataclass
class ValueMatch:
    """A candidate value found near an anchor."""
    text: str
    bbox: tuple[int, int, int, int]
    distance: float
    direction: str  # "right" or "below"
    word_indices: list[int]


# ---------------------------------------------------------------------------
# OCR data extraction
# ---------------------------------------------------------------------------

def get_ocr_dataframe(source: bytes | str) -> tuple[pd.DataFrame, float]:
    """Convert PDF to images, run OCR, return DataFrame with bounding boxes.

    Args:
        source: PDF file path (str) or raw PDF bytes.

    Returns:
        Tuple of (DataFrame with OCR word data, average confidence).
        DataFrame columns: text, left, top, width, height, conf,
                          block_num, line_num, word_num, page_num
    """
    import pytesseract
    from pdf2image import convert_from_bytes, convert_from_path

    if isinstance(source, str):
        images = convert_from_path(source, dpi=300)
    else:
        images = convert_from_bytes(source, dpi=300)

    all_rows: list[pd.DataFrame] = []

    for page_idx, img in enumerate(images):
        data = pytesseract.image_to_data(img, lang="eng", output_type=pytesseract.Output.DATAFRAME)
        data["page_num"] = page_idx + 1
        all_rows.append(data)

    if not all_rows:
        return pd.DataFrame(), 0.0

    df = pd.concat(all_rows, ignore_index=True)

    # Filter out non-word entries (conf == -1 means no text)
    df = df[df["conf"] != -1].copy()

    # Convert text to string and strip whitespace
    df["text"] = df["text"].astype(str).str.strip()

    # Drop empty text rows
    df = df[df["text"].str.len() > 0].copy()

    df = df.reset_index(drop=True)

    # Average OCR confidence
    avg_conf = df["conf"].mean() if len(df) > 0 else 0.0

    return df, avg_conf


def get_ocr_text(ocr_df: pd.DataFrame) -> str:
    """Reconstruct full text from OCR dataframe, grouped by page/block/line."""
    if ocr_df.empty:
        return ""

    lines = []
    for (page, block, line), group in ocr_df.groupby(
        ["page_num", "block_num", "line_num"], sort=True
    ):
        words = group.sort_values("left")["text"].tolist()
        lines.append(" ".join(words))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# N-gram anchor matching
# ---------------------------------------------------------------------------

def _normalize_for_matching(text: str) -> str:
    """Normalize text for anchor matching: lowercase, collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


def find_anchors(
    ocr_df: pd.DataFrame,
    anchor_dict: dict[str, list[str]] | None = None,
) -> list[AnchorMatch]:
    """Find anchor labels in OCR words using n-gram sliding window.

    For each field, tries to match each label phrase (most specific first)
    against consecutive OCR words on the same line.

    Args:
        ocr_df: DataFrame from get_ocr_dataframe().
        anchor_dict: Override anchor labels (default: ANCHOR_LABELS).

    Returns:
        List of AnchorMatch objects found in the OCR text.
    """
    if anchor_dict is None:
        anchor_dict = ANCHOR_LABELS

    if ocr_df.empty:
        return []

    matches: list[AnchorMatch] = []

    # Group words by page + block + line for efficient scanning
    for (page, block, line_num), group in ocr_df.groupby(
        ["page_num", "block_num", "line_num"], sort=True
    ):
        group_sorted = group.sort_values("left")
        words = group_sorted["text"].tolist()
        indices = group_sorted.index.tolist()

        if not words:
            continue

        # Build normalized word list for matching
        words_lower = [w.lower() for w in words]
        n_words = len(words)

        for field_name, labels in anchor_dict.items():
            for specificity, label in enumerate(labels):
                label_words = label.lower().split()
                label_len = len(label_words)

                if label_len > n_words:
                    continue

                # Slide window
                for start in range(n_words - label_len + 1):
                    window = words_lower[start : start + label_len]

                    if _words_match(window, label_words):
                        # Compute bounding box spanning matched words
                        matched_indices = indices[start : start + label_len]
                        matched_rows = ocr_df.loc[matched_indices]

                        left = int(matched_rows["left"].min())
                        top = int(matched_rows["top"].min())
                        right = int(
                            (matched_rows["left"] + matched_rows["width"]).max()
                        )
                        bottom = int(
                            (matched_rows["top"] + matched_rows["height"]).max()
                        )
                        bbox = (left, top, right - left, bottom - top)

                        matches.append(
                            AnchorMatch(
                                field_name=field_name,
                                label=label,
                                bbox=bbox,
                                specificity=specificity,
                                word_indices=matched_indices,
                            )
                        )
                        break  # Found match for this label, move to next label

    return matches


def _words_match(window: list[str], label_words: list[str]) -> bool:
    """Check if OCR window matches label words, allowing fuzzy OCR errors."""
    for w, lw in zip(window, label_words):
        # Clean OCR artifacts: strip punctuation from both sides
        w_clean = re.sub(r"^[^a-z0-9]+|[^a-z0-9%]+$", "", w)
        lw_clean = re.sub(r"^[^a-z0-9]+|[^a-z0-9%]+$", "", lw)

        if w_clean != lw_clean:
            # Allow common OCR substitutions
            if not _fuzzy_word_match(w_clean, lw_clean):
                return False
    return True


def _fuzzy_word_match(ocr_word: str, label_word: str) -> bool:
    """Allow common OCR misreadings."""
    # Common OCR confusions
    ocr_subs = {
        "0": "o", "1": "l", "5": "s", "8": "b",
        "rn": "m", "cl": "d", "ii": "u",
    }
    # Try direct comparison with substitutions
    fixed = ocr_word
    for bad, good in ocr_subs.items():
        fixed = fixed.replace(bad, good)
    if fixed == label_word:
        return True

    # Allow single character difference for short words
    if len(ocr_word) == len(label_word) and len(ocr_word) >= 3:
        diffs = sum(1 for a, b in zip(ocr_word, label_word) if a != b)
        if diffs <= 1:
            return True

    return False


# ---------------------------------------------------------------------------
# Spatial proximity search
# ---------------------------------------------------------------------------

def find_nearest_value(
    ocr_df: pd.DataFrame,
    anchor: AnchorMatch,
    field_name: str,
    value_types: list[str] | None = None,
) -> ValueMatch | None:
    """Find the nearest valid value to an anchor using spatial proximity.

    Search order:
      1. RIGHT of anchor (same line: y-center within 1.5x anchor height)
      2. BELOW anchor (x-overlap or nearby)

    Rightward matches are weighted 0.8x vs downward 1.0x (prefer right).

    Args:
        ocr_df: DataFrame from get_ocr_dataframe().
        anchor: The anchor match to search from.
        field_name: Field being extracted (for value type lookup).
        value_types: Override value types to search for.

    Returns:
        Best ValueMatch, or None if no valid value found nearby.
    """
    if value_types is None:
        value_types = FIELD_VALUE_TYPES.get(field_name, ["monetary", "alphanumeric"])

    a_left, a_top, a_width, a_height = anchor.bbox
    a_right = a_left + a_width
    a_bottom = a_top + a_height
    a_y_center = a_top + a_height / 2

    # Maximum search distance (proportional to page dimensions)
    max_right_dist = a_width * 10  # search far right
    max_below_dist = a_height * 8  # search several lines below

    candidates: list[ValueMatch] = []
    anchor_indices_set = set(anchor.word_indices)

    for idx, row in ocr_df.iterrows():
        if idx in anchor_indices_set:
            continue

        # Skip low-confidence OCR words
        if row["conf"] < 30:
            continue

        w_text = str(row["text"]).strip()
        if not w_text:
            continue

        # Check if pages match (anchors on different pages won't match)
        if row.get("page_num") != ocr_df.loc[anchor.word_indices[0], "page_num"]:
            continue

        w_left = int(row["left"])
        w_top = int(row["top"])
        w_width = int(row["width"])
        w_height = int(row["height"])
        w_y_center = w_top + w_height / 2

        # Check value against expected types
        if not _matches_value_type(w_text, value_types, field_name):
            continue

        # Determine spatial relationship
        direction = None
        distance = float("inf")

        # RIGHT: word starts after anchor ends, y-centers are close
        y_tolerance = a_height * 1.5
        if w_left > a_right and abs(w_y_center - a_y_center) < y_tolerance:
            horiz_dist = w_left - a_right
            if horiz_dist <= max_right_dist:
                distance = horiz_dist * 0.8  # Prefer rightward
                direction = "right"

        # BELOW: word is below anchor, x ranges overlap or are close
        if direction is None:
            if w_top > a_bottom:
                vert_dist = w_top - a_bottom
                if vert_dist <= max_below_dist:
                    # Check x-proximity: value should be roughly aligned or
                    # to the right of anchor
                    w_right = w_left + w_width
                    x_overlap = min(w_right, a_right) - max(w_left, a_left)
                    x_close = abs(w_left - a_left) < a_width * 3

                    if x_overlap > 0 or x_close or w_left >= a_left:
                        distance = vert_dist * 1.0
                        direction = "below"

        if direction is not None:
            candidates.append(
                ValueMatch(
                    text=w_text,
                    bbox=(w_left, w_top, w_width, w_height),
                    distance=distance,
                    direction=direction,
                    word_indices=[idx],
                )
            )

    if not candidates:
        return None

    # For certain fields, try to merge multi-word values (e.g., "1,242.33")
    # But for simple cases, just return the closest match
    candidates.sort(key=lambda c: c.distance)

    best = candidates[0]

    # For monetary values, try to merge adjacent words that form a number
    # e.g., "€" "1,242.33" or "1,242" ".33"
    if field_name in FIELD_VALUE_TYPES and "monetary" in FIELD_VALUE_TYPES[field_name]:
        best = _try_merge_monetary(ocr_df, best, candidates, anchor)

    return best


def _matches_value_type(
    text: str,
    value_types: list[str],
    field_name: str,
) -> bool:
    """Check if text matches any of the expected value types."""
    # Strip currency symbols and whitespace for matching
    clean = text.strip().lstrip("€$£").strip()

    if not clean:
        return False

    # Special handling for specific fields
    if field_name == "mprn":
        # MPRN: 11 digits starting with 10
        stripped = clean.replace(" ", "")
        return bool(re.match(r"^10\d{9}$", stripped))

    if field_name == "vat_rate":
        # VAT rate: number optionally followed by %
        return bool(re.match(r"^\d{1,2}(?:\.\d+)?%?$", clean))

    if field_name == "vat_amount":
        # Must be a monetary value
        return bool(re.match(r"^\d[\d,]*\.\d{2}$", clean))

    if field_name in ("day_kwh", "night_kwh"):
        # kWh: integer, possibly with commas
        stripped = clean.replace(",", "")
        return bool(re.match(r"^\d{2,}$", stripped))

    if field_name == "account_number":
        # Account numbers must start with a digit and be mostly numeric
        stripped = clean.replace(" ", "").replace("-", "").replace("/", "")
        return bool(re.match(r"^\d[\w]{3,19}$", stripped))

    if field_name == "invoice_number":
        # Invoice numbers must start with a digit
        return bool(re.match(r"^\d[\w\-/]{3,19}$", clean))

    if field_name == "billing_period":
        # Must contain a date-like pattern or digit
        return bool(re.search(r"\d", clean))

    if field_name == "gprn":
        # GPRN: 7 digits
        stripped = clean.replace(" ", "")
        return bool(re.match(r"^\d{7}$", stripped))

    for vtype in value_types:
        pattern = VALUE_TYPE_PATTERNS.get(vtype)
        if pattern and re.match(pattern, clean):
            return True

    return False


def _try_merge_monetary(
    ocr_df: pd.DataFrame,
    best: ValueMatch,
    candidates: list[ValueMatch],
    anchor: AnchorMatch,
) -> ValueMatch:
    """Try to merge adjacent words that form a monetary value."""
    text = best.text.strip().lstrip("€$£").strip()

    # If it already looks like a complete monetary value, keep it
    if re.match(r"^\d[\d,]*\.\d{2}$", text):
        return best

    # If text is just "€" or a currency symbol, look for the next candidate
    if text in ("€", "$", "£", "EUR"):
        for c in candidates[1:]:
            c_text = c.text.strip()
            if re.match(r"^\d[\d,]*\.\d{2}$", c_text):
                return c

    return best


# ---------------------------------------------------------------------------
# Disambiguation
# ---------------------------------------------------------------------------

def disambiguate_anchors(
    matches: list[AnchorMatch],
) -> dict[str, AnchorMatch]:
    """When multiple anchors match the same field, pick the best one.

    Rules:
      1. Most specific label first (lowest specificity index)
      2. For ties, prefer last occurrence (summary at bottom of page)
    """
    best: dict[str, AnchorMatch] = {}

    for match in matches:
        field = match.field_name
        if field not in best:
            best[field] = match
            continue

        current = best[field]

        # Prefer more specific label
        if match.specificity < current.specificity:
            best[field] = match
        elif match.specificity == current.specificity:
            # For same specificity, prefer last occurrence (lower on page)
            if match.bbox[1] > current.bbox[1]:  # higher y = lower on page
                best[field] = match

    return best


# ---------------------------------------------------------------------------
# OCR preprocessing
# ---------------------------------------------------------------------------

def preprocess_ocr_text(text: str, provider: str | None = None) -> str:
    """Apply provider-specific preprocessing to OCR text."""
    if provider == "Energia" and "energia_normalize" in _PREPROCESS_HOOKS:
        text = _PREPROCESS_HOOKS["energia_normalize"](text)
    elif provider == "Kerry Petroleum" and "kerry_normalize" in _PREPROCESS_HOOKS:
        text = _PREPROCESS_HOOKS["kerry_normalize"](text)
    return text


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def extract_tier2_spatial(
    source: bytes | str,
) -> tuple[Tier2ExtractionResult, float, pd.DataFrame, str]:
    """Main entry point for spatial extraction from scanned PDFs.

    Args:
        source: PDF file path (str) or raw PDF bytes.

    Returns:
        Tuple of (Tier2ExtractionResult, avg_ocr_confidence, ocr_dataframe, ocr_text).
        The ocr_dataframe and ocr_text are returned so callers can reuse
        the OCR results without re-running the expensive OCR step.
    """
    # Step 1: OCR -> DataFrame
    ocr_df, avg_conf = get_ocr_dataframe(source)

    if ocr_df.empty:
        return Tier2ExtractionResult(
            fields={},
            field_count=0,
            hit_rate=0.0,
            warnings=["OCR produced no text"],
        ), 0.0, ocr_df, ""

    # Step 2: Reconstruct text for provider detection
    ocr_text = get_ocr_text(ocr_df)

    # Detect provider for preprocessing
    provider_result = detect_provider(ocr_text)
    provider = provider_result.provider_name if provider_result.is_known else None

    # Apply preprocessing to OCR text in the dataframe
    if provider:
        processed_text = preprocess_ocr_text(ocr_text, provider)
        # If preprocessing changed the text significantly, re-do OCR matching
        # on the processed text. For now, we work with raw OCR bounding boxes
        # and apply preprocessing only for regex fallback.
        log.info("Detected provider '%s' for spatial extraction", provider)

    # Step 3: Find all anchors
    all_anchors = find_anchors(ocr_df)

    if not all_anchors:
        log.warning("No anchors found in OCR output")
        return Tier2ExtractionResult(
            fields={},
            field_count=0,
            hit_rate=0.0,
            warnings=["No anchor labels found in OCR output"],
        ), avg_conf, ocr_df, ocr_text

    # Step 4: Disambiguate - pick best anchor per field
    best_anchors = disambiguate_anchors(all_anchors)

    # Step 5: For each anchor, find nearest value
    extracted: dict[str, FieldExtractionResult] = {}
    warnings: list[str] = []

    for field_name, anchor in best_anchors.items():
        value_types = FIELD_VALUE_TYPES.get(field_name, ["monetary", "alphanumeric"])
        value_match = find_nearest_value(ocr_df, anchor, field_name, value_types)

        if value_match is not None:
            # Clean value
            clean_val = _clean_extracted_value(value_match.text, field_name)

            extracted[field_name] = FieldExtractionResult(
                field_name=field_name,
                value=clean_val,
                confidence=_spatial_confidence(anchor, value_match, avg_conf),
                pattern_index=0,  # spatial extraction doesn't use pattern index
            )
        else:
            log.debug(
                "No value found for field '%s' near anchor '%s'",
                field_name, anchor.label,
            )

    # Step 6: Also run Tier 2 regex on OCR text as supplement
    from pipeline import extract_tier2_universal

    processed = preprocess_ocr_text(ocr_text, provider)
    regex_result = extract_tier2_universal(processed)

    # Merge strategy:
    # - If only spatial found it: keep spatial
    # - If only regex found it: keep regex
    # - If both found same value: boost confidence (cross-validated)
    # - If both found different values: prefer regex (more reliable for
    #   structured patterns; spatial can hit adjacent wrong values)
    for field_name, regex_field in regex_result.fields.items():
        if field_name not in extracted:
            # Regex found something spatial missed
            extracted[field_name] = regex_field
        else:
            spatial_field = extracted[field_name]
            if _values_equivalent(spatial_field.value, regex_field.value):
                # Both agree: boost confidence (cross-validated)
                extracted[field_name] = FieldExtractionResult(
                    field_name=field_name,
                    value=spatial_field.value,
                    confidence=min(
                        max(spatial_field.confidence, regex_field.confidence) + 0.1,
                        1.0,
                    ),
                    pattern_index=spatial_field.pattern_index,
                )
            else:
                # Disagree: prefer regex (pattern-based matching is more
                # reliable than spatial proximity for correct value selection)
                extracted[field_name] = regex_field

    total_possible = len(ANCHOR_LABELS)
    hit_count = len(extracted)
    hit_rate = hit_count / total_possible if total_possible > 0 else 0.0

    return Tier2ExtractionResult(
        fields=extracted,
        field_count=hit_count,
        hit_rate=hit_rate,
        warnings=warnings,
    ), avg_conf, ocr_df, ocr_text


def _clean_extracted_value(text: str, field_name: str) -> str:
    """Clean and normalize an extracted value."""
    val = text.strip()

    # Strip currency symbols
    val = val.lstrip("€$£").strip()

    # Field-specific cleaning
    if field_name == "mprn":
        val = val.replace(" ", "")
    elif field_name == "vat_rate":
        val = val.rstrip("%").strip()
    elif field_name in ("subtotal", "vat_amount", "total_incl_vat",
                        "standing_charge", "pso_levy", "day_rate",
                        "night_rate"):
        # Strip commas from monetary values
        val = val.replace(",", "")

    return val


def _spatial_confidence(
    anchor: AnchorMatch,
    value: ValueMatch,
    avg_ocr_conf: float,
) -> float:
    """Calculate confidence score for a spatial extraction match."""
    base = 0.70

    # Boost for specific anchors
    if anchor.specificity == 0:
        base += 0.10
    elif anchor.specificity == 1:
        base += 0.05

    # Boost for close proximity
    if value.distance < 50:
        base += 0.05
    elif value.distance < 100:
        base += 0.02

    # Boost for rightward (more reliable than below)
    if value.direction == "right":
        base += 0.05

    # Factor in OCR confidence
    ocr_factor = min(avg_ocr_conf / 100.0, 1.0) * 0.1
    base += ocr_factor

    return min(base, 1.0)


def _values_equivalent(val1: str, val2: str) -> bool:
    """Check if two extracted values are equivalent."""
    v1 = val1.strip().replace(",", "").lstrip("€$£").strip()
    v2 = val2.strip().replace(",", "").lstrip("€$£").strip()

    if v1 == v2:
        return True

    try:
        return abs(float(v1) - float(v2)) < 0.01
    except (ValueError, TypeError):
        return False
