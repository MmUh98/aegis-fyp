from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sign_and_embed_c2pa(source_path: str, output_path: str) -> dict[str, Any]:
    """Create the Spike A Falcon assertion and embed it in a signed JPEG."""
    from spike_a import spike_a_falcon_c2pa as spike_a

    source = Path(source_path)
    output = Path(output_path)
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    secret_key, verification_key = spike_a.FALCON.keygen()
    try:
        payload = spike_a.build_payload(verification_key, source_sha256)
        signature = spike_a.FALCON.sign(secret_key, payload)
    finally:
        del secret_key

    assertion = {
        "alg": "Falcon-512",
        "vk_b64": spike_a.b64e(verification_key),
        "payload_b64": spike_a.b64e(payload),
        "sig_b64": spike_a.b64e(signature),
    }
    spike_a.sign_with_c2pa(source, output, assertion, None)
    report = spike_a.read_report(output)
    manifest = spike_a.active_manifest(report)
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")

    return {
        "success": True,
        "falcon_key_hash": hashlib.sha256(verification_key).hexdigest(),
        "manifest_hash": hashlib.sha256(manifest_bytes).hexdigest(),
    }
