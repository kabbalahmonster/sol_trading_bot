#!/usr/bin/env python3
"""Bulk update sellMin in a positions JSON file.

This is a quick utility to change the take-profit multiplier across the whole grid.

Example:
  python update_sell.py --file positions.json --factor 1.08

Effect:
  For each position:
    sellMin = int(buyMax * factor)

NOTE:
- This does not touch balances/cost.
- Prefer generating a new staging grid via gen_position_json.py when doing major changes.
"""

import argparse
import json


def update_buy_sell_ratio(file_path: str, factor: float):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    for _, value in data.items():
        buy_max = value.get("buyMax", 0)
        value["sellMin"] = int(buy_max * factor)

    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="positions.json file to edit")
    ap.add_argument("--factor", type=float, default=1.08, help="sellMin = buyMax * factor")
    args = ap.parse_args()

    update_buy_sell_ratio(args.file, args.factor)
    print(f"Updated sellMin in {args.file} using factor={args.factor}")


if __name__ == "__main__":
    main()
