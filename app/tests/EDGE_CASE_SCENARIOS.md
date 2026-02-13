# HDF Cross-Reference Edge Case Scenarios

Quick reference for specific test scenarios and expected behavior.

## Scenario Matrix

| Scenario | HDF Data | Bill Data | Expected Result | Warning/Error |
|----------|----------|-----------|-----------------|---------------|
| **Perfect Match** | MPRN A, Jan 1-31 | MPRN A, Jan 1-31 | ✅ Verification succeeds | None |
| **MPRN Off by 1** | MPRN 10006002900 | MPRN 10006002901 | ❌ Blocked | "MPRN mismatch" |
| **No MPRN in Bill** | MPRN A | No MPRN extracted | ❌ Blocked | "Bill has no MPRN" |
| **No Date Overlap** | Feb 1-28 | Jan 1-31 | ❌ Blocked | "No overlap" |
| **50% Coverage** | Jan 1-15 | Jan 1-31 | ⚠️ Allowed | "Coverage: 50%" |
| **80% Coverage** | Jan 1-24 | Jan 1-31 | ⚠️ Allowed | "Coverage: 80%" |
| **HDF Missing Days** | Jan 1-31 (gaps 10-15) | Jan 1-31 | ⚠️ Allowed | "Data gaps detected" |
| **10% Variance** | 1100 kWh | 1000 kWh | ⚠️ Warning | "Variance: +10%" |
| **50% Variance** | 1500 kWh | 1000 kWh | 🔴 Alert | "Major discrepancy" |
| **Corrupt HDF Rows** | 5% rows missing values | Valid bill | ⚠️ Warning | "X rows skipped" |
| **Negative Values** | Some negative kWh | Valid bill | ⚠️ Warning | "Data quality issue" |
| **Duplicate Timestamps** | DST duplicates | Valid bill | ℹ️ Info | "DST handled" |

Legend:
- ✅ Success
- ⚠️ Warning (allowed to proceed)
- 🔴 Alert (allowed but highlighted)
- ❌ Blocked (cannot verify)
- ℹ️ Info (noted but not concerning)

## Detailed Scenarios

### Scenario 1: MPRN Mismatch (One Digit Off)

**Setup:**
- HDF MPRN: `10006002900`
- Bill MPRN: `10006002901`

**Expected Behavior:**
1. HDF uploads successfully
2. Bill uploads successfully
3. Bill Verification tab appears
4. Red error box shown:
   ```
   ❌ Cannot Verify
   Bill MPRN (10006002901) does not match meter data MPRN (10006002900).
   Cannot compare data from different meters.
   ```
5. No consumption comparison shown
6. HDF analysis tabs still available
7. Bill extraction results still shown

**User Actions:**
- Check if bill is for correct property
- Verify MPRN on bill PDF
- If MPRN extracted incorrectly, manually correct
- If different property, upload correct bill

---

### Scenario 2: Partial Date Overlap (50% Coverage)

**Setup:**
- HDF data: Jan 1-15, 2025 (15 days)
- Bill period: Jan 1-31, 2025 (31 days)

**Expected Behavior:**
1. Both files upload successfully
2. Verification proceeds with warning
3. Match Status shows:
   ```
   Data Coverage: 48% (15/31 billing days)
   Billing Days: 31
   HDF Coverage: Jan 1 - Jan 15
   ```
4. Yellow warning box:
   ```
   ⚠️ Partial Coverage
   Only 15 of 31 billing days covered by meter data (48%).
   Results may not be representative.
   ```
5. Consumption comparison shown for overlapping period
6. Delta calculated as: (Bill value / 31 * 15) vs HDF total

**User Actions:**
- Download more HDF data to cover full billing period
- Acknowledge that verification is partial
- Use pro-rata calculations manually if needed

---

### Scenario 3: No Date Overlap

**Setup:**
- HDF data: Feb 1-28, 2025
- Bill period: Jan 1-31, 2025

**Expected Behavior:**
1. Both files upload successfully
2. Verification blocked
3. Red error box:
   ```
   ❌ Cannot Verify
   Bill period (Jan 1 - Jan 31, 2025) falls outside HDF data range (Feb 1 - Feb 28, 2025).
   No overlapping days to compare.
   ```
4. No consumption comparison shown
5. Suggestion:
   ```
   Download HDF data for the billing period from ESB Networks website.
   ```

**User Actions:**
- Download HDF data for correct date range
- Check bill dates are correct
- Verify HDF export didn't fail

---

### Scenario 4: Consumption Variance (10%)

**Setup:**
- HDF total: 1100 kWh
- Bill total: 1000 kWh
- Coverage: 100%

**Expected Behavior:**
1. Verification succeeds
2. Yellow warning shown:
   ```
   ⚠️ Consumption Variance
   Meter data shows 10% more consumption than bill.
   Delta: +100 kWh
   ```
3. Consumption comparison table:
   ```
   Period    | Meter (kWh) | Bill (kWh) | Delta (kWh) | Delta (%)
   --------- | ----------- | ---------- | ----------- | ---------
   Day       | 650         | 600        | +50         | +8.3%
   Night     | 350         | 320        | +30         | +9.4%
   Peak      | 100         | 80         | +20         | +25%
   Total     | 1100        | 1000       | +100        | +10%
   ```
4. Possible causes listed:
   - Bill uses estimated readings
   - Meter readings rounded differently
   - Partial billing period adjustment

**User Actions:**
- Check if bill says "Estimated" or "Actual"
- Verify date ranges are exact match
- Contact supplier if variance unexplained

---

### Scenario 5: Corrupt HDF Data

**Setup:**
- HDF file has 10 rows with missing Read Value
- 1000 total rows
- Coverage: 100% date range

**Expected Behavior:**
1. HDF parsing shows warning:
   ```
   ⚠️ Data Quality Warning
   10 rows skipped due to missing values (1% of file)
   ```
2. Analysis continues with valid rows
3. Consumption totals calculated from 990 valid rows
4. Warning persists in verification:
   ```
   Note: HDF data had quality issues - 1% of readings skipped.
   ```

**User Actions:**
- Re-export HDF from ESB Networks
- Check file wasn't corrupted during download
- Verify readings are reasonable

---

### Scenario 6: HDF with Date Gaps

**Setup:**
- HDF data: Jan 1-31
- Missing: Jan 10-15 (6 days gap)
- Bill: Jan 1-31

**Expected Behavior:**
1. HDF uploads successfully
2. Info message:
   ```
   ℹ️ Date Gaps Detected
   HDF data has gaps: 6 days missing in billing period.
   ```
3. Coverage calculation:
   ```
   Data Coverage: 81% (25/31 billing days)
   ```
4. Consumption comparison notes gap:
   ```
   Note: 6 days missing from meter data.
   Comparison is for available days only.
   ```
5. Pro-rata adjustment suggested

**User Actions:**
- Check why export has gaps
- Re-export from ESB Networks
- Verify meter was operational during gap period

---

### Scenario 7: Negative Consumption Values

**Setup:**
- HDF has some negative import values (data error)
- Dates: Jan 1-31
- Bill: Jan 1-31

**Expected Behavior:**
1. HDF parsing shows warning:
   ```
   ⚠️ Data Quality Issue
   Negative consumption values detected (5 intervals).
   This indicates a data quality problem.
   ```
2. Options:
   - Clip negative values to zero
   - Skip negative intervals
   - Show as-is with warning
3. Verification proceeds with note:
   ```
   HDF data quality issues detected - results may be inaccurate.
   ```

**User Actions:**
- Re-export HDF data
- Check for meter faults
- Contact ESB Networks if issue persists

---

### Scenario 8: Multiple HDF Files for Same Bill

**Setup:**
1. Upload HDF A (Jan 1-15)
2. Upload Bill (Jan 1-31)
3. Verification shows 48% coverage
4. Upload HDF B (Jan 1-31) - replaces HDF A

**Expected Behavior:**
1. First HDF loads
2. Bill verification shows partial coverage
3. Second HDF upload replaces first
4. Verification re-runs automatically
5. Coverage updates to 100%
6. Consumption comparison refreshes

**User Actions:**
- Can try different HDF exports
- System always uses most recent HDF upload
- Clear and re-upload to reset

---

## Error Message Reference

### Hard Errors (Block Verification)

**MPRN Mismatch:**
```
❌ Cannot Verify
Bill MPRN (X) does not match meter data MPRN (Y).
Cannot compare data from different meters.
```

**Missing MPRN:**
```
❌ Cannot Verify
Bill has no MPRN — cannot verify against meter data.
Ensure bill is for correct property.
```

**No Date Overlap:**
```
❌ Cannot Verify
Bill period (DATE1 - DATE2) falls outside HDF data range (DATE3 - DATE4).
Download HDF data for the billing period.
```

### Warnings (Allow Verification)

**Partial Coverage:**
```
⚠️ Partial Coverage
Only X of Y billing days covered by meter data (Z%).
Results may not be representative.
```

**Consumption Variance:**
```
⚠️ Consumption Variance
Meter data shows X% more/less consumption than bill.
Delta: ±Y kWh
```

**Data Quality:**
```
⚠️ Data Quality Warning
N rows skipped due to missing/invalid values (X% of file).
```

### Info Messages

**DST Handling:**
```
ℹ️ DST Transitions Handled
Duplicate/missing timestamps adjusted for daylight saving time.
```

**Date Gaps:**
```
ℹ️ Date Gaps Detected
HDF data has gaps: N days missing in billing period.
```

## Testing Checklist

Use this checklist when validating the verification feature:

- [ ] Perfect match scenario works (100% coverage, matching MPRN)
- [ ] MPRN mismatch blocks verification
- [ ] Missing MPRN blocks verification
- [ ] No date overlap blocks verification
- [ ] Partial overlap (50%) shows warning but proceeds
- [ ] Coverage percentage calculated correctly
- [ ] Consumption delta calculated correctly
- [ ] Variance warnings shown at 5%, 10%, 25% thresholds
- [ ] Corrupt HDF rows handled gracefully
- [ ] Negative values flagged
- [ ] Date gaps detected and noted
- [ ] Duplicate timestamps deduplicated
- [ ] Both HDF and bill data visible independently even with errors
- [ ] Switching HDF files updates verification
- [ ] Clear error messages guide user actions
