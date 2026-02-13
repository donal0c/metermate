# Performance & Stress Testing Guide

## Overview

Comprehensive end-to-end performance tests for the Energy Insight application, validating behavior under stress, timeout scenarios, resource limits, and edge cases.

## Test Coverage

### 1. Large File Handling

**Test Class:** `TestLargeFileHandling`

Tests application behavior with large data files:

- **30-day HDF file** (~1400 readings, ~2800 rows)
  - Validates processing completes within 60 seconds
  - Checks for graceful timeout if exceeded
  - Monitors memory stability during processing

- **Large PDF bills** (100+ pages)
  - Extraction timeout handling
  - Clear error messages for timeouts
  - No memory leaks

**Critical Metrics:**
- Extraction time < 60s or graceful timeout
- Memory usage stable (no leaks)
- Clear error messaging

### 2. Concurrent Operations

**Test Class:** `TestConcurrentOperations`

Tests race conditions and concurrent user actions:

- **Rapid file uploads**: Upload 3 files in quick succession
  - Verifies queue handling (no crashes)
  - State management between uploads

- **Same file uploaded twice**: Re-upload handling
  - Cache invalidation
  - No duplicate processing errors

- **Rapid tab switching during rendering**
  - Navigate between Overview/Heatmap/Charts/Insights/Export
  - 3 complete cycles while data processing
  - No UI crashes or frozen states

**Critical Metrics:**
- App remains stable (no crashes)
- State transitions handled cleanly
- No race condition errors

### 3. Rapid User Actions

**Test Class:** `TestRapidUserActions`

Simulates aggressive user interactions:

- **Upload button spam**: Click upload area 10 times rapidly
  - Verifies UI doesn't break
  - No duplicate upload triggers

- **Rapid expander toggling**: Collapse/expand sections quickly
  - 5 cycles through multiple expanders
  - No rendering glitches

**Critical Metrics:**
- UI remains responsive
- No JavaScript errors
- Graceful handling of rapid clicks

### 4. Cache & State Management

**Test Class:** `TestCacheAndState`

Validates proper state management:

- **File A → File B upload sequence**
  - File A data cleared from view
  - File B data displayed correctly
  - No data mixing

- **Page reload during processing**
  - State clears on reload
  - Fresh session established
  - No stale data persists

- **Sequential uploads (memory leak detection)**
  - Upload 5 files sequentially
  - Memory usage should remain stable
  - No cumulative performance degradation

**Critical Metrics:**
- State transitions clean
- No memory leaks over time
- Cache properly invalidated

### 5. Timeout Scenarios

**Test Class:** `TestTimeoutScenarios`

Tests timeout handling and error messaging:

- **Slow network simulation** (500ms delay)
  - Progress indicators shown
  - Eventually loads successfully

- **Very large file timeout** (90-day HDF)
  - Clear timeout error message
  - Option to retry or cancel
  - App remains functional after timeout

**Critical Metrics:**
- Timeouts handled gracefully
- Clear error messages displayed
- App doesn't crash on timeout

### 6. Browser Compatibility

**Test Class:** `TestBrowserCompatibility`

Tests responsive design across viewports:

- **Mobile viewport** (375x667 - iPhone SE)
  - UI renders correctly
  - File upload functional
  - All features accessible

- **Tablet viewport** (768x1024 - iPad)
  - Optimal layout for medium screens
  - Charts render properly

- **Desktop viewport** (1920x1080 - Full HD)
  - Full feature set visible
  - Charts use available space

**Critical Metrics:**
- Responsive at all breakpoints
- No layout overflow/breaking
- Touch-friendly on mobile

### 7. Graceful Degradation

**Test Class:** `TestGracefulDegradation`

Tests behavior under adverse conditions:

- **Slow 3G network** (750ms delay)
  - App loads (slowly but surely)
  - Progress indicators shown
  - No timeout crashes

- **Missing API key**
  - Clear error message
  - App still functional for non-LLM features
  - Guidance on setting up API key

**Critical Metrics:**
- Works on slow connections
- Clear error messaging
- Partial functionality maintained

### 8. Session State Management

**Test Class:** `TestSessionStateManagement`

Validates Streamlit session handling:

- **Session persistence during interaction**
  - Data retained across tab switches
  - State maintained during UI updates

- **Multiple browser tabs** (limited test)
  - Independent sessions
  - No cross-contamination

**Critical Metrics:**
- Session state stable
- No unexpected state resets
- Data persistence across interactions

### 9. Error Recovery

**Test Class:** `TestErrorRecovery`

Tests resilience and recovery:

- **Invalid file → valid file**
  - Error shown for invalid file
  - App recovers when valid file uploaded
  - No lingering error states

- **Network interruption during upload**
  - Graceful handling of connection loss
  - Clear error message
  - App remains functional

**Critical Metrics:**
- Recovers from errors
- Clear error messages
- No permanent breakage

## Running the Tests

### Run all performance tests:
```bash
cd /Users/donalocallaghan/workspace/vibes/steve
python3 -m pytest -m performance app/tests/test_e2e_performance.py -v
```

### Run specific test class:
```bash
# Test large file handling only
python3 -m pytest app/tests/test_e2e_performance.py::TestLargeFileHandling -v

# Test concurrent operations only
python3 -m pytest app/tests/test_e2e_performance.py::TestConcurrentOperations -v
```

### Run with detailed output:
```bash
python3 -m pytest -m performance app/tests/test_e2e_performance.py -v -s
```

### Run with coverage:
```bash
python3 -m pytest -m performance app/tests/test_e2e_performance.py --cov=app --cov-report=html
```

### Skip slow tests (during development):
```bash
python3 -m pytest -m "performance and not slow" app/tests/test_e2e_performance.py -v
```

## Prerequisites

1. **Install Playwright browsers:**
   ```bash
   python3 -m playwright install
   ```

2. **Install dependencies:**
   ```bash
   cd /Users/donalocallaghan/workspace/vibes/steve/app
   pip install -r requirements.txt
   ```

3. **Test data:**
   - Large HDF files are generated automatically by test fixtures
   - PDF bills should be in `/Users/donalocallaghan/workspace/vibes/steve/Steve_bills/`
   - Tests will skip if required files not found

## Performance Benchmarks

### Expected Performance Metrics

| Scenario | Expected Time | Max Acceptable | Action on Timeout |
|----------|--------------|----------------|-------------------|
| 1-day HDF upload | < 5s | 10s | Show error |
| 30-day HDF upload | < 30s | 60s | Show timeout warning |
| 90-day HDF upload | < 60s | 120s | Graceful timeout |
| PDF bill extraction | < 10s | 45s | Show progress |
| Large PDF (100+ pages) | < 30s | 60s | Timeout error |

### Memory Limits

- **Single file processing:** < 500 MB
- **Peak usage (large file):** < 2 GB
- **Sequential 5 uploads:** Memory should not grow > 10% between uploads

### Network Performance

- **Fast connection (10+ Mbps):** All features work normally
- **Slow connection (3G ~750 Kbps):** Progress indicators shown, app eventually loads
- **Very slow (2G):** May timeout, but should show clear error message

## Test Fixtures

### `streamlit_app` (module-scoped)
- Starts Streamlit app on port 8600
- Waits for app to be ready (max 30s)
- Automatically terminates after all tests
- Yields: `http://localhost:8600`

### `create_large_hdf_file(num_days)`
- Generates temporary HDF CSV file
- Default: 30 days of 30-minute readings
- Includes import and export data
- Auto-cleanup after test

### `create_multi_page_pdf(num_pages)`
- Placeholder for large PDF generation
- Currently returns first available PDF from `Steve_bills/`
- Future: Generate synthetic multi-page PDFs

## Debugging Failed Tests

### Test hangs indefinitely
- Check Streamlit app started correctly (port 8600)
- Verify no firewall blocking localhost:8600
- Check app logs: `app/tests/test_e2e_performance.py` starts app with stdout/stderr capture

### Timeouts too aggressive
- Adjust `page.set_default_timeout()` in test
- Some tests use 60s timeout for large files
- Default Playwright timeout: 30s

### Memory tests failing
- Monitor system memory during test: `top` or Activity Monitor
- Check for memory leaks in app code
- Verify temp files cleaned up properly

### Network simulation not working
- Ensure `page.route()` callback is correct
- Check for conflicting routes
- Verify `page.unroute()` called in finally block

## Continuous Integration

### CI/CD Recommendations

1. **Run on merge to main:**
   - Full performance test suite
   - Generate performance report

2. **Nightly builds:**
   - Extended stress tests (longer timeouts)
   - Memory leak detection over 100+ uploads

3. **Performance regression detection:**
   - Track extraction times over time
   - Alert if processing time increases > 20%
   - Monitor memory usage trends

### GitHub Actions Example

```yaml
name: Performance Tests

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  performance-test:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        cd app
        pip install -r requirements.txt
        python3 -m playwright install --with-deps chromium

    - name: Run performance tests
      run: |
        cd /Users/donalocallaghan/workspace/vibes/steve
        python3 -m pytest -m performance app/tests/test_e2e_performance.py -v --junit-xml=test-results.xml

    - name: Upload test results
      uses: actions/upload-artifact@v3
      if: always()
      with:
        name: performance-test-results
        path: test-results.xml
```

## Known Limitations

1. **Multi-page PDF generation:**
   - Currently uses existing PDFs from `Steve_bills/`
   - Future: Generate synthetic PDFs with reportlab

2. **Memory profiling:**
   - Tests check app stability but don't measure exact memory usage
   - Future: Integrate memory_profiler or tracemalloc

3. **Network simulation:**
   - Basic delay simulation only
   - Doesn't simulate packet loss or bandwidth limits
   - Future: Use Playwright's CDP for advanced network conditions

4. **LLM API timeout:**
   - Difficult to test real API timeouts without mocking
   - Current tests focus on app-level timeout handling

## Future Enhancements

- [ ] Add memory profiling with psutil
- [ ] Generate synthetic large PDFs for testing
- [ ] Test LLM API timeout scenarios with mock server
- [ ] Add performance regression tracking
- [ ] Test OCR timeout scenarios (45s+ per page)
- [ ] Browser-specific tests (Chrome, Firefox, Safari)
- [ ] Accessibility testing (screen readers, keyboard nav)
- [ ] Load testing with multiple concurrent users

## Troubleshooting

### Port 8600 already in use
```bash
# Find process using port 8600
lsof -i :8600

# Kill process
kill -9 <PID>
```

### Playwright browser not installed
```bash
python3 -m playwright install chromium
```

### Test data not found
```bash
# Verify test data locations
ls -la /Users/donalocallaghan/workspace/vibes/steve/Steve_bills/
ls -la /Users/donalocallaghan/workspace/vibes/steve/*.csv
```

### Streamlit app fails to start
```bash
# Test app manually
cd /Users/donalocallaghan/workspace/vibes/steve/app
streamlit run main.py --server.port 8600
```

## Contributing

When adding new performance tests:

1. **Use descriptive test names** that explain what's being tested
2. **Add docstrings** explaining expected behavior
3. **Clean up resources** in finally blocks (temp files, routes)
4. **Set appropriate timeouts** for slow operations
5. **Document expected metrics** in test docstring
6. **Add test to relevant class** or create new class if needed

## Contact

For questions or issues with performance tests, refer to:
- Main test documentation: `app/tests/README.md`
- E2E test guide: `app/tests/README_E2E_TESTS.md`
- Project README: `/Users/donalocallaghan/workspace/vibes/steve/README.md`
