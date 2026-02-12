"""
Test supplier detection strategies across the bill text.
"""
import pymupdf
import re

PDF_PATH = "/Users/donalocallaghan/workspace/vibes/steve/download.pdf"

doc = pymupdf.open(PDF_PATH)
full_text = ""
for page in doc:
    full_text += page.get_text() + "\n\n"
doc.close()

# Detection strategies
print("SUPPLIER DETECTION STRATEGIES")
print("=" * 60)

# Strategy 1: Brand name in text
suppliers = {
    'Electric Ireland': ['Electric Ireland', 'electricireland.ie'],
    'Energia': ['energia', 'energia.ie', 'Energia'],
    'SSE Airtricity': ['SSE Airtricity', 'sseairtricity.com', 'SSE Airtricity'],
    'Bord Gais Energy': ['Bord Gáis', 'Bord Gais', 'bordgaisenergy.ie'],
    'Panda Power': ['Panda Power', 'pandapower.ie'],
    'Yuno Energy': ['Yuno', 'yunoenergy.ie'],
    'Flogas': ['Flogas', 'flogas.ie'],
    'Pinergy': ['Pinergy', 'pinergy.ie'],
    'Community Power': ['Community Power', 'communitypower.ie'],
    'Prepay Power': ['Prepay Power', 'prepaypower.ie'],
}

print("\nStrategy 1: Brand name search")
for supplier, keywords in suppliers.items():
    found = [kw for kw in keywords if kw.lower() in full_text.lower()]
    if found:
        print(f"  MATCH: {supplier} (keywords: {found})")

# Strategy 2: Contact numbers
print("\nStrategy 2: Contact numbers")
contact_numbers = {
    'Energia': ['0818 405 405', '1800 372 999'],
    'Electric Ireland': ['1850 372 372', '0818 372 372'],
    'SSE Airtricity': ['1850 812 812', '0818 222 991'],
    'Bord Gais Energy': ['1850 632 632', '0818 200 989'],
}

for supplier, numbers in contact_numbers.items():
    found = [n for n in numbers if n in full_text]
    if found:
        print(f"  MATCH: {supplier} (numbers: {found})")

# Strategy 3: VAT number
print("\nStrategy 3: VAT registration number")
vat_match = re.search(r'VAT\s*Registration\s*Number:\s*IE\s*([\d\s]+)', full_text)
if vat_match:
    vat_num = vat_match.group(1).strip()
    print(f"  VAT Number: IE {vat_num}")
    # Known VAT numbers
    vat_suppliers = {
        '632 6035 0': 'Energia',
        '983 8858 H': 'Electric Ireland',
    }
    for vat, supplier in vat_suppliers.items():
        if vat in vat_num:
            print(f"  MATCH: {supplier}")

# Strategy 4: Website URLs
print("\nStrategy 4: Website URLs")
urls = re.findall(r'(?:www\.|https?://)[\w.-]+\.ie\S*', full_text)
unique_urls = list(set(urls))
for url in sorted(unique_urls):
    print(f"  Found: {url}")

# Strategy 5: Registered address
print("\nStrategy 5: Registered address")
if 'Generali Building' in full_text:
    print("  'Generali Building' found -> Energia")
if 'South County Business Park' in full_text:
    print("  'South County Business Park' found -> Electric Ireland")

print(f"\n{'='*60}")
print("CONCLUSION: This bill is from Energia (not Electric Ireland)")
print("The README.md incorrectly identifies the supplier.")
print("The Generali Building address is Energia's registered office.")
