"""
Tests for LineItem / GenericBillData dataclasses and legacy compatibility.

Covers acceptance criteria for data model:
  (a) dataclass construction
  (b) serialization to dict/json
  (c) legacy compatibility mapping via generic_to_legacy()
"""
import json
import pytest
from dataclasses import asdict

from bill_parser import (
    LineItem,
    GenericBillData,
    generic_to_legacy,
    BillData,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sample_line_items() -> list[LineItem]:
    return [
        LineItem(
            description="Day Energy",
            quantity=242.0,
            unit="kWh",
            unit_price=0.4321,
            line_total=104.57,
            vat_rate=13.5,
            vat_amount=14.12,
        ),
        LineItem(
            description="Night Energy",
            quantity=130.5,
            unit="kWh",
            unit_price=0.2105,
            line_total=27.47,
            vat_rate=13.5,
            vat_amount=3.71,
        ),
        LineItem(
            description="Standing Charge",
            quantity=61,
            unit="days",
            unit_price=0.6027,
            line_total=36.76,
            vat_rate=13.5,
            vat_amount=4.96,
        ),
        LineItem(
            description="PSO Levy",
            quantity=None,
            unit=None,
            unit_price=None,
            line_total=0.00,
            vat_rate=None,
            vat_amount=None,
        ),
        LineItem(
            description="Discount for this period",
            quantity=None,
            unit=None,
            unit_price=None,
            line_total=15.00,
        ),
    ]


def _sample_generic() -> GenericBillData:
    return GenericBillData(
        provider="Energia",
        invoice_number="1234567",
        account_number="9876543",
        mprn="10306268587",
        gprn=None,
        invoice_date="15 January 2026",
        billing_period="01/11/2025 - 01/01/2026",
        due_date="29 January 2026",
        line_items=_sample_line_items(),
        subtotal=153.80,
        vat_amount=22.79,
        vat_rate=13.5,
        total_incl_vat=176.59,
        extraction_method="tier3_provider",
        confidence_score=0.92,
        raw_text="sample raw text...",
        warnings=["VAT cross-check minor rounding"],
    )


# ---------------------------------------------------------------------------
# (a) Dataclass construction
# ---------------------------------------------------------------------------

class TestLineItemConstruction:
    def test_required_fields_only(self):
        li = LineItem(description="Kerosene", line_total=901.72)
        assert li.description == "Kerosene"
        assert li.line_total == 901.72
        assert li.quantity is None
        assert li.unit is None
        assert li.unit_price is None
        assert li.vat_rate is None
        assert li.vat_amount is None

    def test_all_fields(self):
        li = LineItem(
            description="Day Energy",
            quantity=242.0,
            unit="kWh",
            unit_price=0.4321,
            line_total=104.57,
            vat_rate=13.5,
            vat_amount=14.12,
        )
        assert li.quantity == 242.0
        assert li.unit == "kWh"
        assert li.unit_price == 0.4321
        assert li.vat_rate == 13.5
        assert li.vat_amount == 14.12


class TestGenericBillDataConstruction:
    def test_defaults(self):
        g = GenericBillData()
        assert g.provider == ""
        assert g.line_items == []
        assert g.confidence_score == 0.0
        assert g.warnings == []

    def test_full_construction(self):
        g = _sample_generic()
        assert g.provider == "Energia"
        assert g.mprn == "10306268587"
        assert len(g.line_items) == 5
        assert g.total_incl_vat == 176.59
        assert g.extraction_method == "tier3_provider"

    def test_line_items_are_independent(self):
        """Verify default_factory creates independent lists."""
        g1 = GenericBillData()
        g2 = GenericBillData()
        g1.line_items.append(LineItem(description="x", line_total=1.0))
        assert len(g2.line_items) == 0


# ---------------------------------------------------------------------------
# (b) Serialization to dict / JSON
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_to_dict(self):
        g = _sample_generic()
        d = g.to_dict()
        assert isinstance(d, dict)
        assert d["provider"] == "Energia"
        assert isinstance(d["line_items"], list)
        assert len(d["line_items"]) == 5
        assert d["line_items"][0]["description"] == "Day Energy"

    def test_to_json_roundtrip(self):
        g = _sample_generic()
        j = g.to_json()
        parsed = json.loads(j)
        assert parsed["mprn"] == "10306268587"
        assert parsed["total_incl_vat"] == 176.59

    def test_from_dict_roundtrip(self):
        g = _sample_generic()
        d = g.to_dict()
        g2 = GenericBillData.from_dict(d)
        assert g2.provider == g.provider
        assert g2.mprn == g.mprn
        assert len(g2.line_items) == len(g.line_items)
        assert g2.line_items[0].description == "Day Energy"
        assert g2.total_incl_vat == g.total_incl_vat

    def test_asdict_compat(self):
        """Standard dataclasses.asdict should also work."""
        g = _sample_generic()
        d = asdict(g)
        assert d["provider"] == "Energia"
        assert isinstance(d["line_items"], list)

    def test_line_item_to_dict(self):
        li = LineItem(description="Test", line_total=10.0, quantity=5.0, unit="kWh")
        d = asdict(li)
        assert d["description"] == "Test"
        assert d["line_total"] == 10.0
        assert d["quantity"] == 5.0
        assert d["vat_rate"] is None

    def test_from_dict_with_raw_dicts(self):
        """from_dict should accept line_items as plain dicts."""
        raw = {
            "provider": "SSE",
            "line_items": [
                {"description": "Energy", "line_total": 50.0},
            ],
            "extraction_method": "tier2_generic",
            "confidence_score": 0.7,
        }
        g = GenericBillData.from_dict(raw)
        assert len(g.line_items) == 1
        assert isinstance(g.line_items[0], LineItem)
        assert g.line_items[0].description == "Energy"


# ---------------------------------------------------------------------------
# (c) Legacy compatibility mapping
# ---------------------------------------------------------------------------

class TestGenericToLegacy:
    def test_identity_fields(self):
        g = _sample_generic()
        bill = generic_to_legacy(g)
        assert isinstance(bill, BillData)
        assert bill.supplier == "Energia"
        assert bill.mprn == "10306268587"
        assert bill.account_number == "9876543"
        assert bill.invoice_number == "1234567"

    def test_date_fields(self):
        g = _sample_generic()
        bill = generic_to_legacy(g)
        assert bill.bill_date == "15 January 2026"
        assert bill.payment_due_date == "29 January 2026"
        assert bill.billing_period_start == "01/11/2025"
        assert bill.billing_period_end == "01/01/2026"

    def test_line_items_to_flat_fields(self):
        g = _sample_generic()
        bill = generic_to_legacy(g)
        # Day energy
        assert bill.day_units_kwh == 242.0
        assert bill.day_rate == 0.4321
        assert bill.day_cost == 104.57
        # Night energy
        assert bill.night_units_kwh == 130.5
        assert bill.night_rate == 0.2105
        assert bill.night_cost == 27.47
        # Standing charge
        assert bill.standing_charge_days == 61
        assert bill.standing_charge_rate == 0.6027
        assert bill.standing_charge_total == 36.76
        # PSO
        assert bill.pso_levy == 0.00
        # Discount
        assert bill.discount == 15.00

    def test_total_consumption(self):
        g = _sample_generic()
        bill = generic_to_legacy(g)
        expected = round(242.0 + 130.5, 3)
        assert bill.total_units_kwh == expected

    def test_totals(self):
        g = _sample_generic()
        bill = generic_to_legacy(g)
        assert bill.subtotal_before_vat == 153.80
        assert bill.vat_amount == 22.79
        assert bill.vat_rate_pct == 13.5
        assert bill.total_this_period == 176.59

    def test_metadata(self):
        g = _sample_generic()
        bill = generic_to_legacy(g)
        assert bill.extraction_method == "tier3_provider"
        assert bill.confidence_score == 0.92
        assert "VAT cross-check minor rounding" in bill.warnings

    def test_empty_generic(self):
        """An empty GenericBillData should produce a valid BillData with defaults."""
        g = GenericBillData()
        bill = generic_to_legacy(g)
        assert isinstance(bill, BillData)
        assert bill.supplier is None
        assert bill.total_units_kwh is None

    def test_peak_line_item(self):
        g = GenericBillData(
            provider="Test",
            line_items=[
                LineItem(
                    description="Peak Energy",
                    quantity=50.0,
                    unit="kWh",
                    unit_price=0.55,
                    line_total=27.50,
                ),
            ],
            total_incl_vat=27.50,
        )
        bill = generic_to_legacy(g)
        assert bill.peak_units_kwh == 50.0
        assert bill.peak_rate == 0.55
        assert bill.peak_cost == 27.50

    def test_export_line_item(self):
        g = GenericBillData(
            provider="Test",
            line_items=[
                LineItem(
                    description="Export Units",
                    quantity=100.0,
                    unit="kWh",
                    unit_price=0.185,
                    line_total=18.50,
                ),
            ],
        )
        bill = generic_to_legacy(g)
        assert bill.export_units == 100.0
        assert bill.export_rate == 0.185
        assert bill.export_credit == 18.50

    def test_billing_period_no_spaces(self):
        """Billing period with no spaces around separator should still parse."""
        g = GenericBillData(billing_period="01/11/2025-01/01/2026")
        bill = generic_to_legacy(g)
        assert bill.billing_period_start == "01/11/2025"
        assert bill.billing_period_end == "01/01/2026"

    def test_legacy_asdict_works(self):
        """The converted BillData should work with asdict for Excel export."""
        g = _sample_generic()
        bill = generic_to_legacy(g)
        d = asdict(bill)
        assert isinstance(d, dict)
        assert "supplier" in d
        assert "mprn" in d

    def test_fuel_type_propagated(self):
        """fuel_type should propagate from GenericBillData to BillData."""
        g = GenericBillData(provider="Manual", fuel_type="kerosene")
        bill = generic_to_legacy(g)
        assert bill.fuel_type == "kerosene"

    def test_fuel_type_none_by_default(self):
        """fuel_type should default to None on both models."""
        g = GenericBillData()
        assert g.fuel_type is None
        bill = BillData()
        assert bill.fuel_type is None

    def test_fuel_type_in_asdict(self):
        """fuel_type should appear in asdict output."""
        bill = BillData(supplier="Test", fuel_type="coal")
        d = asdict(bill)
        assert d["fuel_type"] == "coal"

    def test_fuel_type_roundtrip(self):
        """fuel_type should survive GenericBillData -> dict -> from_dict."""
        g = GenericBillData(provider="Test", fuel_type="lpg")
        d = g.to_dict()
        g2 = GenericBillData.from_dict(d)
        assert g2.fuel_type == "lpg"
