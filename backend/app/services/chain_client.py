import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from web3 import Web3

from app.services.decide import OnChainRecord


load_dotenv(Path(__file__).resolve().parents[2] / ".env")

RPC_URL = os.getenv("AMOY_RPC_URL", "https://polygon-amoy.drpc.org")
CONTRACT_ADDRESS = os.getenv("AEGIS_REGISTRY_V2_ADDRESS")

V2_ABI = [
    {
        "inputs": [{"internalType": "string", "name": "manifestHash", "type": "string"}],
        "name": "getRecordByManifestHash",
        "outputs": [
            {"internalType": "address", "name": "creator", "type": "address"},
            {"internalType": "string", "name": "falconKeyHash", "type": "string"},
            {"internalType": "string", "name": "pHash", "type": "string"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"internalType": "bool", "name": "exists", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "string", "name": "pHash", "type": "string"}],
        "name": "getRecordByPHash",
        "outputs": [
            {"internalType": "address", "name": "creator", "type": "address"},
            {"internalType": "string", "name": "falconKeyHash", "type": "string"},
            {"internalType": "string", "name": "manifestHash", "type": "string"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"internalType": "bool", "name": "exists", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

w3 = Web3(Web3.HTTPProvider(RPC_URL))
contract: Any | None = None
if CONTRACT_ADDRESS:
    try:
        contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=V2_ABI)
    except ValueError:
        contract = None


def _connected() -> bool:
    return contract is not None and w3.is_connected()


def lookup_on_chain_by_manifest(manifest_hash: str) -> Optional[OnChainRecord]:
    registry = contract
    if registry is None or not w3.is_connected():
        return None
    try:
        creator, key_hash, phash, timestamp, exists = registry.functions.getRecordByManifestHash(manifest_hash).call()
        if exists:
            return OnChainRecord(
                creator_address=creator,
                falcon_key_hash=key_hash,
                manifest_hash=manifest_hash,
                phash_hex=phash,
                timestamp=timestamp,
            )
    except Exception:
        return None
    return None


def lookup_on_chain_by_phash(phash: str) -> Optional[OnChainRecord]:
    registry = contract
    if registry is None or not w3.is_connected():
        return None
    try:
        creator, key_hash, manifest_hash, timestamp, exists = registry.functions.getRecordByPHash(phash).call()
        if exists:
            return OnChainRecord(
                creator_address=creator,
                falcon_key_hash=key_hash,
                manifest_hash=manifest_hash,
                phash_hex=phash,
                timestamp=timestamp,
            )
    except Exception:
        return None
    return None
