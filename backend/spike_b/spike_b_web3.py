import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3
from web3.types import TxParams, TxReceipt, Wei

# Load this spike's environment file regardless of the caller's working directory.
load_dotenv(Path(__file__).resolve().with_name(".env"))

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
RPC_URL = os.getenv("AMOY_RPC_URL", "https://polygon-amoy.drpc.org")
CONTRACT_ADDRESS = os.getenv("AEGIS_REGISTRY_ADDRESS")

if not PRIVATE_KEY or not CONTRACT_ADDRESS:
    print("Error: PRIVATE_KEY or AEGIS_REGISTRY_ADDRESS missing in .env")
    sys.exit(1)

w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    print(f"Failed to connect to Polygon Amoy via RPC: {RPC_URL}")
    sys.exit(1)

chain_id = w3.eth.chain_id
if chain_id != 80002:
    print(f"Connected to unexpected chain ID: {chain_id}")
    sys.exit(1)

print(f"Connected to Polygon Amoy (Chain ID: {chain_id})")

account = w3.eth.account.from_key(PRIVATE_KEY)
print(f"Using Wallet Address: {account.address}")

artifact_path = (
    Path(__file__).resolve().parents[2]
    / "contracts"
    / "artifacts"
    / "contracts"
    / "AegisRegistry.sol"
    / "AegisRegistry.json"
)

if artifact_path.exists():
    contract_json = json.loads(artifact_path.read_text())
    contract_abi = contract_json["abi"]
    print("Loaded contract ABI from Hardhat build artifacts.")
else:
    contract_abi = [
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "internalType": "address", "name": "creator", "type": "address"},
                {"indexed": False, "internalType": "string", "name": "ipfsCID", "type": "string"},
                {"indexed": False, "internalType": "string", "name": "c2paHash", "type": "string"},
                {"indexed": False, "internalType": "string", "name": "pHash", "type": "string"},
                {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"},
            ],
            "name": "ContentRegistered",
            "type": "event",
        },
        {
            "inputs": [
                {"internalType": "string", "name": "cid", "type": "string"},
                {"internalType": "string", "name": "_c2paHash", "type": "string"},
                {"internalType": "string", "name": "_pHash", "type": "string"},
            ],
            "name": "registerContent",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function",
        },
    ]
    print("Hardhat artifact not found. Using inline fallback ABI.")

contract_address_checksum = Web3.to_checksum_address(CONTRACT_ADDRESS)
registry_contract = w3.eth.contract(address=contract_address_checksum, abi=contract_abi)


def register_media_provenance(cid: str, c2pa_hash: str, phash: str):
    print("\nRegistering media provenance on-chain...")
    print(f"  IPFS CID:  {cid}")
    print(f"  C2PA Hash: {c2pa_hash}")
    print(f"  pHash:     {phash}")

    nonce = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price
    tx_params: TxParams = {
        "chainId": 80002,
        "from": account.address,
        "gas": 200000,
        "maxFeePerGas": Wei(gas_price * 2),
        "maxPriorityFeePerGas": Wei(w3.to_wei("30", "gwei")),
        "nonce": nonce,
    }
    tx = registry_contract.functions.registerContent(
        cid,
        c2pa_hash,
        phash,
    ).build_transaction(tx_params)

    signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    print("Sending raw transaction to Polygon Amoy...")
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    print(f"Transaction hash: {tx_hash.hex()}")

    print("Waiting for transaction receipt...")
    receipt: TxReceipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt["status"] != 1:
        raise RuntimeError("Transaction failed on-chain")

    print("Transaction successful")
    print(f"  Block number: {receipt['blockNumber']}")
    print(f"  Gas used:     {receipt['gasUsed']}")
    print(f"  PolygonScan:  https://amoy.polygonscan.com/tx/{tx_hash.hex()}")

    logs = registry_contract.events.ContentRegistered().process_receipt(receipt)
    if not logs:
        raise RuntimeError("Transaction succeeded but no ContentRegistered event was emitted")

    event_args = logs[0]["args"]
    print("\nContentRegistered event:")
    print(f"  Creator:   {event_args['creator']}")
    print(f"  IPFS CID:  {event_args['ipfsCID']}")
    print(f"  C2PA Hash: {event_args['c2paHash']}")
    print(f"  pHash:     {event_args['pHash']}")
    print(f"  Timestamp: {event_args['timestamp']}")
    return receipt


if __name__ == "__main__":
    register_media_provenance(
        "bafybeigdyr3223vv4626omff63eb2wm2j2b99238382",
        "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "1001101011100101",
    )
