# Invalid PDF Edge Case Tests - Quick Reference

This document provides a detailed breakdown of the `test_e2e_invalid_pdfs.py` test suite.

## Overview

The invalid PDF test suite contains **15 tests** across **8 test classes** that verify the Steve app's resilience when handling corrupted, malformed, and edge-case PDF files.

## Test Fixtures (Programmatically Generated PDFs)

All test PDFs are created programmatically in a temporary directory. No manual file creation is required.

### Corrupted PDFs

| Fixture | Description | File Size | Issue Simulated |
|---------|-------------|-----------|-----------------|
| `corrupted_header_pdf` | PDF with invalid magic number (`%XDF-1.4` instead of `%PDF-1.4`) | ~200 bytes | Corrupted file headers |
| `truncated_pdf` | Valid header but cut off mid-stream | ~150 bytes | Incomplete file transfer |
| `binary_junk_pdf` | Valid PDF with binary garbage in text streams | ~600 bytes | Malware signatures, corrupted content |

### Invalid File Types

| Fixture | Description | File Size | Issue Simulated |
|---------|-------------|-----------|-----------------|
| `text_file_as_pdf` | Plain text file with `.pdf` extension | ~100 bytes | User error, wrong file type |
| `image_file_as_pdf` | JPEG image with `.pdf` extension | ~30 bytes | User error, renamed files |

### Empty/Blank PDFs

| Fixture | Description | File Size | Issue Simulated |
|---------|-------------|-----------|-----------------|
| `empty_pdf` | Valid PDF structure with 0 pages | ~150 bytes | Export errors, empty bills |
| `blank_pages_pdf` | Valid PDF with 2 blank pages (no text/images) | ~300 bytes | Scanned blank pages |

### Extreme Sizes

| Fixture | Description | File Size | Issue Simulated |
|---------|-------------|-----------|-----------------|
| `tiny_pdf` | Minimal valid PDF | ~200 bytes | Corrupted downloads |
| `large_pdf` | 500-page PDF (generated with PyMuPDF) | ~2-3 MB | Batch processing, memory limits |

### Multi-Account Bills

| Fixture | Description | File Size | Issue Simulated |
|---------|-------------|-----------|-----------------|
| `multi_mprn_pdf` | PDF containing 3 different MPRNs | ~1 KB | Consolidated bills, multiple properties |

## Test Classes & Coverage

### 1. TestCorruptedPDFHandling (3 tests)

**Purpose:** Verify app doesn't crash on corrupted PDFs and shows clear errors.

| Test | Checks | Expected Behavior |
|------|--------|-------------------|
| `test_corrupted_header_shows_error` | Corrupted header handling | Error alert, no stack trace |
| `test_truncated_pdf_shows_error` | Truncated file handling | Error/warning alert |
| `test_binary_junk_pdf_handles_gracefully` | Binary garbage in streams | Extracts or shows graceful error |

**Critical validations:**
- No `Traceback` or `RuntimeError` visible to user
- Error messages are user-friendly
- App remains responsive

---

### 2. TestInvalidFileTypes (2 tests)

**Purpose:** Verify non-PDF files renamed as `.pdf` are rejected gracefully.

| Test | Checks | Expected Behavior |
|------|--------|-------------------|
| `test_text_file_as_pdf_shows_error` | Text file with .pdf extension | Clear error message |
| `test_image_file_as_pdf_shows_error` | Image file with .pdf extension | Error alert |

**Critical validations:**
- Error message contains: "error", "invalid", "cannot", or "failed"
- No crashes or hangs

---

### 3. TestEmptyAndBlankPDFs (2 tests)

**Purpose:** Verify empty PDFs and blank pages are handled gracefully.

| Test | Checks | Expected Behavior |
|------|--------|-------------------|
| `test_empty_pdf_shows_clear_message` | 0-page PDF | Clear message about no content |
| `test_blank_pages_pdf_shows_warning` | Blank pages (no text) | Warning about insufficient text |

**Critical validations:**
- Message contains: "no pages", "empty", "insufficient text", "cannot extract", or "no content"
- No crashes

---

### 4. TestExtremeSizes (3 tests)

**Purpose:** Verify tiny and massive PDFs don't cause crashes or timeouts.

| Test | Checks | Expected Behavior |
|------|--------|-------------------|
| `test_tiny_pdf_handles_gracefully` | < 1 KB PDF | Processes without crash |
| `test_large_pdf_shows_timeout_or_completes` | 500-page PDF | Completes or shows timeout |
| `test_large_pdf_does_not_crash_browser` | 500-page PDF | Browser remains responsive |

**Critical validations:**
- App remains functional after tiny PDF
- Large PDF either completes or times out gracefully (< 65 seconds)
- Sidebar remains visible (browser not crashed)

---

### 5. TestMultiAccountBills (1 test)

**Purpose:** Verify bills with multiple MPRNs are handled appropriately.

| Test | Checks | Expected Behavior |
|------|--------|-------------------|
| `test_multi_mprn_pdf_shows_warning_or_extracts_one` | 3 MPRNs in one PDF | Warning or extracts primary MPRN |

**Critical validations:**
- Shows warning about multiple accounts, OR
- Extracts one MPRN (first match wins), OR
- Shows "manual review needed"

---

### 6. TestRecoveryAndResilience (2 tests)

**Purpose:** Verify app continues working after bad uploads.

| Test | Checks | Expected Behavior |
|------|--------|-------------------|
| `test_app_recovers_after_bad_pdf` | Recovery after bad upload | Valid PDF works after error |
| `test_multiple_bad_uploads_dont_crash` | Multiple bad uploads in sequence | App stays responsive |

**Critical validations:**
- App functional after error
- Sidebar visible after multiple failures
- No accumulated errors causing crash

---

### 7. TestErrorMessageQuality (3 tests)

**Purpose:** Verify error messages are user-friendly, not technical jargon.

| Test | Checks | Expected Behavior |
|------|--------|-------------------|
| `test_error_messages_are_user_friendly` | Error clarity | No technical terms exposed |
| `test_no_stack_traces_in_ui` | Stack trace hiding | No stack traces in UI |
| `test_clear_actionable_guidance` | Actionable messages | Helpful guidance words present |

**Critical validations:**
- No exposure of: `Traceback`, `Exception:`, `raise`, `pymupdf`, `NoneType`
- No stack indicators: `File "`, `line `, `Traceback (most recent call last)`
- Contains guidance: `please`, `ensure`, `valid`, `try`, `check`

---

### 8. TestPasswordProtectedPDFs (1 test - SKIPPED)

**Purpose:** Verify encrypted PDFs are handled gracefully (requires additional setup).

| Test | Checks | Expected Behavior |
|------|--------|-------------------|
| `test_password_protected_pdf_shows_clear_error` | Encrypted PDF | Clear password/encryption error |

**Note:** Currently skipped - requires password-protected PDF generation (pypdf or similar).

---

## Running the Tests

### Run all invalid PDF tests
```bash
cd /Users/donalocallaghan/workspace/vibes/steve/app
python3 -m pytest tests/test_e2e_invalid_pdfs.py -v -m e2e
```

### Run specific test class
```bash
python3 -m pytest tests/test_e2e_invalid_pdfs.py::TestCorruptedPDFHandling -v -m e2e
```

### Run single test
```bash
python3 -m pytest tests/test_e2e_invalid_pdfs.py::TestCorruptedPDFHandling::test_corrupted_header_shows_error -v -m e2e
```

### Run with browser visible (for debugging)
```bash
python3 -m pytest tests/test_e2e_invalid_pdfs.py -v -m e2e --headed
```

### Run with screenshot on failure
```bash
python3 -m pytest tests/test_e2e_invalid_pdfs.py -v -m e2e --screenshot on-failure
```

## Expected Test Output

### Successful run
```
test_e2e_invalid_pdfs.py::TestCorruptedPDFHandling::test_corrupted_header_shows_error PASSED
test_e2e_invalid_pdfs.py::TestCorruptedPDFHandling::test_truncated_pdf_shows_error PASSED
test_e2e_invalid_pdfs.py::TestCorruptedPDFHandling::test_binary_junk_pdf_handles_gracefully PASSED
test_e2e_invalid_pdfs.py::TestInvalidFileTypes::test_text_file_as_pdf_shows_error PASSED
test_e2e_invalid_pdfs.py::TestInvalidFileTypes::test_image_file_as_pdf_shows_error PASSED
test_e2e_invalid_pdfs.py::TestEmptyAndBlankPDFs::test_empty_pdf_shows_clear_message PASSED
test_e2e_invalid_pdfs.py::TestEmptyAndBlankPDFs::test_blank_pages_pdf_shows_warning PASSED
test_e2e_invalid_pdfs.py::TestExtremeSizes::test_tiny_pdf_handles_gracefully PASSED
test_e2e_invalid_pdfs.py::TestExtremeSizes::test_large_pdf_shows_timeout_or_completes PASSED
test_e2e_invalid_pdfs.py::TestExtremeSizes::test_large_pdf_does_not_crash_browser PASSED
test_e2e_invalid_pdfs.py::TestMultiAccountBills::test_multi_mprn_pdf_shows_warning_or_extracts_one PASSED
test_e2e_invalid_pdfs.py::TestRecoveryAndResilience::test_app_recovers_after_bad_pdf PASSED
test_e2e_invalid_pdfs.py::TestRecoveryAndResilience::test_multiple_bad_uploads_dont_crash PASSED
test_e2e_invalid_pdfs.py::TestErrorMessageQuality::test_error_messages_are_user_friendly PASSED
test_e2e_invalid_pdfs.py::TestErrorMessageQuality::test_no_stack_traces_in_ui PASSED
test_e2e_invalid_pdfs.py::TestErrorMessageQuality::test_clear_actionable_guidance PASSED
test_e2e_invalid_pdfs.py::TestPasswordProtectedPDFs::test_password_protected_pdf_shows_clear_error SKIPPED

====== 16 passed, 1 skipped in 120.45s ======
```

## Error Handling Expectations

### What the app SHOULD do:
- Show clear error messages like:
  - "Invalid PDF file"
  - "Cannot extract text from this PDF"
  - "File appears to be corrupted"
  - "Please ensure this is a valid electricity bill PDF"
- Remain responsive and functional
- Allow user to upload another file
- Log technical details to console (not shown to user)

### What the app SHOULD NOT do:
- Show raw Python stack traces
- Display technical error messages like "RuntimeError: Cannot open PDF from bytes: ..."
- Crash or freeze
- Show exposed package names (pymupdf, pdfplumber, etc.)
- Leave the app in a broken state

## Common Issues & Debugging

### Large PDF test times out
**Cause:** PyMuPDF generation is slow on first run.
**Fix:** The fixture checks if file exists and reuses it.

### "PyMuPDF not available" skip
**Cause:** PyMuPDF/fitz not installed.
**Fix:** Already in requirements.txt as `pymupdf>=1.24.0`

### Test hangs on large PDF
**Cause:** App might be genuinely processing 500 pages.
**Fix:** Test waits 65s and checks for timeout or completion.

### False positives on error detection
**Cause:** App might handle edge case better than expected.
**Fix:** Tests allow for either error OR successful extraction.

## Performance Benchmarks

| Test Category | Avg Duration | Notes |
|---------------|--------------|-------|
| Corrupted PDFs | 2-3s per test | Fast, small files |
| Invalid types | 2-3s per test | Fast, small files |
| Empty/Blank | 2-3s per test | Fast, small files |
| Tiny PDF | 2s | Instant processing |
| Large PDF (500pg) | 30-65s | Can timeout, expected |
| Multi-MPRN | 3-5s | Normal extraction |
| Recovery | 5-7s | Reloads page |
| Error quality | 2-3s per test | Fast validation |

**Total suite runtime:** ~2-3 minutes (including large PDF test)

## Integration with CI/CD

### Recommended CI configuration:
```yaml
- name: Run invalid PDF edge case tests
  run: |
    cd app
    python3 -m pytest tests/test_e2e_invalid_pdfs.py -v -m e2e --maxfail=3
  timeout-minutes: 5
```

### Skip large PDF test in CI (optional):
```bash
pytest tests/test_e2e_invalid_pdfs.py -v -m e2e -k "not large_pdf"
```

## Maintenance Notes

### Adding new edge cases:
1. Create a new fixture for the corrupted PDF type
2. Add a test in the appropriate test class
3. Update this documentation
4. Ensure test validates both error handling AND recovery

### Updating error message validation:
- Tests are designed to be flexible (look for keywords, not exact messages)
- If error message format changes, update the validation lists in tests
- Keep user-friendly message checks generic

## Related Documentation

- Main test suite: `tests/README.md`
- Bill upload tests: `tests/test_e2e_bill_upload.py`
- Welcome page tests: `tests/test_e2e_welcome.py`
- Pipeline error handling: `/Users/donalocallaghan/workspace/vibes/steve/app/orchestrator.py`
- PDF extraction: `/Users/donalocallaghan/workspace/vibes/steve/app/pipeline.py`
