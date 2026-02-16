# Energy Insight

Irish electricity bill extraction and smart meter analysis tool, built as a Streamlit multipage app for professional energy audits.

## Environment Setup

**This project uses a Python virtual environment.** Always use the venv for running the app, tests, and installing packages.

```bash
# Activate (from project root)
source .venv/bin/activate

# If the venv is missing or broken, recreate it:
python3 -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt
pip install pytest pytest-playwright
python3 -m playwright install chromium
```

**Do NOT use `--break-system-packages` with Homebrew Python.** The project previously ran on bare Homebrew Python 3.14, which caused recurring `ModuleNotFoundError` (e.g. `pydantic`) whenever Homebrew upgraded the Python formula and wiped site-packages. The `.venv/` directory is gitignored.

### Environment Variables

- `GEMINI_API_KEY` - Google Gemini API key for Tier 4 LLM vision extraction (optional; degrades gracefully if missing)
- `GOOGLE_GENAI_USE_VERTEXAI=false` - Use Gemini API directly (not Vertex AI)

## Running the App

```bash
cd app
streamlit run main.py
```

Or use the helper script: `app/run.sh`

## App Structure

```
app/
  main.py                    # Home page (entry point)
  pages/
    1_Bill_Extractor.py      # Bill upload, extraction, comparison
    2_Meter_Analysis.py      # HDF/Excel smart meter analysis
  common/
    theme.py                 # Dark theme CSS, color palette
    components.py            # Reusable UI components (field_html, anomaly cards)
    formatters.py            # Currency, kWh, date formatting
    session.py               # Session state helpers, content hashing
  orchestrator.py            # Extraction pipeline orchestration
  pipeline.py                # Tiers 0-3 extraction logic
  spatial_extraction.py      # OCR spatial extraction (Tier 2)
  llm_extraction.py          # Gemini vision extraction (Tier 4)
  provider_configs.py        # Per-supplier regex configs
  bill_parser.py             # BillData / GenericBillData models
  hdf_parser.py              # ESB Networks HDF CSV parser
  parse_result.py            # ParseResult data model
```

## Extraction Pipeline

Bills are extracted through a tiered pipeline with graceful degradation:

- **Tier 0**: Native text extraction via PyMuPDF. Classifies PDF as native vs scanned.
- **Tier 1**: Provider detection via keyword matching (16 Irish suppliers).
- **Tier 2**: Universal regex patterns (unknown providers) OR spatial OCR via pytesseract for scanned bills.
- **Tier 3**: Provider-specific regex configs (Energia, Go Power, ESB Networks, Kerry Petroleum, Electric Ireland, SSE Airtricity).
- **Tier 4**: Gemini 2.0 Flash vision fallback when regex confidence is low. Requires `GEMINI_API_KEY`.

Confidence scoring cross-validates extracted fields and flags missing critical data.

### Key Data Models

- `GenericBillData` (bill_parser.py) - Provider-agnostic bill with variable-length line items
- `BillData` (bill_parser.py) - Legacy flat model for UI display. Converted via `generic_to_legacy()`
- `PipelineResult` (orchestrator.py) - Full extraction result with all tier outputs

## Bill Extractor Page Design

The Bill Extractor (`pages/1_Bill_Extractor.py`) uses a unified workflow:

- Multi-file uploader in the main content area (no mode switching)
- Files accumulate in `st.session_state["extracted_bills"]` across uploads
- Content hash deduplication prevents re-extracting the same file
- Per-file status chips show supplier name and confidence (green/amber/red)
- 1 bill: shows detailed summary view
- 2+ bills: shows comparison tabs (Summary, Cost Trends, Consumption, Rate Analysis, Export) with expandable individual bill details below
- "Clear All Bills" sidebar button to reset

## Testing

```bash
cd app

# Unit tests only (default - skips e2e)
python3 -m pytest

# E2E Playwright tests only (starts Streamlit server automatically)
python3 -m pytest -m e2e -v

# All tests
python3 -m pytest -m "" -v

# Specific test file
python3 -m pytest test_bill_extractor_unified.py -v
```

### Test Organisation

**Unit tests** (no marker, run by default):
- `test_bill_extractor_unified.py` - Bill accumulation, deduplication, field counting
- `test_bill_data_model.py` - Data model serialization
- `test_pipeline.py` - Tier 0/1 extraction
- `test_tier2.py` / `test_tier3.py` - Regex extraction
- `test_confidence.py` - Confidence scoring
- `test_spatial_extraction.py` - OCR spatial extraction
- `test_orchestrator.py` - Pipeline orchestration
- `test_llm_extraction.py` - LLM extraction (needs GEMINI_API_KEY)
- `test_bill_verification.py` - Cross-field validation

**E2E Playwright tests** (`@pytest.mark.e2e`, skipped by default):
- `test_playwright_unified.py` - Unified bill extractor workflow
- `test_playwright_bill.py` - Single bill upload and display
- `test_playwright_comparison.py` - Multi-bill comparison
- `test_playwright_image_upload.py` - Image bill upload
- `test_playwright_llm.py` - LLM fallback UI
- `test_e2e_bill_comparison.py` - Comparison flow
- `test_e2e_confidence_warnings.py` - Warning display
- `test_e2e_scanned_bills.py` - Scanned bill handling

Each Playwright test file starts its own Streamlit server on a unique port (8596-8599).

## Deployment

Configured for Streamlit Community Cloud:
- `.streamlit/config.toml` - Dark theme, 200MB max upload
- `packages.txt` - System deps: `tesseract-ocr`, `poppler-utils`
- `runtime.txt` - `python-3.12`
- `app/requirements.txt` - Python deps

## Sample Data

`sample_bills/` contains sample PDFs and images for testing (gitignored). Tests that require these files skip gracefully if not present.
