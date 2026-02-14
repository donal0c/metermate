"""Fuel type definitions and kWh conversion factors.

Based on SEAI/BER methodology for Irish energy audits.
Covers common solid fuels, kerosene, and LPG.
"""


FUEL_TYPES = {
    "coal": {
        "display_name": "Coal",
        "units": {
            "tonne": 8140.0,
            "bag_40kg": 325.6,
        },
        "default_unit": "bag_40kg",
    },
    "smokeless_coal": {
        "display_name": "Smokeless Coal",
        "units": {
            "tonne": 8900.0,
            "bag_25kg": 222.5,
        },
        "default_unit": "bag_25kg",
    },
    "peat_briquettes": {
        "display_name": "Peat Briquettes",
        "units": {
            "tonne": 4650.0,
            "bale_12_5kg": 58.0,
        },
        "default_unit": "bale_12_5kg",
    },
    "wood_pellets": {
        "display_name": "Wood Pellets",
        "units": {
            "tonne": 4800.0,
        },
        "default_unit": "tonne",
    },
    "wood_logs": {
        "display_name": "Wood Logs (Seasoned)",
        "units": {
            "tonne": 3500.0,
        },
        "default_unit": "tonne",
    },
    "kerosene": {
        "display_name": "Kerosene",
        "units": {
            "litre": 10.35,
        },
        "default_unit": "litre",
    },
    "lpg": {
        "display_name": "LPG",
        "units": {
            "litre": 7.08,
            "kg": 13.6,
        },
        "default_unit": "litre",
    },
}

UNIT_DISPLAY_NAMES = {
    "tonne": "Tonne",
    "bag_40kg": "Bag (40kg)",
    "bag_25kg": "Bag (25kg)",
    "bale_12_5kg": "Bale (12.5kg)",
    "litre": "Litre",
    "kg": "kg",
}


def convert_to_kwh(fuel_type: str, quantity: float, unit: str) -> float:
    """Convert a fuel quantity to kWh.

    Args:
        fuel_type: Key from FUEL_TYPES (e.g. "coal", "kerosene").
        quantity: Amount of fuel.
        unit: Unit of measurement (must be valid for the fuel type).

    Returns:
        Energy equivalent in kWh.

    Raises:
        ValueError: If fuel_type or unit is unknown/invalid.
    """
    if fuel_type not in FUEL_TYPES:
        raise ValueError(f"Unknown fuel type: {fuel_type}")
    fuel = FUEL_TYPES[fuel_type]
    if unit not in fuel["units"]:
        raise ValueError(
            f"Invalid unit '{unit}' for {fuel['display_name']}. "
            f"Valid units: {list(fuel['units'].keys())}"
        )
    return quantity * fuel["units"][unit]


def get_unit_options(fuel_type: str) -> list[str]:
    """Return the valid unit keys for a fuel type.

    Raises:
        ValueError: If fuel_type is unknown.
    """
    if fuel_type not in FUEL_TYPES:
        raise ValueError(f"Unknown fuel type: {fuel_type}")
    return list(FUEL_TYPES[fuel_type]["units"].keys())


def get_display_name(fuel_type: str) -> str:
    """Return the human-readable display name for a fuel type.

    Raises:
        ValueError: If fuel_type is unknown.
    """
    if fuel_type not in FUEL_TYPES:
        raise ValueError(f"Unknown fuel type: {fuel_type}")
    return FUEL_TYPES[fuel_type]["display_name"]


def get_all_units() -> list[str]:
    """Return a deduplicated list of all possible unit keys across all fuels."""
    units = []
    seen = set()
    for fuel in FUEL_TYPES.values():
        for unit_key in fuel["units"]:
            if unit_key not in seen:
                units.append(unit_key)
                seen.add(unit_key)
    return units


def get_valid_fuel_units_map() -> dict[str, list[str]]:
    """Return a mapping of fuel_type -> list of valid unit keys."""
    return {ft: list(info["units"].keys()) for ft, info in FUEL_TYPES.items()}
