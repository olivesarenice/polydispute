import time

import requests
from web3 import Web3

# --- Configuration ---
identifier_text = "YES_OR_NO_QUERY"
ancillary_data_hex = "0x713a207469746c653a2055532078204972616e206d656574696e6720627920417072696c2031302c20323032363f2c206465736372697074696f6e3a2054686973206d61726b65742077696c6c207265736f6c766520746f2022596573222069662074686572652069732061206469706c6f6d61746963206d656574696e67206265747765656e20726570726573656e74617469766573206f662074686520556e697465642053746174657320616e64204972616e20627920746865206c697374656420646174652c2031313a353920504d2045542e204f74686572776973652c2074686973206d61726b65742077696c6c207265736f6c766520746f20e2809c4e6fe2809d2e0a0a41206469706c6f6d61746963206d656574696e672072656665727320746f20612064656c69626572617465206d656574696e67206265747765656e20726570726573656e74617469766573206f6620746865206c697374656420636f756e74726965732077686f2061726520616374696e6720696e20616e206f6666696369616c20636170616369747920616e642061726520617574686f72697a656420746f20656e6761676520696e206e65676f74696174696f6e206f72206469706c6f6d61637920726567617264696e672055532d4972616e69616e2072656c6174696f6e73206f6e20626568616c66206f6620746865697220676f7665726e6d656e74732e204d656574696e677320636f6e64756374656420696e6469726563746c792c20666f72206578616d706c652c207468726f7567682064657369676e61746564206d65646961746f72732c20666163696c697461746f72732c206f7220696e7465726c6f6375746f727320616374696e67207769746820746865206b6e6f776c6564676520616e6420617574686f72697a6174696f6e206f66207468652072656c6576616e7420676f7665726e6d656e74732c2077696c6c207175616c6966792e200a0a4272696566206772656574696e67732c206368616e636520656e636f756e746572732c206f722074616c6b73206f7468657277697365206e6f742064656c696265726174656c792061696d6564206174206469706c6f6d616379206f72206e65676f74696174696f6e2077696c6c206e6f7420636f756e742e0a0a546865206d656574696e67206d75737420626520696e2d706572736f6e20616e64206d757374206265207075626c69636c792061636b6e6f776c65646765642062792065697468657220676f7665726e6d656e74206f72207265706f72746564206279206120636f6e73656e737573206f66206372656469626c65206d656469612e2052656d6f7465206d656574696e67732c2070686f6e652063616c6c732c206f72206f74686572206d656574696e6773207768657265207468652072656c6576616e74207061727469657320617265206e6f742070726573656e742077696c6c206e6f7420636f756e742e0a0a546865207265736f6c7574696f6e20736f757263657320666f722074686973206d61726b65742077696c6c206265206f6666696369616c20696e666f726d6174696f6e2066726f6d2074686520676f7665726e6d656e7473206f662074686520556e697465642053746174657320616e64204972616e2c20616e64206120636f6e73656e737573206f66206372656469626c65207265706f7274696e672e206d61726b65745f69643a2031373439313231207265735f646174613a2070313a20302c2070323a20312c2070333a20302e352e20576865726520703120636f72726573706f6e647320746f204e6f2c20703220746f205965732c20703320746f20756e6b6e6f776e2f35302d35302e2055706461746573206d61646520627920746865207175657374696f6e2063726561746f7220766961207468652062756c6c6574696e20626f61726420617420307836353037304245393134373734363044384137416545623934656639326665303536433266324137206173206465736372696265642062792068747470733a2f2f706f6c79676f6e7363616e2e636f6d2f74782f3078613134663031623131356334393133363234666333663530386639363066346465613235323735386537336332386635663037663865313964376263613036362073686f756c6420626520636f6e736964657265642e2c696e697469616c697a65723a39313433306361643264333937353736363439393731376661306436366137386438313465356335"
timestamps_to_check = [1774650333, 1775887433]
etherscan_api_key = "QHTC13NBWNEUWWST5ZJZY9DWF13THJAKT1"
voting_address = "0x004395edb43efca9885cedad51ec9faf93bd34ac"
rpc_url = "https://ethereum-rpc.publicnode.com"

w3 = Web3(Web3.HTTPProvider(rpc_url))
voting_address_checksum = w3.to_checksum_address(voting_address)

# Pre-compute byte conversions for strict filtering
target_identifier_bytes = identifier_text.encode("utf-8")
target_ancillary_bytes = Web3.to_bytes(hexstr=ancillary_data_hex)

# DVM uses the keccak256 hash prefixed with "ancillaryDataHash:" for large payloads from MOOV2
h = Web3.keccak(target_ancillary_bytes).hex()
target_ancillary_hashed_bytes = f"ancillaryDataHash:{h[2:]}".encode("utf-8")

# --- 1. Fetch Dynamic ABI from Etherscan ---
print("Fetching exact verified ABI from Etherscan...")
abi_url = f"https://api.etherscan.io/v2/api?chainid=1&module=contract&action=getabi&address={voting_address_checksum}&apikey={etherscan_api_key}"
response = requests.get(abi_url).json()

if response["status"] != "1":
    print(f"Error fetching ABI: {response['result']}")
    exit()

contract = w3.eth.contract(address=voting_address_checksum, abi=response["result"])


def get_block(timestamp):
    url = f"https://api.etherscan.io/v2/api?chainid=1&module=block&action=getblocknobytime&timestamp={timestamp}&closest=before&apikey={etherscan_api_key}"
    res = requests.get(url).json()
    return int(res["result"])


# --- 2. Process Rounds ---
for index, target_time in enumerate(timestamps_to_check):
    print(f"\n===========================================")
    print(f"Processing Round {index + 1} | Base Timestamp: {target_time}")
    print(f"===========================================")

    start_block = get_block(target_time)
    try:
        end_block = get_block(target_time + 1209600)
    except Exception:
        print("End timestamp in the future. Falling back to latest block.")
        end_block = w3.eth.block_number

    print(f"Target Block Range: {start_block} to {end_block}")

    events = []
    current_block = start_block
    step = 500

    while current_block <= end_block:
        chunk_end = min(current_block + step, end_block)
        print(f"Fetching logs from block {current_block} to {chunk_end}...")

        for attempt in range(3):
            try:
                chunk_events = contract.events.VoteRevealed.get_logs(
                    from_block=current_block, to_block=chunk_end
                )
                events.extend(chunk_events)
                break
            except Exception as e:
                print(f"RPC Error (Attempt {attempt+1}): {e}")
                time.sleep(2)

        current_block = chunk_end + 1

    # --- 3. Filter & Aggregate (Strict Ancillary Filter) ---
    vote_tallies = {}
    total_weight = 0

    for event in events:
        args = event["args"]

        # Structure Check: Safely extract explicitly to handle older contracts lacking ancillaryData
        ev_identifier = args.get("identifier", b"")
        ev_ancillary = args.get("ancillaryData", b"")

        # Strictly verify BOTH the identifier and the unique ancillaryData payload
        # Account for MOOV2 compression to ancillaryDataHash or appended metadata
        if ev_identifier.rstrip(b"\0") == target_identifier_bytes:
            if (
                target_ancillary_bytes in ev_ancillary
                or target_ancillary_hashed_bytes in ev_ancillary
            ):
                price = args["price"]

            # Handle varying UMA parameter naming conventions dynamically
            weight = args.get("voterWeight", args.get("numTokens", 0))

            vote_tallies[price] = vote_tallies.get(price, 0) + weight
            total_weight += weight

    # --- 4. Output Breakdown ---
    print(f"\n--- Final Vote Breakdown for Round {index + 1} ---")
    if total_weight == 0:
        print("No votes found for this specific market in this block range.")
    else:
        for price, weight in vote_tallies.items():
            percentage = (weight / total_weight) * 100

            if price == 0:
                outcome = "No"
            elif price == 1000000000000000000:
                outcome = "Yes"
            elif price == 500000000000000000:
                outcome = "Unknown / 50-50"
            else:
                outcome = f"Other ({price})"

            uma_voted = weight / (10**18)
            print(
                f"{outcome.ljust(15)} | Voted: {uma_voted:,.2f} UMA | Percentage: {percentage:.2f}%"
            )
