"""China → US freight estimates from the built-in reference tables."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from cn_us_freight.rates import (
    AIR_CM3_PER_KG,
    AIR_MINIMUM_CHARGEABLE_KG,
    AIR_MINIMUM_USD,
    AIR_RATES_USD_PER_KG,
    DEFAULT_ZONE,
    DISCLAIMER,
    EXCLUSIONS,
    RATE_TABLE_REVISION,
    SEA_KG_PER_CBM,
    SEA_MINIMUM_CHARGEABLE_CBM,
    SEA_MINIMUM_USD,
    SEA_RATES_USD_PER_CBM,
    ZONE_LABELS,
    ZONES,
)

_CUBIC_CM_PER_M3 = Decimal("1000000")
_UNIT = Decimal("0.001")
_CENT = Decimal("0.01")


def _units(value: Decimal) -> Decimal:
    return value.quantize(_UNIT, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _fmt_units(value: Decimal) -> str:
    return f"{_units(value):f}"


def _fmt_money(value: Decimal) -> str:
    return f"{_money(value):f}"


@dataclass(frozen=True)
class FreightEstimate:
    """One planning estimate.

    Quantities and money are ``Decimal`` values rounded by the reference
    model (chargeable units to 0.001, USD to 0.01, half up). ``to_dict()``
    converts those to JSON numbers.
    """

    mode: str
    zone: str
    weight_kg: Decimal
    volume_m3: Decimal
    chargeable_units: Decimal
    chargeable_unit: str
    rate_usd_per_unit: Decimal
    estimated_usd: Decimal
    minimum_quantity_applied: bool
    minimum_charge_applied: bool
    rate_table_revision: str
    assumptions: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready dict of floats, strings, and bools."""

        def num(value: Decimal) -> float:
            return float(value)

        return {
            "mode": self.mode,
            "zone": self.zone,
            "weight_kg": num(self.weight_kg),
            "volume_m3": num(self.volume_m3),
            "chargeable_units": num(self.chargeable_units),
            "chargeable_unit": self.chargeable_unit,
            "rate_usd_per_unit": num(self.rate_usd_per_unit),
            "estimated_usd": num(self.estimated_usd),
            "minimum_quantity_applied": self.minimum_quantity_applied,
            "minimum_charge_applied": self.minimum_charge_applied,
            "rate_table_revision": self.rate_table_revision,
            "assumptions": list(self.assumptions),
        }

    def __str__(self) -> str:
        unit = self.chargeable_unit
        lines = [
            "China → US freight reference estimate",
            (
                f"Rate table: {self.rate_table_revision} "
                "(illustrative, not a carrier quote)"
            ),
            "",
            f"{'Mode:':<16} {self.mode}",
            f"{'Zone:':<16} {self.zone}",
            f"{'Actual weight:':<16} {_fmt_units(self.weight_kg)} kg",
            f"{'Volume:':<16} {_fmt_units(self.volume_m3)} m3",
            f"{'Chargeable:':<16} {_fmt_units(self.chargeable_units)} {unit}",
            f"{'Rate:':<16} {_fmt_money(self.rate_usd_per_unit)} USD/{unit}",
            f"{'Estimated:':<16} {_fmt_money(self.estimated_usd)} USD",
            "",
            "Assumptions:",
        ]
        lines.extend(f"- {item}" for item in self.assumptions)
        return "\n".join(lines)


def estimate(
    weight_kg: float,
    volume_m3: float,
    mode: str,
    zone: str | None = None,
) -> FreightEstimate:
    """Estimate illustrative China → US freight.

    Parameters
    ----------
    weight_kg:
        Actual gross weight in kilograms. Zero is allowed when volume is
        positive.
    volume_m3:
        Shipment volume in cubic meters. Zero is allowed when weight is
        positive.
    mode:
        ``"air"`` or ``"sea"`` (case-insensitive).
    zone:
        ``"west"``, ``"central"``, or ``"east"``. Omit to use the West Coast
        planning zone.

    Returns
    -------
    FreightEstimate
        Chargeable units, estimated USD, and the assumptions behind them.

    Raises
    ------
    ValueError
        If the mode, zone, or measurements are not usable.
    """

    weight = _decimal_input("weight_kg", weight_kg)
    volume = _decimal_input("volume_m3", volume_m3)
    if weight < 0:
        raise ValueError("weight_kg must be greater than or equal to 0")
    if volume < 0:
        raise ValueError("volume_m3 must be greater than or equal to 0")
    if weight == 0 and volume == 0:
        raise ValueError("weight_kg and volume_m3 cannot both be zero")

    mode_key = _normalize_mode(mode)
    zone_key, zone_was_default = _normalize_zone(zone)

    if mode_key == "air":
        actual = weight
        volumetric = volume * _CUBIC_CM_PER_M3 / AIR_CM3_PER_KG
        rate = AIR_RATES_USD_PER_KG[zone_key]
        minimum_quantity = AIR_MINIMUM_CHARGEABLE_KG
        minimum_usd = AIR_MINIMUM_USD
        unit = "kg"
        basis_sentence = _air_basis
    else:
        actual = weight / SEA_KG_PER_CBM
        volumetric = volume
        rate = SEA_RATES_USD_PER_CBM[zone_key]
        minimum_quantity = SEA_MINIMUM_CHARGEABLE_CBM
        minimum_usd = SEA_MINIMUM_USD
        unit = "CBM"
        basis_sentence = _sea_basis

    actual_q = _units(actual)
    volumetric_q = _units(volumetric)
    natural = max(actual_q, volumetric_q)
    minimum_quantity_q = _units(minimum_quantity)
    minimum_quantity_applied = natural < minimum_quantity_q
    chargeable = minimum_quantity_q if minimum_quantity_applied else natural

    rated = _money(chargeable * rate)
    minimum_charge_applied = rated < minimum_usd
    estimated = minimum_usd if minimum_charge_applied else rated

    assumptions = [
        DISCLAIMER.format(revision=RATE_TABLE_REVISION),
        _zone_sentence(
            zone_key,
            zone_was_default,
            rate,
            "kg" if mode_key == "air" else "CBM",
        ),
        basis_sentence(actual_q, volumetric_q),
    ]
    if minimum_quantity_applied:
        assumptions.append(
            "Chargeable "
            f"{unit} was raised from {_fmt_units(natural)} {unit} to the "
            f"minimum of {_fmt_units(minimum_quantity_q)} {unit}."
        )
    assumptions.append(_rating_sentence(chargeable, unit, rate, rated))
    if minimum_charge_applied:
        assumptions.append(
            f"Rated amount {_fmt_money(rated)} USD was below the minimum "
            f"charge of {_fmt_money(minimum_usd)} USD, so the estimate uses "
            "the minimum charge."
        )
    assumptions.append(
        "Chargeable quantity is rounded to 0.001 (half up) before the rate "
        "is applied. USD is rounded to 0.01 (half up)."
    )
    assumptions.append(EXCLUSIONS)

    return FreightEstimate(
        mode=mode_key,
        zone=zone_key,
        weight_kg=weight,
        volume_m3=volume,
        chargeable_units=chargeable,
        chargeable_unit=unit,
        rate_usd_per_unit=rate,
        estimated_usd=_money(estimated),
        minimum_quantity_applied=minimum_quantity_applied,
        minimum_charge_applied=minimum_charge_applied,
        rate_table_revision=RATE_TABLE_REVISION,
        assumptions=tuple(assumptions),
    )


def _decimal_input(name: str, value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{name} must be a finite number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if isinstance(value, Decimal):
        decimal = value
    else:
        decimal = Decimal(str(value))
    if not decimal.is_finite():
        raise ValueError(f"{name} must be a finite number")
    return decimal


def _normalize_mode(mode: object) -> str:
    if not isinstance(mode, str):
        raise ValueError("mode must be 'air' or 'sea'")
    normalized = mode.strip().lower()
    if normalized not in {"air", "sea"}:
        raise ValueError("mode must be 'air' or 'sea'")
    return normalized


def _normalize_zone(zone: object) -> tuple[str, bool]:
    if zone is None:
        return DEFAULT_ZONE, True
    if not isinstance(zone, str):
        raise ValueError(_zone_message(zone))
    normalized = zone.strip().lower()
    if normalized not in ZONES:
        raise ValueError(_zone_message(zone))
    return normalized, False


def _zone_message(zone: object) -> str:
    allowed = ", ".join(ZONES)
    return f"unknown zone {zone!r}; expected one of: {allowed}"


def _zone_sentence(
    zone: str,
    was_default: bool,
    rate: Decimal,
    per: str,
) -> str:
    label = ZONE_LABELS[zone]
    rate_text = f"{_fmt_money(rate)} USD per {per}"
    if was_default:
        return f"Zone defaulted to {zone} ({label}) at {rate_text}."
    return f"Zone {zone} ({label}) at {rate_text}."


def _air_basis(actual: Decimal, volumetric: Decimal) -> str:
    factor = f"{int(AIR_CM3_PER_KG):,}"
    return (
        "Air chargeable weight is the greater of actual weight and volumetric "
        f"weight at {factor} cm³ per kg. "
        + _greater_clause(
            "actual weight",
            actual,
            "kg",
            "volumetric weight",
            volumetric,
            "kg",
        )
    )


def _sea_basis(weight_cbm: Decimal, volume_cbm: Decimal) -> str:
    factor = f"{int(SEA_KG_PER_CBM):,}"
    return (
        "Sea chargeable CBM is the greater of measured volume and weight "
        f"converted at {factor} kg per CBM. "
        + _greater_clause(
            "measured volume",
            volume_cbm,
            "CBM",
            "weight-based CBM",
            weight_cbm,
            "CBM",
        )
    )


def _greater_clause(
    left_name: str,
    left: Decimal,
    left_unit: str,
    right_name: str,
    right: Decimal,
    right_unit: str,
) -> str:
    left_text = f"{_fmt_units(left)} {left_unit}"
    right_text = f"{_fmt_units(right)} {right_unit}"
    if left == right:
        sentence = f"{left_name} and {right_name} are equal at {left_text}."
    elif left > right:
        sentence = (
            f"{left_name} {left_text} is greater than {right_name} {right_text}."
        )
    else:
        sentence = (
            f"{right_name} {right_text} is greater than {left_name} {left_text}."
        )
    return sentence[0].upper() + sentence[1:]


def _rating_sentence(
    chargeable: Decimal,
    unit: str,
    rate: Decimal,
    rated: Decimal,
) -> str:
    return (
        f"Rated amount is {_fmt_units(chargeable)} {unit} × "
        f"{_fmt_money(rate)} USD/{unit} = {_fmt_money(rated)} USD."
    )
