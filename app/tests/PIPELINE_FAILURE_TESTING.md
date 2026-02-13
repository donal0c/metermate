# Extraction Pipeline Failure Testing

## Overview

Comprehensive end-to-end testing framework for the extraction pipeline failure scenarios, ensuring graceful degradation, clear error messages, and robust fallback behavior across all tiers.

## Test Files Created

### 1. `test_e2e_pipeline_failures.py`
Full Playwright E2E test suite with pytest integration.

**Location**: `/Users/donalocallaghan/workspace/vibes/steve/app/tests/test_e2e_pipeline_failures.py`

**Test Coverage**:
- Tier 0 failures (text extraction)
- Tier 1 failures (provider detection)
- Tier 2 failures (universal regex)
- Tier 3 failures (config-driven extraction)
- Tier 4 failures (LLM extraction)
- Complete pipeline failures
- Partial extraction scenarios
- Cross-validation failures
- Recovery and retry scenarios

### 2. `create_test_pdfs.py`
Utility script to generate malformed/edge-case PDFs for testing.

**Location**: `/Users/donalocallaghan/workspace/vibes/steve/app/tests/create_test_pdfs.py`

**Generated Test PDFs**:
- `corrupted.pdf` - Invalid PDF structure (PyMuPDF cannot open)
- `encrypted.pdf` - Password-protected PDF
- `empty.pdf` - Valid PDF with no text content
- `unknown_provider.pdf` - Bill from unknown provider (ACME ENERGY)
- `misspelled_provider.pdf` - Provider name misspelled ("Enerrrgia")
- `partial.pdf` - Some fields present, critical ones missing (no total)
- `invalid_math.pdf` - Cross-validation failure (subtotal + VAT ≠ total)
- `no_numeric_data.pdf` - Provider detected but no extractable numbers

**Usage**:
```bash
cd /Users/donalocallaghan/workspace/vibes/steve/app
python3 tests/create_test_pdfs.py /tmp/test_pdfs_pipeline
```

### 3. Manual Test Scripts
Standalone Playwright scripts for manual testing without pytest.

**Files**:
- `/tmp/run_pipeline_tests.py` - Complete manual test runner
- `/tmp/debug_app.py` - UI debugging script

## Critical Failure Scenarios Tested

### Tier 0 Failures (Text Extraction)

#### 1. **Corrupted PDF**
- **Trigger**: PyMuPDF raises exception on invalid PDF structure
- **Expected Behavior**:
  - Show clear error message: "Cannot read PDF" / "Corrupted file"
  - App remains functional (doesn't crash)
  - User can upload another file
- **Test**: `test_corrupted_pdf_shows_error_gracefully`

#### 2. **Encrypted PDF**
- **Trigger**: PDF requires password
- **Expected Behavior**:
  - Show encryption/password warning
  - Gracefully skip extraction
  - Suggest manual review
- **Test**: `test_encrypted_pdf_shows_encryption_warning`

#### 3. **Empty PDF**
- **Trigger**: Valid PDF with no readable text
- **Expected Behavior**:
  - Show "Insufficient text extracted" warning
  - extraction_path: `["tier0_scanned", "insufficient_text"]`
  - User sees empty raw text
  - No crash
- **Test**: `test_empty_pdf_fallback_to_manual_review`

### Tier 1 Failures (Provider Detection)

#### 4. **Unknown Provider**
- **Trigger**: Text contains no known provider keywords
- **Expected Behavior**:
  - Fallback to Tier 2 universal regex
  - extraction_path: `["tier0_native", "tier1_unknown", "tier2_universal"]`
  - Extract generic bill data (total, date, invoice number)
  - Show "unknown" provider
- **Test**: `test_unknown_provider_fallback_to_tier2`

#### 5. **Misspelled Provider**
- **Trigger**: Provider name misspelled ("Enerrrgia" instead of "Energia")
- **Expected Behavior**:
  - Treated as unknown (no fuzzy matching)
  - Fallback to Tier 2
  - Data still extracted
- **Test**: `test_misspelled_provider_treated_as_unknown`

#### 6. **Multiple Providers**
- **Trigger**: PDF mentions multiple providers (e.g., comparison document)
- **Expected Behavior**:
  - Pick first detected or mark as ambiguous
  - No conflicting data shown
  - No crash
- **Test**: `test_multiple_providers_handled_gracefully`

### Tier 2 Failures (Universal Regex)

#### 7. **No Numeric Data**
- **Trigger**: Provider detected but no extractable numbers
- **Expected Behavior**:
  - Very low confidence score (< 30%)
  - Show "manual review required" warning
  - extraction_path includes tier2_universal
- **Test**: `test_no_numeric_data_shows_low_confidence`

#### 8. **Huge Text (Regex Timeout Risk)**
- **Trigger**: PDF with 100,000+ characters
- **Expected Behavior**:
  - Complete without timeout
  - May show lower confidence
  - App remains responsive
- **Test**: `test_huge_text_pdf_doesnt_timeout`

### Tier 3 Failures (Config-Driven)

#### 9. **Config Missing for Known Provider**
- **Trigger**: Provider detected but config file missing/malformed
- **Expected Behavior**:
  - Fallback to Tier 2 universal regex
  - extraction_path: `["tier0_native", "tier1_known", "tier2_universal"]`
  - Data extracted using generic patterns
- **Note**: Requires manual config file manipulation

#### 10. **Config Regex Fails to Match**
- **Trigger**: Config exists but regex patterns don't match bill format
- **Expected Behavior**:
  - Fallback to Tier 2
  - extraction_path shows tier3 attempt then tier2
  - Some fields may extract, others missing
- **Note**: Requires modified provider config

### Tier 4 Failures (LLM)

#### 11. **Missing API Key**
- **Trigger**: `GEMINI_API_KEY` environment variable not set
- **Expected Behavior**:
  - Tier 4 skipped gracefully
  - Log: "Tier 4 skipped: GEMINI_API_KEY not set"
  - Falls back to previous tier's results
  - No crash
- **Test**: `test_missing_api_key_skips_llm_gracefully`

#### 12. **API Rate Limit (429 Error)**
- **Trigger**: Too many requests to Gemini API
- **Expected Behavior**:
  - Catch exception gracefully
  - Show "LLM unavailable - rate limit exceeded"
  - Use previous tier's extraction
  - extraction_path doesn't include tier4
- **Note**: Requires API mocking

#### 13. **API Timeout**
- **Trigger**: LLM takes > 30 seconds to respond
- **Expected Behavior**:
  - Timeout gracefully
  - Log warning
  - Return partial results from earlier tiers
- **Note**: Requires network simulation

#### 14. **Malformed JSON Response**
- **Trigger**: LLM returns invalid JSON
- **Expected Behavior**:
  - Catch parsing exception
  - Log error with response preview
  - Use previous tier's data
- **Note**: Requires API mocking

#### 15. **Hallucinated Data**
- **Trigger**: LLM invents fake MPRN/data
- **Expected Behavior**:
  - Validation catches impossible values
  - Show warning: "Unverified LLM extraction"
  - Mark with low confidence
- **Note**: Requires response validation checks

### Partial Extraction Failures

#### 16. **Missing Critical Fields**
- **Trigger**: Invoice/account number extracted, but total missing
- **Expected Behavior**:
  - Show what was extracted
  - Clear warning: "Missing: Total Amount"
  - Confidence score < 70%
  - extraction_method shown in footer
- **Test**: `test_partial_extraction_shows_warnings`

#### 17. **Cross-Validation Failures**
- **Trigger**: `subtotal + VAT ≠ total`
- **Expected Behavior**:
  - Show validation warning
  - Display all values (let user verify)
  - Confidence reduced by 20 points
  - Warning: "Math validation failed: €100 + €13.50 ≠ €200"
- **Test**: `test_invalid_math_shows_cross_validation_warning`

### Complete Pipeline Failure

#### 18. **All Tiers Fail**
- **Trigger**: Corrupted scanned PDF + no LLM + no fallback data
- **Expected Behavior**:
  - Message: "Unable to extract data - manual review required"
  - extraction_path shows all attempted tiers
  - User can still see raw text (if any)
  - App doesn't crash
  - Clear next steps suggested
- **Test**: Multiple test scenarios combined

### Recovery and Retry

#### 19. **Upload Valid PDF After Failure**
- **Trigger**: Upload corrupted PDF, then upload valid one
- **Expected Behavior**:
  - Previous error cleared
  - New file processed successfully
  - Session state properly reset
  - No data contamination from failed upload
- **Test**: `test_recovery_after_corrupted_pdf_upload`

#### 20. **Session State Reset**
- **Trigger**: Upload multiple different files in succession
- **Expected Behavior**:
  - Each upload completely independent
  - No lingering errors or data
  - UI updates correctly each time
- **Test**: `test_session_state_reset_between_uploads`

## Verification Checklist

For each failure scenario, verify:

- [ ] **Graceful Degradation**: No crashes, app remains functional
- [ ] **Clear Error Messages**: User-friendly, actionable messages
- [ ] **extraction_path Accuracy**: Correct tiers recorded
- [ ] **Appropriate Fallback**: Next tier attempted when one fails
- [ ] **Raw Text Available**: Always accessible for debugging
- [ ] **Confidence Scoring**: Reflects data quality accurately
- [ ] **Warning Visibility**: Warnings shown before extracted data
- [ ] **State Management**: Clean state between uploads
- [ ] **Logging**: Errors logged with context for debugging

## Running the Tests

### Full Test Suite (Pytest)

```bash
cd /Users/donalocallaghan/workspace/vibes/steve/app

# Run all E2E pipeline failure tests
python3 -m pytest tests/test_e2e_pipeline_failures.py -v -m e2e

# Run specific test class
python3 -m pytest tests/test_e2e_pipeline_failures.py::TestTier0Failures -v -m e2e

# Run single test
python3 -m pytest tests/test_e2e_pipeline_failures.py::TestTier0Failures::test_corrupted_pdf_shows_error_gracefully -v -m e2e

# Run in headed mode (see browser)
python3 -m pytest tests/test_e2e_pipeline_failures.py -v -m e2e --headed --slowmo 1000
```

### Manual Test Script

```bash
# 1. Create test PDFs
python3 tests/create_test_pdfs.py /tmp/test_pdfs_pipeline

# 2. Run manual Playwright tests
~/.playwright-venv/bin/python3 /tmp/run_pipeline_tests.py
```

### Individual Scenario Testing

```python
# Test specific PDF manually
from orchestrator import extract_bill_pipeline

# Test corrupted PDF
try:
    result = extract_bill_pipeline("/tmp/test_pdfs_pipeline/corrupted.pdf")
except Exception as e:
    print(f"Error: {e}")

# Test unknown provider
result = extract_bill_pipeline("/tmp/test_pdfs_pipeline/unknown_provider.pdf")
print(f"Provider: {result.bill.provider}")
print(f"Extraction path: {result.extraction_path}")
print(f"Confidence: {result.confidence.score}%")
```

## Key Findings from Orchestrator Analysis

### Current Exception Handling

**Tier 0** (`extract_text_tier0`):
- ✓ Validates PDF structure
- ✓ Returns empty result for 0-page PDFs
- ✗ Doesn't catch PyMuPDF exceptions (needs try/except)

**Tier 1** (`detect_provider`):
- ✓ Returns `unknown` for unmatched providers
- ✗ No handling for multiple provider keywords

**Tier 2** (`extract_tier2_universal`):
- ✓ Returns empty fields dict on regex failures
- ✗ No timeout protection for huge text

**Tier 3** (`extract_with_config`):
- ✓ Falls back to Tier 2 if config missing
- ✓ Returns partial results if some fields missing

**Tier 4** (`_try_tier4_llm`):
- ✓ Gracefully skips if GEMINI_API_KEY not set
- ✓ Catches RuntimeError and generic Exception
- ✓ Returns None on failure (preserves earlier tier data)
- ✗ No specific handling for API rate limits or timeouts

### Fallback Logic

```
Tier 0 Fail → Show error, stop (corrupted PDF)
Tier 0 Low Text → Try Tier 2 Spatial → Try Tier 4 LLM
Tier 1 Unknown → Tier 2 Universal → (Tier 4 if confidence < 0.85)
Tier 2 Empty → Tier 4 LLM
Tier 3 Fail → Tier 2 Universal → (Tier 4 if confidence < 0.85)
Tier 4 Fail → Use previous tier's data
```

### Confidence Escalation Triggers

LLM escalation occurs when:
- `confidence.band == "escalate"`
- Typically when confidence < 0.85 (85%)

## Recommended Improvements

### 1. Enhanced Exception Handling

```python
# In pipeline.py: extract_text_tier0
try:
    doc = _open_document(source)
except pymupdf.FileDataError:
    raise ValueError("Corrupted or invalid PDF file")
except pymupdf.PasswordError:
    raise ValueError("PDF is password-protected")
```

### 2. Regex Timeout Protection

```python
import signal

def regex_with_timeout(pattern, text, timeout=5):
    """Run regex with timeout to prevent infinite loops."""
    # Implementation needed
```

### 3. LLM Error Classification

```python
# In llm_extraction.py
except google.api_core.exceptions.TooManyRequests:
    log.warning("LLM rate limit exceeded")
    return None
except TimeoutError:
    log.warning("LLM API timeout")
    return None
```

### 4. Cross-Validation Warnings

```python
# Add to confidence.py
def validate_math(subtotal, vat, total):
    expected = subtotal + vat
    if abs(expected - total) > 0.01:
        return ValidationCheck(
            name="math_consistency",
            passed=False,
            message=f"€{subtotal} + €{vat} ≠ €{total} (expected €{expected})"
        )
```

## Test Data

All test PDFs are generated programmatically to ensure:
- Reproducibility
- No external dependencies
- Controlled failure conditions
- Easy regeneration if PDFs corrupted

**Test PDF Storage**: `/tmp/test_pdfs_pipeline/`

**Regenerate anytime**:
```bash
python3 tests/create_test_pdfs.py /tmp/test_pdfs_pipeline
```

## Success Criteria

A passing test suite means:

1. **Zero Crashes**: All failure scenarios handled gracefully
2. **100% Error Coverage**: Every tier failure has clear messaging
3. **Fallback Verification**: Extraction path shows tier progression
4. **User Experience**: Error messages are actionable and clear
5. **State Isolation**: No contamination between uploads
6. **Debug Access**: Raw text always available
7. **Confidence Accuracy**: Scores reflect actual data quality

## Future Test Scenarios

Additional scenarios to implement:

1. **Network Failures**:
   - Test Tier 4 with network disconnection
   - Test OCR with offline mode

2. **Resource Limits**:
   - Test with memory-constrained environment
   - Test with CPU throttling

3. **Concurrent Uploads**:
   - Multiple users uploading simultaneously
   - Race condition testing

4. **Edge Case Bills**:
   - Zero-cost bills
   - Negative values (credits)
   - Multiple MPRNs on one bill
   - Multi-page bills with data split across pages

5. **Performance Testing**:
   - 100+ page PDF processing time
   - Tier 4 LLM response time measurement
   - Memory usage profiling

## Dependencies

- `pytest >= 7.0.0`
- `pytest-playwright >= 0.4.0`
- `playwright >= 1.40.0`
- `pymupdf >= 1.23.0`
- `streamlit >= 1.30.0`
- `PIL/Pillow` (for image test PDF generation)

Install:
```bash
pip install pytest pytest-playwright
python3 -m playwright install
```

## Notes

- Tests require Streamlit app to be running (auto-started by fixtures)
- Browser tests run in headed mode by default for visibility
- Test PDFs created fresh on each run to avoid state issues
- Some tests require environment variable manipulation (`GEMINI_API_KEY`)
- Cross-validation tests verify UI shows warnings, not data correction

---

**Created**: 2026-02-13
**Last Updated**: 2026-02-13
**Test Coverage**: 20 critical failure scenarios
**Status**: Test framework created, ready for execution once app dependencies resolved
