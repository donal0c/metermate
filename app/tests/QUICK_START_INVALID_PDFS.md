# Invalid PDF Edge Case Tests - Quick Start Guide

## What This Is

Comprehensive Playwright E2E tests that verify the energy bill app **gracefully handles corrupted, malformed, and edge-case PDF files** without crashing or exposing technical errors to users.

## 30-Second Quick Start

```bash
cd /Users/donalocallaghan/workspace/vibes/steve/app
python3 -m pytest tests/test_e2e_invalid_pdfs.py -v -m e2e
```

**Expected:** 16 passed, 1 skipped in ~2-3 minutes

## What Gets Tested

### 10 Critical Edge Cases
1. **Corrupted PDF headers** - Invalid file structure
2. **Truncated PDFs** - Files cut off mid-stream
3. **Empty PDFs** - 0 pages
4. **Fake PDFs** - .txt or .jpg renamed as .pdf
5. **Blank PDFs** - Valid structure but no content
6. **Tiny PDFs** - < 1 KB files
7. **Large PDFs** - 500+ pages (performance test)
8. **Multi-account bills** - 3+ MPRNs in single PDF
9. **Binary junk** - Corrupted text streams
10. **Password-protected** - Encrypted PDFs (test exists, currently skipped)

### 5 Key Behaviors
- No crashes or stack traces shown to users
- Clear, user-friendly error messages
- App continues working after errors
- Graceful timeout handling (60s max)
- Browser/page remains responsive

## Test Structure

```
17 tests across 8 test classes
├── TestCorruptedPDFHandling (3 tests)
├── TestInvalidFileTypes (2 tests)
├── TestEmptyAndBlankPDFs (2 tests)
├── TestExtremeSizes (3 tests)
├── TestMultiAccountBills (1 test)
├── TestRecoveryAndResilience (2 tests)
├── TestErrorMessageQuality (3 tests)
└── TestPasswordProtectedPDFs (1 test - skipped)
```

## Running Tests

### All tests
```bash
pytest tests/test_e2e_invalid_pdfs.py -v -m e2e
```

### Specific test class
```bash
pytest tests/test_e2e_invalid_pdfs.py::TestCorruptedPDFHandling -v -m e2e
```

### Skip slow large PDF test (faster CI)
```bash
pytest tests/test_e2e_invalid_pdfs.py -v -m e2e -k "not large_pdf"
```

### With browser visible (debugging)
```bash
pytest tests/test_e2e_invalid_pdfs.py -v -m e2e --headed
```

## No Manual Setup Required

All test PDFs are generated programmatically:
- No external files needed
- Automatic cleanup
- Reproducible across environments
- Cached after first run (large PDF)

## Key Features

### Programmatic PDF Generation
10 fixtures create corrupted PDFs on-the-fly:
```python
@pytest.fixture(scope="module")
def corrupted_header_pdf(temp_dir):
    """Generate PDF with invalid magic number."""
    # Creates %XDF-1.4 instead of %PDF-1.4
```

### Flexible Error Validation
Tests check for error indicators, not exact messages:
```python
has_error = any(
    indicator in content.lower()
    for indicator in ["error", "invalid", "cannot", "failed"]
)
```

### Recovery Testing
Verifies app continues working after bad uploads:
```python
def test_app_recovers_after_bad_pdf():
    # Upload bad PDF -> error shown
    # Upload good PDF -> works normally
```

## Expected Behaviors

### Good Error Messages
- "Invalid PDF file"
- "Cannot extract text from this PDF"
- "Please ensure this is a valid electricity bill PDF"

### Bad Error Messages (Should NOT Appear)
- Stack traces (`Traceback`, `File "`, `line `)
- Technical exceptions (`RuntimeError`, `Exception:`)
- Package names (`pymupdf`, `pdfplumber`)

## Performance

| Test Category | Duration | Notes |
|---------------|----------|-------|
| Corrupted PDFs | 2-3s each | Fast, small files |
| Invalid types | 2-3s each | Fast validation |
| Empty/Blank | 2-3s each | Quick processing |
| Tiny PDF | 2s | Instant |
| **Large PDF** | **30-65s** | Can timeout, can skip in CI |
| Multi-MPRN | 3-5s | Normal extraction |
| Recovery | 5-7s | Page reloads |
| Error quality | 2-3s each | Fast checks |

**Total:** ~2-3 minutes (full suite)

## Troubleshooting

### "PyMuPDF not available"
Already in requirements.txt - should not happen.

### Large PDF test hangs
Expected - can take up to 65s. Or skip with:
```bash
pytest tests/test_e2e_invalid_pdfs.py -v -m e2e -k "not large_pdf"
```

### Port 8601 already in use
```bash
lsof -i :8601 | grep LISTEN | awk '{print $2}' | xargs kill -9
```

## CI/CD Integration

```yaml
- name: Invalid PDF Tests
  run: |
    cd app
    pytest tests/test_e2e_invalid_pdfs.py -v -m e2e -k "not large_pdf" --maxfail=3
  timeout-minutes: 5
```

## Documentation

- **This file** - Quick start guide
- **INVALID_PDF_TESTS.md** - Detailed reference (fixtures, expected behaviors, debugging)
- **IMPLEMENTATION_SUMMARY.md** - Implementation details and design decisions
- **README.md** - Integration with full test suite

## Verification

### Check tests are ready
```bash
pytest tests/test_e2e_invalid_pdfs.py --collect-only -m e2e
# Should show: ====== 17 tests collected ======
```

### Import test module
```bash
python3 -c "import tests.test_e2e_invalid_pdfs; print('OK')"
# Should print: Test file imports successfully
```

## What Success Looks Like

```
test_corrupted_header_shows_error PASSED
test_truncated_pdf_shows_error PASSED
test_binary_junk_pdf_handles_gracefully PASSED
test_text_file_as_pdf_shows_error PASSED
test_image_file_as_pdf_shows_error PASSED
test_empty_pdf_shows_clear_message PASSED
test_blank_pages_pdf_shows_warning PASSED
test_tiny_pdf_handles_gracefully PASSED
test_large_pdf_shows_timeout_or_completes PASSED
test_large_pdf_does_not_crash_browser PASSED
test_multi_mprn_pdf_shows_warning_or_extracts_one PASSED
test_app_recovers_after_bad_pdf PASSED
test_multiple_bad_uploads_dont_crash PASSED
test_error_messages_are_user_friendly PASSED
test_no_stack_traces_in_ui PASSED
test_clear_actionable_guidance PASSED
test_password_protected_pdf_shows_clear_error SKIPPED

====== 16 passed, 1 skipped in 120.45s ======
```

## Files Created

```
tests/test_e2e_invalid_pdfs.py          # 620 lines - main test file
tests/INVALID_PDF_TESTS.md              # Detailed reference guide
tests/IMPLEMENTATION_SUMMARY.md         # Implementation details
tests/QUICK_START_INVALID_PDFS.md       # This file
tests/README.md (updated)               # Integration with test suite
```

## Next Steps

1. **Run the tests:**
   ```bash
   pytest tests/test_e2e_invalid_pdfs.py -v -m e2e
   ```

2. **Review results** - 16 should pass, 1 should skip

3. **Add to CI/CD** - Include in automated test pipeline

4. **Extend as needed** - Add more edge cases using existing patterns

## Support

For detailed documentation, see:
- `tests/INVALID_PDF_TESTS.md` - Complete test reference
- `tests/README.md` - Full test suite documentation

For implementation details, see:
- `tests/IMPLEMENTATION_SUMMARY.md` - Design decisions and architecture
