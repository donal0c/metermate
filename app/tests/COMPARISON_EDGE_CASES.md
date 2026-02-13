# Multi-Bill Comparison Edge Case Test Guide

This document describes critical edge cases for the multi-bill comparison functionality and provides testing guidance.

## Overview

The `test_e2e_comparison_edge.py` file contains comprehensive automated tests for edge cases in multi-bill comparison. These tests verify that the application handles unusual, extreme, and error conditions gracefully.

## Test Categories

### 1. Provider Mismatches

**Rationale:** Users may compare bills from different electricity providers with different tariff structures, data formats, and billing conventions.

#### Test Cases:

- **Different Providers (Energia vs Go Power)**
  - File 1: `3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf` (Energia, Day/Night tariff)
  - File 2: `1845.pdf` (Go Power, 24hr tariff)
  - **Expected:** Comparison renders without errors, shows both bills, Rate Analysis handles incompatible tariffs

- **Different Tariff Structures**
  - Mixed Day/Night vs 24-hour tariffs
  - **Expected:** Rate Analysis shows N/A for incomparable rates or provides appropriate messaging

- **Different Billing Periods**
  - 30-day period vs 60-day period
  - **Expected:** Comparison works, period information displayed correctly, metrics calculated appropriately

### 2. Data Inconsistencies

**Rationale:** Bills may have varying data quality, missing fields, or inconsistent structures depending on provider and document quality.

#### Test Cases:

- **Different Data Quality (High vs Low Confidence)**
  - Native PDF (high confidence) vs Scanned PDF (lower confidence)
  - Files: Energia native PDF vs `094634_scan_14012026.pdf`
  - **Expected:** Shows confidence scores for each bill, comparison proceeds with available data

- **Zero or Very Low Consumption**
  - Bill with 0 kWh or minimal consumption
  - **Expected:** Charts render without errors, metrics display correctly, no division by zero errors

- **Missing Export Data**
  - Some bills have solar export, others don't
  - **Expected:** Consumption charts show export where available, N/A or omit where missing

- **Mixed Currency (£ vs €)**
  - **Expected:** Warning displayed if currencies don't match, comparison may be blocked or warned

### 3. Extreme Comparisons

**Rationale:** Users may compare bills with vastly different values or time periods.

#### Test Cases:

- **Vastly Different Consumption (100× difference)**
  - 100 kWh bill vs 10,000 kWh bill
  - **Expected:** Charts scale appropriately, percentage changes displayed, no UI breaking

- **Large Time Gap (5+ years)**
  - 2024 bill vs 2025 bill (or larger gap)
  - Files: `2024 Mar - Apr.pdf` vs `3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf`
  - **Expected:** Cost Trends chart handles gaps, both periods displayed, no interpolation errors

- **Same Property, Different Tariff Plans**
  - **Expected:** Rate comparison shows both plans, highlights differences

- **Residential vs Commercial (if applicable)**
  - **Expected:** Comparison works or shows appropriate warning

### 4. Upload Edge Cases

**Rationale:** Users may not follow ideal upload workflows.

#### Test Cases:

- **Only 1 Bill Uploaded**
  - **Expected:** Message prompting "Upload 2 or more bills to compare", no comparison tabs shown

- **10+ Bills (Performance Test)**
  - **Expected:** UI remains responsive, all bills displayed, charts render correctly

- **Duplicate Bills (Same Bill Twice)**
  - **Expected:** Either warns about duplicates OR processes both with identical data without crashing

- **Bills in Random Order**
  - **Expected:** Bills sorted chronologically by billing period date in trend charts

- **Partial Upload Failure**
  - One bill extracts successfully, another fails
  - **Expected:** Shows successful bills, warns about failed ones, export includes only successful

### 5. Visualization Edge Cases

**Rationale:** Charts must handle missing data, gaps, and unusual distributions.

#### Test Cases:

- **Cost Trends with Missing Months**
  - Bills from March, then August (gap in between)
  - **Expected:** Chart shows gap or interpolates appropriately, labeled clearly

- **Rate Comparison with N/A Values**
  - Different tariff structures mean not all rates comparable
  - **Expected:** Table shows N/A or "--" for incomparable rates, no errors

- **Consumption Chart with Zero Values**
  - **Expected:** Chart renders, zero values shown, axes scaled appropriately

- **Export with 0 Successful Extractions**
  - All bills failed to extract
  - **Expected:** Export button disabled or shows appropriate message

### 6. Navigation Edge Cases

**Rationale:** Users may switch modes, use browser navigation, or modify uploads mid-process.

#### Test Cases:

- **Switch from Comparison to Single Mode Mid-Render**
  - Upload bills in comparison mode, immediately switch to Single File
  - **Expected:** Mode switches without crash, state resets cleanly

- **Upload Single, Switch to Comparison, Upload Second**
  - Upload one bill in single mode → switch to comparison → upload more
  - **Expected:** State resets when switching modes, prompts for multiple uploads

- **Clear One File from Comparison**
  - Remove one of multiple uploaded files
  - **Expected:** Comparison updates to reflect remaining files

- **Browser Back Button in Comparison Mode**
  - **Expected:** Graceful handling (Streamlit apps typically don't support back button well)

## Manual Testing Guide

Since automated Playwright tests may encounter environment-specific issues, here's how to manually test edge cases:

### Setup

1. Start the app: `streamlit run app/main.py`
2. Navigate to the sidebar
3. Select "Bill Comparison" mode

### Test Procedure

For each test case above:

1. **Upload Files:** Use the multi-file uploader to select the test files mentioned
2. **Wait for Extraction:** Give the app 10-15 seconds to process multiple bills
3. **Verify Results:**
   - Check the heading shows correct bill count (e.g., "Bill Comparison — 2 bills")
   - Verify no error alerts appear
   - Navigate through all tabs: Summary, Cost Trends, Consumption, Rate Analysis, Export
   - Check that each tab renders without errors
   - Verify data is displayed appropriately given the edge case
4. **Document Results:** Note any crashes, errors, or unexpected behavior

### Critical Checks

For EVERY test case, verify:

- ✓ No unhandled exceptions / error alerts
- ✓ UI remains usable
- ✓ Data displays (even if partial or with N/A values)
- ✓ Charts render (even if with gaps or unusual scaling)
- ✓ Export functionality available (if at least one bill extracted successfully)

## Running Automated Tests

### Prerequisites

```bash
pip install playwright pytest pytest-playwright
python3 -m playwright install chromium
```

### Run All Edge Case Tests

```bash
# From the project root
cd app
python3 -m pytest tests/test_e2e_comparison_edge.py -v -m e2e
```

### Run Specific Test Class

```bash
python3 -m pytest tests/test_e2e_comparison_edge.py::TestProviderMismatches -v -m e2e
```

### Run Single Test

```bash
python3 -m pytest tests/test_e2e_comparison_edge.py::TestUploadEdgeCases::test_single_bill_upload_prompts_for_more -v -m e2e
```

### Debugging Failed Tests

If tests fail due to Streamlit rendering issues:

1. **Check Streamlit Version:** Ensure Streamlit is up to date
2. **Run in Headed Mode:** Edit test to use `headless=False` to see browser
3. **Increase Timeouts:** Some systems need longer for React rendering
4. **Check Port Conflicts:** Ensure port 8596 is available
5. **Fall Back to Manual Testing:** Use the manual guide above

## Known Issues & Limitations

### Streamlit Rendering in Headless Mode

On some systems, Streamlit's React components may not fully render in headless browser mode used by Playwright. This is an environmental issue, not a bug in the tests or app.

**Workaround:** Use manual testing guide or run tests in headed mode.

### Test Independence

Each test starts a new Streamlit instance, which can be slow. Consider running tests in parallel if needed:

```bash
python3 -m pytest tests/test_e2e_comparison_edge.py -v -m e2e -n auto
```

(Requires `pytest-xdist`)

## Adding New Edge Cases

When adding new edge case tests:

1. **Document the Rationale:** Explain why this edge case matters
2. **Specify Test Data:** List exact files or data conditions needed
3. **Define Expected Behavior:** What should happen (not crash is minimum, but specify desired behavior)
4. **Add to Manual Guide:** Include manual testing steps
5. **Write Automated Test:** Follow existing test patterns in `test_e2e_comparison_edge.py`

## Test Data Requirements

Ensure these files exist in `Steve_bills/` directory:

- `3 Energia 134 Bank Place (01.03.2025-31.03.2025).pdf` - Energia native PDF, high quality
- `1845.pdf` - Go Power bill
- `2024 Mar - Apr.pdf` - Energia bill from 2024
- `094634_scan_14012026.pdf` - Scanned bill, lower quality
- `2024 Heating Oil Invoices.pdf` - Non-electricity bill (for negative testing)

## Success Criteria

Edge case testing is successful when:

1. **All automated tests pass** (or documented environment issues explained)
2. **Manual testing confirms** graceful handling of each edge case
3. **No unhandled exceptions** for any edge case
4. **Data displays appropriately** even when incomplete or unusual
5. **User receives clear feedback** for unusual situations (warnings, N/A values, prompts)

## Related Documentation

- `test_e2e_bill_comparison.py` - Standard comparison workflow tests
- `test_e2e_bill_upload.py` - Single bill upload tests
- Main app documentation in `../README.md`
