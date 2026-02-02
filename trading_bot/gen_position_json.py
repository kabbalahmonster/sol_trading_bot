import argparse
import json
import os

# Default filenames live next to main.py (same folder)
DEFAULT_ACTIVE = "positions.json"
DEFAULT_STAGING = "positions.staging.json"

stoploss_factor = 1.1
gain_factor = 1.08


def calculate_positions(high, low, n=20):
    step = (low / high) ** (1 / (n - 1))
    levels = [round(high * (step ** i)) for i in range(n)]
    levels.reverse()
    print(levels)
    return levels


def generate_positions(levels, gain_factor=1.08, stoploss_factor=1.2):
    positions = {}
    for i, level in enumerate(levels):
        position_id = f"{i + 1}"  # ID starts from 1
        buy_min = levels[i - 1] if i > 0 else 0  # Previous level or 0 for the first level
        buy_max = level  # Current level
        sell_min = round(buy_max * gain_factor)  # Current level * gain
        stoploss = round(buy_max / stoploss_factor)  # Calculate stoploss

        positions[position_id] = {
            "id": position_id,
            "balance": 0,
            "buyMax": buy_max,
            "buyMin": buy_min,
            "sellMin": sell_min,
            "cost": 0,
            "stoploss": stoploss,
        }
    return positions


def save_positions_to_file(positions, out_path):
    with open(out_path, "w", encoding="utf-8") as file:
        json.dump(positions, file, indent=4)
    print(f"Positions data saved to {out_path}")


def main():
    ap = argparse.ArgumentParser(description="Generate grid positions JSON.")
    ap.add_argument("--high", type=int, default=120000)
    ap.add_argument("--low", type=int, default=1000)
    ap.add_argument("--n", type=int, default=72)
    ap.add_argument("--out", default=DEFAULT_STAGING, help="Output filename (default: positions.staging.json)")
    ap.add_argument("--gain", type=float, default=gain_factor, help="sellMin = buyMax * gain")
    ap.add_argument("--stoploss-factor", type=float, default=stoploss_factor, help="stoploss = buyMax / stoploss_factor")

    args = ap.parse_args()

    levels = calculate_positions(args.high, args.low, args.n)
    positions = generate_positions(levels, gain_factor=args.gain, stoploss_factor=args.stoploss_factor)

    out_path = args.out
    # keep paths relative to the script's working dir (same folder as main.py)
    save_positions_to_file(positions, out_path)


if __name__ == "__main__":
    main()
