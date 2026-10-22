# cn-us-freight

Planning estimates for **China → United States** air and sea freight. Give the library a weight and a volume. It returns chargeable units, an estimated USD amount, and the assumptions behind that amount.

The rates live in this repository as a **reference table**. They are rounded teaching defaults for small wholesale and e-commerce planning. They are not a carrier quote, a tariff, a surcharge schedule, or an offer to carry freight. Get a real quote before you book.

## Install

Python 3.9 or newer.

From a checkout of this repository:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"   # library, CLI, and pytest
```

Use `pip install -e .` if you only want the `cn-us-freight` command and the `cn_us_freight` package.

The package is not published to a package index. Install it from this repository.

## Command line

```bash
cn-us-freight estimate --weight 80 --volume 0.3 --mode air --zone east
```

```text
China → US freight reference estimate
Rate table: reference-1 (illustrative, not a carrier quote)

Mode:            air
Zone:            east
Actual weight:   80.000 kg
Volume:          0.300 m3
Chargeable:      80.000 kg
Rate:            7.20 USD/kg
Estimated:       576.00 USD

Assumptions:
- Illustrative reference rates from table reference-1, not a carrier quote or booking.
- Zone east (US East Coast planning zone) at 7.20 USD per kg.
- Air chargeable weight is the greater of actual weight and volumetric weight at 6,000 cm³ per kg. Actual weight 80.000 kg is greater than volumetric weight 50.000 kg.
- Rated amount is 80.000 kg × 7.20 USD/kg = 576.00 USD.
- Chargeable quantity is rounded to 0.001 (half up) before the rate is applied. USD is rounded to 0.01 (half up).
- Excludes customs duties, taxes, insurance, pickup, origin and destination terminal fees, and final-mile delivery.
```

Add `--json` for a machine-readable object (`chargeable_units`, `estimated_usd`, `assumptions`, and the flags below).

| Flag | Required | Meaning |
| --- | --- | --- |
| `--weight` | yes | Actual gross weight in kilograms |
| `--volume` | yes | Volume in cubic meters |
| `--mode` | yes | `air` or `sea` |
| `--zone` | no | `west`, `central`, or `east`. Defaults to `west` |
| `--json` | no | Print JSON instead of text |

`mode` and `zone` are case-insensitive. Exit code `0` means an estimate was printed. Exit code `2` means the arguments were missing or rejected. Library validation errors look like `error: weight_kg must be greater than or equal to 0` on stderr.

## Python

```python
from cn_us_freight import estimate

result = estimate(weight_kg=12, volume_m3=0.2, mode="air", zone="west")
result.chargeable_units   # Decimal('33.333')  kilograms
result.chargeable_unit    # 'kg'
result.estimated_usd      # Decimal('183.33')
result.assumptions        # tuple[str, ...]
result.to_dict()          # JSON-ready floats, strings, and bools
```

`estimate(weight_kg, volume_m3, mode, zone=None)` raises `ValueError` for an unknown mode or zone, a non-numeric measurement, NaN or infinity, a negative measurement, or a shipment that is both 0 kg and 0 m³. Money and chargeable quantity stay `Decimal` so cent rounding does not depend on binary floats. `str(result)` is the same layout as the text CLI.

Omit `zone` to use `west`. The assumptions say when that default was applied.

## How the estimate is calculated

Add the cartons up yourself, then pass the totals:

```text
volume_m3 = length_cm × width_cm × height_cm × pieces / 1_000_000
weight_kg = kilograms per piece × pieces
```

### Air

Chargeable kilograms are the greater of:

- actual kilograms
- volumetric kilograms = `volume_m3 × 1,000,000 / 6,000`

`6,000` cm³ per kg is the usual international air volumetric factor. A light, bulky carton is billed on volume. A dense carton is billed on the scale weight.

### Sea

Chargeable CBM (cubic meters) are the greater of:

- measured volume in m³
- weight-based CBM = `weight_kg / 1,000`

This model uses weight-or-measurement at 1,000 kg per CBM.

### Floors in this reference model

These floors are part of the model, not a claim about what any carrier files:

| Mode | Minimum chargeable | Minimum charge |
| --- | --- | --- |
| air | 1 kg | 45 USD |
| sea | 1 CBM | 100 USD |

The quantity floor is applied after each basis is rounded. The dollar floor is applied after `chargeable × rate` is rounded to the cent. If that rounded amount is already at least the dollar floor, the minimum charge is not flagged.

### Rounding

Half up, in this order:

1. Round actual and volumetric bases to 0.001.
2. Keep the greater one.
3. Raise it to the quantity floor when it is below that floor.
4. Multiply by the zone rate.
5. Round to 0.01 USD.
6. Replace the rated amount with the dollar floor when it is still below that floor.

### Zones

| Zone | Planning label | Air USD/kg | Sea USD/CBM |
| --- | --- | --- | --- |
| `west` | US West Coast | 5.50 | 90.00 |
| `central` | US central / Gulf | 6.40 | 120.00 |
| `east` | US East Coast | 7.20 | 160.00 |

Table id: `reference-1`. West is the default because that is the planning zone used when you do not pass one. These labels are not a carrier zone map.

Same cargo, different zone (20 kg, 0.05 m³, air): west 110.00 USD, central 128.00 USD, east 144.00 USD.

## Worked examples

| Weight kg | Volume m³ | Mode | Zone | Chargeable | USD | What bound |
| --- | --- | --- | --- | --- | --- | --- |
| 80 | 0.30 | air | east | 80 kg | 576.00 | actual weight (volume is only 50 kg) |
| 12 | 0.20 | air | west | 33.333 kg | 183.33 | volumetric weight |
| 0.4 | 0.002 | air | west (default) | 1 kg | 45.00 | 1 kg floor, then the 45 USD floor |
| 5 | 0.01 | air | central | 5 kg | 45.00 | dollar floor only (rated 32.00 USD) |
| 400 | 3.2 | sea | west | 3.2 CBM | 288.00 | measured volume |
| 2800 | 1.5 | sea | central | 2.8 CBM | 336.00 | weight at 1,000 kg per CBM |
| 200 | 0.4 | sea | east | 1 CBM | 160.00 | 1 CBM floor; east rate is above 100 USD |
| 200 | 0.4 | sea | west | 1 CBM | 100.00 | 1 CBM floor and the 100 USD floor |
| 100 | 1 | sea | west | 1 CBM | 100.00 | dollar floor only |

`tests/test_estimate.py` locks this table and the rounding boundary where 8.180 kg of west-coast air (44.99 USD) takes the 45 USD floor, and 8.181 kg rates to 45.00 USD without the floor flag.

## What is left out

The assumptions on every result repeat the exclusions:

- customs duties, taxes, and brokerage
- insurance
- pickup and final-mile delivery
- origin and destination terminal, documentation, and handling fees
- separate fuel, security, or peak surcharges (the table is a single USD rate per chargeable unit)
- transit time
- dangerous goods, oversize pieces, residential delivery, and remote postal codes

A useful comparison is air versus sea for a weight and cube you already know. It is not a booking.

## Updating the rates

Rates, floors, and conversion factors are constants in [`src/cn_us_freight/rates.py`](src/cn_us_freight/rates.py). Nothing in this project downloads prices.

1. Edit the figures you want. Keep them as `Decimal` values.
2. Keep `west`, `central`, and `east` in both the air and sea tables, in that order. Importing the module rejects a missing zone, a non-Decimal rate, or a non-positive rate.
3. Change `RATE_TABLE_REVISION` when the numbers change. That id marks an edit of this file. It is not a market date and it does not mean a carrier published those numbers.
4. Update `test_reference_table_values` and any example amounts in `tests/test_estimate.py`, plus the tables in this README.
5. Run `pytest`.

## Development

```bash
pytest
```

GitHub Actions installs the package with `pip install -e ".[dev]"` and runs `pytest` on Python 3.9 and 3.12, then runs one CLI smoke command.

The console script entry point is `cn-us-freight = cn_us_freight.cli:main`. `python -m cn_us_freight` calls the same function.

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 huhengheng-sudo.
