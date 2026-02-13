# Quick Start: Data Quality Tests

## Installation

```bash
cd /Users/donalocallaghan/workspace/vibes/steve/app
source venv/bin/activate
pip install pytest pytest-playwright pymupdf
python3 -m playwright install
```

## Run All Data Quality Tests

```bash
# Run all 27 data quality edge case tests
python3 -m pytest -m e2e tests/test_e2e_data_quality.py -v
```

## Run Specific Test Categories

### 1. Missing Critical Fields (4 tests)

```bash
# Test bills missing MPRN, totals, dates, identifiers
python3 -m pytest tests/test_e2e_data_quality.py::TestMissingCriticalFields -v -m e2e
```

**What it tests:**
- Bill with no MPRN (should escalate to manual review)
- Bill with no total amount
- Bill with no billing period dates
- Bill with account number but no MPRN

### 2. Cross-Field Validation (4 tests)

```bash
# Test mathematical inconsistencies
python3 -m pytest tests/test_e2e_data_quality.py::TestCrossFieldValidation -v -m e2e
```

**What it tests:**
- Subtotal + VAT ≠ Total (off by > €0.01)
- Day kWh + Night kWh ≠ Total kWh
- Negative VAT amounts
- VAT rates > 30%

### 3. Extreme Values (4 tests)

```bash
# Test unusual but potentially valid amounts
python3 -m pytest tests/test_e2e_data_quality.py::TestExtremeValues -v -m e2e
```

**What it tests:**
- €0.00 total (credit bill)
- €999,999.99 total (commercial mega-bill)
- 0 kWh consumption (estimated bill)
- Negative balance (customer in credit)

### 4. Unusual Date Formats (6 tests)

```bash
# Test date parsing edge cases
python3 -m pytest tests/test_e2e_data_quality.py::TestUnusualDateFormats -v -m e2e
```

**What it tests:**
- US format (MM/DD/YYYY) vs Irish (DD/MM/YYYY)
- Ambiguous dates (01/02/2025)
- Future dates (billing period end > today)
- Invalid dates (30/02/2025)
- Long periods (> 90 days)
- Short periods (1 day)

### 5. Currency & Number Formatting (5 tests)

```bash
# Test number format variations
python3 -m pytest tests/test_e2e_data_quality.py::TestCurrencyFormatting -v -m e2e
```

**What it tests:**
- UK pounds (£) instead of euros
- European decimals (comma as decimal separator)
- No currency symbols
- Scientific notation (1.5E+03)
- Leading zeros (0001234)

### 6. Provider Edge Cases (4 tests)

```bash
# Test unusual provider scenarios
python3 -m pytest tests/test_e2e_data_quality.py::TestProviderEdgeCases -v -m e2e
```

**What it tests:**
- Defunct providers (Bord Gáis Energy)
- Unknown new providers
- Misspelled provider names
- Generic provider text

## Run Individual Tests

### Example: Test missing MPRN handling

```bash
python3 -m pytest tests/test_e2e_data_quality.py::TestMissingCriticalFields::test_bill_missing_mprn -v -m e2e
```

### Example: Test VAT mismatch detection

```bash
python3 -m pytest tests/test_e2e_data_quality.py::TestCrossFieldValidation::test_subtotal_plus_vat_mismatch -v -m e2e
```

### Example: Test zero total bills

```bash
python3 -m pytest tests/test_e2e_data_quality.py::TestExtremeValues::test_zero_total -v -m e2e
```

### Example: Test ambiguous dates

```bash
python3 -m pytest tests/test_e2e_data_quality.py::TestUnusualDateFormats::test_ambiguous_date -v -m e2e
```

## Debugging Failed Tests

### Run with Playwright debugging

```bash
PWDEBUG=1 python3 -m pytest tests/test_e2e_data_quality.py::TestMissingCriticalFields::test_bill_missing_mprn -v -m e2e
```

### Run with headed browser (visible)

```bash
python3 -m pytest tests/test_e2e_data_quality.py::TestMissingCriticalFields -v -m e2e --headed
```

### Run with screenshots on failure

```bash
python3 -m pytest tests/test_e2e_data_quality.py -v -m e2e --screenshot on-failure
```

### Run with full output (no capture)

```bash
python3 -m pytest tests/test_e2e_data_quality.py -v -m e2e -s
```

## Understanding Test Output

### Passing Test

```
tests/test_e2e_data_quality.py::TestMissingCriticalFields::test_bill_missing_mprn PASSED [4%]
```

### Failing Test

```
tests/test_e2e_data_quality.py::TestCrossFieldValidation::test_subtotal_plus_vat_mismatch FAILED [12%]
FAILED tests/test_e2e_data_quality.py::TestCrossFieldValidation::test_subtotal_plus_vat_mismatch - AssertionError: Should warn about math error
```

### Skipped Test

```
tests/test_e2e_data_quality.py::TestMissingCriticalFields::test_bill_missing_total SKIPPED [8%]
s.s: E2E tests are skipped by default. Run with: pytest -m e2e
```

## Expected Test Behavior

### What Tests Check

1. **No Crashes**: App handles edge cases without throwing errors
2. **Warnings Displayed**: Appropriate warnings shown for invalid data
3. **Partial Extraction**: Attempts to extract what it can even with missing fields
4. **Math Validation**: Detects cross-field inconsistencies
5. **Graceful Degradation**: Shows meaningful messages instead of stack traces

### What Tests Don't Check

- Exact warning text (varies by implementation)
- Perfect field extraction (some edge cases may not parse perfectly)
- Specific UI layout (focuses on data presence, not styling)

## Common Issues

### Port Already in Use

```bash
# Kill process on port 8606
lsof -i :8606 | grep LISTEN | awk '{print $2}' | xargs kill -9
```

### Streamlit Won't Start

```bash
# Check if main.py exists
ls -la /Users/donalocallaghan/workspace/vibes/steve/app/main.py

# Try running Streamlit manually
cd /Users/donalocallaghan/workspace/vibes/steve/app
python3 -m streamlit run main.py --server.port 8606
```

### PyMuPDF Not Found

```bash
pip install pymupdf
```

### Playwright Browsers Missing

```bash
python3 -m playwright install chromium
```

## Quick Test Matrix

| Test Category | Count | Focus | Example Edge Case |
|--------------|-------|-------|-------------------|
| Missing Fields | 4 | Data completeness | No MPRN |
| Validation | 4 | Math accuracy | Subtotal + VAT ≠ Total |
| Extreme Values | 4 | Boundary conditions | €0.00 or €999,999.99 |
| Date Formats | 6 | Date parsing | 30/02/2025 (invalid) |
| Number Formats | 5 | Number parsing | 1.234,56 (European) |
| Providers | 4 | Provider detection | Unknown provider |
| **Total** | **27** | **Data quality** | **Comprehensive** |

## Next Steps

After running data quality tests:

1. **Review failures**: Check which edge cases fail
2. **Update parsers**: Improve extraction for failing cases
3. **Add validation**: Implement cross-field validation warnings
4. **Document behavior**: Update docs for known limitations
5. **Iterate**: Re-run tests after fixes

## Related Test Suites

- `test_e2e_bill_upload.py`: Basic bill extraction tests
- `test_e2e_invalid_pdfs.py`: Corrupted PDF handling tests
- `test_e2e_bill_verification.py`: HDF cross-reference tests
- `test_bill_verification.py`: Unit tests for validation logic
