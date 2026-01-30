import json

# Function to reset "cost" to 0 where "balance" is 0
def reset_costs(file_path):
    # Step 1: Read the JSON file
    with open(file_path, 'r') as file:
        data = json.load(file)

    # Step 2: Iterate through the dictionary values
    for key, record in data.items():
        if isinstance(record, dict) and record.get("balance") == 0:
            record["cost"] = 0

    # Step 3: Save the updated dataset back to the JSON file
    with open(file_path, 'w') as file:
        json.dump(data, file, indent=4)

# Example usage
file_path = ""  # Replace with your JSON file path
reset_costs(file_path)