"""
Bill Parser - Irish Electricity Bill Data Extraction
=====================================================

Extracts structured data from Irish electricity bills (PDF format).
Adapted from bill_extractor_prototype.py for integration with the
Streamlit app (accepts bytes input from st.file_uploader).

Tested against Energia bills; designed to be extended for other suppliers.
"""
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional
import pymupdf


# ---------------------------------------------------------------------------
# Data model – Generic pipeline (LineItem + GenericBillData)
# ---------------------------------------------------------------------------

@dataclass
class LineItem:
    """A single line item on an invoice / bill."""
    description: str
    line_total: float
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    vat_rate: Optional[float] = None
    vat_amount: Optional[float] = None


@dataclass
class GenericBillData:
    """Provider-agnostic bill representation for the generic extraction pipeline.

    Designed to represent any Irish utility bill (electricity, gas, heating oil)
    with variable-length line items instead of hardcoded per-tariff fields.
    """
    # Identity
    provider: str = ""
    invoice_number: Optional[str] = None
    account_number: Optional[str] = None
    mprn: Optional[str] = None
    gprn: Optional[str] = None

    # Dates
    invoice_date: Optional[str] = None
    billing_period: Optional[str] = None
    due_date: Optional[str] = None

    # Line items (variable length)
    line_items: list = field(default_factory=list)

    # Totals
    subtotal: Optional[float] = None
    vat_amount: Optional[float] = None
    vat_rate: Optional[float] = None
    total_incl_vat: Optional[float] = None

    # Metadata
    extraction_method: str = ""
    confidence_score: float = 0.0
    raw_text: Optional[str] = None
    warnings: list = field(default_factory=list)

    # ---- serialization helpers ----

    def to_dict(self) -> dict:
        """Serialize to a plain dict (line_items become list-of-dicts)."""
        d = asdict(self)
        return d

    def to_json(self, **kwargs) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), default=str, **kwargs)

    @classmethod
    def from_dict(cls, d: dict) -> "GenericBillData":
        """Construct from a plain dict (inverse of to_dict)."""
        d = dict(d)  # Avoid mutating caller's dict
        items_raw = d.pop("line_items", [])
        items = [LineItem(**li) if isinstance(li, dict) else li for li in items_raw]
        # Filter to known fields to avoid TypeError on unknown keys
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(line_items=items, **filtered)


def generic_to_legacy(generic: GenericBillData) -> "BillData":
    """Convert a GenericBillData to the legacy BillData used by the Streamlit UI.

    Maps the generic model's fields and line items back to the flat field layout
    expected by ``show_bill_summary()`` and ``generate_bill_excel()`` in main.py.
    """
    bill = BillData()

    # --- Identity ---
    bill.supplier = generic.provider or None
    bill.mprn = generic.mprn
    bill.account_number = generic.account_number
    bill.invoice_number = generic.invoice_number

    # --- Dates ---
    bill.bill_date = generic.invoice_date
    bill.payment_due_date = generic.due_date
    if generic.billing_period:
        parts = generic.billing_period.split(" - ", 1)
        if len(parts) == 2:
            bill.billing_period_start = parts[0].strip()
            bill.billing_period_end = parts[1].strip()
        else:
            # Try alternate separator
            parts = generic.billing_period.split("-", 1)
            if len(parts) == 2 and len(parts[0].strip()) > 4:
                bill.billing_period_start = parts[0].strip()
                bill.billing_period_end = parts[1].strip()

    # --- Line items → flat fields ---
    for item in generic.line_items:
        desc_lower = item.description.lower()

        if "day" in desc_lower and "stand" not in desc_lower:
            bill.day_units_kwh = item.quantity
            bill.day_rate = item.unit_price
            bill.day_cost = item.line_total
        elif "night" in desc_lower:
            bill.night_units_kwh = item.quantity
            bill.night_rate = item.unit_price
            bill.night_cost = item.line_total
        elif "peak" in desc_lower:
            bill.peak_units_kwh = item.quantity
            bill.peak_rate = item.unit_price
            bill.peak_cost = item.line_total
        elif "standing" in desc_lower:
            bill.standing_charge_total = item.line_total
            if item.quantity is not None:
                bill.standing_charge_days = int(item.quantity)
            bill.standing_charge_rate = item.unit_price
        elif "pso" in desc_lower or "public service" in desc_lower:
            bill.pso_levy = item.line_total
        elif "discount" in desc_lower:
            bill.discount = item.line_total
        elif "export" in desc_lower:
            bill.export_units = item.quantity
            bill.export_rate = item.unit_price
            bill.export_credit = item.line_total

    # Total consumption
    total = 0.0
    has_any = False
    for v in [bill.day_units_kwh, bill.night_units_kwh, bill.peak_units_kwh]:
        if v is not None:
            total += v
            has_any = True
    bill.total_units_kwh = round(total, 3) if has_any else None

    # --- Totals ---
    bill.subtotal_before_vat = generic.subtotal
    bill.vat_amount = generic.vat_amount
    bill.vat_rate_pct = generic.vat_rate
    bill.total_this_period = generic.total_incl_vat

    # --- Metadata ---
    bill.extraction_method = generic.extraction_method
    bill.confidence_score = generic.confidence_score
    bill.warnings = list(generic.warnings)

    return bill


# ---------------------------------------------------------------------------
# Data model – Legacy (flat Energia-style fields)
# ---------------------------------------------------------------------------

@dataclass
class BillData:
    """Structured representation of an Irish electricity bill."""
    # Extraction metadata
    extraction_method: str = ""
    confidence_score: float = 0.0
    warnings: list = field(default_factory=list)

    # Supplier
    supplier: Optional[str] = None

    # Account / Identity
    customer_name: Optional[str] = None
    premises: Optional[str] = None
    mprn: Optional[str] = None
    account_number: Optional[str] = None
    invoice_number: Optional[str] = None
    meter_number: Optional[str] = None
    dg_code: Optional[str] = None
    mcc_code: Optional[str] = None

    # Dates
    bill_date: Optional[str] = None
    billing_period_start: Optional[str] = None
    billing_period_end: Optional[str] = None
    payment_due_date: Optional[str] = None
    contract_end_date: Optional[str] = None
    ceg_export_start: Optional[str] = None
    ceg_export_end: Optional[str] = None

    # Consumption (kWh)
    day_units_kwh: Optional[float] = None
    night_units_kwh: Optional[float] = None
    peak_units_kwh: Optional[float] = None
    total_units_kwh: Optional[float] = None

    # Unit rates (EUR/kWh)
    day_rate: Optional[float] = None
    night_rate: Optional[float] = None
    peak_rate: Optional[float] = None

    # Costs (EUR)
    day_cost: Optional[float] = None
    night_cost: Optional[float] = None
    peak_cost: Optional[float] = None
    standing_charge_days: Optional[int] = None
    standing_charge_rate: Optional[float] = None
    standing_charge_total: Optional[float] = None
    discount: Optional[float] = None
    pso_levy: Optional[float] = None
    subtotal_before_vat: Optional[float] = None
    vat_rate_pct: Optional[float] = None
    vat_amount: Optional[float] = None
    total_this_period: Optional[float] = None

    # Export (solar)
    export_units: Optional[float] = None
    export_rate: Optional[float] = None
    export_credit: Optional[float] = None

    # Balance
    previous_balance: Optional[float] = None
    payments_received: Optional[float] = None
    amount_due: Optional[float] = None

    # Tariff info
    tariff_type: Optional[str] = None
    eab_current: Optional[float] = None
    eab_new: Optional[float] = None


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text_pymupdf(pdf_bytes: bytes) -> tuple[str, dict]:
    """Extract text from PDF bytes using PyMuPDF. Returns (text, metadata)."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    metadata = {
        'pages': doc.page_count,
        'creator': doc.metadata.get('creator', ''),
        'producer': doc.metadata.get('producer', ''),
        'pages_with_text': [],
        'pages_image_only': [],
    }

    full_text = ""
    for i, page in enumerate(doc):
        text = page.get_text()
        if text.strip() and len(text.strip()) > 10:
            full_text += text + "\n\n"
            metadata['pages_with_text'].append(i + 1)
        else:
            metadata['pages_image_only'].append(i + 1)

    doc.close()
    return full_text, metadata


def extract_text_ocr(pdf_bytes: bytes) -> str:
    """Fallback OCR extraction for scanned/image PDFs."""
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except ImportError:
        return ""

    images = convert_from_bytes(pdf_bytes, dpi=300)
    full_text = ""
    for img in images:
        text = pytesseract.image_to_string(img, lang='eng')
        full_text += text + "\n\n"
    return full_text


# ---------------------------------------------------------------------------
# Supplier detection
# ---------------------------------------------------------------------------

SUPPLIER_SIGNATURES = {
    'Energia': {
        'keywords': ['energia', 'energia.ie'],
        'phone': ['0818 405 405', '1800 372 999'],
        'vat': '632 6035',
        'address': 'Generali Building',
    },
    'Electric Ireland': {
        'keywords': ['Electric Ireland', 'electricireland.ie'],
        'phone': ['1850 372 372', '0818 372 372'],
        'vat': '983 8858',
        'address': 'South County Business Park',
    },
    'SSE Airtricity': {
        'keywords': ['SSE Airtricity', 'sseairtricity.com'],
        'phone': ['1850 812 812', '0818 222 991'],
        'vat': '',
        'address': 'Red Oak South',
    },
    'Bord Gais Energy': {
        'keywords': ['Bord Gais', 'Bord Gáis', 'bordgaisenergy.ie'],
        'phone': ['1850 632 632', '0818 200 989'],
        'vat': '',
        'address': 'Warrington Place',
    },
    'Panda Power': {
        'keywords': ['Panda Power', 'pandapower.ie'],
        'phone': [],
        'vat': '',
        'address': '',
    },
    'Yuno Energy': {
        'keywords': ['Yuno', 'yunoenergy.ie'],
        'phone': [],
        'vat': '',
        'address': '',
    },
    'Flogas': {
        'keywords': ['Flogas', 'flogas.ie'],
        'phone': [],
        'vat': '',
        'address': '',
    },
    'Pinergy': {
        'keywords': ['Pinergy', 'pinergy.ie'],
        'phone': [],
        'vat': '',
        'address': '',
    },
}


def detect_supplier(text: str) -> tuple[str, float]:
    """Detect supplier from bill text. Returns (name, confidence)."""
    text_lower = text.lower()
    scores = {}

    for supplier, sig in SUPPLIER_SIGNATURES.items():
        score = 0
        for kw in sig['keywords']:
            if kw.lower() in text_lower:
                score += 3

        for phone in sig['phone']:
            if phone in text:
                score += 5

        if sig['vat'] and sig['vat'] in text:
            score += 10

        if sig['address'] and sig['address'] in text:
            score += 4

        if score > 0:
            scores[supplier] = score

    if not scores:
        return 'Unknown', 0.0

    best = max(scores, key=scores.get)
    confidence = min(scores[best] / 22.0, 1.0)
    return best, round(confidence, 2)


# ---------------------------------------------------------------------------
# Field extraction (regex-based)
# ---------------------------------------------------------------------------

def _parse_eur(val: str) -> Optional[float]:
    """Parse a euro amount string, handling commas."""
    if val is None:
        return None
    val = val.replace(',', '').rstrip('.')
    try:
        return float(val)
    except ValueError:
        return None


def extract_fields(text: str) -> BillData:
    """Extract all structured fields from bill text."""
    bill = BillData()

    # Supplier
    supplier, conf = detect_supplier(text)
    bill.supplier = supplier

    # MPRN - 11 digit number starting with 10
    m = re.search(r'\b(10\d{9})\b', text)
    bill.mprn = m.group(1) if m else None

    # Account Number
    m = re.search(r'Account\s*Number\s*\n?\s*(\d{7,})', text)
    bill.account_number = m.group(1) if m else None

    # Invoice Number
    m = re.search(r'Invoice\s*No\.?\s*\n?\s*(\d+)', text)
    bill.invoice_number = m.group(1) if m else None

    # Meter Number
    m = re.search(r'Meter\s+(\d{7,8})', text)
    bill.meter_number = m.group(1) if m else None

    # DG code
    m = re.search(r'\bDG(\d)\b', text)
    bill.dg_code = f"DG{m.group(1)}" if m else None

    # MCC code
    m = re.search(r'\bMCC(\d+)\b', text)
    bill.mcc_code = f"MCC{m.group(1)}" if m else None

    # Customer name
    m = re.search(r'(Mr|Mrs|Ms|Dr|Miss)\s+(.+?)(?:\n|$)', text)
    bill.customer_name = m.group(0).strip() if m else None

    # Premises
    m = re.search(r'Premises\s*Supplied:\s*\n?\s*(.+?)(?:\n|$)', text)
    bill.premises = m.group(1).strip() if m else None

    # Billing Period
    m = re.search(r'Billing\s*Period\s*\n?\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})', text)
    if m:
        bill.billing_period_start = m.group(1)
        bill.billing_period_end = m.group(2)

    # CEG Export Period
    m = re.search(r'CEG\s*Export\s*Period\s*\n?\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})', text)
    if m:
        bill.ceg_export_start = m.group(1)
        bill.ceg_export_end = m.group(2)

    # Bill Date
    m = re.search(r'Date\s*of\s*this\s*Bill\s*\n?\s*(\d{1,2}\s+\w+\s+\d{4})', text)
    bill.bill_date = m.group(1) if m else None

    # Payment Due Date
    m = re.search(r'Payment\s*Due\s*Date\s*\n?\s*(\d{1,2}\s+\w+\s+\d{4})', text)
    bill.payment_due_date = m.group(1) if m else None

    # Contract End Date
    m = re.search(r'Contract\s*End\s*Date\s*\n?\s*(\d{1,2}\s+\w+\s+\d{4})', text)
    bill.contract_end_date = m.group(1) if m else None

    # Tariff
    m = re.search(r'Tariff\s*\n?\s*(Electricity|Gas)', text)
    bill.tariff_type = m.group(1) if m else None

    # ---- Consumption & Rates ----
    # Day units & rate
    m = re.search(r'Day\s+([\d,]+\.\d+)\s*Units?\s*at\s*€([\d.]+)\s*per\s*Unit', text)
    if m:
        bill.day_units_kwh = _parse_eur(m.group(1))
        bill.day_rate = _parse_eur(m.group(2))

    # Night units & rate
    m = re.search(r'Night\s+([\d,]+\.\d+)\s*Units?\s*at\s*€([\d.]+)\s*per\s*Unit', text)
    if m:
        bill.night_units_kwh = _parse_eur(m.group(1))
        bill.night_rate = _parse_eur(m.group(2))

    # Peak units & rate
    m = re.search(r'Peak\s+([\d,]+\.\d+)\s*Units?\s*at\s*€([\d.]+)\s*per\s*Unit', text)
    if m:
        bill.peak_units_kwh = _parse_eur(m.group(1))
        bill.peak_rate = _parse_eur(m.group(2))

    # Total consumption
    total = 0
    for v in [bill.day_units_kwh, bill.night_units_kwh, bill.peak_units_kwh]:
        if v:
            total += v
    bill.total_units_kwh = round(total, 3) if total > 0 else None

    # ---- Costs ----
    # Day cost
    m = re.search(r'Day\s+[\d,.]+\s*Units?\s*at\s*€[\d.]+\s*per\s*Unit\s*\n?\s*€([\d,.]+)', text)
    bill.day_cost = _parse_eur(m.group(1)) if m else None

    # Night cost
    m = re.search(r'Night\s+[\d,.]+\s*Units?\s*at\s*€[\d.]+\s*per\s*Unit\s*\n?\s*€([\d,.]+)', text)
    bill.night_cost = _parse_eur(m.group(1)) if m else None

    # Peak cost
    m = re.search(r'Peak\s+[\d,.]+\s*Units?\s*at\s*€[\d.]+\s*per\s*Unit\s*\n?\s*€([\d,.]+)', text)
    bill.peak_cost = _parse_eur(m.group(1)) if m else None

    # Standing charge
    m = re.search(r'Standing\s*Charge\s+(\d+)\s*days?\s*at\s*€([\d.]+)\s*per\s*day\s*\n?\s*€([\d.]+)', text)
    if m:
        bill.standing_charge_days = int(m.group(1))
        bill.standing_charge_rate = _parse_eur(m.group(2))
        bill.standing_charge_total = _parse_eur(m.group(3))

    # Discount
    m = re.search(r'discount\s*(?:for\s*this\s*period)?\s*\n?\s*€([\d,.]+)\s*CR', text, re.IGNORECASE)
    bill.discount = _parse_eur(m.group(1)) if m else None

    # PSO Levy
    m = re.search(r'Public\s*Service\s*Obligation\s*Levy.*?€([\d.]+)\s*$', text, re.MULTILINE)
    bill.pso_levy = _parse_eur(m.group(1)) if m else None

    # Subtotal
    m = re.search(r'Sub\s*Total\s*before\s*VAT\s*\n?\s*€([\d,.]+)', text)
    bill.subtotal_before_vat = _parse_eur(m.group(1)) if m else None

    # VAT
    m = re.search(r'VAT\s*on\s*€[\d,.]+\s*at\s*(\d+)%\s*\n?\s*€([\d,.]+)', text)
    if m:
        bill.vat_rate_pct = float(m.group(1))
        bill.vat_amount = _parse_eur(m.group(2))

    # Export credits
    m = re.search(r'Export\s*Units?\s*([\d,.]+)\s*at\s*€(-?[\d.]+)\s*per\s*unit\s*\n?\s*€([\d,.]+)CR', text, re.IGNORECASE)
    if m:
        bill.export_units = _parse_eur(m.group(1))
        bill.export_rate = _parse_eur(m.group(2))
        bill.export_credit = _parse_eur(m.group(3))

    # Total for period
    m = re.search(r'Total\s*transactions?\s*for\s*this\s*period\s*\n?\s*€([\d,.]+)', text)
    bill.total_this_period = _parse_eur(m.group(1)) if m else None

    # Balance
    m = re.search(r'Balance\s*at\s*(?:previous|last)\s*bill\s*\n?\s*€([\d,.]+)', text)
    bill.previous_balance = _parse_eur(m.group(1)) if m else None

    m = re.search(r'Payment.*?received.*?\n?\s*€([\d,.]+)', text)
    bill.payments_received = _parse_eur(m.group(1)) if m else None

    m = re.search(r'New\s*account\s*balance.*?\n?\s*€([\d,.]+)', text)
    bill.amount_due = _parse_eur(m.group(1)) if m else None

    # EAB
    m = re.search(r'Current\s*plan\s*EAB\s*€([\d,.]+)', text)
    bill.eab_current = _parse_eur(m.group(1)) if m else None

    m = re.search(r'New\s*tariff\s*EAB\s*€([\d,.]+)', text)
    bill.eab_new = _parse_eur(m.group(1)) if m else None

    # ---- Confidence scoring ----
    bill.confidence_score = compute_confidence(bill)
    bill.warnings = compute_warnings(bill)

    return bill


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

CRITICAL_FIELDS = [
    'mprn', 'billing_period_start', 'billing_period_end',
    'total_units_kwh', 'total_this_period',
]

IMPORTANT_FIELDS = [
    'supplier', 'account_number', 'bill_date',
    'day_units_kwh', 'night_units_kwh',
    'day_rate', 'night_rate',
    'standing_charge_total', 'vat_amount',
    'subtotal_before_vat',
]

OPTIONAL_FIELDS = [
    'customer_name', 'premises', 'meter_number',
    'peak_units_kwh', 'peak_rate',
    'discount', 'pso_levy', 'export_units',
    'eab_current', 'eab_new',
    'contract_end_date', 'payment_due_date',
]


def compute_confidence(bill: BillData) -> float:
    """Compute overall confidence score (0.0 to 1.0)."""
    score = 0
    max_score = 0

    for field_name in CRITICAL_FIELDS:
        max_score += 3
        if getattr(bill, field_name) is not None:
            score += 3

    for field_name in IMPORTANT_FIELDS:
        max_score += 2
        if getattr(bill, field_name) is not None:
            score += 2

    for field_name in OPTIONAL_FIELDS:
        max_score += 1
        if getattr(bill, field_name) is not None:
            score += 1

    return round(score / max_score, 3) if max_score > 0 else 0.0


def compute_warnings(bill: BillData) -> list:
    """Flag potential issues with extracted data."""
    warnings = []

    if bill.mprn and not re.match(r'^10\d{9}$', bill.mprn):
        warnings.append("MPRN format invalid (expected 11 digits starting with 10)")

    if bill.total_units_kwh and bill.total_units_kwh > 10000:
        warnings.append(f"Total consumption {bill.total_units_kwh} kWh seems very high for a ~2 month period")

    if bill.total_units_kwh and bill.total_units_kwh < 50:
        warnings.append(f"Total consumption {bill.total_units_kwh} kWh seems very low for a ~2 month period")

    if bill.vat_rate_pct and bill.vat_rate_pct not in [9.0, 13.5, 23.0]:
        warnings.append(f"VAT rate {bill.vat_rate_pct}% is unusual for Ireland")

    # Cross-check: subtotal * VAT rate should approximately equal VAT amount
    if bill.subtotal_before_vat and bill.vat_rate_pct and bill.vat_amount:
        expected_vat = round(bill.subtotal_before_vat * bill.vat_rate_pct / 100, 2)
        if abs(expected_vat - bill.vat_amount) > 0.10:
            warnings.append(
                f"VAT cross-check failed: {bill.subtotal_before_vat} * {bill.vat_rate_pct}% = "
                f"€{expected_vat}, but extracted €{bill.vat_amount}"
            )

    # Cross-check: day_units * day_rate should approximately equal day_cost
    for unit_type in ['day', 'night', 'peak']:
        units = getattr(bill, f'{unit_type}_units_kwh')
        rate = getattr(bill, f'{unit_type}_rate')
        cost = getattr(bill, f'{unit_type}_cost')
        if units and rate and cost:
            expected = round(units * rate, 2)
            if abs(expected - cost) > 0.50:
                warnings.append(
                    f"{unit_type.title()} cost cross-check: {units} * €{rate} = €{expected}, "
                    f"but extracted €{cost}"
                )

    if bill.supplier == 'Unknown':
        warnings.append("Could not identify supplier")

    for field_name in CRITICAL_FIELDS:
        if getattr(bill, field_name) is None:
            warnings.append(f"Critical field '{field_name}' not extracted")

    return warnings


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def extract_bill(pdf_bytes: bytes) -> BillData:
    """Extract structured data from a bill PDF.

    Args:
        pdf_bytes: Raw PDF file content as bytes.

    Returns:
        BillData with all extracted fields, confidence score, and warnings.
    """
    # Step 1: Try direct text extraction
    text, metadata = extract_text_pymupdf(pdf_bytes)

    if len(text.strip()) < 100:
        # Likely a scanned/image PDF -- fall back to OCR
        text = extract_text_ocr(pdf_bytes)
        method = "OCR (pytesseract)"
    else:
        method = "Direct text (PyMuPDF)"

    bill = extract_fields(text)
    bill.extraction_method = method

    return bill
