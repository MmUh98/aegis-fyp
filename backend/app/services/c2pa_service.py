from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from app.services.decide import C2PAStatus


def _load_spike_a() -> tuple[Any, Any, Any, Any]:
    from spike_a import spike_a_falcon_c2pa as spike_a_module

    return (
        spike_a_module.c2pa,
        spike_a_module.active_manifest,
        spike_a_module.find_assertion,
        spike_a_module.verify_assertion,
    )


def _manifest_hash(manifest: dict[str, Any]) -> str:
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def verify_c2pa_file(file_path: str) -> dict[str, Any]:
    """Read and validate the C2PA report plus Aegis Falcon assertion.

    Missing optional C2PA dependencies are represented as ABSENT by the caller.
    A report with validation errors is explicitly marked TAMPERED.
    """
    c2pa, active_manifest, find_assertion, verify_assertion = _load_spike_a()
    path = Path(file_path)
    with c2pa.Context() as context, path.open("rb") as handle:
        media_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(
            path.suffix.lower(), "video/mp4"
        )
        with c2pa.Reader(media_type, handle, context=context) as reader:
            report = json.loads(reader.json())

    manifests = report.get("manifests") or {}
    if not manifests:
        return {"status": C2PAStatus.ABSENT, "valid": False, "tampered": False}

    validation_status = report.get("validation_status") or []
    if report.get("validation_state") not in {None, "Valid"} or any(
        "mismatch" in str(item.get("code", "")).lower() or "invalid" in str(item.get("code", "")).lower()
        for item in validation_status
    ):
        return {"status": C2PAStatus.TAMPERED, "valid": False, "tampered": True}

    manifest = active_manifest(report)
    assertion = find_assertion(report, "com.aegis.falcon512")
    if not assertion:
        return {"status": C2PAStatus.VALID, "valid": True, "manifest_hash": _manifest_hash(manifest)}

    assertion_valid, _ = verify_assertion(assertion)
    if not assertion_valid:
        return {"status": C2PAStatus.TAMPERED, "valid": False, "tampered": True}

    payload = json.loads(base64.b64decode(assertion["payload_b64"]))
    return {
        "status": C2PAStatus.VALID,
        "valid": True,
        "manifest_hash": _manifest_hash(manifest),
        "falcon_key_hash": payload.get("vk_sha256"),
    }
