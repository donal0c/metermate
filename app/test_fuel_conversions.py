"""Unit tests for fuel_conversions module.

Tests conversion factors, unit validation, and helper functions.
"""

import pytest

from fuel_conversions import (
    FUEL_TYPES,
    UNIT_DISPLAY_NAMES,
    convert_to_kwh,
    get_unit_options,
    get_display_name,
    get_all_units,
    get_valid_fuel_units_map,
)


# ---------------------------------------------------------------------------
# convert_to_kwh
# ---------------------------------------------------------------------------

class TestConvertToKwh:
    """Test kWh conversion for each fuel type."""

    def test_coal_bag(self):
        result = convert_to_kwh("coal", 5, "bag_40kg")
        assert result == pytest.approx(5 * 325.6)

    def test_coal_tonne(self):
        result = convert_to_kwh("coal", 1, "tonne")
        assert result == pytest.approx(8140.0)

    def test_smokeless_coal_bag(self):
        result = convert_to_kwh("smokeless_coal", 3, "bag_25kg")
        assert result == pytest.approx(3 * 222.5)

    def test_smokeless_coal_tonne(self):
        result = convert_to_kwh("smokeless_coal", 1, "tonne")
        assert result == pytest.approx(8900.0)

    def test_peat_briquettes_bale(self):
        result = convert_to_kwh("peat_briquettes", 10, "bale_12_5kg")
        assert result == pytest.approx(10 * 58.0)

    def test_peat_briquettes_tonne(self):
        result = convert_to_kwh("peat_briquettes", 1, "tonne")
        assert result == pytest.approx(4650.0)

    def test_wood_pellets_tonne(self):
        result = convert_to_kwh("wood_pellets", 2, "tonne")
        assert result == pytest.approx(2 * 4800.0)

    def test_wood_logs_tonne(self):
        result = convert_to_kwh("wood_logs", 0.5, "tonne")
        assert result == pytest.approx(0.5 * 3500.0)

    def test_kerosene_litres(self):
        result = convert_to_kwh("kerosene", 500, "litre")
        assert result == pytest.approx(500 * 10.35)

    def test_lpg_litres(self):
        result = convert_to_kwh("lpg", 100, "litre")
        assert result == pytest.approx(100 * 7.08)

    def test_lpg_kg(self):
        result = convert_to_kwh("lpg", 47, "kg")
        assert result == pytest.approx(47 * 13.6)

    def test_zero_quantity(self):
        result = convert_to_kwh("coal", 0, "bag_40kg")
        assert result == 0.0

    def test_unknown_fuel_raises(self):
        with pytest.raises(ValueError, match="Unknown fuel type"):
            convert_to_kwh("nuclear", 1, "rod")

    def test_invalid_unit_for_fuel_raises(self):
        with pytest.raises(ValueError, match="Invalid unit"):
            convert_to_kwh("coal", 1, "litre")

    def test_kerosene_bag_raises(self):
        with pytest.raises(ValueError, match="Invalid unit"):
            convert_to_kwh("kerosene", 1, "bag_40kg")


# ---------------------------------------------------------------------------
# get_unit_options
# ---------------------------------------------------------------------------

class TestGetUnitOptions:
    """Test unit option retrieval for each fuel type."""

    def test_coal_units(self):
        units = get_unit_options("coal")
        assert "tonne" in units
        assert "bag_40kg" in units
        assert len(units) == 2

    def test_kerosene_units(self):
        units = get_unit_options("kerosene")
        assert units == ["litre"]

    def test_lpg_units(self):
        units = get_unit_options("lpg")
        assert "litre" in units
        assert "kg" in units

    def test_unknown_fuel_raises(self):
        with pytest.raises(ValueError, match="Unknown fuel type"):
            get_unit_options("plutonium")


# ---------------------------------------------------------------------------
# get_display_name
# ---------------------------------------------------------------------------

class TestGetDisplayName:
    """Test display name retrieval."""

    def test_coal(self):
        assert get_display_name("coal") == "Coal"

    def test_kerosene(self):
        assert get_display_name("kerosene") == "Kerosene"

    def test_wood_logs(self):
        assert get_display_name("wood_logs") == "Wood Logs (Seasoned)"

    def test_smokeless_coal(self):
        assert get_display_name("smokeless_coal") == "Smokeless Coal"

    def test_unknown_fuel_raises(self):
        with pytest.raises(ValueError, match="Unknown fuel type"):
            get_display_name("diesel")


# ---------------------------------------------------------------------------
# get_all_units
# ---------------------------------------------------------------------------

class TestGetAllUnits:
    """Test the aggregated unit list."""

    def test_returns_list(self):
        units = get_all_units()
        assert isinstance(units, list)
        assert len(units) > 0

    def test_no_duplicates(self):
        units = get_all_units()
        assert len(units) == len(set(units))

    def test_contains_common_units(self):
        units = get_all_units()
        assert "tonne" in units
        assert "litre" in units
        assert "kg" in units
        assert "bag_40kg" in units


# ---------------------------------------------------------------------------
# get_valid_fuel_units_map
# ---------------------------------------------------------------------------

class TestGetValidFuelUnitsMap:
    """Test the fuel-to-units mapping."""

    def test_all_fuels_present(self):
        mapping = get_valid_fuel_units_map()
        for fuel_key in FUEL_TYPES:
            assert fuel_key in mapping

    def test_units_match_fuel_types(self):
        mapping = get_valid_fuel_units_map()
        assert mapping["coal"] == ["tonne", "bag_40kg"]
        assert mapping["kerosene"] == ["litre"]


# ---------------------------------------------------------------------------
# UNIT_DISPLAY_NAMES coverage
# ---------------------------------------------------------------------------

class TestUnitDisplayNames:
    """Ensure all units used in FUEL_TYPES have display names."""

    def test_all_units_have_display_names(self):
        all_units = get_all_units()
        for unit in all_units:
            assert unit in UNIT_DISPLAY_NAMES, \
                f"Unit '{unit}' missing from UNIT_DISPLAY_NAMES"
