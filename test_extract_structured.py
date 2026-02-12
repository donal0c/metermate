"""
Structured data extraction from Electric Ireland bill.
Tests regex-based extraction against pdfplumber and pymupdf output.
"""
import re
import pymupdf

PDF_PATH = "/Users/donalocallaghan/workspace/vibes/steve/download.pdf"


def extract_all_text(pdf_path):
    """Extract all text from PDF using PyMuPDF (best results from testing)."""
    doc = pymupdf.open(pdf_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n\n"
    doc.close()
    return full_text


def extract_fields(text):
    """Extract structured fields from Electric Ireland bill text."""
    results = {}

    # MPRN - 11 digit number at the start, or labelled
    mprn_match = re.search(r'\b(10\d{9})\b', text)
    results['mprn'] = mprn_match.group(1) if mprn_match else None

    # Account Number
    acct_match = re.search(r'Account\s*Number\s*\n?\s*(\d+)', text)
    results['account_number'] = acct_match.group(1) if acct_match else None

    # Invoice Number
    inv_match = re.search(r'Invoice\s*No\.?\s*\n?\s*(\d+)', text)
    results['invoice_number'] = inv_match.group(1) if inv_match else None

    # Billing Period
    period_match = re.search(r'Billing\s*Period\s*\n?\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})', text)
    if period_match:
        results['billing_period_start'] = period_match.group(1)
        results['billing_period_end'] = period_match.group(2)
    else:
        results['billing_period_start'] = None
        results['billing_period_end'] = None

    # CEG Export Period
    ceg_match = re.search(r'CEG\s*Export\s*Period\s*\n?\s*(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})', text)
    if ceg_match:
        results['ceg_export_start'] = ceg_match.group(1)
        results['ceg_export_end'] = ceg_match.group(2)
    else:
        results['ceg_export_start'] = None
        results['ceg_export_end'] = None

    # Bill Date
    date_match = re.search(r'Date\s*of\s*this\s*Bill\s*\n?\s*(\d{1,2}\s+\w+\s+\d{4})', text)
    results['bill_date'] = date_match.group(1) if date_match else None

    # Payment Due Date
    due_match = re.search(r'Payment\s*Due\s*Date\s*\n?\s*(\d{1,2}\s+\w+\s+\d{4})', text)
    results['payment_due_date'] = due_match.group(1) if due_match else None

    # Contract End Date
    contract_match = re.search(r'Contract\s*End\s*Date\s*\n?\s*(\d{1,2}\s+\w+\s+\d{4})', text)
    results['contract_end_date'] = contract_match.group(1) if contract_match else None

    # Tariff type
    tariff_match = re.search(r'Tariff\s*\n?\s*(Electricity|Gas)', text)
    results['tariff'] = tariff_match.group(1) if tariff_match else None

    # Meter Number
    meter_match = re.search(r'Meter\s+(\d{8})', text)
    results['meter_number'] = meter_match.group(1) if meter_match else None

    # Consumption: Day/Smart day units
    day_units = re.search(r'(?:Day|Smart\s*day)\s+(\d+[\.,]\d+)\s*Units?\s*at\s*.*?per\s*Unit', text)
    results['day_units_kwh'] = day_units.group(1) if day_units else None

    # Consumption: Night units
    night_units = re.search(r'Night\s+(\d[\d,]*\.\d+)\s*Units?\s*at\s*.*?per\s*Unit', text)
    results['night_units_kwh'] = night_units.group(1) if night_units else None

    # Consumption: Peak units
    peak_units = re.search(r'Peak\s+(\d+[\.,]\d+)\s*Units?\s*at\s*.*?per\s*Unit', text)
    results['peak_units_kwh'] = peak_units.group(1) if peak_units else None

    # Unit rates
    day_rate = re.search(r'Day\s+[\d,.]+\s*Units?\s*at\s*€([\d.]+)\s*per\s*Unit', text)
    results['day_rate_eur'] = day_rate.group(1) if day_rate else None

    night_rate = re.search(r'Night\s+[\d,.]+\s*Units?\s*at\s*€([\d.]+)\s*per\s*Unit', text)
    results['night_rate_eur'] = night_rate.group(1) if night_rate else None

    peak_rate = re.search(r'Peak\s+[\d,.]+\s*Units?\s*at\s*€([\d.]+)\s*per\s*Unit', text)
    results['peak_rate_eur'] = peak_rate.group(1) if peak_rate else None

    # Standing charge
    sc_match = re.search(r'Standing\s*Charge\s+(\d+)\s*days?\s*at\s*€([\d.]+)\s*per\s*day\s*\n?\s*€([\d.]+)', text)
    if sc_match:
        results['standing_charge_days'] = sc_match.group(1)
        results['standing_charge_rate'] = sc_match.group(2)
        results['standing_charge_total'] = sc_match.group(3)
    else:
        results['standing_charge_days'] = None
        results['standing_charge_rate'] = None
        results['standing_charge_total'] = None

    # Day cost
    day_cost = re.search(r'Day\s+[\d,.]+\s*Units?\s*at\s*€[\d.]+\s*per\s*Unit\s*\n?\s*€([\d.]+)', text)
    results['day_cost_eur'] = day_cost.group(1) if day_cost else None

    # Night cost
    night_cost = re.search(r'Night\s+[\d,.]+\s*Units?\s*at\s*€[\d.]+\s*per\s*Unit\s*\n?\s*€([\d.]+)', text)
    results['night_cost_eur'] = night_cost.group(1) if night_cost else None

    # Peak cost
    peak_cost = re.search(r'Peak\s+[\d,.]+\s*Units?\s*at\s*€[\d.]+\s*per\s*Unit\s*\n?\s*€([\d.]+)', text)
    results['peak_cost_eur'] = peak_cost.group(1) if peak_cost else None

    # Discount
    discount = re.search(r'(?:Your\s*)?discount\s*(?:for\s*this\s*period)?\s*\n?\s*€([\d,.]+)\s*CR', text, re.IGNORECASE)
    results['discount_eur'] = discount.group(1) if discount else None

    # PSO Levy
    pso = re.search(r'Public\s*Service\s*Obligation\s*Levy.*?€([\d.]+)\s*$', text, re.MULTILINE)
    results['pso_levy_eur'] = pso.group(1) if pso else None

    # Sub Total before VAT
    subtotal = re.search(r'Sub\s*Total\s*before\s*VAT\s*\n?\s*€([\d,.]+)', text)
    results['subtotal_before_vat'] = subtotal.group(1) if subtotal else None

    # VAT
    vat_match = re.search(r'VAT\s*on\s*€[\d,.]+\s*at\s*(\d+)%\s*\n?\s*€([\d,.]+)', text)
    if vat_match:
        results['vat_rate_pct'] = vat_match.group(1)
        results['vat_amount_eur'] = vat_match.group(2)
    else:
        results['vat_rate_pct'] = None
        results['vat_amount_eur'] = None

    # Export credits
    export_match = re.search(r'Export\s*Units?\s*([\d,.]+)\s*at\s*€(-?[\d.]+)\s*per\s*unit\s*\n?\s*€([\d,.]+)CR', text, re.IGNORECASE)
    if export_match:
        results['export_units'] = export_match.group(1)
        results['export_rate'] = export_match.group(2)
        results['export_credit_eur'] = export_match.group(3)
    else:
        results['export_units'] = None
        results['export_rate'] = None
        results['export_credit_eur'] = None

    # Total for period
    total_match = re.search(r'Total\s*transactions?\s*for\s*this\s*period\s*\n?\s*€([\d,.]+)', text)
    results['total_this_period'] = total_match.group(1) if total_match else None

    # Amount due / New balance
    amount_due = re.search(r'New\s*account\s*balance.*?\n?\s*€([\d,.]+)', text)
    results['amount_due'] = amount_due.group(1) if amount_due else None

    # Previous balance
    prev_balance = re.search(r'Balance\s*at\s*(?:previous|last)\s*bill\s*\n?\s*€([\d,.]+)', text)
    results['previous_balance'] = prev_balance.group(1) if prev_balance else None

    # Payments received
    payments = re.search(r'Payment.*?received.*?\n?\s*€([\d,.]+)', text)
    results['payments_received'] = payments.group(1) if payments else None

    # Customer name
    name_match = re.search(r'(Mr|Mrs|Ms|Dr)\s+(.+?)(?:\n|$)', text)
    if name_match:
        results['customer_name'] = name_match.group(0).strip()
    else:
        results['customer_name'] = None

    # Address - premises supplied
    premises_match = re.search(r'Premises\s*Supplied:\s*\n?\s*(.+?)(?:\n|$)', text)
    results['premises'] = premises_match.group(1).strip() if premises_match else None

    # DG2 code
    dg2_match = re.search(r'\bDG(\d)\b', text)
    results['dg_code'] = f"DG{dg2_match.group(1)}" if dg2_match else None

    # MCC code
    mcc_match = re.search(r'\bMCC(\d+)\b', text)
    results['mcc_code'] = f"MCC{mcc_match.group(1)}" if mcc_match else None

    # Supplier detection
    if 'Electric Ireland' in text or 'Generali Building' in text or 'Blanchardstown' in text:
        results['supplier'] = 'Electric Ireland'
    elif 'SSE Airtricity' in text:
        results['supplier'] = 'SSE Airtricity'
    elif 'Bord Gáis' in text or 'Bord Gais' in text:
        results['supplier'] = 'Bord Gáis Energy'
    elif 'Energia' in text:
        results['supplier'] = 'Energia'
    elif 'Panda Power' in text or 'Yuno' in text:
        results['supplier'] = 'Panda Power / Yuno Energy'
    else:
        results['supplier'] = 'Unknown'

    # EAB (Estimated Annual Bill)
    eab_current = re.search(r'Current\s*plan\s*EAB\s*€([\d,.]+)', text)
    results['eab_current'] = eab_current.group(1) if eab_current else None

    eab_new = re.search(r'New\s*tariff\s*EAB\s*€([\d,.]+)', text)
    results['eab_new'] = eab_new.group(1) if eab_new else None

    # Average daily use
    daily_use = re.findall(r'([\d.]+)\s*$', text[text.find('Average daily'):text.find('Same period')], re.MULTILINE) if 'Average daily' in text else []
    results['avg_daily_units'] = daily_use if daily_use else None

    return results


def compute_total_consumption(results):
    """Compute total kWh from extracted day/night/peak."""
    total = 0
    for field in ['day_units_kwh', 'night_units_kwh', 'peak_units_kwh']:
        val = results.get(field)
        if val:
            total += float(val.replace(',', ''))
    return round(total, 3) if total > 0 else None


# Run extraction
print("Extracting text from PDF...")
text = extract_all_text(PDF_PATH)
print(f"Total text length: {len(text)} characters\n")

print("Extracting structured fields...\n")
fields = extract_fields(text)

# Report
print("=" * 60)
print("EXTRACTION RESULTS")
print("=" * 60)

categories = {
    "Supplier & Account": ['supplier', 'customer_name', 'premises', 'mprn', 'account_number',
                           'invoice_number', 'meter_number', 'dg_code', 'mcc_code'],
    "Dates": ['bill_date', 'billing_period_start', 'billing_period_end',
              'payment_due_date', 'contract_end_date',
              'ceg_export_start', 'ceg_export_end'],
    "Consumption (kWh)": ['day_units_kwh', 'night_units_kwh', 'peak_units_kwh'],
    "Unit Rates (EUR/kWh)": ['day_rate_eur', 'night_rate_eur', 'peak_rate_eur'],
    "Costs": ['day_cost_eur', 'night_cost_eur', 'peak_cost_eur',
              'standing_charge_days', 'standing_charge_rate', 'standing_charge_total',
              'discount_eur', 'pso_levy_eur', 'subtotal_before_vat',
              'vat_rate_pct', 'vat_amount_eur',
              'export_units', 'export_rate', 'export_credit_eur',
              'total_this_period'],
    "Balance": ['previous_balance', 'payments_received', 'amount_due'],
    "Tariff Info": ['tariff', 'eab_current', 'eab_new'],
}

extracted_count = 0
total_count = 0

for category, field_names in categories.items():
    print(f"\n  {category}:")
    for name in field_names:
        total_count += 1
        value = fields.get(name)
        status = "OK" if value else "MISSING"
        if value:
            extracted_count += 1
        print(f"    {status:7s} {name:30s} = {value}")

total_kwh = compute_total_consumption(fields)
print(f"\n  Computed:")
print(f"    {'OK' if total_kwh else 'MISSING':7s} {'total_consumption_kwh':30s} = {total_kwh}")

print(f"\n{'='*60}")
print(f"SUMMARY: {extracted_count}/{total_count} fields extracted successfully ({extracted_count/total_count*100:.1f}%)")
print(f"{'='*60}")
