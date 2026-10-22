"""Tests for air and sea reference estimates, minima, zones, and validation."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

import pytest

from cn_us_freight import FreightEstimate, __version__, estimate
from cn_us_freight.cli import main
from cn_us_freight.rates import (
    AIR_CM3_PER_KG,
    AIR_MINIMUM_CHARGEABLE_KG,
    AIR_MINIMUM_USD,
    AIR_RATES_USD_PER_KG,
    DEFAULT_ZONE,
    RATE_TABLE_REVISION,
    SEA_KG_PER_CBM,
    SEA_MINIMUM_CHARGEABLE_CBM,
    SEA_MINIMUM_USD,
    SEA_RATES_USD_PER_CBM,
    ZONES,
)

_UNIT = Decimal("0.001")
_CENT = Decimal("0.01")


def _expected(
    weight: object,
    volume: object,
    mode: str,
    zone: str,
) -> tuple[Decimal, Decimal, bool, bool]:
    """Independent reading of the reference model documented in the README."""

    weight_dec = Decimal(str(weight))
    volume_dec = Decimal(str(volume))
    if mode == "air":
        actual = weight_dec
        volumetric = volume_dec * Decimal(1_000_000) / AIR_CM3_PER_KG
        rate = AIR_RATES_USD_PER_KG[zone]
        minimum_quantity = AIR_MINIMUM_CHARGEABLE_KG
        minimum_usd = AIR_MINIMUM_USD
    else:
        actual = weight_dec / SEA_KG_PER_CBM
        volumetric = volume_dec
        rate = SEA_RATES_USD_PER_CBM[zone]
        minimum_quantity = SEA_MINIMUM_CHARGEABLE_CBM
        minimum_usd = SEA_MINIMUM_USD

    natural = max(
        actual.quantize(_UNIT, rounding=ROUND_HALF_UP),
        volumetric.quantize(_UNIT, rounding=ROUND_HALF_UP),
    )
    minimum_quantity_q = minimum_quantity.quantize(_UNIT, rounding=ROUND_HALF_UP)
    quantity_applied = natural < minimum_quantity_q
    chargeable = minimum_quantity_q if quantity_applied else natural
    rated = (chargeable * rate).quantize(_CENT, rounding=ROUND_HALF_UP)
    charge_applied = rated < minimum_usd
    estimated = minimum_usd if charge_applied else rated
    return chargeable, estimated.quantize(_CENT, rounding=ROUND_HALF_UP), quantity_applied, charge_applied


def test_reference_table_values():
    assert RATE_TABLE_REVISION == "reference-1"
    assert DEFAULT_ZONE == "west"
    assert ZONES == ("west", "central", "east")
    assert dict(AIR_RATES_USD_PER_KG) == {
        "west": Decimal("5.50"),
        "central": Decimal("6.40"),
        "east": Decimal("7.20"),
    }
    assert dict(SEA_RATES_USD_PER_CBM) == {
        "west": Decimal("90.00"),
        "central": Decimal("120.00"),
        "east": Decimal("160.00"),
    }
    assert AIR_MINIMUM_CHARGEABLE_KG == Decimal("1")
    assert AIR_MINIMUM_USD == Decimal("45.00")
    assert SEA_MINIMUM_CHARGEABLE_CBM == Decimal("1")
    assert SEA_MINIMUM_USD == Decimal("100.00")
    assert AIR_CM3_PER_KG == Decimal("6000")
    assert SEA_KG_PER_CBM == Decimal("1000")
    assert __version__ == "0.1.0"


@pytest.mark.parametrize(
    ("weight", "volume", "mode", "zone"),
    [
        (80, Decimal("0.3"), "air", "east"),
        (12, Decimal("0.2"), "air", "west"),
        (Decimal("0.4"), Decimal("0.002"), "air", "west"),
        (5, Decimal("0.01"), "air", "central"),
        (400, Decimal("3.2"), "sea", "west"),
        (2800, Decimal("1.5"), "sea", "central"),
        (200, Decimal("0.4"), "sea", "east"),
        (100, 1, "sea", "west"),
        (0, 2, "sea", "east"),
        (10, 0, "air", "central"),
        (Decimal("8.180"), 0, "air", "west"),
        (Decimal("8.181"), 0, "air", "west"),
    ],
)
def test_formula_matches_reference_model(weight, volume, mode, zone):
    result = estimate(weight, volume, mode, zone=zone)
    chargeable, estimated, quantity_applied, charge_applied = _expected(
        weight, volume, mode, zone
    )
    assert result.chargeable_units == chargeable
    assert result.estimated_usd == estimated
    assert result.minimum_quantity_applied is quantity_applied
    assert result.minimum_charge_applied is charge_applied
    assert result.mode == mode
    assert result.zone == zone
    assert isinstance(result, FreightEstimate)


def test_air_actual_weight_wins_over_volume():
    result = estimate(80, 0.3, "air", zone="east")
    assert result.chargeable_unit == "kg"
    assert result.chargeable_units == Decimal("80.000")
    assert result.rate_usd_per_unit == Decimal("7.20")
    assert result.estimated_usd == Decimal("576.00")
    assert result.minimum_quantity_applied is False
    assert result.minimum_charge_applied is False
    text = " ".join(result.assumptions)
    assert "Actual weight 80.000 kg is greater than volumetric weight 50.000 kg" in text
    assert "not a carrier quote" in text


def test_air_volumetric_weight_wins_and_rounds_to_cents():
    result = estimate(12, 0.2, "air", zone="west")
    assert result.chargeable_units == Decimal("33.333")
    assert result.estimated_usd == Decimal("183.33")
    text = " ".join(result.assumptions)
    assert "Volumetric weight 33.333 kg is greater than actual weight 12.000 kg" in text
    assert "33.333 kg × 5.50 USD/kg = 183.33 USD" in text


def test_air_half_up_on_chargeable_weight():
    result = estimate(0, Decimal("0.060003"), "air", zone="east")
    assert result.chargeable_units == Decimal("10.001")
    assert result.estimated_usd == Decimal("72.01")
    assert result.minimum_quantity_applied is False
    assert result.minimum_charge_applied is False


def test_air_tiny_shipment_applies_both_minima():
    result = estimate(0.4, 0.002, "air")
    assert result.zone == "west"
    assert result.chargeable_units == Decimal("1.000")
    assert result.estimated_usd == Decimal("45.00")
    assert result.minimum_quantity_applied is True
    assert result.minimum_charge_applied is True
    text = " ".join(result.assumptions)
    assert "raised from 0.400 kg to the minimum of 1.000 kg" in text
    assert "below the minimum charge of 45.00 USD" in text
    assert "Zone defaulted to west" in text


def test_air_minimum_charge_without_quantity_floor():
    result = estimate(5, 0.01, "air", zone="central")
    assert result.chargeable_units == Decimal("5.000")
    assert result.estimated_usd == Decimal("45.00")
    assert result.minimum_quantity_applied is False
    assert result.minimum_charge_applied is True


def test_air_minimum_charge_uses_rounded_dollars():
    below = estimate(Decimal("8.180"), 0, "air", zone="west")
    assert below.minimum_charge_applied is True
    assert below.estimated_usd == Decimal("45.00")

    rounded_up = estimate(Decimal("8.181"), 0, "air", zone="west")
    assert rounded_up.chargeable_units == Decimal("8.181")
    assert rounded_up.minimum_charge_applied is False
    assert rounded_up.estimated_usd == Decimal("45.00")
    assert "8.181 kg × 5.50 USD/kg = 45.00 USD" in " ".join(rounded_up.assumptions)


def test_sea_volume_wins():
    result = estimate(400, 3.2, "sea", zone="west")
    assert result.chargeable_unit == "CBM"
    assert result.chargeable_units == Decimal("3.200")
    assert result.estimated_usd == Decimal("288.00")
    assert result.minimum_quantity_applied is False
    assert result.minimum_charge_applied is False
    assert "Measured volume 3.200 CBM is greater than weight-based CBM 0.400 CBM" in " ".join(
        result.assumptions
    )


def test_sea_weight_wins():
    result = estimate(2800, 1.5, "sea", zone="central")
    assert result.chargeable_units == Decimal("2.800")
    assert result.rate_usd_per_unit == Decimal("120.00")
    assert result.estimated_usd == Decimal("336.00")
    assert "Weight-based CBM 2.800 CBM is greater than measured volume 1.500 CBM" in " ".join(
        result.assumptions
    )


def test_sea_east_minimum_quantity_only():
    result = estimate(200, 0.4, "sea", zone="east")
    assert result.chargeable_units == Decimal("1.000")
    assert result.estimated_usd == Decimal("160.00")
    assert result.minimum_quantity_applied is True
    assert result.minimum_charge_applied is False
    assert "raised from 0.400 CBM to the minimum of 1.000 CBM" in " ".join(result.assumptions)


def test_sea_west_both_minima():
    result = estimate(200, 0.4, "Sea", zone="WEST")
    assert result.mode == "sea"
    assert result.zone == "west"
    assert result.chargeable_units == Decimal("1.000")
    assert result.estimated_usd == Decimal("100.00")
    assert result.minimum_quantity_applied is True
    assert result.minimum_charge_applied is True


def test_sea_west_exact_cbm_minimum_charge_only():
    result = estimate(100, 1, "sea", zone="west")
    assert result.chargeable_units == Decimal("1.000")
    assert result.estimated_usd == Decimal("100.00")
    assert result.minimum_quantity_applied is False
    assert result.minimum_charge_applied is True
    assert "defaulted" not in " ".join(result.assumptions)


def test_equal_air_bases_are_described():
    result = estimate(50, 0.3, "air", zone="west")
    assert result.chargeable_units == Decimal("50.000")
    assert result.estimated_usd == Decimal("275.00")
    assert "Actual weight and volumetric weight are equal at 50.000 kg" in " ".join(
        result.assumptions
    )


def test_zones_change_the_rate_for_the_same_cargo():
    common = dict(weight_kg=20, volume_m3=0.05)
    air = [estimate(mode="air", zone=zone, **common) for zone in ZONES]
    sea = [estimate(mode="sea", zone=zone, volume_m3=2, weight_kg=100) for zone in ZONES]
    assert [item.estimated_usd for item in air] == [
        Decimal("110.00"),
        Decimal("128.00"),
        Decimal("144.00"),
    ]
    assert [item.estimated_usd for item in sea] == [
        Decimal("180.00"),
        Decimal("240.00"),
        Decimal("320.00"),
    ]
    assert air[0].chargeable_units == air[1].chargeable_units == air[2].chargeable_units


def test_zero_weight_uses_volume_and_zero_volume_uses_weight():
    by_volume = estimate(0, 2, "sea", zone="west")
    assert by_volume.chargeable_units == Decimal("2.000")
    assert by_volume.estimated_usd == Decimal("180.00")

    by_weight = estimate(10, 0, "air", zone="west")
    assert by_weight.chargeable_units == Decimal("10.000")
    assert by_weight.estimated_usd == Decimal("55.00")


def test_assumptions_always_state_reference_and_exclusions():
    result = estimate(10, 0.05, " AIR ", zone=" east ")
    assert result.mode == "air"
    assert result.zone == "east"
    assert result.assumptions[0].startswith("Illustrative reference rates")
    assert "not a carrier quote" in result.assumptions[0]
    assert result.rate_table_revision == "reference-1"
    assert any("duties" in line for line in result.assumptions)
    assert "minimum" not in " ".join(result.assumptions).lower()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"weight_kg": -1, "volume_m3": 1, "mode": "air"},
        {"weight_kg": 1, "volume_m3": -0.01, "mode": "sea"},
        {"weight_kg": 0, "volume_m3": 0, "mode": "air"},
        {"weight_kg": "10", "volume_m3": 1, "mode": "air"},
        {"weight_kg": True, "volume_m3": 1, "mode": "air"},
        {"weight_kg": False, "volume_m3": 1, "mode": "sea"},
        {"weight_kg": float("nan"), "volume_m3": 1, "mode": "air"},
        {"weight_kg": 1, "volume_m3": float("inf"), "mode": "sea"},
        {"weight_kg": Decimal("NaN"), "volume_m3": 1, "mode": "air"},
        {"weight_kg": 1, "volume_m3": 1, "mode": "rail"},
        {"weight_kg": 1, "volume_m3": 1, "mode": ""},
        {"weight_kg": 1, "volume_m3": 1, "mode": None},
        {"weight_kg": 1, "volume_m3": 1, "mode": "air", "zone": "hawaii"},
        {"weight_kg": 1, "volume_m3": 1, "mode": "air", "zone": ""},
        {"weight_kg": 1, "volume_m3": 1, "mode": "air", "zone": "west coast"},
        {"weight_kg": 1, "volume_m3": 1, "mode": "sea", "zone": 1},
    ],
)
def test_validation_rejects_unusable_input(kwargs):
    with pytest.raises(ValueError):
        estimate(**kwargs)


def test_validation_messages_name_the_problem():
    with pytest.raises(ValueError, match="weight_kg"):
        estimate(-1, 1, "air")
    with pytest.raises(ValueError, match="volume_m3"):
        estimate(1, -1, "sea")
    with pytest.raises(ValueError, match="cannot both be zero"):
        estimate(0, 0, "air")
    with pytest.raises(ValueError, match="mode"):
        estimate(1, 1, "truck")
    with pytest.raises(ValueError, match="unknown zone"):
        estimate(1, 1, "air", zone="hawaii")


def test_cli_text_and_json(capsys):
    assert (
        main(
            [
                "estimate",
                "--weight",
                "80",
                "--volume",
                "0.3",
                "--mode",
                "air",
                "--zone",
                "east",
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "Estimated:       576.00 USD" in text
    assert "not a carrier quote" in text

    assert (
        main(
            [
                "estimate",
                "--weight",
                "80",
                "--volume",
                "0.3",
                "--mode",
                "air",
                "--zone",
                "east",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["estimated_usd"] == 576.0
    assert payload["chargeable_units"] == 80.0
    assert payload["chargeable_unit"] == "kg"
    assert payload["zone"] == "east"
    assert payload["minimum_charge_applied"] is False
    assert payload["rate_table_revision"] == "reference-1"
    assert isinstance(payload["assumptions"], list)


def test_cli_validation_and_usage(capsys):
    assert main(["estimate", "--weight", "-1", "--volume", "1", "--mode", "sea"]) == 2
    error = capsys.readouterr().err
    assert "weight_kg" in error

    assert main(["estimate", "--weight", "1", "--volume", "1", "--mode", "rail"]) == 2
    assert "mode" in capsys.readouterr().err

    assert main(["estimate", "--weight", "1", "--volume", "1"]) == 2
    assert main(["--help"]) == 0
    assert "cn-us-freight" in capsys.readouterr().out


def _console_scripts():
    try:
        return importlib.metadata.entry_points(group="console_scripts")
    except TypeError:
        # Python 3.9 has no selection arguments on entry_points().
        return importlib.metadata.entry_points()["console_scripts"]


def test_console_script_entry_point_and_module():
    matches = [item for item in _console_scripts() if item.name == "cn-us-freight"]
    assert len(matches) == 1
    assert matches[0].value == "cn_us_freight.cli:main"

    module = subprocess.run(
        [
            sys.executable,
            "-m",
            "cn_us_freight",
            "estimate",
            "--weight",
            "400",
            "--volume",
            "3.2",
            "--mode",
            "sea",
            "--zone",
            "west",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(module.stdout)["estimated_usd"] == 288.0

    script = Path(sys.executable).with_name("cn-us-freight")
    assert script.is_file()
    installed = subprocess.run(
        [
            str(script),
            "estimate",
            "--weight",
            "200",
            "--volume",
            "0.4",
            "--mode",
            "sea",
            "--zone",
            "east",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(installed.stdout)
    assert payload["chargeable_unit"] == "CBM"
    assert payload["chargeable_units"] == 1.0
    assert payload["estimated_usd"] == 160.0
    assert payload["minimum_quantity_applied"] is True
