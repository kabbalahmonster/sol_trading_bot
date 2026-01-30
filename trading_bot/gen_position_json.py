import json

# File path for the positions JSON file
POSITIONS_FILE = "positions.json"

stoploss_factor = 1.1
gain_factor = 1.08

def calculate_positions(high, low, n=20):
    step = (low / high) ** (1 / (n - 1))
    levels = [round(high * (step ** i)) for i in range(n)]
    levels.reverse()
    print(levels)
    return levels

def generate_positions(levels, stoploss_factor=1.2):
    positions = {}
    for i, level in enumerate(levels):
        position_id = f"{i + 1}"  # ID starts from 1
        buy_min = levels[i - 1] if i > 0 else 0  # Previous level or 0 for the first level
        buy_max = level  # Current level
        sell_min = round(buy_max * gain_factor)  # Current level * 1.08
        stoploss = round(buy_max / stoploss_factor)  # Calculate stoploss

        positions[position_id] = {
            "id": position_id,
            "balance": 0,
            "buyMax": buy_max,
            "buyMin": buy_min,
            "sellMin": sell_min,
            "cost": 0,  # Initialize cost field
            "stoploss": stoploss  # Add stoploss field
        }
    return positions

def save_positions_to_file(positions):
    with open(POSITIONS_FILE, "w") as file:
        json.dump(positions, file, indent=4)
    print(f"Positions data saved to {POSITIONS_FILE}")

# Main function
def main():
    high = 120000
    low = 1000
    n = 72

    # Calculate levels
    levels = calculate_positions(high, low, n)

    # Generate positions based on levels
    positions = generate_positions(levels)

    # Save positions to file
    save_positions_to_file(positions)

if __name__ == "__main__":
    main()