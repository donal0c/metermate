# Data Quality & Validation E2E Tests

## Overview

The `test_e2e_data_quality.py` file contains comprehensive end-to-end tests for data quality and validation edge cases. These tests ensure the application handles malformed, incomplete, and unusual bill data gracefully without silently accepting invalid data.

## Test Categories

### 1. Missing Critical Fields (`TestMissingCriticalFields`)

Tests bills missing essential information that would make verification impossible:

- **No MPRN**: Bill without meter point reference number (should escalate to manual review)
- **No Total**: Bill without a total amount
- **No Dates**: Bill without billing period dates
- **Account Only**: Bill with account number but no other identifiers

**Expected Behavior**: App should display warnings and indicate incomplete data, not fail silently.

### 2. Cross-Field Validation Failures (`TestCrossFieldValidation`)

Tests mathematical inconsistencies and validation errors:

- **Subtotal + VAT ≠ Total**: Math errors (off by > €0.01)
- **Consumption Sum Mismatch**: Day kWh + Night kWh ≠ Total kWh
- **Negative VAT**: Unusual negative VAT amounts (credit adjustments)
- **VAT Rate > 30%**: Suspiciously high VAT rates

**Expected Behavior**: App should detect and warn about mathematical inconsistencies.

### 3. Extreme Values (`TestExtremeValues`)

Tests bills with unusual but potentially valid amounts:

- **€0.00 Total**: Credit bills or zero consumption
- **€999,999.99 Total**: Commercial mega-bills
- **0 kWh Consumption**: Estimated bills with no meter reading
- **999,999 kWh**: Industrial-scale consumption
- **Negative Balance**: Customer in credit

**Expected Behavior**: App should handle extreme values without overflow or errors.

### 4. Unusual Date Formats (`TestUnusualDateFormats`)

Tests various date formatting ambiguities and edge cases:

- **US Format**: MM/DD/YYYY vs Irish DD/MM/YYYY
- **Ambiguous Dates**: 01/02/2025 (Jan 2 or Feb 1?)
- **Future Dates**: Billing period end > today
- **Invalid Dates**: 30/02/2025 (doesn't exist)
- **Long Periods**: > 90 days
- **Short Periods**: 1 day

**Expected Behavior**: App should parse dates according to Irish format conventions or show warnings for ambiguous/invalid dates.

### 5. Currency & Number Formatting (`TestCurrencyFormatting`)

Tests various number formatting variations:

- **UK Pounds (£)**: Instead of euros
- **European Decimals**: Comma as decimal separator (1.234,56)
- **No Currency Symbol**: Just numbers
- **Scientific Notation**: 1.5E+03
- **Leading Zeros**: 0001234

**Expected Behavior**: App should extract numeric values regardless of formatting style.

### 6. Provider Edge Cases (`TestProviderEdgeCases`)

Tests bills from unusual or problematic providers:

- **Defunct Providers**: Bord Gáis Energy (rebranded to Energia)
- **Unknown Providers**: New providers not in configuration
- **Misspelled Names**: "Energya" instead of "Energia"
- **Generic Text**: "Your Energy Supplier" instead of specific name

**Expected Behavior**: App should attempt extraction even for unknown providers.

### 7. Combined Edge Cases (`TestCombinedEdgeCases`)

Tests bills with multiple issues simultaneously:

- **Multiple Issues**: Missing MPRN + invalid dates + wrong currency + math errors
- **Minimal Valid Bill**: Absolute minimum required fields

**Expected Behavior**: App should handle gracefully without crashing.

## Implementation Details

### Test PDF Generation

Tests use `pymupdf` to programmatically create test PDFs with specific edge-case content:

```python
def create_test_bill_pdf(content: str, filename: str, temp_dir: str) -> str:
    """Create a test PDF with the given text content."""
    pdf_path = os.path.join(temp_dir, filename)
    doc = pymupdf.open()
    page = doc.new_page()
    point = pymupdf.Point(50, 50)
    page.insert_text(point, content, fontsize=10)
    doc.save(pdf_path)
    doc.close()
    return pdf_path
```

This approach allows:
- Dynamic test data generation
- No dependency on external PDF files
- Complete control over edge-case content
- Reproducible test scenarios

### Temporary File Management

Tests use Python's `tempfile.TemporaryDirectory()` to create and cleanup test PDFs:

```python
@pytest.fixture
def temp_pdf_dir():
    """Create a temporary directory for test PDFs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir
    # Automatic cleanup after tests
```

## Running the Tests

### Prerequisites

```bash
# Install test dependencies
cd /Users/donalocallaghan/workspace/vibes/steve/app
source venv/bin/activate
pip install pytest pytest-playwright pymupdf

# Install Playwright browsers
python3 -m playwright install
```

### Run All Data Quality Tests

```bash
# From app/ directory
python3 -m pytest -m e2e tests/test_e2e_data_quality.py -v
```

### Run Specific Test Classes

```bash
# Test missing fields only
python3 -m pytest tests/test_e2e_data_quality.py::TestMissingCriticalFields -v

# Test validation failures only
python3 -m pytest tests/test_e2e_data_quality.py::TestCrossFieldValidation -v

# Test extreme values only
python3 -m pytest tests/test_e2e_data_quality.py::TestExtremeValues -v

# Test date formats only
python3 -m pytest tests/test_e2e_data_quality.py::TestUnusualDateFormats -v

# Test currency formatting only
python3 -m pytest tests/test_e2e_data_quality.py::TestCurrencyFormatting -v

# Test provider edge cases only
python3 -m pytest tests/test_e2e_data_quality.py::TestProviderEdgeCases -v
```

### Run Specific Individual Tests

```bash
# Test missing MPRN handling
python3 -m pytest tests/test_e2e_data_quality.py::TestMissingCriticalFields::test_bill_missing_mprn -v

# Test VAT mismatch detection
python3 -m pytest tests/test_e2e_data_quality.py::TestCrossFieldValidation::test_subtotal_plus_vat_mismatch -v

# Test zero total bills
python3 -m pytest tests/test_e2e_data_quality.py::TestExtremeValues::test_zero_total -v
```

## Test Assertions

These tests focus on verifying that the app:

1. **Doesn't Crash**: Handles edge cases without throwing errors
2. **Shows Warnings**: Displays appropriate warnings for invalid/suspicious data
3. **Extracts What It Can**: Attempts partial extraction even with missing fields
4. **Validates Math**: Detects cross-field validation failures
5. **Handles Edge Cases**: Processes extreme values without overflow/underflow

## Expected Test Results

### Pass Criteria

A test passes if:
- The app loads and processes the bill without crashing
- Appropriate warnings/errors are shown for invalid data
- Data is extracted to the best of the app's ability
- No silent acceptance of clearly invalid data

### Known Limitations

Some edge cases may not be fully handled in the current implementation:

- **Date Ambiguity**: App assumes DD/MM/YYYY format (Irish standard)
- **Currency Detection**: May not distinguish £ from € in all cases
- **Provider Matching**: Unknown providers may not trigger specific validation rules
- **Number Formats**: European decimal separators (commas) may be misinterpreted

## Extending the Tests

To add new edge-case tests:

1. **Add a new test method** to an appropriate test class
2. **Create test bill content** with the edge case
3. **Generate PDF** using `create_test_bill_pdf()`
4. **Upload and verify** using `upload_bill_and_wait()`
5. **Assert expected behavior** (warnings, extracted values, etc.)

Example:

```python
def test_new_edge_case(self, page: Page, streamlit_app: str, temp_pdf_dir: str):
    """Test description."""
    bill_text = """
    Your test bill content here
    """

    pdf_path = create_test_bill_pdf(bill_text, "test_name.pdf", temp_pdf_dir)

    page.goto(streamlit_app)
    page.wait_for_load_state("networkidle")
    upload_bill_and_wait(page, pdf_path)

    # Assertions
    page_content = page.content()
    assert "expected_text" in page_content.lower()
```

## Integration with CI/CD

These tests can be integrated into CI/CD pipelines:

```yaml
# .github/workflows/test.yml
name: E2E Data Quality Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.14'
      - run: pip install -r app/requirements.txt
      - run: pip install pytest pytest-playwright pymupdf
      - run: python3 -m playwright install --with-deps
      - run: pytest -m e2e app/tests/test_e2e_data_quality.py -v
```

## Troubleshooting

### Tests Failing to Start Streamlit

If tests fail with "Streamlit app did not start within 30 seconds":

1. Check if port 8606 is already in use
2. Increase timeout in `streamlit_app` fixture
3. Check Streamlit logs in test output

### PDF Generation Errors

If PDF creation fails:

1. Ensure `pymupdf` is installed: `pip install pymupdf`
2. Check temp directory permissions
3. Verify PyMuPDF version compatibility

### Assertion Failures

If tests pass but assertions fail:

1. Examine the actual page content: `print(page.content())`
2. Use Playwright's debugging: `PWDEBUG=1 pytest ...`
3. Take screenshots: `page.screenshot(path="debug.png")`
4. Update assertions to match actual app behavior

## Related Tests

- `test_e2e_bill_upload.py`: Basic bill upload and extraction
- `test_e2e_bill_verification.py`: HDF cross-reference validation
- `test_e2e_confidence_warnings.py`: Confidence scoring and warnings
- `test_bill_verification.py`: Unit tests for validation logic
