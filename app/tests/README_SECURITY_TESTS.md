# Security E2E Tests

## Overview

This test suite (`test_e2e_security.py`) contains comprehensive security tests for the electricity bill analyzer application. These are **defensive security tests** designed to verify the application properly handles malicious inputs and prevents common vulnerabilities.

## Test Categories

### 1. File Upload Security (`TestFileUploadSecurity`)
Tests for file upload vulnerabilities:
- ✅ Executable files renamed as PDFs
- ✅ Path traversal attempts in filenames/content
- ✅ Extremely long filenames (200+ chars)
- ✅ Special characters and XSS in filenames
- ✅ Null byte injection attempts

**What we test:**
- File type validation
- Filename sanitization
- No system path exposure

### 2. Data Injection Attacks (`TestDataInjectionAttacks`)
Tests for injection vulnerabilities in extracted bill data:
- ✅ SQL injection in MPRN field (`'; DROP TABLE bills; --`)
- ✅ XSS in account number (`<script>alert(document.cookie)</script>`)
- ✅ Path traversal in invoice number (`../../../etc/passwd`)
- ✅ Integer overflow in amounts (100+ digit numbers)
- ✅ HTML injection in provider name (`<img src=x onerror=alert(1)>`)
- ✅ Command injection in date fields (`2025-01-01; rm -rf /`)

**What we test:**
- HTML escaping in UI output
- No JavaScript execution from data
- Safe handling of special characters

### 3. PDF Content Attacks (`TestPDFContentAttacks`)
Tests for malicious PDF content:
- ✅ PDFs with embedded JavaScript
- ✅ Large PDFs (50+ pages)
- ✅ Corrupted PDF files
- ✅ Empty PDFs

**What we test:**
- PDF JavaScript doesn't execute
- Large file handling without hanging
- Graceful error handling for corrupted files

### 4. Output Sanitization (`TestOutputSanitization`)
Tests that all output is properly sanitized:
- ✅ HTML tags are escaped in extracted text
- ✅ Script tags are escaped in raw text view
- ✅ No XSS execution in any output

**What we test:**
- All HTML content is entity-encoded
- No unescaped script tags in output
- Safe rendering of user-controlled data

### 5. Session & Cache Security (`TestSessionAndCacheSecurity`)
Tests for sensitive data exposure:
- ✅ No sensitive data in browser localStorage
- ✅ No stack traces exposed in errors
- ✅ No system paths in error messages

**What we test:**
- MPRN/account numbers not in plain text storage
- Error messages don't leak internal details
- No file system paths exposed

### 6. Resource Exhaustion (`TestResourceExhaustion`)
Tests for DoS attack vectors:
- ✅ Very large PDFs (100+ pages)
- ✅ Rapid sequential uploads

**What we test:**
- File size handling or rejection
- No application hangs
- Graceful degradation

### 7. CSRF & Session Security (`TestCSRFAndSessionSecurity`)
Tests for session handling:
- ✅ Session isolation between browser tabs
- ✅ No data leakage between sessions

**What we test:**
- Proper session separation
- No cross-session data exposure

### 8. Input Validation (`TestInputValidation`)
Tests for input type checking:
- ✅ Text files with .pdf extension rejected
- ✅ Unicode characters handled properly

**What we test:**
- File type detection beyond extension
- UTF-8/Unicode support

### 9. Error Handling (`TestErrorHandling`)
Tests for graceful error handling:
- ✅ User-friendly errors for corrupted PDFs
- ✅ Recovery after upload errors

**What we test:**
- No technical jargon in errors
- Application recovers from errors
- No permanent state corruption

## Running the Tests

### Prerequisites

```bash
# Activate virtual environment
cd app
source venv/bin/activate

# Install Playwright browsers (first time only)
python3 -m playwright install
```

### Run All Security Tests

```bash
# Run all security tests
python3 -m pytest tests/test_e2e_security.py -m e2e -v

# Run with detailed output
python3 -m pytest tests/test_e2e_security.py -m e2e -v -s

# Run specific test class
python3 -m pytest tests/test_e2e_security.py::TestFileUploadSecurity -m e2e -v

# Run specific test
python3 -m pytest tests/test_e2e_security.py::TestDataInjectionAttacks::test_xss_in_account_number -m e2e -v
```

### Run in Headful Mode (See Browser)

```bash
# See what's happening in the browser
python3 -m pytest tests/test_e2e_security.py -m e2e -v --headed --slowmo 1000
```

### Generate HTML Report

```bash
# Install pytest-html
pip install pytest-html

# Generate report
python3 -m pytest tests/test_e2e_security.py -m e2e --html=security_report.html --self-contained-html
```

## Understanding Test Results

### ✅ PASS - What It Means
When a security test **passes**, it means the application:
- **Properly rejects** malicious input, OR
- **Safely handles** malicious input without executing it, OR
- **Escapes/sanitizes** dangerous content in output

### ❌ FAIL - What It Means
When a security test **fails**, it indicates a potential vulnerability:
- Malicious content is executing (XSS)
- Sensitive data is being exposed
- Input validation is insufficient
- Error messages leak internal details

## Expected Security Behaviors

### File Upload
- ✅ Should validate file type by content, not just extension
- ✅ Should reject non-PDF files
- ✅ Should handle corrupted files gracefully
- ✅ Should sanitize filenames

### Data Extraction
- ✅ All extracted data should be HTML-escaped when displayed
- ✅ No JavaScript execution from bill content
- ✅ No SQL injection possible (app doesn't use SQL, but still tested)

### Error Handling
- ✅ Errors should be user-friendly
- ✅ No stack traces exposed to users
- ✅ No file system paths in error messages
- ✅ Application should recover from errors

### Session Security
- ✅ No sensitive data in localStorage
- ✅ Sessions isolated between tabs
- ✅ No data persistence across sessions (unless intended)

## Common Issues and Solutions

### Test Timeout
If tests hang:
```bash
# Increase timeout (default 30s)
python3 -m pytest tests/test_e2e_security.py -m e2e --timeout=120
```

### Streamlit Port Conflict
If port 8601 is in use:
1. Edit `STREAMLIT_PORT` in `test_e2e_security.py`
2. Or kill existing Streamlit processes:
```bash
pkill -f streamlit
```

### Browser Not Installed
```bash
# Install Playwright browsers
python3 -m playwright install chromium
```

## Security Test Philosophy

These tests follow security testing best practices:

1. **Defensive Testing**: We create malicious inputs programmatically in the test suite
2. **No Actual Attacks**: Tests verify the app defends against attacks, not that attacks work
3. **Comprehensive Coverage**: Test all input vectors (files, data, UI)
4. **Output Validation**: Verify all output is sanitized
5. **Error Handling**: Ensure errors don't leak sensitive info

## Interpreting Results for Security Audit

### For Developers
- All tests should PASS in production
- FAILs indicate security vulnerabilities that must be fixed
- Review failed tests immediately

### For Security Auditors
- This suite tests common web vulnerabilities (OWASP Top 10)
- Covers: XSS, injection, file upload, information disclosure
- Tests both input validation and output encoding
- Verifies error handling doesn't leak sensitive data

## Adding New Security Tests

To add a new security test:

1. **Identify the attack vector**: What malicious input could an attacker provide?
2. **Create test data**: Generate malicious PDF or content
3. **Verify safe handling**: Assert the app doesn't execute/expose the malicious content
4. **Add to appropriate test class**: File upload, data injection, etc.

Example template:
```python
def test_new_security_check(self, page: Page, streamlit_app: str, temp_dir: str):
    """Should safely handle [attack vector]."""
    # Create malicious input
    malicious_pdf = create_malicious_pdf("malicious content", "test.pdf", temp_dir)

    # Upload to app
    page.goto(streamlit_app)
    page.wait_for_load_state("networkidle")
    file_input = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    file_input.set_input_files(malicious_pdf)
    page.wait_for_timeout(2000)

    # Verify safe handling
    content = page.content()
    assert "expected_safe_behavior" in content, "Should handle safely"
```

## CI/CD Integration

To run in CI/CD pipeline:

```bash
# GitHub Actions example
- name: Run Security Tests
  run: |
    source venv/bin/activate
    python3 -m playwright install --with-deps chromium
    python3 -m pytest tests/test_e2e_security.py -m e2e -v --junit-xml=security-results.xml
```

## Related Documentation

- [E2E Tests Index](../../E2E_TESTS_INDEX.md)
- [Test Suite Summary](../../TEST_SUITE_SUMMARY.md)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)

## Questions?

If you have questions about these security tests or find a potential vulnerability not covered:
1. Review existing test classes for similar patterns
2. Check Streamlit security documentation
3. Consult OWASP guidelines for web application security
