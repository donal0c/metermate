# Data Quality Test Coverage Summary

## Overview

Comprehensive E2E test suite for data quality and validation edge cases in bill extraction.

**Total Tests**: 29 (across 7 test classes)
**Test File**: `test_e2e_data_quality.py`
**Port**: 8606
**Approach**: Programmatic PDF generation with `pymupdf`

## Coverage Matrix

### 1. Missing Critical Fields (4 tests)

| Test | Edge Case | Expected Behavior |
|------|-----------|-------------------|
| `test_bill_missing_mprn` | No MPRN | Warning/manual review flag |
| `test_bill_missing_total` | No total amount | Validation warning |
| `test_bill_missing_dates` | No billing period | Date warning |
| `test_bill_account_only_no_mprn` | Account # but no MPRN | MPRN warning |

**Risk Level**: HIGH - Missing critical fields prevent verification

### 2. Cross-Field Validation (4 tests)

| Test | Edge Case | Expected Behavior |
|------|-----------|-------------------|
| `test_subtotal_plus_vat_mismatch` | Subtotal + VAT ≠ Total | Math error warning |
| `test_consumption_sum_mismatch` | Day + Night ≠ Total kWh | Consumption mismatch |
| `test_negative_vat_amount` | VAT < 0 | Handle credit adjustment |
| `test_vat_rate_too_high` | VAT > 30% | Flag suspicious rate |

**Risk Level**: MEDIUM - Indicates data quality issues or billing errors

### 3. Extreme Values (4 tests)

| Test | Edge Case | Expected Behavior |
|------|-----------|-------------------|
| `test_zero_total` | €0.00 total | Handle without errors |
| `test_mega_commercial_bill` | €999,999.99 total | No overflow |
| `test_zero_kwh_estimated_bill` | 0 kWh consumption | Accept estimated bill |
| `test_negative_balance_customer_in_credit` | Balance < 0 | Show credit status |

**Risk Level**: LOW - Valid edge cases that should be supported

### 4. Unusual Date Formats (6 tests)

| Test | Edge Case | Expected Behavior |
|------|-----------|-------------------|
| `test_us_date_format` | MM/DD/YYYY | Parse or warn |
| `test_ambiguous_date` | 01/02/2025 | Assume DD/MM/YYYY |
| `test_future_date` | End date > today | Accept with warning |
| `test_invalid_date` | 30/02/2025 | Parse error handling |
| `test_long_billing_period` | > 90 days | Accept long periods |
| `test_one_day_period` | 1 day only | Accept short periods |

**Risk Level**: MEDIUM - Date parsing errors can cause verification failures

### 5. Currency & Number Formatting (5 tests)

| Test | Edge Case | Expected Behavior |
|------|-----------|-------------------|
| `test_uk_pounds_instead_of_euros` | £ instead of € | Extract numbers |
| `test_european_decimal_separator` | 1.234,56 format | Parse correctly |
| `test_no_currency_symbol` | Numbers only | Extract values |
| `test_scientific_notation` | 1.5E+03 | Parse if possible |
| `test_leading_zeros` | 0001234 | Normalize numbers |

**Risk Level**: LOW - Formatting variations, not data errors

### 6. Provider Edge Cases (4 tests)

| Test | Edge Case | Expected Behavior |
|------|-----------|-------------------|
| `test_defunct_provider_bord_gais` | Old provider name | Extract anyway |
| `test_unknown_new_provider` | Not in config | Attempt extraction |
| `test_misspelled_provider` | Typo in name | Extract as written |
| `test_generic_provider_text` | "Your Energy Supplier" | Generic extraction |

**Risk Level**: LOW - Provider detection, not critical for extraction

### 7. Combined Edge Cases (2 tests)

| Test | Edge Case | Expected Behavior |
|------|-----------|-------------------|
| `test_multiple_issues_combined` | Many issues at once | Graceful degradation |
| `test_minimal_valid_bill` | Minimal required fields | Accept minimal data |

**Risk Level**: HIGH - Tests resilience under multiple failures

## Critical Validation Rules

### Should REJECT (block processing)

1. **No MPRN + No verification possible** → Manual review
2. **Date overlap < 50%** → Can't verify against HDF
3. **MPRN mismatch** → Wrong meter data

### Should WARN (flag but proceed)

1. **Subtotal + VAT ≠ Total** (> €0.01 difference)
2. **Day + Night ≠ Total kWh** (> 0.1 kWh difference)
3. **VAT rate < 0% or > 30%**
4. **Missing total amount**
5. **Missing billing dates**
6. **Future billing period end**
7. **Invalid dates** (30/02/2025)

### Should ACCEPT (valid edge cases)

1. **€0.00 total** (credit bill)
2. **Very large amounts** (commercial bills)
3. **0 kWh consumption** (estimated bill)
4. **Negative balance** (customer in credit)
5. **Long billing periods** (> 90 days)
6. **Short billing periods** (1 day)
7. **Unknown providers**

## Test Implementation

### PDF Generation

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

### Temporary Files

All test PDFs are created in temporary directories and automatically cleaned up after tests complete.

### Upload Helper

```python
def upload_bill_and_wait(page: Page, pdf_path: str, wait_time: int = 3000):
    """Helper to upload a bill PDF and wait for processing."""
    file_input = page.locator('[data-testid="stFileUploader"] input[type="file"]').first
    file_input.set_input_files(pdf_path)
    page.wait_for_timeout(wait_time)
```

## Assertion Strategy

Tests use flexible assertions that check for expected behavior without being overly prescriptive:

```python
# Check for any relevant warning keywords
assert any(keyword in page_content.lower() for keyword in [
    "mprn", "missing", "warning", "manual review", "incomplete"
]), "Should warn about missing MPRN"
```

This approach allows the app to evolve its warning messages without breaking tests.

## Known Limitations

### Current Implementation

1. **Date Parsing**: Assumes DD/MM/YYYY (Irish format)
   - US format (MM/DD/YYYY) may be misinterpreted
   - Ambiguous dates default to DD/MM/YYYY

2. **Number Parsing**: Assumes dot as decimal separator
   - European format (comma) may be misinterpreted
   - Scientific notation may not parse

3. **Provider Matching**: Based on configured providers
   - Unknown providers use generic extraction
   - Misspellings may not match provider-specific rules

4. **Currency Detection**: May not distinguish £ from €
   - Relies on text context
   - No automatic currency conversion

### Future Improvements

1. **Smart Date Parsing**: Detect format from context
2. **Locale-Aware Numbers**: Support European decimal format
3. **Provider Fuzzy Matching**: Handle misspellings
4. **Currency Validation**: Flag non-Euro amounts
5. **Cross-Field Validation**: Implement math checks in app

## Running Tests

### All data quality tests
```bash
pytest -m e2e tests/test_e2e_data_quality.py -v
```

### Specific risk level
```bash
# High-risk tests (missing critical fields, combined issues)
pytest -m e2e tests/test_e2e_data_quality.py::TestMissingCriticalFields -v
pytest -m e2e tests/test_e2e_data_quality.py::TestCombinedEdgeCases -v

# Medium-risk tests (validation, date parsing)
pytest -m e2e tests/test_e2e_data_quality.py::TestCrossFieldValidation -v
pytest -m e2e tests/test_e2e_data_quality.py::TestUnusualDateFormats -v

# Low-risk tests (formatting, providers, extreme values)
pytest -m e2e tests/test_e2e_data_quality.py::TestCurrencyFormatting -v
pytest -m e2e tests/test_e2e_data_quality.py::TestProviderEdgeCases -v
pytest -m e2e tests/test_e2e_data_quality.py::TestExtremeValues -v
```

## Integration with Verification

These data quality tests complement the bill verification tests:

1. **Data Quality Tests** → Ensure extraction handles edge cases
2. **Bill Verification Tests** → Ensure HDF cross-reference works
3. **Combined** → End-to-end confidence in data accuracy

### Test Flow

```
Bill PDF → Extraction → Data Quality Check → HDF Verification → Result
           (tested)    (these tests)          (separate tests)
```

## Coverage Gaps

Tests to consider adding:

1. **Multi-page bills** with fields spread across pages
2. **Bills in other languages** (Irish, Polish, etc.)
3. **Historical bills** from 10+ years ago
4. **Bills with payment plans** or installments
5. **Bills with solar export** negative amounts
6. **Bills with demand charges** (kVA instead of kWh)
7. **Bills with time-of-use** (TOU) tariffs
8. **Bills with carbon tax** line items
9. **Bills with smart meter fees** itemized
10. **Bills with reconnection fees** or penalties

## Success Metrics

### Test Passing Criteria

A test passes if:
1. App doesn't crash or show stack traces
2. Appropriate warnings are displayed (where applicable)
3. Data extraction attempts graceful degradation
4. No silent acceptance of clearly invalid data

### Quality Indicators

- **100% pass rate** → Robust edge case handling
- **75-99% pass rate** → Some edge cases need work
- **< 75% pass rate** → Significant quality issues

## Related Documentation

- `README_DATA_QUALITY_TESTS.md` - Detailed test documentation
- `QUICK_START_DATA_QUALITY.md` - Quick reference guide
- `README.md` - Overall E2E test suite documentation
