"""Test pdfplumber extraction against the sample Electric Ireland bill."""
import pdfplumber
import json

PDF_PATH = "/Users/donalocallaghan/workspace/vibes/steve/download.pdf"

with pdfplumber.open(PDF_PATH) as pdf:
    print(f"Total pages: {len(pdf.pages)}")
    print(f"PDF metadata: {pdf.metadata}")
    print()

    for i, page in enumerate(pdf.pages):
        print(f"{'='*60}")
        print(f"PAGE {i+1} (size: {page.width}x{page.height})")
        print(f"{'='*60}")

        # Extract text
        text = page.extract_text()
        if text:
            print(f"\n--- TEXT (length={len(text)}) ---")
            print(text)
        else:
            print("\n--- NO TEXT EXTRACTED ---")

        # Extract tables
        tables = page.extract_tables()
        if tables:
            print(f"\n--- TABLES ({len(tables)} found) ---")
            for j, table in enumerate(tables):
                print(f"\nTable {j+1} ({len(table)} rows):")
                for row in table:
                    print(f"  {row}")
        else:
            print("\n--- NO TABLES FOUND ---")

        # Check for images
        images = page.images
        if images:
            print(f"\n--- IMAGES ({len(images)} found) ---")
            for img in images:
                print(f"  Size: {img.get('width', '?')}x{img.get('height', '?')}, "
                      f"Position: ({img.get('x0', '?')}, {img.get('top', '?')})")

        print()
