"""
Manual Playwright Test Script for Pipeline Failures
====================================================

Run this directly with the Playwright Python interpreter to manually test
pipeline failure scenarios.

Usage:
    ~/.playwright-venv/bin/python3 tests/manual_pipeline_failure_test.py
"""
import os
import io
import time
import tempfile
import pymupdf
from pathlib import Path
from playwright.sync_api import sync_playwright


# ---------------------------------------------------------------------------
# Test PDF Generators
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------

def run_pipeline_failure_tests():
    """Run manual pipeline failure tests."""
    print("Creating test PDFs...")

    with tempfile.TemporaryDirectory() as tmpdir:
        test_pdfs = {
            "corrupted": os.path.join(tmpdir, "corrupted.pdf"),
            "empty": os.path.join(tmpdir, "empty.pdf"),
            "unknown_provider": os.path.join(tmpdir, "unknown_provider.pdf"),
            "partial": os.path.join(tmpdir, "partial.pdf"),
            "invalid_math": os.path.join(tmpdir, "invalid_math.pdf"),
        }

        create_corrupted_pdf(test_pdfs["corrupted"])
        create_empty_pdf(test_pdfs["empty"])
        create_unknown_provider_pdf(test_pdfs["unknown_provider"])
        create_partial_extraction_pdf(test_pdfs["partial"])
        create_invalid_math_pdf(test_pdfs["invalid_math"])

        print(f"Test PDFs created in: {tmpdir}")
        print("\nStarting Streamlit app...")

        # App settings
        app_dir = os.path.dirname(os.path.dirname(__file__))
        app_path = os.path.join(app_dir, "main.py")
        streamlit_url = "http://localhost:8601"

        # Start Streamlit app
        import subprocess
        proc = subprocess.Popen(
            [
                "python3", "-m", "streamlit", "run", app_path,
                "--server.port", "8601",
                "--server.headless", "true",
                "--browser.gatherUsageStats", "false",
            ],
            cwd=app_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for app to start
        import urllib.request
        print("Waiting for Streamlit to start...")
        for i in range(30):
            try:
                urllib.request.urlopen(streamlit_url, timeout=2)
                print(f"App started after {i+1} seconds")
                break
            except Exception:
                time.sleep(1)
        else:
            proc.terminate()
            print("ERROR: Streamlit app did not start within 30 seconds")
            return

        print("\nRunning tests with Playwright...\n")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, slow_mo=500)
            context = browser.new_context()
            page = context.new_page()

            # Test 1: Empty PDF (insufficient text)
            print("=" * 70)
            print("TEST 1: Empty PDF - Insufficient Text")
            print("=" * 70)
            page.goto(streamlit_url)
            page.wait_for_load_state("networkidle")

            # Find and upload file
            file_input = page.locator('input[type="file"]').first
            if file_input.is_visible():
                file_input.set_input_files(test_pdfs["empty"])
                page.wait_for_timeout(3000)

                content = page.content()
                print("✓ Uploaded empty PDF")

                if "insufficient text" in content.lower() or "manual review" in content.lower():
                    print("✓ PASS: Shows 'insufficient text' or 'manual review' message")
                else:
                    print("✗ FAIL: Should show insufficient text warning")

                if "Energy Insight" in content:
                    print("✓ PASS: App did not crash")
                else:
                    print("✗ FAIL: App appears to have crashed")
            else:
                print("✗ FAIL: Could not find file uploader")

            page.wait_for_timeout(2000)

            # Test 2: Unknown Provider
            print("\n" + "=" * 70)
            print("TEST 2: Unknown Provider - Fallback to Tier 2")
            print("=" * 70)
            page.goto(streamlit_url)
            page.wait_for_load_state("networkidle")

            file_input = page.locator('input[type="file"]').first
            file_input.set_input_files(test_pdfs["unknown_provider"])
            page.wait_for_timeout(3000)

            content = page.content()
            print("✓ Uploaded unknown provider PDF")

            if "unknown" in content.lower() or "ACME" in content:
                print("✓ PASS: Detected unknown provider")
            else:
                print("✗ FAIL: Should detect unknown provider")

            if "€170.25" in content or "€150" in content:
                print("✓ PASS: Extracted numeric data using Tier 2")
            else:
                print("✗ FAIL: Should extract numeric data even for unknown provider")

            page.wait_for_timeout(2000)

            # Test 3: Partial Extraction
            print("\n" + "=" * 70)
            print("TEST 3: Partial Extraction - Missing Critical Fields")
            print("=" * 70)
            page.goto(streamlit_url)
            page.wait_for_load_state("networkidle")

            file_input = page.locator('input[type="file"]').first
            file_input.set_input_files(test_pdfs["partial"])
            page.wait_for_timeout(3000)

            content = page.content()
            print("✓ Uploaded partial extraction PDF")

            if "INV-001" in content or "ACC-123" in content:
                print("✓ PASS: Extracted available fields")
            else:
                print("✗ FAIL: Should extract invoice/account number")

            if any(term in content.lower() for term in ["warning", "missing", "incomplete", "manual review"]):
                print("✓ PASS: Shows warning about missing fields")
            else:
                print("✗ FAIL: Should warn about missing critical fields")

            page.wait_for_timeout(2000)

            # Test 4: Invalid Math (Cross-Validation)
            print("\n" + "=" * 70)
            print("TEST 4: Invalid Math - Cross-Validation Failure")
            print("=" * 70)
            page.goto(streamlit_url)
            page.wait_for_load_state("networkidle")

            file_input = page.locator('input[type="file"]').first
            file_input.set_input_files(test_pdfs["invalid_math"])
            page.wait_for_timeout(3000)

            content = page.content()
            print("✓ Uploaded invalid math PDF")

            if "€100" in content or "€200" in content:
                print("✓ PASS: Extracted monetary values")
            else:
                print("✗ FAIL: Should extract monetary values")

            if any(term in content.lower() for term in ["validation", "warning", "mismatch", "inconsistent"]):
                print("✓ PASS: Shows cross-validation warning")
            else:
                print("✗ FAIL: Should show validation warning for math mismatch")

            page.wait_for_timeout(2000)

            # Test 5: Corrupted PDF
            print("\n" + "=" * 70)
            print("TEST 5: Corrupted PDF - Tier 0 Failure")
            print("=" * 70)
            page.goto(streamlit_url)
            page.wait_for_load_state("networkidle")

            file_input = page.locator('input[type="file"]').first
            file_input.set_input_files(test_pdfs["corrupted"])
            page.wait_for_timeout(3000)

            content = page.content()
            print("✓ Uploaded corrupted PDF")

            # Check for error message
            if any(term in content.lower() for term in ["error", "corrupt", "invalid", "cannot", "failed"]):
                print("✓ PASS: Shows error message for corrupted PDF")
            else:
                print("✗ FAIL: Should show error for corrupted PDF")

            if "Energy Insight" in content:
                print("✓ PASS: App did not crash after error")
            else:
                print("✗ FAIL: App should remain functional after error")

            print("\n" + "=" * 70)
            print("Tests completed!")
            print("=" * 70)
            print("\nBrowser will close in 5 seconds...")
            page.wait_for_timeout(5000)

            browser.close()

        # Cleanup
        proc.terminate()
        proc.wait(timeout=10)
        print("\nStreamlit app stopped.")


if __name__ == "__main__":
    run_pipeline_failure_tests()
