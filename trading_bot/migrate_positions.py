#!/usr/bin/env python3
"""Migrate balances/costs from an active grid into a new grid.

When you update your grid (new price range, new N positions, different gain factor),
you don't want to lose track of open positions. This script moves open balances
from the old grid into the nearest-higher sellMin slot in the new grid.

Typical workflow:
1) Generate new grid to staging:
   python gen_position_json.py ... --out positions.staging.json
2) Migrate active -> staging:
   python migrate_positions.py --active positions.json --new positions.staging.json --out positions.merged.json
3) Promote merged:
   cp positions.merged.json positions.json

NOTE:
- This is a best-effort mapping. Always sanity-check the merged file.
"""

import argparse
import json

DEFAULT_ACTIVE = "positions.json"
DEFAULT_STAGING = "positions.staging.json"
DEFAULT_MERGED = "positions.merged.json"


def merge_positions(active_file, new_file, output_file):
    """Move balances/cost from active positions into a new grid.

    Strategy (same as your original):
    - Sort NEW positions by sellMin.
    - For each ACTIVE position with balance/cost, place it into the first NEW slot
      with a higher sellMin that hasn't been used.

    This helps you migrate open positions forward into an updated grid.
    """

    with open(active_file, "r", encoding="utf-8") as f:
        positions_a = json.load(f)
    with open(new_file, "r", encoding="utf-8") as f:
        positions_b = json.load(f)

    positions_b_sorted = sorted(positions_b.values(), key=lambda x: x["sellMin"])
    used_positions = set()

    for pos_a in positions_a.values():
        balance = int(pos_a.get("balance", 0) or 0)
        cost = int(pos_a.get("cost", 0) or 0)

        if balance > 0 or cost > 0:
            for pos_b in positions_b_sorted:
                if pos_b["id"] not in used_positions and pos_b["sellMin"] > pos_a["sellMin"]:
                    positions_b[pos_b["id"]]["balance"] = balance
                    positions_b[pos_b["id"]]["cost"] = cost
                    used_positions.add(pos_b["id"])
                    break

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(positions_b, f, indent=4)


def main():
    ap = argparse.ArgumentParser(description="Migrate balances/costs from active positions.json into a new grid.")
    ap.add_argument("--active", default=DEFAULT_ACTIVE, help="Existing active positions.json")
    ap.add_argument("--new", dest="newfile", default=DEFAULT_STAGING, help="New/staging positions file")
    ap.add_argument("--out", default=DEFAULT_MERGED, help="Merged output file")
    args = ap.parse_args()

    merge_positions(args.active, args.newfile, args.out)
    print(f"Merged positions written to {args.out}")


if __name__ == "__main__":
    main()
