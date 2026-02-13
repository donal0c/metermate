# OCR Pipeline Failure Test Suite

Comprehensive E2E tests for OCR pipeline edge cases and failure scenarios.

## Overview

The test suite in `test_e2e_ocr_failures.py` validates that the bill extraction pipeline correctly handles:

- **Rotated Documents** - 90°, 180°, and mixed rotation
- **Low Quality Scans** - 72 DPI (very low), 150 DPI (minimum), 600+ DPI (very high)
- **Obscured/Damaged Bills** - Coffee stains, watermarks, faded ink, crumpled artifacts
- **OCR Confusion Scenarios** - 1-bit scans, noise, gridlines, decorative fonts
- **Image-Only PDFs** - Phone photos, screenshots, no text layer
- **Performance Edge Cases** - Large files, low confidence, complete extraction failure

## Test Organization

### Test Classes

1. **TestRotatedDocuments** - Verifies rotation detection and handling
2. **TestLowQualityScans** - Tests various DPI levels and scan quality
3. **TestObscuredDamagedBills** - Tests extraction with visual obstructions
4. **TestOCRConfusionScenarios** - Tests character confusion and noise
5. **TestImageOnlyPDFs** - Tests PDFs with no embedded text
6. **TestPerformanceEdgeCases** - Tests extreme scenarios and timeouts
7. **TestExtractionMethodVerification** - Verifies correct extraction path
8. **TestUserExperience** - Tests user-facing error messages and warnings

### Key Scenarios Tested

#### Rotated Documents
- 90° clockwise rotation (should still extract)
- 180° upside down (should not crash)
- Mixed rotation across pages (future enhancement)

#### Low Quality Scans
- **72 DPI**: Very low resolution, should trigger OCR confidence warning
- **150 DPI**: Minimum acceptable, should complete extraction
- **600 DPI**: Very high resolution, should not timeout

#### Obscured/Damaged Bills
- **Coffee stain** over MPRN area - tests resilience to missing data
- **Watermark** overlay - tests extraction through visual noise
- **Faded ink** (low contrast) - tests OCR on degraded text
- **Blurred scan** - tests handling of poor focus

#### OCR Confusion
- **1-bit black and white** - tests binary threshold scans
- **Noise artifacts** - tests extraction with added Gaussian noise
- **Character confusion** - 0/O, 1/l, 5/S substitutions (implicit in fuzzy matching)

#### Image-Only PDFs
- **Phone camera photo** - lower resolution, may have perspective skew
- **Screenshot** - digital capture with potential compression artifacts

#### Performance Edge Cases
- **Very large images** - high DPI that could cause memory/timeout issues
- **Combined degradation** - multiple issues (low DPI + blur + low contrast)
- **Complete failure** - blank PDFs, gibberish output

## Test Fixture Generation

Tests dynamically generate degraded PDFs using PIL/Pillow:

```python
# Example: Create a rotated PDF
img = pdf_to_image(source_pdf, page=0, dpi=300)
rotated = img.rotate(270, expand=True, fillcolor="white")
image_to_pdf(rotated, output_path)
```

### Image Manipulations Available

- **Rotation**: `Image.rotate(angle, expand=True)`
- **Resolution**: `pdf_to_image(pdf, dpi=72/150/600)`
- **Blur**: `image.filter(ImageFilter.GaussianBlur(radius=3))`
- **Contrast**: `ImageEnhance.Contrast(img).enhance(0.4)`
- **Watermark**: Alpha composite overlay
- **Stain**: Semi-transparent ellipse overlay
- **1-bit**: `grayscale.point(lambda x: 0 if x < 128 else 255, "1")`
- **Noise**: NumPy Gaussian noise addition

## Running the Tests

### Prerequisites

```bash
pip install Pillow pdf2image pytesseract playwright pytest-playwright
python3 -m playwright install
```

### Run All OCR Failure Tests

```bash
# From app/ directory
python3 -m pytest tests/test_e2e_ocr_failures.py -v -m e2e
```

### Run Specific Test Class

```bash
python3 -m pytest tests/test_e2e_ocr_failures.py::TestLowQualityScans -v -m e2e
```

### Run Single Test

```bash
python3 -m pytest tests/test_e2e_ocr_failures.py::TestUserExperience::test_helpful_error_message_on_no_text -v -m e2e
```

### Demo Fixture Generation (No Browser Required)

```bash
python3 tests/demo_ocr_test_fixtures.py
```

This demonstrates the test fixture creation without requiring a running Streamlit app.

## What the Tests Verify

### ✅ Spatial Extraction Triggers

Tests verify that spatial/OCR extraction is triggered for:
- Image-only PDFs (no embedded text layer)
- Low-quality scans
- Rotated documents

```python
assert has_spatial_extraction_indicator(page), \
    "Should indicate spatial/OCR extraction for scanned PDF"
```

### ✅ OCR Confidence Warnings

Tests verify warnings appear when OCR confidence is low:

```python
assert has_ocr_confidence_warning(page), \
    "Should show OCR quality warning for poor quality scan"
```

### ✅ Graceful Degradation

Tests ensure the pipeline never crashes, even on:
- Completely blank PDFs
- Severely degraded scans
- Invalid/corrupted images

```python
assert not has_error_alert(page), \
    "Should not crash on severely degraded bill"
```

### ✅ Helpful Error Messages

Tests verify users receive actionable feedback:

```python
helpful_indicators = [
    "no text",
    "could not extract",
    "manual review recommended"
]
assert any(indicator in content for indicator in helpful_indicators)
```

## Test Fixtures

Tests create temporary PDFs in each test's scope:

| Fixture Type | File Name Pattern | Purpose |
|--------------|------------------|---------|
| Rotated | `rotated_90.pdf` | Test rotation handling |
| Low Resolution | `72dpi.pdf`, `150dpi.pdf`, `600dpi.pdf` | Test DPI thresholds |
| Blurred | `blurred.pdf` | Test poor focus |
| Faded | `faded.pdf` | Test low contrast |
| Watermarked | `watermarked.pdf` | Test visual overlays |
| Stained | `stained.pdf` | Test obscured regions |
| 1-bit | `1bit.pdf` | Test binary scans |
| Noisy | `noisy.pdf` | Test with artifacts |
| Blank | `blank.pdf` | Test complete failure |

## Architecture Integration

### Pipeline Flow

```
PDF Upload
  ↓
Tier 0: Native Text Detection
  ↓ (if no text or low quality)
Tier 2: Spatial OCR Extraction
  ├─ pdf2image → PIL Image
  ├─ pytesseract → OCR DataFrame
  ├─ Anchor matching
  ├─ Spatial proximity search
  └─ Confidence calculation
  ↓ (if confidence < threshold)
Tier 4: LLM Vision Fallback
  ↓
User sees:
  • Extracted fields
  • Confidence score
  • Warnings/errors
  • Extraction method used
```

### Files Involved

- **`spatial_extraction.py`** - OCR anchor-based extraction
- **`pipeline.py`** - Tier 0/1/2/3 extraction logic
- **`orchestrator.py`** - Pipeline coordination
- **`main.py`** - Streamlit UI that displays warnings
- **`llm_extraction.py`** - Tier 4 LLM vision fallback

## Expected Test Behavior

### Normal Scans (150-300 DPI)
- ✅ Extraction completes
- ✅ Confidence 70-90%
- ✅ Most fields extracted
- ✅ No errors

### Poor Quality (72 DPI, blurred, faded)
- ⚠️ Extraction completes
- ⚠️ Confidence 40-70%
- ⚠️ Some fields missing
- ⚠️ "Low confidence" warning

### Severely Degraded (combined issues)
- ⚠️ Extraction completes
- ⚠️ Confidence < 40%
- ⚠️ Many fields missing
- ⚠️ "Manual review recommended"

### Complete Failure (blank, gibberish)
- ❌ Extraction fails gracefully
- ❌ Helpful error message
- ❌ No crash/exception
- ❌ Clear user guidance

## Maintenance

### Adding New Test Scenarios

1. Create a new image manipulation function:
```python
def create_[scenario]_pdf(source_pdf: str, output_path: str, ...):
    img = pdf_to_image(source_pdf, page=0, dpi=200)
    # Apply transformations
    modified = transform(img)
    image_to_pdf(modified, output_path)
```

2. Add test method to appropriate class:
```python
def test_[scenario](self, page: Page, streamlit_app: str, temp_dir: str):
    if not PIL_AVAILABLE:
        pytest.skip("PIL/Pillow not available")

    test_path = os.path.join(temp_dir, "test.pdf")
    create_[scenario]_pdf(SOURCE_BILL, test_path)

    page.goto(streamlit_app)
    page.wait_for_load_state("networkidle")
    upload_pdf(page, test_path)

    # Assertions
    assert ..., "Expected behavior"
```

### Extending Verification Checks

Add helper functions to check for specific UI elements:

```python
def has_[indicator](page: Page) -> bool:
    """Check if [specific feature] is displayed."""
    content = get_page_text(page).lower()
    indicators = ["keyword1", "keyword2"]
    return any(i in content for i in indicators)
```

## Troubleshooting

### Tests Skip with "PIL/Pillow not available"

Install image processing dependencies:
```bash
pip install Pillow pdf2image
brew install poppler  # Required for pdf2image on macOS
```

### Streamlit App Fails to Start

Increase fixture timeout in `streamlit_app()` fixture:
```python
for _ in range(60):  # Increase from 30 to 60 seconds
    try:
        urllib.request.urlopen(url, timeout=2)
        break
    ...
```

### OCR Not Working

Install Tesseract OCR:
```bash
brew install tesseract  # macOS
```

### Tests Timeout on Large Images

Increase page wait timeout:
```python
page.wait_for_timeout(15000)  # 15 seconds for very large images
```

## Future Enhancements

- [ ] Mixed rotation (page 1 normal, page 2 rotated)
- [ ] Multi-page scanned bills
- [ ] Perspective correction (phone photos at angle)
- [ ] Handwritten notes obscuring text
- [ ] Hole-punched bills (missing portions)
- [ ] Multi-column layout confusion
- [ ] Vertical text orientation
- [ ] Non-English character recognition
- [ ] Color degradation (not just grayscale)
- [ ] Compression artifacts (JPEG quality)
- [ ] Security/sensitive data redaction
- [ ] Benchmark performance vs accuracy tradeoffs

## Related Documentation

- **E2E Test README**: `tests/README_E2E_TESTS.md` - General E2E testing guide
- **Spatial Extraction**: `spatial_extraction.py` - OCR implementation
- **Pipeline Design**: `research_generic_pipeline_output.txt` - Architecture doc
