import json

def calculate_total_balance(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    
    total_balance = sum(float(item['balance']) for item in data.values())
    total_balance /= 1_000_000_000
    print(f'Total Balance: {total_balance}')

if __name__ == "__main__":
    json_file_path = ''  # Replace with your JSON file path
    calculate_total_balance(json_file_path)