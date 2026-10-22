"""Command line for the China → US freight reference estimator."""

from __future__ import annotations

import argparse
import json
import sys

from cn_us_freight.estimate import estimate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cn-us-freight",
        description=(
            "Estimate illustrative China to United States air and sea freight. "
            "Reference rates only, not carrier quotes."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    estimate_parser = subparsers.add_parser(
        "estimate",
        help="Estimate freight from weight, volume, and mode",
        description=(
            "Estimate one shipment. Weight is kilograms, volume is cubic "
            "meters, and mode is air or sea. Zone defaults to west."
        ),
    )
    estimate_parser.add_argument(
        "--weight",
        required=True,
        type=float,
        help="Actual gross weight in kilograms",
    )
    estimate_parser.add_argument(
        "--volume",
        required=True,
        type=float,
        help="Volume in cubic meters",
    )
    estimate_parser.add_argument(
        "--mode",
        required=True,
        help="Transport mode: air or sea",
    )
    estimate_parser.add_argument(
        "--zone",
        default=None,
        help="Destination zone: west, central, or east (default: west)",
    )
    estimate_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the estimate as JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return code if isinstance(code, int) else 1

    try:
        result = estimate(
            args.weight,
            args.volume,
            args.mode,
            zone=args.zone,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
