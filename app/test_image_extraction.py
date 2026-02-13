"""
Unit tests for image-based bill extraction.

Tests:
  - get_ocr_dataframe() with is_image=True
  - extract_bill_from_image() returns a valid PipelineResult
  - Image extension routing logic
"""
import os

import pytest

BILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "Steve_bills")
IMAGE_PATH = os.path.join(BILLS_DIR, "Steve_bill_photo.jpg")


def _image_exists() -> bool:
    return os.path.exists(IMAGE_PATH)


class TestImageExtensionRouting:
    """Test that image extensions are correctly detected."""

    def test_jpg_detected(self):
        assert "photo.jpg".lower().endswith((".jpg", ".jpeg", ".png"))

    def test_jpeg_detected(self):
        assert "scan.jpeg".lower().endswith((".jpg", ".jpeg", ".png"))

    def test_png_detected(self):
        assert "bill.png".lower().endswith((".jpg", ".jpeg", ".png"))

    def test_pdf_not_detected_as_image(self):
        assert not "bill.pdf".lower().endswith((".jpg", ".jpeg", ".png"))

    def test_csv_not_detected_as_image(self):
        assert not "data.csv".lower().endswith((".jpg", ".jpeg", ".png"))


@pytest.mark.skipif(not _image_exists(), reason="Steve_bill_photo.jpg not found")
class TestGetOcrDataframeImage:
    """Test OCR dataframe extraction from images."""

    def test_returns_dataframe_and_confidence(self):
        from spatial_extraction import get_ocr_dataframe

        df, avg_conf = get_ocr_dataframe(IMAGE_PATH, is_image=True)
        assert not df.empty, "OCR should produce words from the bill image"
        assert avg_conf > 0, "Average OCR confidence should be positive"

    def test_dataframe_has_required_columns(self):
        from spatial_extraction import get_ocr_dataframe

        df, _ = get_ocr_dataframe(IMAGE_PATH, is_image=True)
        for col in ("text", "left", "top", "width", "height", "conf", "page_num"):
            assert col in df.columns, f"Missing column: {col}"

    def test_works_with_bytes(self):
        from spatial_extraction import get_ocr_dataframe

        with open(IMAGE_PATH, "rb") as f:
            image_bytes = f.read()
        df, avg_conf = get_ocr_dataframe(image_bytes, is_image=True)
        assert not df.empty, "OCR should work with image bytes"


@pytest.mark.skipif(not _image_exists(), reason="Steve_bill_photo.jpg not found")
class TestExtractBillFromImage:
    """Test the full image extraction pipeline."""

    def test_returns_pipeline_result(self):
        from orchestrator import extract_bill_from_image, PipelineResult

        result = extract_bill_from_image(IMAGE_PATH)
        assert isinstance(result, PipelineResult)

    def test_extraction_path_starts_with_image_input(self):
        from orchestrator import extract_bill_from_image

        result = extract_bill_from_image(IMAGE_PATH)
        assert "image_input" in result.extraction_path

    def test_bill_has_confidence_score(self):
        from orchestrator import extract_bill_from_image

        result = extract_bill_from_image(IMAGE_PATH)
        assert result.confidence is not None
        assert 0.0 <= result.confidence.score <= 1.0

    def test_works_with_bytes(self):
        from orchestrator import extract_bill_from_image, PipelineResult

        with open(IMAGE_PATH, "rb") as f:
            image_bytes = f.read()
        result = extract_bill_from_image(image_bytes)
        assert isinstance(result, PipelineResult)
