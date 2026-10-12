from __future__ import annotations

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, File, HTTPException, UploadFile
from web3 import Web3

from app.schemas.registration import RegistrationResponse
from app.services.fingerprint import compute_phash
from app.services.registration import sign_and_embed_c2pa

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

router = APIRouter(prefix="/api/v1", tags=["Registration"])

BACKEND_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BACKEND_DIR / "secure_temp_uploads"
REGISTERED_DIR = BACKEND_DIR / "registered_media"
UPLOAD_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
REGISTERED_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg"}
ALLOWED_CONTENT_TYPES = {"image/jpeg"}
MAX_FILE_SIZE = 50 * 1024 * 1024
RPC_URL = os.getenv("AMOY_RPC_URL", "https://polygon-amoy.drpc.org")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
CONTRACT_ADDRESS = os.getenv("AEGIS_REGISTRY_V2_ADDRESS")

V2_ABI = [
    {
        "inputs": [
            {"internalType": "string", "name": "falconKeyHash", "type": "string"},
            {"internalType": "string", "name": "manifestHash", "type": "string"},
            {"internalType": "string", "name": "pHash", "type": "string"},
        ],
        "name": "registerContent",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


@router.post("/register", response_model=RegistrationResponse)
def register_media(file: UploadFile = File(...)) -> RegistrationResponse:
    if not PRIVATE_KEY or not CONTRACT_ADDRESS:
        raise HTTPException(status_code=500, detail="Server registration configuration is incomplete")

    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS or file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Registration currently supports JPEG uploads only")

    safe_id = uuid.uuid4().hex
    temp_input_path = UPLOAD_DIR / f"{safe_id}_raw{extension}"
    output_signed_path = REGISTERED_DIR / f"{safe_id}_signed{extension}"

    try:
        size = 0
        with temp_input_path.open("xb") as output:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="File size exceeds 50 MB")
                output.write(chunk)

        c2pa_result = sign_and_embed_c2pa(str(temp_input_path), str(output_signed_path))
        if not c2pa_result.get("success"):
            raise HTTPException(status_code=500, detail="C2PA signing failed")

        phash = compute_phash(str(output_signed_path))
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            raise HTTPException(status_code=502, detail="Failed to connect to Polygon Amoy RPC node")

        account = w3.eth.account.from_key(PRIVATE_KEY)
        contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=V2_ABI)
        nonce = w3.eth.get_transaction_count(account.address)
        fee = w3.eth.get_fee_history(1, "latest", [50])
        base_fee = fee["baseFeePerGas"][-1]
        priority_fee = w3.to_wei(30, "gwei")
        max_fee = base_fee * 2 + priority_fee
        tx = contract.functions.registerContent(
            c2pa_result["falcon_key_hash"], c2pa_result["manifest_hash"], phash
        ).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "chainId": 80002,
                "maxFeePerGas": max_fee,
                "maxPriorityFeePerGas": priority_fee,
            }
        )
        tx["gas"] = (w3.eth.estimate_gas(tx) * 110) // 100
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt["status"] != 1:
            raise HTTPException(status_code=502, detail="Registration transaction failed on-chain")

        tx_hex = tx_hash.hex()
        return RegistrationResponse(
            success=True,
            filename=filename,
            falcon_key_hash=c2pa_result["falcon_key_hash"],
            manifest_hash=c2pa_result["manifest_hash"],
            phash=phash,
            tx_hash=tx_hex,
            block_number=int(receipt["blockNumber"]),
            explorer_url=f"https://amoy.polygonscan.com/tx/{tx_hex}",
            message="Content successfully signed, fingerprinted, and anchored on Polygon Amoy.",
        )
    except HTTPException:
        output_signed_path.unlink(missing_ok=True)
        raise
    except Exception as error:
        output_signed_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Registration pipeline failed: {error}") from error
    finally:
        file.file.close()
        temp_input_path.unlink(missing_ok=True)
