"""
Create Test PDFs for Pipeline Failure Testing
==============================================

Run this with the app venv to create test PDFs:
    python3 tests/create_test_pdfs.py /tmp/test_pdfs
"""
import os
import sys
import pymupdf
from pathlib import Path


def create_corrupted_pdf(output_path: str):
    """Create a corrupted PDF that PyMuPDF cannot open."""
    with open(output_path, "wb") as f:
        f.write(b"%PDF-1.4\n")
        f.write(b"1 0 obj\n")
        f.write(b"<<\n")
        f.write(b"/Type /Catalog\n")
        f.write(b"/Pages 2 0")  # Truncated


def create_empty_pdf(output_path: str):
    """Create a valid PDF with no text content."""
    doc = pymupdf.open()
    doc.new_page(width=612, height=792)
    doc.save(output_path)
    doc.close()


def create_unknown_provider_pdf(output_path: str):
    """Create a PDF with bill-like content but unknown provider."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    text = """
    ACME ENERGY CORP
    Invoice #12345
    Account: ACC-9876

    Billing Period: 01/01/2025 - 31/01/2025

    Energy Charges: €150.00
    VAT (13.5%): €20.25
    Total Due: €170.25
    """
    page.insert_text((100, 100), text)
    doc.save(output_path)
    doc.close()


def create_partial_extraction_pdf(output_path: str):
    """Create a PDF that will extract some fields but miss critical ones."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    text = """
    Energia

    Invoice Number: INV-001
    Account: ACC-123

    Day Units: 500 kWh
    Rate: €0.20

    (Total amount missing from document)
    """
    page.insert_text((100, 100), text)
    doc.save(output_path)
    doc.close()


def create_invalid_math_pdf(output_path: str):
    """Create a PDF where subtotal + VAT != total."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    text = """
    Energia

    Invoice: INV-999
    MPRN: 10123456789

    Subtotal: €100.00
    VAT (13.5%): €13.50
    Total: €200.00

    (Math doesn't add up - should be €113.50)
    """
    page.insert_text((100, 100), text)
    doc.save(output_path)
    doc.close()


def create_misspelled_provider_pdf(output_path: str):
    """Create a PDF with misspelled provider name."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    text = """
    Enerrrgia Power Solutions

    Invoice Number: INV-2025-001
    Account Number: 123456789

    Total: €200.00
    """
    page.insert_text((100, 100), text)
    doc.save(output_path)
    doc.close()


def create_no_numeric_data_pdf(output_path: str):
    """Create a PDF with provider info but no extractable numeric data."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    text = """
    Energia

    Dear Customer,

    Thank you for your payment. Your account is in good standing.

    No charges this period.

    Best regards,
    Energia Customer Service
    """
    page.insert_text((100, 100), text)
    doc.save(output_path)
    doc.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 create_test_pdfs.py <output_directory>")
        sys.exit(1)

    output_dir = sys.argv[1]
    os.makedirs(output_dir, exist_ok=True)

    test_pdfs = {
        "corrupted.pdf": create_corrupted_pdf,
        "empty.pdf": create_empty_pdf,
        "unknown_provider.pdf": create_unknown_provider_pdf,
        "partial.pdf": create_partial_extraction_pdf,
        "invalid_math.pdf": create_invalid_math_pdf,
        "misspelled_provider.pdf": create_misspelled_provider_pdf,
        "no_numeric_data.pdf": create_no_numeric_data_pdf,
    }

    print(f"Creating test PDFs in: {output_dir}\n")

    for filename, creator_func in test_pdfs.items():
        filepath = os.path.join(output_dir, filename)
        try:
            creator_func(filepath)
            print(f"✓ Created: {filename}")
        except Exception as e:
            print(f"✗ Failed to create {filename}: {e}")

    print(f"\nAll test PDFs created successfully in: {output_dir}")
