import builtins
import sys
import types

import pandas as pd

from bill_verification import parse_bill_date as parse_verification_date
from common.formatters import parse_bill_date as parse_formatter_date
from llm_extraction import Tier4ExtractionResult, extract_tier4_llm
from orchestrator import _build_bill, extract_bill_from_image
from pipeline import (
    ConfidenceResult,
    FieldExtractionResult,
    Tier2ExtractionResult,
    Tier3ExtractionResult,
    ValidationCheck,
    detect_provider,
)


def _accept_confidence() -> ConfidenceResult:
    return ConfidenceResult(
        score=0.9,
        band="accept",
        fields_found=5,
        expected_fields=5,
        validation_checks=[],
        validation_pass_rate=1.0,
        field_coverage=1.0,
    )


def _escalate_confidence() -> ConfidenceResult:
    return ConfidenceResult(
        score=0.2,
        band="escalate",
        fields_found=1,
        expected_fields=5,
        validation_checks=[ValidationCheck("totals_crosscheck", False, "low coverage")],
        validation_pass_rate=0.0,
        field_coverage=0.2,
    )


def test_build_bill_parses_calculated_cost_strings():
    tier3 = Tier3ExtractionResult(
        provider="Energia",
        fields={
            "day_kwh": FieldExtractionResult("day_kwh", "100", 0.8, 0),
            "day_rate": FieldExtractionResult("day_rate", "0.25", 0.8, 0),
            "day_cost": FieldExtractionResult("day_cost", "25.00 (calculated)", 0.7, -1),
        },
        field_count=3,
        hit_rate=0.3,
        warnings=[],
    )
    bill = _build_bill(
        tier3=tier3,
        provider="Energia",
        confidence=_accept_confidence(),
        extraction_method="test",
        raw_text="",
    )
    assert bill.line_items
    assert bill.line_items[0].line_total == 25.00


def test_image_escalation_merge_prefers_llm(monkeypatch):
    spatial_fields = {
        "total_incl_vat": FieldExtractionResult("total_incl_vat", "111.11", 0.8, 0),
    }
    spatial = Tier2ExtractionResult(
        fields=spatial_fields,
        field_count=1,
        hit_rate=0.1,
        warnings=[],
    )
    tier4 = Tier4ExtractionResult(
        fields={
            "total_incl_vat": FieldExtractionResult("total_incl_vat", "222.22", 0.8, -1),
            "provider": FieldExtractionResult("provider", "Energia", 0.8, -1),
        },
        field_count=2,
        hit_rate=0.1,
        warnings=[],
    )

    monkeypatch.setattr("orchestrator.extract_tier2_spatial", lambda source, is_image=True: (spatial, 85.0, pd.DataFrame(), "energia"))
    monkeypatch.setattr("orchestrator.detect_provider", lambda text: types.SimpleNamespace(provider_name="unknown", is_known=False))
    monkeypatch.setattr("orchestrator.get_provider_config", lambda provider: None)

    call_count = {"n": 0}

    def fake_confidence(*args, **kwargs):
        call_count["n"] += 1
        return _escalate_confidence() if call_count["n"] == 1 else _accept_confidence()

    monkeypatch.setattr("orchestrator.calculate_confidence", fake_confidence)
    monkeypatch.setattr("orchestrator._try_tier4_llm", lambda source, extraction_path, is_image=True: tier4)

    result = extract_bill_from_image(b"fake-image-bytes")
    assert result.bill.total_incl_vat == 222.22


def test_llm_missing_google_genai_module_raises_runtime_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "google.genai" or (name == "google" and fromlist and "genai" in fromlist):
            raise ModuleNotFoundError("No module named 'google.genai'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    try:
        raised = False
        try:
            extract_tier4_llm(b"fake pdf bytes")
        except RuntimeError as exc:
            raised = True
            assert "google-genai package not installed" in str(exc)
        assert raised
    finally:
        monkeypatch.setattr(builtins, "__import__", real_import)


def test_llm_pdf_uses_multiple_pages(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MAX_PDF_PAGES", "3")

    class FakeDoc:
        page_count = 3

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    pymupdf_stub = types.SimpleNamespace(open=lambda *args, **kwargs: FakeDoc())
    monkeypatch.setitem(sys.modules, "pymupdf", pymupdf_stub)

    calls: dict[str, list] = {"pages": [], "contents": []}

    monkeypatch.setattr(
        "llm_extraction._image_bytes_from_pdf",
        lambda source, page_num=0: calls["pages"].append(page_num) or f"page-{page_num}".encode(),
    )

    class FakePart:
        @staticmethod
        def from_bytes(data, mime_type):
            return {"data": data, "mime_type": mime_type}

    monkeypatch.setattr("llm_extraction._get_genai_types", lambda: types.SimpleNamespace(Part=FakePart))

    class FakeClient:
        class _Models:
            @staticmethod
            def generate_content(model, contents, config):
                calls["contents"] = contents
                return types.SimpleNamespace(text='{"provider":"Energia"}')

        models = _Models()

    monkeypatch.setattr("llm_extraction._get_gemini_client", lambda: FakeClient())

    result = extract_tier4_llm("fake.pdf")
    assert result.field_count >= 1
    assert calls["pages"] == [0, 1, 2]
    assert len(calls["contents"]) == 4  # 3 page images + prompt


def test_provider_detection_avoids_substring_false_positives():
    text = "Calibration report for calorimeter systems and yunohost migration notes."
    detected = detect_provider(text)
    assert detected.provider_name == "unknown"


def test_short_year_date_parsing_supported():
    parsed_1 = parse_formatter_date("1 Mar 23")
    parsed_2 = parse_verification_date("1 Mar 23")
    assert parsed_1 is not None
    assert parsed_2 is not None
    assert parsed_1.year == 2023
    assert parsed_2.year == 2023


def test_spatial_ocr_uses_all_pages_by_default(monkeypatch):
    from spatial_extraction import get_ocr_dataframe

    fake_images = [object(), object(), object()]
    kwargs_seen = {}

    def fake_convert_from_path(path, **kwargs):
        kwargs_seen.update(kwargs)
        return fake_images

    pdf2image_stub = types.SimpleNamespace(
        convert_from_path=fake_convert_from_path,
        convert_from_bytes=lambda source, **kwargs: fake_images,
    )
    monkeypatch.setitem(sys.modules, "pdf2image", pdf2image_stub)

    class FakeOutput:
        DATAFRAME = "dataframe"

    def fake_image_to_data(img, lang, output_type):
        return pd.DataFrame(
            [
                {
                    "text": "Total",
                    "left": 1,
                    "top": 1,
                    "width": 1,
                    "height": 1,
                    "conf": 90,
                    "block_num": 1,
                    "line_num": 1,
                    "word_num": 1,
                }
            ]
        )

    pytesseract_stub = types.SimpleNamespace(
        image_to_data=fake_image_to_data,
        Output=FakeOutput,
    )
    monkeypatch.setitem(sys.modules, "pytesseract", pytesseract_stub)

    df, _avg_conf = get_ocr_dataframe("fake.pdf")
    assert len(df["page_num"].unique()) == 3
    assert "last_page" not in kwargs_seen
