"""
Demonstration Script: OCR Test Fixture Generation
==================================================

This script demonstrates the test fixture generation capabilities for OCR
failure scenarios without requiring a running Streamlit instance.

It creates sample degraded PDFs and validates that the image manipulation
works correctly.

Usage:
    python3 tests/demo_ocr_test_fixtures.py
"""
import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
    from pdf2image import convert_from_path
    PIL_AVAILABLE = True
except ImportError as e:
    print(f"Error: Required libraries not available: {e}")
    print("Install with: pip install Pillow pdf2image")
    sys.exit(1)

# Source bill for creating degraded test fixtures
BILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "Steve_bills")
SOURCE_BILL = os.path.join(BILLS_DIR, "1845.pdf")


def pdf_to_image(pdf_path: str, page: int = 0, dpi: int = 300) -> Image.Image:
    """Convert PDF page to PIL Image."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Source PDF not found: {pdf_path}")

    images = convert_from_path(pdf_path, dpi=dpi, first_page=page+1, last_page=page+1)
    if not images:
        raise ValueError(f"Could not convert PDF page {page}")
    return images[0]


def image_to_pdf(image: Image.Image, output_path: str):
    """Convert PIL Image to PDF file."""
    if image.mode == "RGBA":
        image = image.convert("RGB")
    elif image.mode != "RGB":
        image = image.convert("RGB")

    # Save directly as PDF using PIL
    image.save(output_path, "PDF", resolution=100.0, save_all=True)


def demo_rotated_pdf(source_pdf: str, output_dir: str):
    """Demonstrate creating rotated PDF."""
    print("Creating rotated PDF (90° clockwise)...")
    img = pdf_to_image(source_pdf, page=0, dpi=200)
    rotated = img.rotate(270, expand=True, fillcolor="white")  # 270° = 90° clockwise

    output_path = os.path.join(output_dir, "rotated_90_degrees.pdf")
    image_to_pdf(rotated, output_path)
    print(f"  ✓ Created: {output_path}")
    print(f"    Original size: {img.size}, Rotated size: {rotated.size}")


def demo_low_res_pdf(source_pdf: str, output_dir: str):
    """Demonstrate creating low-resolution scan."""
    print("\nCreating low-resolution scan (72 DPI)...")
    img = pdf_to_image(source_pdf, page=0, dpi=72)

    output_path = os.path.join(output_dir, "low_res_72dpi.pdf")
    image_to_pdf(img, output_path)
    print(f"  ✓ Created: {output_path}")
    print(f"    Image size: {img.size}")


def demo_blurred_pdf(source_pdf: str, output_dir: str):
    """Demonstrate creating blurred scan."""
    print("\nCreating blurred scan (simulates poor focus)...")
    img = pdf_to_image(source_pdf, page=0, dpi=150)
    blurred = img.filter(ImageFilter.GaussianBlur(radius=3))

    output_path = os.path.join(output_dir, "blurred.pdf")
    image_to_pdf(blurred, output_path)
    print(f"  ✓ Created: {output_path}")


def demo_low_contrast_pdf(source_pdf: str, output_dir: str):
    """Demonstrate creating low-contrast scan (faded ink)."""
    print("\nCreating low-contrast scan (simulates faded ink)...")
    img = pdf_to_image(source_pdf, page=0, dpi=150)

    enhancer = ImageEnhance.Contrast(img)
    low_contrast = enhancer.enhance(0.4)

    output_path = os.path.join(output_dir, "faded_ink.pdf")
    image_to_pdf(low_contrast, output_path)
    print(f"  ✓ Created: {output_path}")


def demo_watermarked_pdf(source_pdf: str, output_dir: str):
    """Demonstrate creating watermarked PDF."""
    print("\nCreating watermarked PDF...")
    img = pdf_to_image(source_pdf, page=0, dpi=150)

    # Create transparent overlay
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    # Draw watermark
    width, height = img.size
    draw.text(
        (width // 4, height // 3),
        "SAMPLE",
        fill=(128, 128, 128, 100),
    )

    # Composite
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    watermarked = Image.alpha_composite(img, overlay)

    output_path = os.path.join(output_dir, "watermarked.pdf")
    image_to_pdf(watermarked, output_path)
    print(f"  ✓ Created: {output_path}")


def demo_stained_pdf(source_pdf: str, output_dir: str):
    """Demonstrate creating stained PDF (coffee stain)."""
    print("\nCreating stained PDF (coffee stain over key area)...")
    img = pdf_to_image(source_pdf, page=0, dpi=150)

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    # Draw stain in upper-right quadrant
    width, height = img.size
    stain_x = int(width * 0.6)
    stain_y = int(height * 0.15)
    stain_radius = int(width * 0.12)

    draw.ellipse(
        [
            stain_x - stain_radius,
            stain_y - stain_radius,
            stain_x + stain_radius,
            stain_y + stain_radius,
        ],
        fill=(139, 90, 43, 120),  # Semi-transparent brown
    )

    stained = Image.alpha_composite(img, overlay)

    output_path = os.path.join(output_dir, "coffee_stained.pdf")
    image_to_pdf(stained, output_path)
    print(f"  ✓ Created: {output_path}")


def demo_1bit_pdf(source_pdf: str, output_dir: str):
    """Demonstrate creating 1-bit black and white scan."""
    print("\nCreating 1-bit black and white scan...")
    img = pdf_to_image(source_pdf, page=0, dpi=150)

    grayscale = img.convert("L")
    bw = grayscale.point(lambda x: 0 if x < 128 else 255, "1")

    output_path = os.path.join(output_dir, "1bit_bw.pdf")
    image_to_pdf(bw.convert("RGB"), output_path)
    print(f"  ✓ Created: {output_path}")


def demo_blank_pdf(output_dir: str):
    """Demonstrate creating completely blank PDF."""
    print("\nCreating blank PDF (for error handling tests)...")
    blank_img = Image.new("RGB", (2480, 3508), color="white")  # A4 at 300 DPI

    output_path = os.path.join(output_dir, "blank.pdf")
    image_to_pdf(blank_img, output_path)
    print(f"  ✓ Created: {output_path}")


def main():
    """Run all demonstrations."""
    print("=" * 70)
    print("OCR Test Fixture Generation Demo")
    print("=" * 70)

    if not os.path.exists(SOURCE_BILL):
        print(f"\nError: Source bill not found: {SOURCE_BILL}")
        print("Please ensure Steve_bills/1845.pdf exists.")
        return 1

    print(f"\nSource bill: {SOURCE_BILL}")

    # Create temp directory for output
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Output directory: {tmpdir}\n")

        try:
            demo_rotated_pdf(SOURCE_BILL, tmpdir)
            demo_low_res_pdf(SOURCE_BILL, tmpdir)
            demo_blurred_pdf(SOURCE_BILL, tmpdir)
            demo_low_contrast_pdf(SOURCE_BILL, tmpdir)
            demo_watermarked_pdf(SOURCE_BILL, tmpdir)
            demo_stained_pdf(SOURCE_BILL, tmpdir)
            demo_1bit_pdf(SOURCE_BILL, tmpdir)
            demo_blank_pdf(tmpdir)

            print("\n" + "=" * 70)
            print("All test fixtures generated successfully!")
            print("=" * 70)
            print(f"\nGenerated files (in {tmpdir}):")
            for filename in sorted(os.listdir(tmpdir)):
                filepath = os.path.join(tmpdir, filename)
                size_kb = os.path.getsize(filepath) / 1024
                print(f"  • {filename:30s} ({size_kb:>6.1f} KB)")

            print("\nThese fixtures can be used to test:")
            print("  ✓ Rotated documents (90°, 180°)")
            print("  ✓ Low quality scans (72 DPI)")
            print("  ✓ Obscured bills (stains, watermarks)")
            print("  ✓ Low contrast / faded ink")
            print("  ✓ Blurred scans (poor focus)")
            print("  ✓ 1-bit black and white scans")
            print("  ✓ Blank PDFs (error handling)")

            print("\nNote: Files are in a temporary directory and will be deleted")
            print("      when this script exits. The E2E tests create similar")
            print("      fixtures dynamically during test execution.")

            return 0

        except Exception as e:
            print(f"\n✗ Error during fixture generation: {e}")
            import traceback
            traceback.print_exc()
            return 1


if __name__ == "__main__":
    sys.exit(main())
