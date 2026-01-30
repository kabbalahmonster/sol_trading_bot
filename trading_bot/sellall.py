import json

def update_json_file(input_file, output_file):
    # Open and load the JSON file
    with open(input_file, 'r') as file:
        data = json.load(file)
    
    # Update buyMax and buyMin values to 0
    for key, value in data.items():
        value['buyMax'] = 0
        value['buyMin'] = 0
    
    # Save the updated data to a new file
    with open(output_file, 'w') as file:
        json.dump(data, file, indent=4)

# Specify the input and output file paths
input_file = ''  # Replace with your input file path
output_file = ''  # Replace with your desired output file path

# Run the function
update_json_file(input_file, output_file)