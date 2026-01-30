import json

def update_buy_sell_ratio(file_path, factor):
    # Load the JSON data from the file
    with open(file_path, 'r') as file:
        data = json.load(file)
    
    # Update each sellMin based on the buyMax and factor
    for key, value in data.items():
        buy_max = value.get("buyMax", 0)
        value["sellMin"] = int(buy_max * factor)
    
    # Save the updated JSON back to the file
    with open(file_path, 'w') as file:
        json.dump(data, file, indent=4)

# Example usage
file_path = ""  # Path to your JSON file
factor = 1.08  # Multiplication factor
update_buy_sell_ratio(file_path, factor)