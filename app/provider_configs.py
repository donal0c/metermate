"""
Provider-specific extraction configurations for Tier 3.

Each provider config defines:
  - detection_keywords: used by Tier 1 (reference only here)
  - version: schema version for future migrations
  - preprocess: optional text normalization hook name
  - fields: dict of field_name -> extraction rule(s)

Field extraction rules:
  - anchor_regex: optional regex to locate the region of interest
  - value_regex: regex with capture group(s) for the field value
  - patterns: list of (anchor_regex, value_regex) tuples tried in order
  - confidence: expected reliability (0.0-1.0)
  - transform: optional post-extraction transform ('strip_commas', 'strip_spaces', etc.)
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Energia
# ---------------------------------------------------------------------------

ENERGIA_CONFIG = {
    "provider": "Energia",
    "version": 1,
    "detection_keywords": ["energia", "energia.ie"],
    "preprocess": "energia_normalize",
    "fields": {
        "mprn": {
            "patterns": [
                (None, r"MPRN\s*(?:Number|No\.?|:)?\s*[:\s]*(\d[\d\s]{9,13}\d)"),
                (None, r"(?:MPRN|Meter\s*Point)[:\s#]*(\d{10,11})"),
                (None, r"\b(10\d{9})\b"),
            ],
            "confidence": 0.95,
            "transform": "strip_spaces",
        },
        "account_number": {
            "patterns": [
                (None, r"(?:Account|Acct|A/C)\s*(?:No|Number|#|Num)[:\s.]*(\d[\d\s]{6,12}\d)"),
                (None, r"Account\s*Number\s*\n?\s*(\d{7,})"),
            ],
            "confidence": 0.90,
            "transform": "strip_spaces",
        },
        "invoice_number": {
            "patterns": [
                (None, r"(?:Invoice|Bill)\s*(?:No|Number|#)\.?\s*[:\s]*(\d+)"),
            ],
            "confidence": 0.85,
        },
        "billing_period": {
            "patterns": [
                (None, r"(?:Billing|Bill|Accounting)\s*Period\s*[:\s]*(\d{1,2}\s+\w+\s+\d{4}\s*(?:to|-)\s*\d{1,2}\s+\w+\s+\d{4})"),
                # Multiline: label on one line, dates on the next
                (None, r"(?:Billing|Bill|Accounting)\s*Period\s*\n\s*(\d{1,2}\s+\w+\s+\d{4}\s*(?:to|-)\s*\d{1,2}\s+\w+\s+\d{4})"),
                # dd/mm/yyyy - dd/mm/yyyy
                (None, r"(?:Billing|Bill|Accounting)\s*Period\s*[:\s]*(\d{2}/\d{2}/\d{4})\s*[-–]\s*(\d{2}/\d{2}/\d{4})"),
                (None, r"(?:Billing|Bill|Accounting)\s*Period\s*\n?\s*(\d{2}/\d{2}/\d{4})\s*[-–]\s*(\d{2}/\d{2}/\d{4})"),
                # dd.mm.yyyy - dd.mm.yyyy
                (None, r"(?:Billing|Bill|Accounting)\s*Period\s*[:\s]*(\d{2}\.\d{2}\.\d{4})\s*[-–]\s*(\d{2}\.\d{2}\.\d{4})"),
                (None, r"(?:Billing|Bill|Accounting)\s*Period\s*\n?\s*(\d{2}\.\d{2}\.\d{4})\s*[-–]\s*(\d{2}\.\d{2}\.\d{4})"),
            ],
            "confidence": 0.90,
        },
        "invoice_date": {
            "patterns": [
                (None, r"(?:Invoice|Bill)\s*Date\s*[:\s]*(\d{1,2}\s+\w+\s+\d{4})"),
                (None, r"(?:Invoice|Bill)\s*Date\s*\n?\s*(\d{1,2}\s+\w+\s+\d{4})"),
                # ACCOUNT SUMMARY section: "Date\n11 Apr 2025"
                (r"ACCOUNT\s*SUMMARY", r"Date\s*\n\s*(\d{1,2}\s+\w+\s+\d{4})"),
                (None, r"(?:Invoice|Bill)\s*Date\s*[:\s]*(\d{2}/\d{2}/\d{4})"),
                (None, r"(?:Invoice|Bill)\s*Date\s*[:\s]*(\d{2}\.\d{2}\.\d{4})"),
            ],
            "confidence": 0.85,
        },
        "day_kwh": {
            "patterns": [
                (None, r"Day\s+(?:Energy|Rate)\s+(\d[\d,]*)\s*(?:kWh|xWh|XWh)"),
                (None, r"Day\s+Energy\n\s*(\d[\d,]*)\n\s*kWh"),
            ],
            "confidence": 0.90,
            "transform": "strip_commas",
        },
        "day_rate": {
            "patterns": [
                (None, r"Day\s+(?:Energy|Rate)\s+\d[\d,]*\s*(?:kWh|xWh)\s*@\s*[€\u20ac]?\s*(\d+\.\d+)"),
                (None, r"Day\s+Energy\n\s*\d[\d,]*\n\s*kWh\n\s*@\n\s*[€](\d+\.\d+)"),
            ],
            "confidence": 0.90,
        },
        "day_cost": {
            "patterns": [
                (None, r"Day\s+(?:Energy|Rate)\s+\d[\d,]*\s*(?:kWh|xWh)\s*@\s*[€\u20ac]?\s*\d+\.\d+\s*[€\u20ac]\s*(\d+\.\d+)"),
                (None, r"Day\s+Energy\n\s*\d[\d,]*\n\s*kWh\n\s*@\n\s*[€]\d+\.\d+\n\s*[€](\d+\.\d+)"),
            ],
            "confidence": 0.85,
        },
        "night_kwh": {
            "patterns": [
                (None, r"Night\s+(?:Energy|Rate)\s+(\d[\d,]*)\s*(?:kWh|xWh|XWh)"),
                (None, r"Night\s+Energy\n\s*(\d[\d,]*)\n\s*kWh"),
            ],
            "confidence": 0.90,
            "transform": "strip_commas",
        },
        "night_rate": {
            "patterns": [
                (None, r"Night\s+(?:Energy|Rate)\s+\d[\d,]*\s*(?:kWh|xWh)\s*@\s*[€\u20ac]?\s*(\d+\.\d+)"),
                (None, r"Night\s+Energy\n\s*\d[\d,]*\n\s*kWh\n\s*@\n\s*[€](\d+\.\d+)"),
            ],
            "confidence": 0.90,
        },
        "night_cost": {
            "patterns": [
                (None, r"Night\s+(?:Energy|Rate)\s+\d[\d,]*\s*(?:kWh|xWh)\s*@\s*[€\u20ac]?\s*\d+\.\d+\s*[€\u20ac]\s*(\d+\.\d+)"),
                (None, r"Night\s+Energy\n\s*\d[\d,]*\n\s*kWh\n\s*@\n\s*[€]\d+\.\d+\n\s*[€](\d+\.\d+)"),
            ],
            "confidence": 0.85,
        },
        "standing_charge": {
            "patterns": [
                (None, r"Standing\s*Charge\s*\.?\s*(\d+)\.?\s*Days?\s*@\.?\s*#?[€\u20ac]?\s*(\d+\.\d+)\s*#?[€\u20ac]\s*(\d+\.\d+)"),
                (None, r"Standing\s+Charge\s*\n\s*(\d+)\s*\n\s*Days\s*\n\s*@\s*\n\s*[€]?(\d+\.\d+)\s*\n\s*[€](\d+\.\d+)"),
            ],
            "confidence": 0.85,
            "capture_groups": {"days": 1, "rate": 2, "total": 3},
        },
        "pso_levy": {
            "patterns": [
                (None, r"PSO\s+Levy.*?[€\u20ac]\s*(\d+[\d,.]*\.\d{2})"),
                (None, r"PSO\s+Levy\s+Flat\s+Charge\s*\n\s*[€](\d+\.\d+)"),
                (None, r"Public\s*Service\s*Obligation\s*Levy.*?[€\u20ac](\d+\.\d+)"),
            ],
            "confidence": 0.80,
        },
        "subtotal": {
            "patterns": [
                (None, r"Total\s*Excluding\s*VAT\s*:?\s*~*\s*[€\u20ac]?\s*([\d,]+\.\d{2})"),
                (None, r"Sub\s*Total\s*(?:before\s*VAT)?\s*\n?\s*[€\u20ac]([\d,]+\.\d{2})"),
            ],
            "confidence": 0.90,
            "transform": "strip_commas",
        },
        "vat_rate": {
            "patterns": [
                (None, r"VAT\.?\s*@?\s*(?:on\s*[€\u20ac][\d,.]+\s*at\s*)?(\d+\.?\d*)%"),
                (None, r"VAT\.?\s*@?\s*(\d+)\s*%"),
            ],
            "confidence": 0.90,
        },
        "vat_amount": {
            "patterns": [
                (None, r"VAT\.?\s*@?\s*\d+\.?\d*%\s*[€\u20ac]?\s*([\d,]+\.\d{2})"),
                (None, r"VAT\s+on\s+[€\u20ac][\d,.]+\s+at\s+\d+%\s*\n?\s*[€\u20ac]([\d,]+\.\d{2})"),
            ],
            "confidence": 0.90,
            "transform": "strip_commas",
        },
        "total_incl_vat": {
            "patterns": [
                (None, r"Total\s*Charges?\s*[Ff]or\s*(?:the|this)\s*Period\s*[€\u20ac]?\s*([\d,]+\.\d{2})"),
                (None, r"Total\s+transactions?\s+for\s+this\s+period\s*\n?\s*[€\u20ac]([\d,]+\.\d{2})"),
            ],
            "confidence": 0.90,
            "transform": "strip_commas",
        },
    },
}


# ---------------------------------------------------------------------------
# Go Power
# ---------------------------------------------------------------------------

GO_POWER_CONFIG = {
    "provider": "Go Power",
    "version": 1,
    "detection_keywords": ["go power", "gopower", "gopower.ie"],
    "preprocess": None,
    "fields": {
        "mprn": {
            "patterns": [
                (None, r"MPRN\s*(?:Number|No\.?|:)?\s*[:\s]*(\d{11})"),
                (None, r"\b(10\d{9})\b"),
            ],
            "confidence": 0.95,
        },
        "account_number": {
            "patterns": [
                (None, r"(?:Account|Acc\.?\s*)\s*(?:Code|Number|No\.?)\s*[:\s]*([A-Z0-9]{3,20})"),
            ],
            "confidence": 0.85,
        },
        "billing_period": {
            "patterns": [
                (None, r"(?:Billing|Accounting|Usage)\s*Period\s*[:\s]*(\d{1,2}\s+\w+\s+\d{2,4}\s*(?:to|-)\s*\d{1,2}\s+\w+\s+\d{2,4})"),
                # Go Power compressed format: "Usage Period 1 - 31/03/2024"
                (None, r"Usage\s+Period\s+(\d{1,2})\s*-\s*(\d{1,2}/\d{2}/\d{4})"),
            ],
            "confidence": 0.90,
        },
        "invoice_date": {
            "patterns": [
                (None, r"Doc\.?\s+Date\s*\n?\s*(\d{2}/\d{2}/\d{4})"),
            ],
            "confidence": 0.85,
        },
        "day_kwh": {
            "patterns": [
                (None, r"Energy\s+(\d[\d,]*)\s*kWh\s+\d+\.\d+"),
                (None, r"Energy\s+Charges\s+Energy\s+(\d[\d,]*)\s*kWh"),
            ],
            "confidence": 0.90,
            "transform": "strip_commas",
        },
        "day_rate": {
            "patterns": [
                (None, r"Energy\s+\d[\d,]*\s*kWh\s+(\d+\.\d+)\s*[€\u20ac]"),
            ],
            "confidence": 0.85,
            "transform": "cents_to_euros",
        },
        "day_cost": {
            "patterns": [
                (None, r"Energy\s+\d[\d,]*\s*kWh\s+\d+\.\d+\s*[€\u20ac](\d[\d,]*\.\d{2})"),
            ],
            "confidence": 0.85,
            "transform": "strip_commas",
        },
        "standing_charge": {
            "patterns": [
                (None, r"Standing\s+Charge\s+.*?[€\u20ac]\s*(\d+[\d,.]*\.\d{2})"),
            ],
            "confidence": 0.85,
        },
        "pso_levy": {
            "patterns": [
                (None, r"PSO\s+Levy.*?[€\u20ac]\s*(\d+[\d,.]*\.\d{2})"),
            ],
            "confidence": 0.80,
        },
        "subtotal": {
            "patterns": [
                (None, r"(?:Total\s+Excluding\s+VAT|Sub\s*Total)\s*[:\s]*[€\u20ac]?\s*([\d,]+\.\d{2})"),
            ],
            "confidence": 0.90,
            "transform": "strip_commas",
        },
        "vat_rate": {
            "patterns": [
                (None, r"VAT\s*@?\s*(\d+\.?\d*)%"),
            ],
            "confidence": 0.90,
        },
        "vat_amount": {
            "patterns": [
                (None, r"VAT\s*@?\s*\d+\.?\d*%\s*[€\u20ac]?\s*([\d,]+\.\d{2})"),
            ],
            "confidence": 0.90,
            "transform": "strip_commas",
        },
        "total_incl_vat": {
            "patterns": [
                (None, r"(?:Total\s+Charges?\s+[Ff]or\s+(?:the|this)\s+Period|NEW\s+BALANCE\s+DUE)\s*[:\s]*[€\u20ac]?\s*([\d,]+\.\d{2})"),
                (None, r"Total\s+balance\s+due\s*[€\u20ac]\s*([\d,]+\.\d{2})"),
            ],
            "confidence": 0.90,
            "transform": "strip_commas",
        },
    },
}


# ---------------------------------------------------------------------------
# ESB Networks
# ---------------------------------------------------------------------------

ESB_NETWORKS_CONFIG = {
    "provider": "ESB Networks",
    "version": 1,
    "detection_keywords": ["esb networks", "esb network"],
    "preprocess": None,
    "fields": {
        "mprn": {
            "patterns": [
                (None, r"MPRN\s*(?:Number|No\.?|:)?\s*[:\s]*(\d{11})"),
                # ESB format with spaces: "10 305 584 286"
                (None, r"(10[\s]*\d[\s]*\d[\s]*\d[\s]*\d[\s]*\d[\s]*\d[\s]*\d[\s]*\d[\s]*\d)"),
                (None, r"\b(10\d{9})\b"),
            ],
            "confidence": 0.95,
            "transform": "strip_spaces",
        },
        "account_number": {
            "patterns": [
                (None, r"(?:Account|Your\s+account)\s*(?:number|No\.?)\s*[:\s]*(\d{9,10})"),
                (None, r"(\d{9,10})\n"),
            ],
            "confidence": 0.80,
        },
        "invoice_number": {
            "patterns": [
                (None, r"(?:Invoice|Bill|Doc)\s*(?:No|Number)\.?\s*[:\s]*(\d{10})"),
                (None, r"(\d{10})\n"),
            ],
            "confidence": 0.75,
        },
        "billing_period": {
            "patterns": [
                (None, r"(?:Billing\s*period|Usage\s*Period)\s*[\s\-]*(\d{1,2}\s+\w+\s+\d{2,4})\s*to\s*(\d{1,2}\s+\w+\s+\d{2,4})"),
            ],
            "confidence": 0.85,
        },
        "standing_charge": {
            "patterns": [
                # ESB: multiple periods with total on separate line
                # Format: "Standing Charge\n{total}\n{days} days @ €{rate} / day"
                (None, r"Standing\s+Charge\s+([\d.]+)\s+(\d+)\s+days?\s+@\s+[€\u20ac](\d+\.\d+)\s*/\s*day"),
            ],
            "confidence": 0.85,
            "multi_match": True,
            "capture_groups": {"total": 1, "days": 2, "rate": 3},
        },
        "pso_levy": {
            "patterns": [
                (None, r"PSO\s+Levy.*?(\d+\.\d+)"),
            ],
            "confidence": 0.80,
        },
        "subtotal": {
            "patterns": [
                (None, r"Total\s+electricity\s+charges\s+([\d,.]+)"),
            ],
            "confidence": 0.85,
            "transform": "strip_commas",
        },
        "vat_rate": {
            "patterns": [
                (None, r"VAT\s+\d+\.\d+\s+(\d+)%"),
            ],
            "confidence": 0.90,
        },
        "vat_amount": {
            "patterns": [
                (None, r"VAT\s+(\d+\.\d+)\s+\d+%"),
            ],
            "confidence": 0.90,
        },
        "total_incl_vat": {
            "patterns": [
                (None, r"(?:Total\s+Charges?\s+[Ff]or\s+(?:the|this)\s+Period|Total\s+due)\s*[:\s]*[€\u20ac]?\s*([\d,]+\.\d{2})"),
            ],
            "confidence": 0.85,
            "transform": "strip_commas",
        },
        "mcc_code": {
            "patterns": [
                (None, r"MCC\s*(\d+)"),
            ],
            "confidence": 0.90,
        },
        "dg_code": {
            "patterns": [
                (None, r"(DG\d+)"),
            ],
            "confidence": 0.90,
        },
    },
}


# ---------------------------------------------------------------------------
# Kerry Petroleum
# ---------------------------------------------------------------------------

KERRY_PETROLEUM_CONFIG = {
    "provider": "Kerry Petroleum",
    "version": 1,
    "detection_keywords": ["kerry petroleum"],
    "preprocess": "kerry_normalize",
    "fields": {
        "invoice_number": {
            "patterns": [
                (None, r"INVOICE\s*(?:No|N[oO0]?)\.?\s*[:\s]*(\d{6})"),
            ],
            "confidence": 0.90,
        },
        "invoice_date": {
            "patterns": [
                (None, r"Date[:\s]*(\d{1,2}/\d{1,2}/\d{2,4})"),
            ],
            "confidence": 0.85,
        },
        "litres": {
            "patterns": [
                (None, r"KEROSENE\s+(\d{2,4})\s+\d+\.\d{2}"),
            ],
            "confidence": 0.85,
        },
        "unit_price": {
            "patterns": [
                (None, r"KEROSENE\s+\d{2,4}\s+(\d+\.\d{2})\s+\d+\.\d{2}"),
            ],
            "confidence": 0.80,
        },
        "subtotal": {
            "patterns": [
                (None, r"KEROSENE\s+\d{2,4}\s+\d+\.\d{2}\s+(\d+\.\d{2})"),
            ],
            "confidence": 0.80,
            "transform": "strip_commas",
        },
        "vat_rate": {
            "patterns": [
                (None, r"(\d+\.\d+)\s*%?\s*\d+\.\d{2}\s*\d[\d,]*\.\d{2}\s*$"),
                (None, r"KEROSENE\s+\d+\s+\d+\.\d{2}\s+\d+\.\d{2}\s+(\d+\.\d{2})"),
            ],
            "confidence": 0.75,
        },
        "vat_amount": {
            "patterns": [
                (None, r"KEROSENE\s+\d+\s+\d+\.\d{2}\s+\d+\.\d{2}\s+\d+\.\d{2}\s+(\d+\.\d{2})"),
            ],
            "confidence": 0.75,
        },
        "total_incl_vat": {
            "patterns": [
                (None, r"KEROSENE\s+\d+\s+\d+\.\d{2}\s+\d+\.\d{2}\s+\d+\.\d{2}\s+\d+\.\d{2}\s+([\d,]+\.\d{2})"),
                (None, r"(?:Total|TOTAL)\s*[:\s]*[€\u20ac]?\s*([\d,]+\.\d{2})"),
            ],
            "confidence": 0.80,
            "transform": "strip_commas",
        },
    },
}


# ---------------------------------------------------------------------------
# Electric Ireland
# ---------------------------------------------------------------------------

ELECTRIC_IRELAND_CONFIG = {
    "provider": "Electric Ireland",
    "version": 1,
    "detection_keywords": ["electric ireland", "electricireland.ie"],
    "preprocess": None,
    "fields": {
        "mprn": {
            "patterns": [
                (None, r"MPRN\s*(?:Number|No\.?|:)?\s*[:\s]*(\d{11})"),
                # Format with spaces: "10 306 268 587"
                (None, r"(10[\s]*\d[\s]*\d[\s]*\d[\s]*\d[\s]*\d[\s]*\d[\s]*\d[\s]*\d[\s]*\d)"),
                (None, r"\b(10\d{9})\b"),
            ],
            "confidence": 0.95,
            "transform": "strip_spaces",
        },
        "account_number": {
            "patterns": [
                # New format: "Account Number\n2298483377"
                (None, r"Account\s*Number\s*\n\s*(\d{7,10})"),
                # Old format: "<950960495>"
                (None, r"<(\d{9,10})>"),
            ],
            "confidence": 0.85,
        },
        "invoice_number": {
            "patterns": [
                # New format: "Invoice No.\n37870775"
                (None, r"Invoice\s*(?:No|Number)\.?\s*\n\s*(\d{7,10})"),
                (None, r"Invoice\s*(?:No|Number|#)\.?\s*[:\s]+(\d{7,10})"),
                # Old format: number appears right after date "1 Mar 23\n310148750"
                (r"Date\s+of\s+issue", r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{2,4}\s*\n\s*(\d{9,10})"),
            ],
            "confidence": 0.85,
        },
        "invoice_date": {
            "patterns": [
                # New format: "Date of this Bill\n22 December 2025"
                (None, r"Date\s+of\s+this\s+Bill\s*\n\s*(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4})"),
                # Old format: "Date of issue" then date within 500 chars
                (r"Date\s+of\s+issue", r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{2,4})"),
                (None, r"Date\s+of\s+(?:issue|this\s+Bill)\s*[:\s]*(\d{2}/\d{2}/\d{4})"),
            ],
            "confidence": 0.85,
        },
        "billing_period": {
            "patterns": [
                # New format: "Billing Period\n23/10/2025 - 19/12/2025"
                (None, r"Billing\s+Period\s*\n\s*(\d{2}/\d{2}/\d{4})\s*[-–]\s*(\d{2}/\d{2}/\d{4})"),
                # Old format: "Billing period" anchor, then "24 Dec 22 to 27 Feb 23"
                (r"Billing\s+[Pp]eriod", r"(\d{1,2}\s+\w{3,9}\s+\d{2,4})\s+to\s+(\d{1,2}\s+\w{3,9}\s+\d{2,4})"),
            ],
            "confidence": 0.90,
        },
        "day_kwh": {
            "patterns": [
                # New format: "Day 841.699 Units at €0.3865 per Unit"
                (None, r"Day\s+(\d[\d,.]*)\s+Units?\s+at"),
                # Old format: "consumption is 3192 kWh"
                (None, r"[Cc]onsumption\s+is\s+(\d[\d,]*)\s*kWh"),
            ],
            "confidence": 0.85,
            "transform": "strip_commas",
        },
        "day_rate": {
            "patterns": [
                # New format: "Day 841.699 Units at €0.3865 per Unit"
                (None, r"Day\s+\d[\d,.]*\s+Units?\s+at\s+[€\u20ac](\d+\.\d+)"),
                # Old format table: "3192\n0.3992\nGeneral"
                (r"Your\s+electricity\s+usage", r"\d+\s*\n\s*(\d+\.\d{4})\s*\n\s*General"),
            ],
            "confidence": 0.85,
        },
        "night_kwh": {
            "patterns": [
                (None, r"Night\s+(\d[\d,.]*)\s+Units?\s+at"),
            ],
            "confidence": 0.85,
            "transform": "strip_commas",
        },
        "night_rate": {
            "patterns": [
                (None, r"Night\s+\d[\d,.]*\s+Units?\s+at\s+[€\u20ac](\d+\.\d+)"),
            ],
            "confidence": 0.85,
        },
        "peak_kwh": {
            "patterns": [
                (None, r"Peak\s+(\d[\d,.]*)\s+Units?\s+at"),
            ],
            "confidence": 0.85,
            "transform": "strip_commas",
        },
        "peak_rate": {
            "patterns": [
                (None, r"Peak\s+\d[\d,.]*\s+Units?\s+at\s+[€\u20ac](\d+\.\d+)"),
            ],
            "confidence": 0.85,
        },
        "standing_charge": {
            "patterns": [
                # New format: "Standing Charge 57 days at €0.84 per day\n€47.88"
                (None, r"Standing\s+Charge\s+(\d+)\s+days?\s+at\s+[€\u20ac](\d+\.\d+)\s+per\s+day\s*\n\s*[€\u20ac](\d+\.\d+)"),
                # Old format: "Standing Charge\n63.12\n66  days @ €0.9563 / day"
                (None, r"Standing\s+Charge\s*\n\s*(\d+\.\d+)\s*\n\s*\d+\s+days?"),
            ],
            "confidence": 0.85,
        },
        "pso_levy": {
            "patterns": [
                # New format: "Public Service Obligation Levy - 2 months at €2.01\n€4.02"
                (None, r"Public\s+Service\s+Obligation\s+Levy.*?\n\s*[€\u20ac](\d+\.\d{2})"),
                # Old format: "PSO Levy Dec/Jan\n0.00"
                (None, r"PSO\s+Levy.*?\n\s*(\d+\.\d{2})"),
            ],
            "confidence": 0.80,
        },
        "subtotal": {
            "patterns": [
                # New format: "Sub Total before VAT\n€523.46"
                (None, r"Sub\s*Total\s+before\s+VAT\s*\n\s*[€\u20ac]([\d,]+\.\d{2})"),
                # Old format: "Total electricity charges\n1274.25"
                (None, r"Total\s+electricity\s+charges\s*\n?\s*([\d,]+\.\d{2})"),
                (None, r"Charges\s+for\s+this\s+period\s*\n?\s*[€\u20ac]([\d,]+\.\d{2})"),
            ],
            "confidence": 0.85,
            "transform": "strip_commas",
        },
        "vat_rate": {
            "patterns": [
                # New format: "VAT on €523.46 at 9%"
                (None, r"VAT\s+on\s+[€\u20ac][\d,.]+\s+at\s+(\d+)%"),
                # Old format: "9% on €1267.29"
                (None, r"(\d+)%\s+on\s+[€\u20ac][\d,.]+"),
                (None, r"VAT\s+charged\s+at\s+(\d+)%"),
            ],
            "confidence": 0.90,
        },
        "vat_amount": {
            "patterns": [
                # New format: "VAT on €523.46 at 9%\n€47.11"
                (None, r"VAT\s+on\s+[€\u20ac][\d,.]+\s+at\s+\d+%\s*\n\s*[€\u20ac]([\d,]+\.\d{2})"),
                # Old format page 1: "VAT\n€93.42"
                (None, r"^VAT\s*\n\s*[€\u20ac]([\d,]+\.\d{2})"),
            ],
            "confidence": 0.85,
            "transform": "strip_commas",
        },
        "total_incl_vat": {
            "patterns": [
                # New format: "Total transactions for this period\n€554.38"
                (None, r"Total\s+transactions?\s+for\s+this\s+period\s*\n\s*[€\u20ac]([\d,]+\.\d{2})"),
                # Old format: "Total due\n€1131.35"
                (None, r"Total\s+due\s*\n\s*[€\u20ac]([\d,]+\.\d{2})"),
                (None, r"Amount\s+due\s*\n?\s*[€\u20ac]([\d,]+\.\d{2})"),
            ],
            "confidence": 0.90,
            "transform": "strip_commas",
        },
        "mcc_code": {
            "patterns": [
                (None, r"(MCC\d+)"),
            ],
            "confidence": 0.90,
        },
        "dg_code": {
            "patterns": [
                (None, r"(DG\d+)"),
            ],
            "confidence": 0.90,
        },
    },
}


# ---------------------------------------------------------------------------
# SSE Airtricity
# ---------------------------------------------------------------------------

SSE_AIRTRICITY_CONFIG = {
    "provider": "SSE Airtricity",
    "version": 1,
    "detection_keywords": ["sse airtricity", "airtricity", "sseairtricity.com"],
    "preprocess": None,
    "fields": {
        "mprn": {
            "patterns": [
                (None, r"MPRN\s*(?:Number|No\.?|:)?\s*[:\s]*(\d{11})"),
                (None, r"\b(10\d{9})\b"),
            ],
            "confidence": 0.95,
        },
        "account_number": {
            "patterns": [
                (None, r"Account\s*Number\s*[:\s]+(\d{4,10})"),
                (None, r"Account\s*Number\s*\n\s*(\d{4,10})"),
            ],
            "confidence": 0.85,
        },
        "invoice_number": {
            "patterns": [
                (None, r"Invoice\s*Number\s*[:\s]+(\d+)"),
            ],
            "confidence": 0.80,
        },
        "invoice_date": {
            "patterns": [
                (None, r"Date\s+of\s+Issue\s*[:\s]*(\d{2}/\d{2}/\d{4})"),
                (None, r"Date\s+of\s+Issue\s*[:\s]*(\d{1,2}\s+\w+\s+\d{4})"),
            ],
            "confidence": 0.90,
        },
        "billing_period": {
            "patterns": [
                # Near "Electricity Billing Period" or standalone date range
                (None, r"(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})"),
                (None, r"(\d{1,2}\s+\w+\s+\d{4})\s+to\s+(\d{1,2}\s+\w+\s+\d{4})"),
            ],
            "confidence": 0.90,
        },
        "day_kwh": {
            "patterns": [
                # "SmartSaver Std Day\n247.00"
                (None, r"SmartSaver\s+Std\s+Day\s*\n\s*(\d+(?:\.\d+)?)"),
                (None, r"(?:Day|Standard)\s+(?:Units?|Usage)\s*[:\s]*(\d[\d,.]*)\s*(?:kWh)?"),
            ],
            "confidence": 0.85,
            "transform": "strip_commas",
        },
        "day_rate": {
            "patterns": [
                # "SmartSaver Std Day\n247.00\n0.1712"
                (None, r"SmartSaver\s+Std\s+Day\s*\n\s*\d+(?:\.\d+)?\s*\n\s*(\d+\.\d+)"),
            ],
            "confidence": 0.85,
        },
        "night_kwh": {
            "patterns": [
                (None, r"SmartSaver\s+Std\s+Night\s*\n\s*(\d+(?:\.\d+)?)"),
                (None, r"Night\s+(?:Units?|Usage)\s*[:\s]*(\d[\d,.]*)\s*(?:kWh)?"),
            ],
            "confidence": 0.85,
            "transform": "strip_commas",
        },
        "night_rate": {
            "patterns": [
                (None, r"SmartSaver\s+Std\s+Night\s*\n\s*\d+(?:\.\d+)?\s*\n\s*(\d+\.\d+)"),
            ],
            "confidence": 0.85,
        },
        "standing_charge": {
            "patterns": [
                # "Standing Charge P4 Dom Rural\n31.00\n0.6037\n18.72"
                # Groups: (days, rate, total)
                (None, r"Standing\s+Charge.*?\n\s*(\d+(?:\.\d+)?)\s*\n\s*(\d+\.\d+)\s*\n\s*(\d+\.\d+)"),
            ],
            "confidence": 0.85,
        },
        "pso_levy": {
            "patterns": [
                # Amount is the last value before VAT line
                (r"PSO\s+Levy", r"(\d+\.\d{2})\s*\n\s*VAT"),
                (None, r"PSO\s+Levy.*?[€\u20ac]\s*(\d+\.\d{2})"),
            ],
            "confidence": 0.80,
        },
        "subtotal": {
            "patterns": [
                (None, r"Total\s+costs\s+for\s+this\s+period\s+(\d+\.\d{2})"),
            ],
            "confidence": 0.90,
        },
        "vat_rate": {
            "patterns": [
                (None, r"VAT\s*\n?\s*(\d+\.?\d*)%"),
            ],
            "confidence": 0.90,
        },
        "vat_amount": {
            "patterns": [
                (None, r"Total\s+VAT\s+(\d+\.\d{2})"),
            ],
            "confidence": 0.90,
        },
        "total_incl_vat": {
            "patterns": [
                (None, r"Total\s+charges\s+for\s+this\s+period\s+(\d+\.\d{2})"),
                (None, r"TOTAL\s+DUE\s*\n\s*[€\u20ac]\s*(\d[\d,.]+\.\d{2})"),
                (None, r"Total\s+Amount\s+Outstanding\s+(\d+\.\d{2})"),
            ],
            "confidence": 0.90,
        },
        "mcc_code": {
            "patterns": [
                (None, r"(MCC\d+)"),
            ],
            "confidence": 0.90,
        },
        "dg_code": {
            "patterns": [
                (None, r"(DG\d+)"),
            ],
            "confidence": 0.90,
        },
    },
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PROVIDER_CONFIGS: dict[str, dict] = {
    "Energia": ENERGIA_CONFIG,
    "Go Power": GO_POWER_CONFIG,
    "ESB Networks": ESB_NETWORKS_CONFIG,
    "Kerry Petroleum": KERRY_PETROLEUM_CONFIG,
    "Electric Ireland": ELECTRIC_IRELAND_CONFIG,
    "SSE Airtricity": SSE_AIRTRICITY_CONFIG,
}


def get_provider_config(provider_name: str) -> dict | None:
    """Look up a provider config by name. Returns None if not found."""
    return PROVIDER_CONFIGS.get(provider_name)
