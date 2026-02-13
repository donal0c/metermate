# HDF Analysis End-to-End Tests

This directory contains end-to-end (E2E) Playwright tests for the HDF (Smart Meter Data) Analysis & Visualizations feature.

## Overview

The `test_e2e_hdf_analysis.py` file contains comprehensive tests that validate:

### Test Coverage

1. **File Upload & Parsing** (`TestHDFFileUpload`)
   - Real HDF CSV file upload from project root
   - Minimal test fixture creation
   - MPRN extraction and display
   - Date range parsing and display

2. **Tab Navigation** (`TestHDFTabs`)
   - Overview tab: Summary statistics
   - Heatmap tab: Usage heatmap visualization
   - Charts tab: Analysis charts
   - Insights tab: Anomaly detection and insights
   - Export tab: Excel export functionality

3. **Heatmap & Auto-Generated Insights** (`TestHDFHeatmapAndInsights`)
   - Heatmap Plotly chart rendering
   - Auto-generated interpretation text
   - Peak usage analysis
   - Night-time usage analysis
   - Weekday vs weekend patterns

4. **Data Filtering** (`TestHDFFiltering`)
   - Date range filter availability (sidebar)
   - Load type filtering (import/export)
   - Filter UI visibility after upload

5. **Charts & Visualizations** (`TestHDFCharts`)
   - Daily profile chart rendering
   - Time-series data display
   - Monthly trends (when applicable)

6. **Anomaly Detection** (`TestHDFAnomalyDetection`)
   - Anomaly display in Insights tab
   - Anomaly recommendations
   - Severity level indicators

7. **Export Functionality** (`TestHDFExport`)
   - Excel export option visibility
   - Export button availability

8. **Summary Statistics** (`TestHDFSummaryStats`)
   - Total consumption display
   - Average daily consumption
   - Baseload/peak metrics
   - Tariff period breakdown (Night/Peak/Day)

9. **UI Components** (`TestHDFHeaderAndSidebar`)
   - MPRN display in header
   - Success message with reading count
   - Date range in success message

## Requirements

```bash
pip install playwright pytest pytest-playwright
python3 -m playwright install  # Install browser binaries
```

## Running the Tests

### Run E2E tests only (default skip)
```bash
pytest -m e2e app/tests/test_e2e_hdf_analysis.py -v
```

### Run specific test class
```bash
pytest -m e2e app/tests/test_e2e_hdf_analysis.py::TestHDFFileUpload -v
```

### Run specific test
```bash
pytest -m e2e app/tests/test_e2e_hdf_analysis.py::TestHDFTabs::test_overview_tab_displays -v
```

### Run unit tests (skip E2E)
```bash
pytest  # Default - skips E2E tests
```

### Run all tests
```bash
pytest -m "" -v
```

## Test Data

The tests use two approaches for test data:

### 1. Real HDF File (Project Root)
The test suite automatically detects HDF CSV files in the project root with names containing "HDF" (case-insensitive):
- Example: `HDF_calckWh_10306268587_03-02-2026.csv`
- Required columns: MPRN, Meter Serial Number, Read Value, Read Type, Read Date and End Time
- Data: 30-minute interval smart meter readings

### 2. Minimal Test Fixture
Built-in `create_minimal_hdf_fixture()` function generates:
- 48 readings (24 hours of 30-minute intervals)
- Mixed import/export values
- Single MPRN (10306268587)
- Valid dates (starting Jan 15, 2026)
- Realistic consumption patterns

## Test Architecture

### Fixtures

**`streamlit_app`** (module-scoped):
- Starts Streamlit app on port 8599
- Waits for app readiness (up to 30 seconds)
- Cleans up on module teardown
- Automatically re-used across all test methods

### Helpers

**`find_hdf_file()`**:
- Scans project root for HDF CSV files
- Returns first match or None

**`create_minimal_hdf_fixture()`**:
- Creates temporary HDF CSV with realistic data
- Returns file path
- Uses Python's tempfile module

**`_upload_hdf()` pattern**:
- Common method in test classes
- Navigates to app
- Uploads HDF via Streamlit file uploader
- Waits for parsing completion

## Expected Test Behavior

### Passing Tests
- File uploads successfully
- Tabs render without errors
- Summary statistics display
- Charts and heatmaps render (Plotly SVG)
- Filters become available
- Export button is visible

### What Tests Check
- Page content for expected keywords
- Plotly chart markers (SVG or plotly.json)
- UI element visibility
- Tab navigation functionality
- Data presence after upload

### Timeout Handling
- Initial page load: 15 seconds
- Streamlit parsing: 3 seconds
- Tab navigation: 2 seconds
- File upload: 3 seconds

## Common Assertions

```python
# Chart rendering
assert "plotly" in page.content().lower() or "svg" in page.content()

# Data display
assert "10306268587" in content  # MPRN
assert "readings" in content.lower()  # Reading count

# Functionality
assert "Download" in content or "Excel" in content.lower()

# Interpretation text
assert "Peak usage" in content or "peak" in content.lower()
```

## Debugging

### Run with verbose output
```bash
pytest -m e2e app/tests/test_e2e_hdf_analysis.py -vv -s
```

### Take screenshots on failure
Add to test method:
```python
page.screenshot(path="/tmp/screenshot.png")
```

### Check Streamlit logs
```bash
# Look at stderr from the Streamlit process
# Logs appear in the pytest output when tests run
```

### Slow down tests
```python
page.wait_for_timeout(5000)  # Add delay
```

## Known Limitations

1. **Minimal fixture** has only 24 hours of data
   - May not trigger all anomaly detection rules
   - Monthly seasonal analysis won't work
   - Some trend charts may be limited

2. **Chart validation** uses string matching
   - Checks for "plotly" or "svg" in HTML
   - Doesn't validate chart content accuracy

3. **Filter testing** checks for UI presence
   - Doesn't fully exercise filtering logic
   - Would need more complex test fixtures

4. **Export test** checks button visibility
   - Doesn't attempt actual file download
   - Would require additional Playwright configuration

## Extending Tests

### Add new test class
```python
class TestHDFNewFeature:
    """Test description."""

    def _setup_method(self, page: Page, streamlit_app: str):
        """Common setup."""
        hdf_path = create_minimal_hdf_fixture()
        # Upload and navigate...

    def test_new_functionality(self, page: Page, streamlit_app: str):
        """Test description."""
        # Implementation
```

### Create larger test fixtures
```python
def create_large_hdf_fixture(days=30):
    """Create HDF with multiple days of data."""
    # Implementation
```

### Add file download testing
```python
def test_export_downloads_file(self, page: Page, streamlit_app: str):
    with page.expect_download() as download_info:
        page.click("button:has-text('Download')")
    download = download_info.value
    # Verify file
```

## Files

- `test_e2e_hdf_analysis.py` - Main test file (30 tests)
- `README_E2E_TESTS.md` - This documentation

## Integration with CI/CD

To integrate with GitHub Actions or CI pipeline:

```yaml
# .github/workflows/e2e-tests.yml
name: E2E Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: 3.14
      - run: pip install -r requirements.txt
      - run: python3 -m playwright install
      - run: pytest -m e2e app/tests/test_e2e_hdf_analysis.py -v
```

## Troubleshooting

### App doesn't start
```
Streamlit app did not start within 30 seconds
```
**Solution**: Increase timeout in `streamlit_app` fixture, check port 8599 is available

### File upload fails
```
file_input.set_input_files() - Path does not exist
```
**Solution**: Ensure HDF file exists or let test create fixture

### Assertion fails on "Peak usage"
```
AssertionError: Heatmap interpretation should mention peak usage
```
**Solution**: Check that _heatmap_interpretation() is being called in main.py

### Tests skip
```
Skipped: E2E tests are skipped by default
```
**Solution**: Run with `-m e2e` flag explicitly

## Performance Notes

- Full test suite takes ~2-5 minutes (30 tests)
- Streamlit startup: ~5-10 seconds
- Each test: ~3-5 seconds
- Parallel execution supported via pytest-xdist:
  ```bash
  pytest -m e2e -n auto app/tests/test_e2e_hdf_analysis.py
  ```

## See Also

- `app/main.py` - Main Streamlit app
- `app/hdf_parser.py` - HDF parsing logic
- `conftest.py` - Pytest configuration
- `test_playwright_bill.py` - Similar bill upload tests
