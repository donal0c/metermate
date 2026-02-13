# HDF Cross-Reference Edge Case Testing

This document describes the edge case test suite for HDF (smart meter data) and bill verification cross-referencing.

## Overview

The test suite in `test_e2e_hdf_crossref_edge.py` validates critical failure modes where HDF and bill data don't align perfectly. Real-world scenarios are messy, and the app must handle mismatches gracefully.

## Test Categories

### 1. MPRN Mismatches

**Why it matters:** Different MPRNs mean different properties. Cross-referencing wrong data leads to incorrect verification results.

Test scenarios:
- **One digit off** (e.g., 10006002900 vs 10006002901)
  - Common typo scenario
  - Should block verification with clear error
  - Error message should show both MPRNs side-by-side

- **Missing MPRN in bill**
  - Some scanned bills don't extract MPRN successfully
  - Should block verification
  - Should suggest manual MPRN entry or bill reupload

- **Format differences** (e.g., "10006002900" vs "1000 600 2900")
  - MPRN may have spaces in bill PDF
  - Should normalize and match
  - Normalization: strip all whitespace for comparison

### 2. Date Range Issues

**Why it matters:** Consumption comparison is meaningless if date ranges don't overlap.

Test scenarios:
- **No overlap** (Bill: Jan 2025, HDF: Feb 2025)
  - Zero days in common
  - Should block verification completely
  - Error: "Bill period falls outside HDF data range"

- **Partial overlap** (Bill: 30 days, HDF: only 15 days)
  - Some coverage but incomplete
  - Should allow verification with warning
  - Warning: "Coverage: 50% - results may not be representative"

- **Bill period longer than HDF** (Bill: 60 days, HDF: 30 days)
  - Can verify for overlapping period only
  - Coverage percentage: 50%
  - Should scale consumption estimates if needed

- **HDF has gaps** (Missing days 10-15 mid-period)
  - Data export may have date gaps
  - Should still process available data
  - Coverage calculation accounts for actual days present

### 3. Consumption Discrepancies

**Why it matters:** Large variances indicate billing errors or meter issues.

Test scenarios:
- **10% variance** (Bill: 1000 kWh, HDF: 1100 kWh)
  - Common threshold for investigation
  - Should show warning (amber)
  - Warning: "Consumption variance > 5%"

- **10x error** (Bill: 500 kWh, HDF: 50 kWh or vice versa)
  - Likely decimal point error or wrong unit (kW vs kWh)
  - Should show critical alert (red)
  - Alert: "Major consumption discrepancy detected"

- **Estimated readings**
  - Bill may say "Estimated" not "Actual"
  - Should warn: "Bill uses estimated readings - cannot verify accurately"
  - HDF always has actual readings

- **Different tariff periods**
  - Bill: Day/Night split
  - HDF: 24hr or different split
  - Should attempt mapping or note incompatibility

### 4. Data Quality in HDF

**Why it matters:** Real HDF exports can be corrupted or incomplete.

Test scenarios:
- **Corrupt rows** (Missing values in some rows)
  - CSV may have blank cells
  - Should skip corrupt rows and process rest
  - Warning: "X rows skipped due to missing data"

- **Negative consumption values**
  - Data errors or export issues
  - Should flag or clip to zero
  - Warning: "Negative values detected - data quality issue"

- **Timestamp gaps** (30-min intervals with some missing)
  - Export may skip midnight or DST transitions
  - Should interpolate or mark as incomplete
  - Coverage calculation excludes gap periods

- **Duplicate timestamps**
  - DST fall-back creates duplicate 02:00-03:00 hour
  - Should deduplicate or average
  - Info: "Duplicate timestamps handled (likely DST)"

### 5. Verification Warnings

**Why it matters:** Users need clear feedback about verification quality.

Warning types:
- **Coverage percentage** (< 100%)
  - "Coverage: 85% (51/60 billing days)"
  - Shown in Match Status section
  - Green: 95-100%, Amber: 70-94%, Red: <70%

- **MPRN mismatch** (Hard error)
  - Blocks verification completely
  - Shown in red alert box
  - "Cannot verify: MPRNs don't match"

- **Consumption variance** (Warning)
  - Shown when delta > 5%
  - Amber warning with percentage
  - "Bill shows 8% more than meter data"

- **Date range non-overlap** (Hard error)
  - Blocks verification completely
  - Shows both date ranges side-by-side
  - "No overlap between bill period and HDF data"

## Synthetic Data Generation

The test suite includes a flexible HDF fixture generator:

```python
create_hdf_fixture(
    mprn="10006002900",           # Custom MPRN
    start_date=datetime(...),     # Start date
    days=30,                      # Duration
    missing_days=[10, 11, 12],    # Date gaps
    corrupt_rows=5,               # Rows with missing data
    negative_values=True,         # Include negative values
    duplicate_timestamps=True,    # Duplicate some timestamps
    gaps_in_timestamps=True       # Skip some 30-min intervals
)
```

This allows testing all edge cases without real data files.

## Edge Case Workflows

### Workflow 1: Upload HDF, then bill for different property
1. Upload HDF for MPRN A
2. Upload bill for MPRN B
3. Should show: "MPRN mismatch" error
4. Verification blocked
5. Both HDF and bill data still visible independently

### Workflow 2: Upload bill first (no HDF)
1. Upload bill PDF via verification uploader
2. No HDF data available yet
3. Should show: "No HDF data loaded - upload smart meter data first"
4. Bill extraction results still shown
5. After HDF upload, verification auto-runs

### Workflow 3: Switch HDF files with active bill
1. Upload HDF A, then bill matching HDF A
2. Verification runs successfully
3. Upload different HDF B (replaces HDF A)
4. Verification re-runs against HDF B
5. May now show MPRN mismatch or date mismatch

### Workflow 4: Remove bill and re-upload
1. Active verification shown
2. Clear bill uploader
3. Verification tab disappears
4. Re-upload same bill
5. Verification recalculates (should match previous)

## Running the Tests

### Run all edge case tests:
```bash
cd /Users/donalocallaghan/workspace/vibes/steve
python3 -m pytest app/tests/test_e2e_hdf_crossref_edge.py -v -m e2e
```

### Run specific test class:
```bash
python3 -m pytest app/tests/test_e2e_hdf_crossref_edge.py::TestMPRNMismatches -v -m e2e
```

### Run with test runner script:
```bash
python3 run_edge_tests.py
```

### Run single test:
```bash
python3 -m pytest app/tests/test_e2e_hdf_crossref_edge.py::TestDataQualityIssues::test_hdf_with_corrupt_rows -v -m e2e
```

## Test Implementation Notes

### Current Status:
- **21 test cases** defined
- Tests validate:
  - Synthetic HDF generation with various corruption modes
  - HDF parsing and error handling
  - Date range calculations
  - MPRN extraction
  - Data quality handling

### Limitations:
- Many tests are **skipped** because they require bill PDF creation
- Bill PDF generation would require PyPDF2 or ReportLab
- Full verification flow tests need both HDF and bill fixtures

### Future Enhancements:
1. Add bill PDF fixture generator
2. Test full verification workflow end-to-end
3. Add tests for export credit verification
4. Test standing charge calculations
5. Add rate comparison edge cases

## Coverage Summary

The edge case tests ensure robustness across:
- ✅ Data corruption (missing values, invalid data)
- ✅ Date misalignment (gaps, partial overlap, no overlap)
- ✅ MPRN handling (extraction, validation, normalization)
- ✅ Timestamp issues (gaps, duplicates, DST)
- ⏳ Consumption variance detection (requires bill PDF)
- ⏳ Full verification workflow (requires bill PDF)

Legend: ✅ Implemented, ⏳ Partially implemented

## Key Takeaways

1. **Graceful degradation** - App should handle bad data without crashing
2. **Clear error messages** - Users need to understand what's wrong
3. **Independent display** - Show HDF and bill data separately even if verification fails
4. **Coverage transparency** - Always show coverage percentage
5. **Mismatch warnings** - Highlight discrepancies clearly
