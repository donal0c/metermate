"""
Test OCR extraction using pytesseract on the image-based pages.
Also test full-page OCR to simulate a scanned bill scenario.
"""
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import time

PDF_PATH = "/Users/donalocallaghan/workspace/vibes/steve/download.pdf"

print("Converting PDF pages to images at 300 DPI...")
start = time.time()
images = convert_from_path(PDF_PATH, dpi=300)
print(f"Conversion took {time.time()-start:.1f}s, got {len(images)} pages\n")

for i, img in enumerate(images):
    print(f"{'='*60}")
    print(f"PAGE {i+1} OCR (image size: {img.size[0]}x{img.size[1]})")
    print(f"{'='*60}")

    start = time.time()
    text = pytesseract.image_to_string(img, lang='eng')
    elapsed = time.time() - start

    if text.strip():
        print(f"\n--- OCR TEXT (length={len(text.strip())}, took {elapsed:.1f}s) ---")
        print(text.strip())
    else:
        print(f"\n--- NO OCR TEXT (took {elapsed:.1f}s) ---")
    print()

# Also test OCR with different configs for better accuracy on bill text
print("="*60)
print("ENHANCED OCR ON PAGE 3 (the detailed bill page)")
print("="*60)

# Page 3 has the consumption/cost details
page3 = images[2]

# Try with --psm 6 (assume a uniform block of text)
text_psm6 = pytesseract.image_to_string(page3, lang='eng', config='--psm 6')
print(f"\n--- PSM 6 (uniform block) - length={len(text_psm6.strip())} ---")
print(text_psm6.strip()[:2000])

print("\n" + "="*60)
print("COMPARING OCR vs DIRECT TEXT EXTRACTION ON PAGE 3")
print("="*60)

# Check key data points
import pymupdf
doc = pymupdf.open(PDF_PATH)
direct_text = doc[2].get_text()
doc.close()

key_values = {
    'MPRN': '10306268587',
    'Day units': '841.699',
    'Night units': '1290.023',  # or 1,290.023
    'Peak units': '240.474',
    'Standing charge': '47.88',
    'Day cost': '325.32',
    'Night cost': '274.13',
    'Peak cost': '104.37',
    'Discount': '232.26',
    'Total': '554.38',
    'Export units': '87.512',
    'Meter number': '33670191',
}

print(f"\n{'Field':<20} {'Direct':>10} {'OCR':>10}")
print("-" * 45)
for field, value in key_values.items():
    in_direct = "YES" if value in direct_text else "NO"
    in_ocr = "YES" if value in text_psm6 else "NO"
    print(f"{field:<20} {in_direct:>10} {in_ocr:>10}")
