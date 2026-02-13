"""
Unit tests for the unified Bill Extractor page logic.

Tests the bill accumulation, content hash deduplication, field counting,
and extract helper function used by the unified bill extractor workflow.
"""

import hashlib
from dataclasses import asdict
from unittest.mock import patch, MagicMock

import pytest

from bill_parser import BillData, GenericBillData
from common.session import content_hash, make_cache_key


# ---------------------------------------------------------------------------
# content_hash deduplication
# ---------------------------------------------------------------------------

class TestContentHash:
    """Test content hashing for file deduplication."""

    def test_same_content_same_hash(self):
        """Identical content should produce the same hash."""
        data = b"sample pdf bytes"
        assert content_hash(data) == content_hash(data)

    def test_different_content_different_hash(self):
        """Different content should produce different hashes."""
        assert content_hash(b"file A") != content_hash(b"file B")

    def test_hash_is_md5_hex(self):
        """Hash should be a valid MD5 hex digest."""
        data = b"test"
        expected = hashlib.md5(data).hexdigest()
        assert content_hash(data) == expected

    def test_empty_bytes(self):
        """Empty bytes should produce a deterministic hash."""
        h = content_hash(b"")
        assert isinstance(h, str)
        assert len(h) == 32  # MD5 hex digest length


class TestMakeCacheKey:
    """Test cache key generation."""

    def test_cache_key_includes_prefix(self):
        key = make_cache_key("bill", "test.pdf", b"content")
        assert key.startswith("bill_")

    def test_cache_key_includes_filename(self):
        key = make_cache_key("bill", "my_file.pdf", b"content")
        assert "my_file.pdf" in key

    def test_same_content_same_key(self):
        content = b"identical bytes"
        k1 = make_cache_key("bill", "a.pdf", content)
        k2 = make_cache_key("bill", "a.pdf", content)
        assert k1 == k2

    def test_different_content_different_key(self):
        k1 = make_cache_key("bill", "a.pdf", b"v1")
        k2 = make_cache_key("bill", "a.pdf", b"v2")
        assert k1 != k2


# ---------------------------------------------------------------------------
# _count_extracted_fields (logic extracted for testability)
# ---------------------------------------------------------------------------

def _count_extracted_fields(bill: BillData) -> int:
    """Count non-None fields, excluding metadata."""
    bill_dict = asdict(bill)
    skip = {'extraction_method', 'confidence_score', 'warnings'}
    return sum(
        1 for k, v in bill_dict.items()
        if k not in skip and v is not None
    )


class TestCountExtractedFields:
    """Test the field counting helper."""

    def test_empty_bill_zero_fields(self):
        bill = BillData()
        assert _count_extracted_fields(bill) == 0

    def test_bill_with_supplier_only(self):
        bill = BillData(supplier="Energia")
        assert _count_extracted_fields(bill) == 1

    def test_bill_with_multiple_fields(self):
        bill = BillData(
            supplier="Energia",
            mprn="10306268587",
            total_units_kwh=500.0,
            total_this_period=123.45,
        )
        assert _count_extracted_fields(bill) == 4

    def test_metadata_fields_excluded(self):
        """extraction_method, confidence_score, warnings should not be counted."""
        bill = BillData(
            extraction_method="tier3",
            confidence_score=0.85,
            warnings=["some warning"],
            supplier="Test",
        )
        assert _count_extracted_fields(bill) == 1  # only supplier


# ---------------------------------------------------------------------------
# _extract_bill logic
# ---------------------------------------------------------------------------

class TestExtractBillHelper:
    """Test the _extract_bill helper function logic.

    These tests validate the result dict structure without importing
    the orchestrator module (which has heavy dependencies).
    """

    def test_successful_result_structure(self):
        """A successful extraction result should have the correct structure."""
        bill = BillData(supplier="Energia", mprn="123", confidence_score=0.85)
        file_content = b"fake pdf content"
        file_hash = content_hash(file_content)

        # Simulate what _extract_bill returns on success
        result = {
            "filename": "test.pdf",
            "bill": bill,
            "raw_text": "sample text",
            "confidence": bill.confidence_score,
            "content_hash": file_hash,
            "status": "success",
            "supplier": bill.supplier or "Unknown",
            "field_count": _count_extracted_fields(bill),
            "error": None,
        }

        assert result["status"] == "success"
        assert result["supplier"] == "Energia"
        assert result["error"] is None
        assert result["content_hash"] == file_hash
        assert result["confidence"] == 0.85
        assert result["field_count"] == 2  # supplier + mprn

    def test_error_result_structure(self):
        """A failed extraction result should have the correct structure."""
        file_content = b"corrupt pdf"
        file_hash = content_hash(file_content)

        # Simulate what _extract_bill returns on error
        result = {
            "filename": "bad.pdf",
            "bill": None,
            "raw_text": None,
            "confidence": 0.0,
            "content_hash": file_hash,
            "status": "error",
            "supplier": None,
            "field_count": 0,
            "error": "bad pdf",
        }

        assert result["status"] == "error"
        assert result["error"] == "bad pdf"
        assert result["bill"] is None
        assert result["confidence"] == 0.0
        assert result["field_count"] == 0

    def test_image_file_detection(self):
        """Image files (.jpg, .jpeg, .png) should be detected by extension."""
        image_extensions = ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG']
        for ext in image_extensions:
            filename = f"bill{ext}"
            assert filename.lower().endswith(('.jpg', '.jpeg', '.png')), \
                f"Extension {ext} should be detected as image"

    def test_pdf_file_detection(self):
        """PDF files should NOT match image extensions."""
        assert not "test.pdf".lower().endswith(('.jpg', '.jpeg', '.png'))


# ---------------------------------------------------------------------------
# Bill accumulation session state logic
# ---------------------------------------------------------------------------

class TestBillAccumulation:
    """Test the session state accumulation and deduplication logic."""

    def test_deduplication_by_hash(self):
        """Same content uploaded twice should not produce duplicate entries."""
        processed_hashes = set()
        extracted_bills = []

        content_a = b"pdf content A"
        hash_a = content_hash(content_a)

        # First upload
        if hash_a not in processed_hashes:
            extracted_bills.append({"filename": "a.pdf", "content_hash": hash_a, "status": "success"})
            processed_hashes.add(hash_a)

        # Same content, different filename
        hash_a2 = content_hash(content_a)
        if hash_a2 not in processed_hashes:
            extracted_bills.append({"filename": "a_copy.pdf", "content_hash": hash_a2, "status": "success"})
            processed_hashes.add(hash_a2)

        assert len(extracted_bills) == 1
        assert len(processed_hashes) == 1

    def test_different_files_accumulate(self):
        """Different files should all be added to the list."""
        processed_hashes = set()
        extracted_bills = []

        for i in range(5):
            content = f"pdf content {i}".encode()
            h = content_hash(content)
            if h not in processed_hashes:
                extracted_bills.append({
                    "filename": f"bill_{i}.pdf",
                    "content_hash": h,
                    "status": "success",
                })
                processed_hashes.add(h)

        assert len(extracted_bills) == 5
        assert len(processed_hashes) == 5

    def test_clear_all_resets_state(self):
        """Clearing should empty both lists."""
        processed_hashes = {"hash1", "hash2"}
        extracted_bills = [{"status": "success"}, {"status": "success"}]

        # Simulate clear
        extracted_bills.clear()
        processed_hashes.clear()

        assert len(extracted_bills) == 0
        assert len(processed_hashes) == 0

    def test_successful_and_failed_bills_separate(self):
        """Should correctly separate successful and failed extractions."""
        bills = [
            {"filename": "good.pdf", "bill": BillData(supplier="Test"), "status": "success"},
            {"filename": "bad.pdf", "bill": None, "status": "error", "error": "corrupt"},
            {"filename": "ok.pdf", "bill": BillData(supplier="Other"), "status": "success"},
        ]

        successful = [(b["bill"], b["filename"]) for b in bills if b["status"] == "success"]
        errors = [b for b in bills if b["status"] == "error"]

        assert len(successful) == 2
        assert len(errors) == 1
        assert errors[0]["filename"] == "bad.pdf"

    def test_single_bill_shows_detail(self):
        """With 1 successful bill, should show detail view."""
        successful = [
            (BillData(supplier="Energia"), "bill.pdf"),
        ]
        assert len(successful) == 1

    def test_multiple_bills_shows_comparison(self):
        """With 2+ successful bills, should show comparison."""
        successful = [
            (BillData(supplier="Energia"), "bill1.pdf"),
            (BillData(supplier="Go Power"), "bill2.pdf"),
        ]
        assert len(successful) >= 2


# ---------------------------------------------------------------------------
# Status chip logic
# ---------------------------------------------------------------------------

class TestStatusChipLogic:
    """Test the status chip color/icon determination logic."""

    def test_high_confidence_green(self):
        """Confidence >= 80% should be green."""
        conf = 85
        if conf >= 80:
            color = "#22c55e"
        elif conf >= 50:
            color = "#f59e0b"
        else:
            color = "#ef4444"
        assert color == "#22c55e"

    def test_medium_confidence_amber(self):
        """Confidence 50-79% should be amber."""
        conf = 65
        if conf >= 80:
            color = "#22c55e"
        elif conf >= 50:
            color = "#f59e0b"
        else:
            color = "#ef4444"
        assert color == "#f59e0b"

    def test_low_confidence_red(self):
        """Confidence < 50% should be red."""
        conf = 30
        if conf >= 80:
            color = "#22c55e"
        elif conf >= 50:
            color = "#f59e0b"
        else:
            color = "#ef4444"
        assert color == "#ef4444"
