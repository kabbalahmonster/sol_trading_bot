#!/usr/bin/env python3
"""Reset cost to 0 for empty positions.

Sometimes a grid ends up with stale cost values even when balance is 0.
This script cleans that up:

  If balance == 0 -> cost = 0

USAGE:
  python cost_reset.py --file positions.json
"""

import argparse
import json


def reset_costs(file_path: str):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    for _, record in data.items():
        if isinstance(record, dict) and int(record.get("balance", 0) or 0) == 0:
            record["cost"] = 0

    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="positions.json file to clean")
    args = ap.parse_args()

    reset_costs(args.file)
    print(f"Reset costs in {args.file}")


if __name__ == "__main__":
    main()
