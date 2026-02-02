#!/usr/bin/env python3
"""Zero out buy bands in a positions JSON file ("sell-only" mode helper).

This does NOT sell anything on-chain. It only edits the JSON grid so that
no future buys will trigger, while still allowing sell logic in the bot.

It sets:
  buyMin = 0
  buyMax = 0

USAGE:
  python sellall.py --in positions.json --out positions.sellonly.json

Then (manually) swap files:
  cp positions.sellonly.json positions.json

NOTE:
- If you prefer, you can also just flip BUYS_ACTIVE=False in main.py.
  This script is helpful if you want the state embedded in the JSON.
"""

import argparse
import json


def update_json_file(input_file: str, output_file: str):
    with open(input_file, "r", encoding="utf-8") as file:
        data = json.load(file)

    for _, value in data.items():
        value["buyMax"] = 0
        value["buyMin"] = 0

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", required=True, help="Input positions.json")
    ap.add_argument("--out", required=True, help="Output file")
    args = ap.parse_args()

    update_json_file(args.infile, args.out)
    print(f"Wrote sell-only grid to {args.out}")


if __name__ == "__main__":
    main()
