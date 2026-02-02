#!/usr/bin/env python3
"""Sum total token balance across all grid positions.

This reads a positions JSON file and sums the `balance` fields.
Useful for quickly seeing how much of the token you are holding.

USAGE:
  python total_positions.py --file positions.json

NOTES:
- `balance` in positions.json is token units in the mint's base units (not SOL).
- This script currently divides by 1e9 (legacy assumption). Adjust if your token decimals differ.
"""

import argparse
import json


def calculate_total_balance(file_path: str, divisor: float = 1_000_000_000):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    total_balance = sum(float(item.get("balance", 0) or 0) for item in data.values())
    total_balance /= divisor
    print(f"Total Balance: {total_balance}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="positions.json file")
    ap.add_argument("--divisor", type=float, default=1_000_000_000, help="Divide raw balances by this")
    args = ap.parse_args()

    calculate_total_balance(args.file, divisor=args.divisor)


if __name__ == "__main__":
    main()
