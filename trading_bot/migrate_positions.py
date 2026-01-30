import json

def merge_positions(file_a, file_b, output_file):
    # Load JSON data from files
    with open(file_a, 'r') as f:
        positions_a = json.load(f)
    with open(file_b, 'r') as f:
        positions_b = json.load(f)

    # Sort positions_b by sellMin
    positions_b_sorted = sorted(positions_b.values(), key=lambda x: x['sellMin'])

    # Track used positions in positions_b
    used_positions = set()

    # Iterate through positions_a and assign balances and costs to positions_b
    for pos_a in positions_a.values():
        balance = pos_a['balance']
        cost = pos_a['cost']
        if balance > 0 or cost > 0:
            for pos_b in positions_b_sorted:
                if pos_b['id'] not in used_positions and pos_b['sellMin'] > pos_a['sellMin']:
                    # Assign balance and cost, and mark position as used
                    positions_b[pos_b['id']]['balance'] = balance
                    positions_b[pos_b['id']]['cost'] = cost
                    used_positions.add(pos_b['id'])
                    break

    # Save the updated positions_b to the output file
    with open(output_file, 'w') as f:
        json.dump(positions_b, f, indent=4)

# Example usage
merge_positions('positions.json', 'new_positions.json', 'merged_positions.json')