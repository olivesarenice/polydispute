import requests
from web3 import Web3

question_id = "0x3cbac528a25752d2e2d480ace84e53f4365df5e41a7c45dce135849a07973cd7"  # "0x77bac422ade9297902c93986424731827ff5ced95a988c5d6cbd9d0791485526"
adapter_address = "0x65070BE91477460D8A7AeEb94ef92fe056C2f2A7"
polygonscan_api_key = "QHTC1****"

# 1. Get ABI
abi_url = f"https://api.etherscan.io/v2/api?chainid=137&module=contract&action=getabi&address={adapter_address}&apikey={polygonscan_api_key}"
response = requests.get(abi_url).json()
abi = response["result"]

# 2. Connect
w3 = Web3(Web3.HTTPProvider("https://polygon.drpc.org"))
contract = w3.eth.contract(address=w3.to_checksum_address(adapter_address), abi=abi)

# 3. Identify the UMA Oracle Version
# Most adapters have a public 'umaOracle' or 'optimisticOracle' variable
try:
    oracle_address = contract.functions.umaOracle().call()
except:
    try:
        oracle_address = contract.functions.optimisticOracle().call()
    except:
        oracle_address = "Unknown"

print(f"--- Contract Metadata ---")
print(f"Adapter Address: {adapter_address}")
print(f"UMA Oracle Address: {oracle_address}")
print(f"Hint: If Oracle is 0x796... it is likely OOv2. If 0x595... it is likely OOv3.")

# 4. Fetch Question Data
question_data = contract.functions.getQuestion(question_id).call()

# The struct return usually looks like:
# (ancillaryData, reward, bond, liveness, resolutionTime, etc.)
# We extract ancillaryData and decode it.
ancillary_data_bytes = question_data[11]

print(f"\n--- Question Data ---")
print(f"Ancillary Data (Hex): 0x{ancillary_data_bytes.hex()}")

try:
    # Decode hex to string to see the actual human-readable rules
    decoded_text = ancillary_data_bytes.decode("utf-8")
    print(f"Decoded Claim: {decoded_text}")
except Exception as e:
    print(f"Could not decode to UTF-8: {e}")

# Logic to help you pick the subgraph
if (
    "ASSERT_TRUTH" in decoded_text
    or oracle_address.lower() == "0x595358830c877E038b7ad83a579f7371F7Bb0029".lower()
):
    print("\n>>> TARGET: Optimistic Oracle V3 Subgraph (Polygon)")
else:
    print("\n>>> TARGET: Optimistic Oracle V2 Subgraph (Polygon)")
