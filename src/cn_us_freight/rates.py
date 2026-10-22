"""Illustrative China → United States reference rates.

The numbers in this module are rounded planning defaults for small wholesale
and e-commerce estimates. They are not carrier quotes, tariffs, fuel
surcharges, or offers to carry freight.

``RATE_TABLE_REVISION`` tracks edits to this file. It is not a market-quote
date. When you change a figure, bump the revision and update the tests.
"""

from decimal import Decimal
from types import MappingProxyType

RATE_TABLE_REVISION = "reference-1"

# Planning labels, not a carrier's zone map.
ZONES = ("west", "central", "east")

ZONE_LABELS = MappingProxyType(
    {
        "west": "US West Coast planning zone",
        "central": "US central / Gulf planning zone",
        "east": "US East Coast planning zone",
    }
)

DEFAULT_ZONE = "west"

# Usual international air volumetric factor: 6,000 cm³ per kg.
AIR_CM3_PER_KG = Decimal("6000")

# Air reference, USD per chargeable kilogram.
AIR_RATES_USD_PER_KG = MappingProxyType(
    {
        "west": Decimal("5.50"),
        "central": Decimal("6.40"),
        "east": Decimal("7.20"),
    }
)

# This model bills at least this much chargeable weight.
AIR_MINIMUM_CHARGEABLE_KG = Decimal("1")

# This model bills at least this much for an air shipment.
AIR_MINIMUM_USD = Decimal("45.00")

# Weight-or-measurement conversion used by this model: 1 CBM = 1,000 kg.
SEA_KG_PER_CBM = Decimal("1000")

# Sea reference, USD per chargeable cubic meter (port-to-port planning).
SEA_RATES_USD_PER_CBM = MappingProxyType(
    {
        "west": Decimal("90.00"),
        "central": Decimal("120.00"),
        "east": Decimal("160.00"),
    }
)

# This model bills at least this much chargeable volume.
SEA_MINIMUM_CHARGEABLE_CBM = Decimal("1")

# This model bills at least this much for a sea shipment.
SEA_MINIMUM_USD = Decimal("100.00")

DISCLAIMER = (
    "Illustrative reference rates from table {revision}, "
    "not a carrier quote or booking."
)

EXCLUSIONS = (
    "Excludes customs duties, taxes, insurance, pickup, origin and "
    "destination terminal fees, and final-mile delivery."
)


def _check_tables() -> None:
    air_zones = tuple(AIR_RATES_USD_PER_KG)
    sea_zones = tuple(SEA_RATES_USD_PER_CBM)
    if air_zones != ZONES or sea_zones != ZONES or tuple(ZONE_LABELS) != ZONES:
        raise RuntimeError(
            "Air rates, sea rates, and zone labels must use the same zones "
            f"in this order: {', '.join(ZONES)}"
        )
    if DEFAULT_ZONE not in ZONES:
        raise RuntimeError("DEFAULT_ZONE must be one of the reference zones")

    tables = (AIR_RATES_USD_PER_KG, SEA_RATES_USD_PER_CBM)
    for table in tables:
        for zone, rate in table.items():
            if not isinstance(rate, Decimal) or not rate.is_finite() or rate <= 0:
                raise RuntimeError(f"reference rate for {zone} must be a positive Decimal")

    minimums = (
        AIR_MINIMUM_CHARGEABLE_KG,
        AIR_MINIMUM_USD,
        SEA_MINIMUM_CHARGEABLE_CBM,
        SEA_MINIMUM_USD,
        AIR_CM3_PER_KG,
        SEA_KG_PER_CBM,
    )
    for value in minimums:
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            raise RuntimeError("reference factors and minimums must be positive Decimals")


_check_tables()
