# E2E Tests for Energy Insight

This directory contains end-to-end (E2E) tests for the Energy Insight Streamlit application using Playwright.

## Test Files

### `test_e2e_bill_upload.py` (NEW)
Comprehensive tests for **Single Bill Upload & Extraction** with native PDFs.

**Test scenarios covered:**
1. Upload PDF via sidebar file uploader
2. Extraction completes without errors
3. Provider name is correctly detected (Energia, Go Power)
4. Confidence score is displayed and >= 70%
5. Account Details section shows: MPRN, Account Number, Invoice Number
6. Billing Period section shows dates (1 Mar 2025 → 31 Mar 2025 for Energia)
7. Consumption section shows kWh values
8. Costs section shows subtotal, VAT, total
9. Field counts match expected (e.g., "Account: 4/6")

**Test classes:**
- `TestBillUploadUI` (3 tests) - File uploader visibility and upload flow
- `TestEnergiaExtraction` (19 tests) - Energia bill extraction validation
- `TestGoPowerExtraction` (9 tests) - Go Power bill extraction validation
- `TestExtractionUI` (4 tests) - UI components and display features
- `TestExtractionValidation` (3 tests) - Data consistency and validation

**Bill files tested:**
- `3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf` - Native Energia bill
- `1845.pdf` - Go Power bill (scanned)

### `test_e2e_invalid_pdfs.py` (NEW)
Comprehensive tests for **Corrupted & Invalid PDF Edge Cases**.

**Test scenarios covered:**
1. Password-protected PDFs (clear error message)
2. Corrupted PDF headers (invalid structure)
3. Empty PDFs (0 pages)
4. Non-PDF files renamed (.txt, .jpg as .pdf)
5. Truncated PDFs (file cut off mid-stream)
6. PDFs with no text or images (blank pages)
7. Multi-account bills (3+ MPRNs in single PDF)
8. Extremely large PDFs (500+ pages, performance test)
9. Tiny PDFs (< 1 KB files)
10. PDFs with embedded binary junk in text streams

**Expected behaviors tested:**
- No crashes or stack traces exposed to user
- Clear error messages ("Invalid PDF", "Cannot extract text", etc.)
- Graceful fallback (skip to next tier or show manual review prompt)
- App continues working after errors (recovery testing)
- Memory limit handling for large files

**Test classes:**
- `TestCorruptedPDFHandling` (3 tests) - Corrupted headers, truncated files, binary junk
- `TestInvalidFileTypes` (2 tests) - Text and image files renamed as .pdf
- `TestEmptyAndBlankPDFs` (2 tests) - Empty PDFs and blank pages
- `TestExtremeSizes` (3 tests) - Tiny PDFs (< 1KB), large PDFs (500+ pages)
- `TestMultiAccountBills` (1 test) - Multiple MPRNs in single bill
- `TestRecoveryAndResilience` (2 tests) - App recovery after bad uploads
- `TestErrorMessageQuality` (3 tests) - User-friendly error messages
- `TestPasswordProtectedPDFs` (1 test) - Encrypted/password-protected PDFs

**Test fixtures generate corrupted files:**
- All test PDFs are created programmatically in a temp directory
- No manual file creation needed
- Fixtures include: corrupted_header, empty, truncated, text_as_pdf, image_as_pdf, tiny, blank_pages, large_500_pages, multi_mprn, binary_junk

### `test_e2e_data_quality.py` (NEW)
Comprehensive tests for **Data Quality & Validation Edge Cases**.

**Test scenarios covered:**
1. Missing critical fields (MPRN, total, dates, account #)
2. Cross-field validation failures (math errors, negative values)
3. Extreme values (€0.00, €999,999.99, 0 kWh, negative balances)
4. Unusual date formats (US vs Irish, ambiguous, future, invalid)
5. Currency & number formatting (pounds, European decimals, scientific notation)
6. Provider edge cases (defunct, unknown, misspelled)

**Expected behaviors tested:**
- No silent acceptance of invalid data
- Appropriate warnings displayed for missing/invalid fields
- Math validation for subtotal + VAT = total
- Consumption sum validation (day + night = total kWh)
- Extreme value handling without overflow
- Date parsing according to Irish format (DD/MM/YYYY)
- Graceful handling of unknown providers

**Test classes:**
- `TestMissingCriticalFields` (4 tests) - No MPRN, no total, no dates, account-only
- `TestCrossFieldValidation` (4 tests) - VAT mismatch, consumption mismatch, negative VAT, high VAT rate
- `TestExtremeValues` (4 tests) - Zero total, mega-bills, zero kWh, negative balance
- `TestUnusualDateFormats` (6 tests) - US dates, ambiguous dates, future dates, invalid dates, long periods, 1-day periods
- `TestCurrencyFormatting` (5 tests) - UK pounds, European decimals, no currency, scientific notation, leading zeros
- `TestProviderEdgeCases` (4 tests) - Defunct providers, unknown providers, misspelled names, generic text
- `TestCombinedEdgeCases` (2 tests) - Multiple issues, minimal valid bill

**Test implementation:**
- All test PDFs created programmatically using `pymupdf`
- No dependency on external PDF files
- Temporary directory cleanup automatic
- Dynamic edge-case generation for reproducibility

See `README_DATA_QUALITY_TESTS.md` for detailed documentation.

### `test_e2e_welcome.py`
Comprehensive tests for the Welcome Page & Navigation functionality.

**Test scenarios covered:**
1. App starts successfully on port 8501
2. Welcome page displays "Welcome to Energy Insight" heading
3. File uploader is visible in sidebar
4. "Try sample HDF data" button is present and clickable
5. "Try sample bill" button is present and clickable
6. Clicking sample bill button loads bill extraction view with confidence metrics
7. Navigation back to welcome page works

**Test classes:**
- `TestAppStartup` - Verifies app starts and welcome page displays correctly
- `TestSampleDataButtons` - Tests sample data button presence and functionality
- `TestBillExtractionView` - Tests bill extraction view and confidence metrics
- `TestNavigation` - Tests navigation between views
- `TestPageResponsiveness` - Tests page load times and responsiveness
- `TestScreenshots` - Captures screenshots for debugging

## Prerequisites

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Install Playwright browsers:**
   ```bash
   python3 -m playwright install
   ```

3. **Ensure sample data exists:**
   - HDF sample: `/Users/donalocallaghan/workspace/vibes/steve/HDF_calckWh_10306268587_03-02-2026.csv`
   - Bill sample: `/Users/donalocallaghan/workspace/vibes/steve/sample_bills/1845.pdf`

## Running Tests

### Run all E2E tests
```bash
cd /Users/donalocallaghan/workspace/vibes/steve/app
python3 -m pytest tests/ -v -m e2e
```

### Run all bill upload tests
```bash
python3 -m pytest tests/test_e2e_bill_upload.py -v -m e2e
```

### Run all welcome page tests
```bash
python3 -m pytest tests/test_e2e_welcome.py -v -m e2e
```

### Run all invalid PDF edge case tests
```bash
python3 -m pytest tests/test_e2e_invalid_pdfs.py -v -m e2e
```

### Run all data quality edge case tests
```bash
python3 -m pytest tests/test_e2e_data_quality.py -v -m e2e
```

### Run specific test class (e.g., Energia extraction)
```bash
python3 -m pytest tests/test_e2e_bill_upload.py::TestEnergiaExtraction -v -m e2e
```

### Run specific edge case tests (e.g., corrupted PDFs)
```bash
python3 -m pytest tests/test_e2e_invalid_pdfs.py::TestCorruptedPDFHandling -v -m e2e
```

### Run specific test
```bash
python3 -m pytest tests/test_e2e_bill_upload.py::TestEnergiaExtraction::test_confidence_score_displayed_and_valid -v -m e2e
```

### Run with verbose output and browser visibility
```bash
python3 -m pytest tests/test_e2e_welcome.py -v -m e2e --headed
```

### Run with failure screenshots
```bash
python3 -m pytest tests/test_e2e_welcome.py -v -m e2e --screenshot on-failure
```

## Bill Upload Tests Details

The `test_e2e_bill_upload.py` file contains 38 tests organized into 5 test classes:

### Energia Bill Tests (19 tests)
Tests the native Energia bill: `3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf`

- Provider detection and naming
- Confidence score validation (>= 70%)
- Account Details fields: MPRN, Account Number, Invoice Number
- Billing Period dates: 1 Mar 2025 → 31 Mar 2025
- Consumption values in kWh
- Cost breakdown: subtotal, VAT, total
- Field count validation (e.g., "Account: 4/6")

### Go Power Bill Tests (9 tests)
Tests the Go Power bill: `1845.pdf` (scanned PDF)

- Provider detection as "Go Power"
- MPRN extraction: 10006002900
- Confidence score display
- All major sections visibility
- Field count validation

### Key Validations
1. **Provider Detection**: Correctly identifies Energia and Go Power
2. **Confidence Score**: Displayed as percentage, >= 70% threshold
3. **Section Headers**: Account Details, Billing Period, Consumption, Costs, Balance
4. **Field Format**: Shows "Section: X/Y" format (e.g., "Account: 4/6")
5. **Date Format**: Uses arrow separator "→" between period start and end
6. **Currency**: Euro symbol (€) for monetary values
7. **Units**: "kWh" for energy consumption
8. **Export**: Download button for Excel export
9. **Error Handling**: No error alerts for valid PDFs
10. **Warning Order**: Warnings appear before Account Details section

## Test Configuration

### Ports
- Bill upload tests use **port 8599** (to avoid conflicts with other tests)
- Invalid PDF tests use **port 8601** (to avoid conflicts with other tests)
- Data quality tests use **port 8606** (to avoid conflicts with other tests)
- Welcome page tests use **port 8501** (Streamlit default)

### Waits & Timeouts
- Page load timeout: 15 seconds
- Bill extraction timeout: 5 seconds
- Page load test limit: 15 seconds total

### Automatic Cleanup
The `streamlit_app` fixture automatically:
1. Starts the Streamlit server
2. Waits for readiness (up to 30 seconds)
3. Terminates the process after tests complete
4. Handles cleanup even on test failure

## Troubleshooting

### Port Already in Use
If port 8501 is busy:
1. Kill the existing Streamlit process:
   ```bash
   lsof -i :8501 | grep LISTEN | awk '{print $2}' | xargs kill -9
   ```
2. Re-run tests

### Playwright Browsers Not Installed
```bash
python3 -m playwright install chromium
```

### Sample Files Not Found
Tests gracefully skip if sample files don't exist:
- HDF sample is optional (test checks `os.path.exists()`)
- Bill sample is optional (test checks `os.path.exists()`)

### Tests Marked as Skipped by Default
E2E tests require explicit `-m e2e` flag:
```bash
pytest tests/test_e2e_welcome.py -m e2e  # Runs E2E tests
pytest tests/test_e2e_welcome.py         # Skips E2E tests
```

## Interpreting Results

### Successful Test Run
```
test_app_starts_on_port_8501 PASSED
test_welcome_page_displays_heading PASSED
test_file_uploader_visible_in_sidebar PASSED
...
====== 15 passed in 45.23s ======
```

### Common Failures

**"Streamlit app did not start"**
- Check that main.py is in the correct location
- Check for Python errors in the app code
- Verify all dependencies are installed

**"Welcome to Energy Insight" not found**
- The heading text might have changed in main.py
- Check `show_welcome()` function in main.py
- Verify page fully loaded with `page.wait_for_load_state("networkidle")`

**Sample button not clickable**
- Sample files might not exist
- Button might be disabled (check `disabled` attribute)
- Tests skip gracefully if files don't exist

## Screenshots

Screenshots are saved to `tests/screenshots/` directory:
- `welcome_page.png` - Welcome page reference screenshot
- `bill_extraction.png` - Bill extraction view reference screenshot

These are generated by `TestScreenshots` class for debugging.

## Extending Tests

To add new test scenarios:

1. **Add new test class:**
   ```python
   class TestNewFeature:
       """Test new feature functionality."""

       def test_new_feature(self, page: Page, streamlit_app: str):
           """Test description."""
           page.goto(streamlit_app)
           page.wait_for_load_state("networkidle")
           # Add test code here
           assert True
   ```

2. **Mark with E2E marker:**
   ```python
   @pytest.mark.e2e
   def test_example():
       pass
   ```

3. **Use Playwright locators:**
   - `page.get_by_text()` - Find by visible text
   - `page.locator()` - Find by CSS selector
   - `page.get_by_role()` - Find by accessibility role
   - `page.get_by_test_id()` - Find by data-testid attribute

## Best Practices

1. **Always wait for network idle:**
   ```python
   page.wait_for_load_state("networkidle")
   ```

2. **Use expect() for assertions:**
   ```python
   from playwright.sync_api import expect
   expect(element).to_be_visible()
   ```

3. **Add timeouts to waits:**
   ```python
   page.get_by_text("text").to_be_visible(timeout=15000)
   ```

4. **Clean up resources:**
   - The `streamlit_app` fixture handles cleanup automatically
   - No manual cleanup needed in tests

5. **Skip gracefully when needed:**
   ```python
   if not os.path.exists(sample_file):
       pytest.skip("Sample file not found")
   ```

## Performance Notes

- Full test suite runs in ~45-60 seconds
- Bill extraction tests add ~5 seconds per test
- Screenshot tests add minimal overhead (~100ms)
- Network idle wait is the primary timing factor

## Related Files

- `/Users/donalocallaghan/workspace/vibes/steve/app/main.py` - Main Streamlit app
- `/Users/donalocallaghan/workspace/vibes/steve/app/conftest.py` - Parent pytest config
- `/Users/donalocallaghan/workspace/vibes/steve/app/requirements.txt` - Dependencies

## Support

For issues with specific tests, check:
1. Streamlit app logs (subprocess stderr)
2. Playwright trace file (if enabled)
3. Screenshots in `tests/screenshots/` directory
