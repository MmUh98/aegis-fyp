from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.services.c2pa_service import verify_c2pa_file
from app.services.chain_client import lookup_on_chain_by_manifest, lookup_on_chain_by_phash
from app.services.decide import C2PAStatus, DecisionResult, decide
from app.services.fingerprint import compute_phash, hamming_distance

app = FastAPI(title="Aegis Media Provenance API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in os.getenv("AEGIS_CORS_ORIGINS", "http://localhost:5173").split(",") if origin],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(os.getenv("AEGIS_UPLOAD_DIR", "secure_temp_uploads"))
UPLOAD_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "video/mp4", "video/quicktime"}
MAX_FILE_SIZE = 50 * 1024 * 1024


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "Aegis Media Provenance API", "docs": "/docs", "health": "/health"}


def _calculate_ai_score(file_path: Path, extension: str) -> float | None:
    if extension in {".mp4", ".mov"}:
        return None
    from PIL import Image
    from spike_c.spike_c_siglip2 import calculate_deepfake_score

    with Image.open(file_path) as image:
        return calculate_deepfake_score(image.convert("RGB"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/verify", response_model=DecisionResult)
def verify_media(file: UploadFile = File(...)) -> DecisionResult:
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported media extension")
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported media MIME type")

    temp_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{extension}"
    size = 0
    try:
        with temp_path.open("xb") as output:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="File size exceeds 50 MB")
                output.write(chunk)

        computed_phash: str | None = None
        try:
            computed_phash = compute_phash(str(temp_path))
        except Exception:
            pass

        c2pa_status = C2PAStatus.ABSENT
        manifest_hash: str | None = None
        falcon_key_hash: str | None = None
        try:
            c2pa_result = verify_c2pa_file(str(temp_path))
            c2pa_status = c2pa_result.get("status", C2PAStatus.ABSENT)
            manifest_hash = c2pa_result.get("manifest_hash")
            falcon_key_hash = c2pa_result.get("falcon_key_hash")
        except Exception:
            c2pa_status = C2PAStatus.ABSENT

        on_chain_record = lookup_on_chain_by_manifest(manifest_hash) if manifest_hash else None
        phash_distance = None
        if on_chain_record is None and computed_phash:
            on_chain_record = lookup_on_chain_by_phash(computed_phash)
            if on_chain_record:
                try:
                    phash_distance = hamming_distance(computed_phash, on_chain_record.phash_hex)
                except ValueError:
                    on_chain_record = None

        ai_score = None
        ai_error = False
        if c2pa_status == C2PAStatus.ABSENT and on_chain_record is None:
            try:
                ai_score = _calculate_ai_score(temp_path, extension)
                ai_error = ai_score is None
            except Exception:
                ai_error = True

        return decide(
            c2pa_status=c2pa_status,
            manifest_hash=manifest_hash,
            falcon_key_hash=falcon_key_hash,
            on_chain_record=on_chain_record,
            phash_distance=phash_distance,
            ai_score=ai_score,
            ai_error=ai_error,
        )
    finally:
        file.file.close()
        temp_path.unlink(missing_ok=True)
