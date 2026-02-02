import json
import time
from datetime import datetime
from dotenv import load_dotenv
from jup_python_sdk.clients.ultra_api_client import UltraApiClient
from jup_python_sdk.models.ultra_api.ultra_order_request_model import UltraOrderRequest

from jup_python_sdk.models.ultra_api.ultra_execute_request_model import UltraExecuteRequest
import requests

import random

import sys
import os

class Tee:
    def __init__(self, filename, mode="w"):
        self.terminal = sys.stdout
        self.logfile = open(filename, mode)

    def write(self, message):
        self.terminal.write(message)
        try:
            self.logfile.write(message)
        except OSError as e:
            # Handle specific errors, such as disk space issues
            if e.errno == 28:  # Error code 28: No space left on device
                self.terminal.write("Warning: Unable to write to logfile due to insufficient disk space.\n")
            else:
                self.terminal.write(f"Warning: An error occurred while writing to logfile: {e}\n")

    def flush(self):
        self.terminal.flush()
        self.logfile.flush()

# Ensure the logs folder exists
os.makedirs("logs", exist_ok=True)

# Generate a new numbered log file
def get_new_log_file():
    log_number = 1
    while os.path.exists(f"logs/log{log_number}.txt"):
        log_number += 1
    return f"logs/log{log_number}.txt"

# Redirect stdout to both terminal and the new log file
log_file = get_new_log_file()
sys.stdout = Tee(log_file)


# ------------------------------
# Configuration / Environment
# ------------------------------
# Copy .env.example -> .env and fill in values.
#
# The Jupiter Ultra SDK uses PRIVATE_KEY for signing.
# - PRIVATE_KEY can be base58 OR a uint8 array string.
# - Optional: JUPITER_API_KEY enables the non-lite endpoint.

# Load .env from the current working directory (repo assumes you run from trading_bot/)
load_dotenv()

# Optional: if JUPITER_API_KEY is set, UltraApiClient will use https://api.jup.ag
# otherwise it defaults to https://lite-api.jup.ag
client = UltraApiClient(api_key=os.getenv("JUPITER_API_KEY") or None)

# Define boolean flags to control functionality
SELLS_ACTIVE = True
BUYS_ACTIVE = True
STOPLOSS_ACTIVE = False

# Max simultaneously open positions (grid slots with balance>0)
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "20"))

# Quote endpoint base (no-key default)
JUP_QUOTE_BASE = os.getenv("JUP_QUOTE_BASE", "https://lite-api.jup.ag").rstrip("/")

# Token config
ticker = os.getenv("TICKER", "")  # TOKEN TICKER (for logs only)
# NOTE: tokenId should be a Solana *mint address* (e.g. endswith 'pump' for pump.fun coins)
tokenId = os.getenv("TOKEN_MINT", "")  # TOKEN MINT

# Well-known mints
sol = "So11111111111111111111111111111111111111112"  # WSOL

# Position sizing for buys (lamports). Default 0.04 SOL
amount = int(os.getenv("AMOUNT_LAMPORTS", "40000000"))


def getQuote(id, amount=1000000, max_retries=5, backoff_factor=1):
    """Get a Jupiter quote for swapping token->WSOL.

    Returns outAmount (string/number) or None.

    Notes:
    - Uses Jupiter Lite by default (no API key required).
    - Adds small randomness to the amount to reduce cached responses.
    """
    amount += random.randint(-1000, 1000)  # Add randomness to the amount

    url = f"{JUP_QUOTE_BASE}/swap/v1/quote?inputMint={id}&outputMint={sol}&amount={amount}"

    headers = {'Accept': 'application/json'}
    # Optional API key (not required)
    if os.getenv("JUPITER_API_KEY"):
        headers["x-api-key"] = os.getenv("JUPITER_API_KEY")
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=10)  # Set a timeout for the request
            
            # Check if the response is successful
            if response.status_code != 200:
                print(f"Error: API request failed with status code {response.status_code}")
                print(f"Response content: {response.text}")
                return None

            data = response.json()
            if not data or 'outAmount' not in data:
                print("Error: API returned an invalid or empty response.")
                return None

            #print("----DEBUG DATA DUMP----")
            #print(data)
            return data['outAmount']
        
        except requests.exceptions.Timeout:
            print(f"Timeout occurred on attempt {attempt + 1}. Retrying...")
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error on attempt {attempt + 1}: {e}. Retrying...")
        except json.JSONDecodeError:
            print("Error: Failed to decode JSON response.")
            print(f"Response content: {response.text}")
            return None
        
        # Wait before retrying (exponential backoff)
        time.sleep(backoff_factor * (2 ** attempt))
    
    print("Error: Max retries reached. Unable to fetch quote.")
    return None

def getMcap(id, max_retries=5, backoff_factor=1):
    url = f"https://lite-api.jup.ag/ultra/v1/search?query={id}"
    headers = {'Accept': 'application/json'}
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=10)  # Set a timeout for the request
            
            # Check if the response is successful
            if response.status_code != 200:
                print(f"Error: API request failed with status code {response.status_code}")
                print(f"Response content: {response.text}")
                return None

            data = response.json()
            if not data:
                print("Error: API returned an empty response.")
                return None

            print("symbol:", data[0]['symbol'])
            return data[0]['mcap']
        
        except requests.exceptions.Timeout:
            print(f"Timeout occurred on attempt {attempt + 1}. Retrying...")
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error on attempt {attempt + 1}: {e}. Retrying...")
        except json.JSONDecodeError:
            print("Error: Failed to decode JSON response.")
            print(f"Response content: {response.text}")
            return None
        
        # Wait before retrying (exponential backoff)
        time.sleep(backoff_factor * (2 ** attempt))
    
    print("Error: Max retries reached. Unable to fetch market cap.")
    return None


    
def place_order(input_mint, output_mint, amount):
    order_request = UltraOrderRequest(
        input_mint=input_mint,
        output_mint=output_mint,
        amount=amount,
        taker=client._get_public_key()
    )
    tokens = 0
    cost = 0
    try:
        client_response = client.order_and_execute(order_request)
        #print(client.order_and_execute(order_request))
        signature = str(client_response["signature"])

        print("Order and Execute API Response:")
        print(f"  - Status: {client_response.get('status')}")
        if client_response.get("status") == "Failed":
            print(f"  - Code: {client_response.get('code')}")
            print(f"  - Error: {client_response.get('error')}")
        else:
            tokens = client_response["totalOutputAmount"]
            cost = client_response["totalInputAmount"]    
        print(f"  - Input Amount (Cost): {cost}")
        print(f"  - Output Amount: {tokens}")
        print(f"  - Transaction Signature: {signature}")
        print(f"  - View on Solscan: https://solscan.io/tx/{signature}")

    except Exception as e:
        print("Error occurred while processing the swap:", str(e))

    return tokens, cost


#=====================================================================================================

    
def execute_sell(input_mint, output_mint, amount, pos_cost):
    order_request = UltraOrderRequest(
        input_mint=input_mint,
        output_mint=output_mint,
        amount=amount,
        taker=client._get_public_key()
    )
    tokens = 0
    cost = 0
    try:
        order_response = client.order(order_request)


        print("Order API Response:")
        print(f"  - Status: {order_response.get('status')}")
        if order_response.get("status") == "Failed":
            print(f"  - Code: {order_response.get('code')}")
            print(f"  - Error: {order_response.get('error')}")

        print(order_response)

        should_order = False       
        min_sell_req = int(pos_cost) + 2000000

        if int(order_response["otherAmountThreshold"]) > min_sell_req and int(order_response["outAmount"]) > min_sell_req:
            should_order = True
            print("Proceeding to execute the order...")
        else:           
            print("Order conditions not met; skipping execution.")



        if should_order:
            request_id = order_response["requestId"]
            signed_transaction = client._sign_base64_transaction(
                order_response["transaction"]
            )

            execute_request = UltraExecuteRequest(
                request_id=request_id,
                signed_transaction=client._serialize_versioned_transaction(
                    signed_transaction
                ),
            )


            execute_response = client.execute(execute_request)
            #signature = str(client_response["signature"])


            print("Execute API Response:")
            print(execute_response)

            signature = str(execute_response["signature"])

            if not execute_response.get("status") == "Failed":
                tokens = execute_response["totalOutputAmount"]
                cost = execute_response["totalInputAmount"]

            print(f"  - Input Amount (Cost): {cost}")
            print(f"  - Output Amount: {tokens}")
            print(f"  - Transaction Signature: {signature}")
            print(f"  - View on Solscan: https://solscan.io/tx/{signature}")

    except Exception as e:
        print("Error occurred while processing the swap:", str(e))

    return tokens, cost



#=====================================================================================================

def save_json(data, filename="positions.json"):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)


def load_json(filename="positions.json"):
    with open(filename, "r") as f:
        return json.load(f)




def main():
    print("Running task...")
    positions = load_json()
    runCnt = 0

    # Initialize total counters for the session
    total_buys = 0
    total_sells = 0
    total_profit = 0  # Initialize total profit tracker
    active_positions = MAX_POSITIONS

    try:
        while True:
            currentMcap = getQuote(tokenId)
            buy_count = 0
            sell_count = 0
            non_zero_positions = 0
            total_positions = len(positions)

            print("-------------------------------")
            print("             Iteration ", runCnt)
            print("-------------------------------")
            if currentMcap is None:
                print("Skipping this iteration due to API error.")
                time.sleep(5)
                continue

            currentMcap = int(currentMcap)  # Convert to integer after ensuring it's not None
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"Timestamp: {current_time}")
            print(f"Current Price in Sol: {currentMcap}")
            print("---------------------------------")

            for key, position in positions.items():
                position["balance"] = int(position["balance"]) if isinstance(position["balance"], str) else position["balance"]
                position["cost"] = int(position["cost"]) if isinstance(position["cost"], str) else position["cost"]

                if position["balance"] > 0:
                    non_zero_positions += 1
                    # Include sell target (sellMin) and stoploss in the report
                    print(f"Position {key:<2}  - Current Balance: {position['balance']:<10}  Sell Target: {position['sellMin']}  Stop Loss: {position['stoploss']}")

                # Check stop-loss condition
                if STOPLOSS_ACTIVE and position["balance"] > 0 and currentMcap < position["stoploss"]:
                    print(f"  - Stop Loss Triggered for position {key}: Current Price ({currentMcap}) is below Stop Loss ({position['stoploss']}). Selling...")
                    sell_amount = int(position["balance"] * 0.99)  # Sell 95% of the position
                    #sell_amount = int(position["balance"])
                    tokens_received, _ = place_order(tokenId, sol, sell_amount)

                    # Calculate loss
                    loss = int(position["cost"]) - int(tokens_received)
                    total_profit -= loss  # Deduct loss from total profit

                    # Reset balance and cost
                    position["balance"] = 0
                    position["cost"] = 0
                    save_json(positions)

                    print(f"  - Sold 99% of position {key} (Amount: {sell_amount})")
                    print(f"  - Tokens Received: {tokens_received}")
                    print(f"  - Loss from Sale: {loss}")
                    print(f"  - Reset Balance and Cost for position {key}")
                    sell_count += 1
                    total_sells += 1
                    continue  # Skip further checks for this position

                # Check buy condition
                if BUYS_ACTIVE and position["buyMin"] <= currentMcap <= position["buyMax"] and position["balance"] == 0:
                    if active_positions >= MAX_POSITIONS:
                        print(f"Max positions reached ({MAX_POSITIONS}). Skipping buy for position {key}.")
                        continue                    
                    
                    print(f"  - Buying for position {key}...")
                    positionSize, cost = place_order(sol, tokenId, amount)
                    position["balance"] = int(positionSize)
                    position["cost"] = int(cost)
                    save_json(positions)
                    print(f"  - Updated Balance for position {key}: {positionSize}")
                    buy_count += 1
                    total_buys += 1

                # Check sell condition
                elif SELLS_ACTIVE and currentMcap > position["sellMin"] and position["balance"] != 0:

                    print(f"  - Selling for position {key}...")
                    sell_amount = int(position["balance"] * 0.99)  # Sell 99% of the position
                    #tokens_received, _ = place_order(tokenId, sol, sell_amount)
                    tokens_received, _ = execute_sell(tokenId, sol, sell_amount, position["cost"])

                    if int(tokens_received) > 0:
                        # Calculate profit
                        profit = int(tokens_received) - int(position["cost"])
                        total_profit += profit

                        # Reset balance and cost
                        position["balance"] = 0
                        position["cost"] = 0
                        save_json(positions)

                        print(f"  - Sold 99% of position {key} (Amount: {sell_amount})")
                        print(f"  - Tokens Received: {tokens_received}")
                        print(f"  - Profit from Sale: {profit}")
                        print(f"  - Reset Balance and Cost for position {key}")
                        sell_count += 1
                        total_sells += 1
                        non_zero_positions -= 1  # Decrease non-zero positions count

                        if profit < 0:
                            print("Profit was below 0. Pausing bot for 180s to protect from loss.")
                            time.sleep(180)
                            print("Resuming operations.")
                    else:
                        print(f"  - Sell order for position {key} did not execute successfully. No tokens received.")


            print("-------------------------------")
            print(f"Iteration {runCnt} Summary: {ticker}")
            print(f"Timestamp: {current_time}")
            print(f"Current Market Cap: {currentMcap}")
            #print(f"  - Buy Txns (this iteration): {buy_count}")
            #print(f"  - Sell Txns (this iteration): {sell_count}")
            #print(f"  - Total Buy Txns (session): {total_buys}")
            #print(f"  - Total Sell Txns (session): {total_sells}")
            print(f" - Buys/Sells :{total_buys}/{total_sells}")
            #print(f"  - Current Positions: {non_zero_positions}/{total_positions}")
            print(f" - Current Positions: {non_zero_positions}/{MAX_POSITIONS}/{total_positions}")
            #print(f"  - Max Active Positions: {MAX_POSITIONS}")
            print(f" - Total Profit (session): {total_profit / 1e9:.9G}")
            #print("-------------------------------")
            #print("")

            runCnt += 1
            active_positions = non_zero_positions
            time.sleep(6)

    finally:
        client.close()

def debug():
    """Debug loop: print the current quote every few seconds.

    This is the intended mode for first-time setup of a new coin:
    1) set TOKEN_MINT
    2) run debug() to observe the quote scale
    3) generate positions.json grid using gen_position_json.py
    4) switch to main()
    """
    while True:
        print(getQuote(tokenId))
        time.sleep(3)

if __name__ == "__main__":
    # Default behavior stays the same (main), but you can do:
    #   RUN_MODE=debug python main.py
    mode = os.getenv("RUN_MODE", "main").lower().strip()
    if mode == "debug":
        debug()
    else:
        main()
