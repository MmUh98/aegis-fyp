from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.routers import register
from spike_c import audio_evaluator
from spike_c.evaluator import evaluate_multimodal_deepfake, load_detector
from app.services.c2pa_service import verify_c2pa_file
from app.services.chain_client import lookup_on_chain_by_manifest, lookup_on_chain_by_phash
from app.services.decide import C2PAStatus, DecisionResult, decide
from app.services.fingerprint import compute_phash, hamming_distance

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_detector()
    try:
        audio_evaluator.load_audio_detector()
        logger.info("Aegis detectors ready: visual=enabled audio=enabled")
    except Exception:
        logger.exception("Audio detector unavailable; continuing with audio disabled")
    yield


app = FastAPI(title="Aegis Media Provenance API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin
        for origin in os.getenv(
            "AEGIS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(register.router)

UPLOAD_DIR = Path(os.getenv("AEGIS_UPLOAD_DIR", "secure_temp_uploads"))
UPLOAD_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "video/mp4", "video/quicktime", "video/webm"}
MAX_IMAGE_SIZE = 15 * 1024 * 1024
MAX_VIDEO_SIZE = 50 * 1024 * 1024


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "Aegis Media Provenance API", "docs": "/docs", "health": "/health"}


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
    max_file_size = MAX_VIDEO_SIZE if extension in VIDEO_EXTENSIONS else MAX_IMAGE_SIZE

    temp_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{extension}"
    size = 0
    try:
        with temp_path.open("xb") as output:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_file_size:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File size exceeds {max_file_size // (1024 * 1024)} MB",
                    )
                output.write(chunk)

        c2pa_status = C2PAStatus.ABSENT
        manifest_hash: str | None = None
        falcon_key_hash: str | None = None
        computed_phash: str | None = None
        on_chain_record = None
        registry_status = "NOT_APPLICABLE" if extension in VIDEO_EXTENSIONS else "NOT_FOUND"
        if extension in IMAGE_EXTENSIONS:
            try:
                computed_phash = compute_phash(str(temp_path))
            except Exception:
                pass
            try:
                c2pa_result = verify_c2pa_file(str(temp_path))
                c2pa_status = c2pa_result.get("status", C2PAStatus.ABSENT)
                manifest_hash = c2pa_result.get("manifest_hash")
                falcon_key_hash = c2pa_result.get("falcon_key_hash")
            except Exception:
                c2pa_status = C2PAStatus.ABSENT
            on_chain_record = lookup_on_chain_by_manifest(manifest_hash) if manifest_hash else None
            if on_chain_record is not None:
                registry_status = "MATCH"
        phash_distance = None
        if on_chain_record is None and computed_phash:
            on_chain_record = lookup_on_chain_by_phash(computed_phash)
            if on_chain_record:
                registry_status = "MATCH"
                try:
                    phash_distance = hamming_distance(computed_phash, on_chain_record.phash_hex)
                except ValueError:
                    on_chain_record = None

        if c2pa_status == C2PAStatus.ABSENT and on_chain_record is None:
            multimodal = evaluate_multimodal_deepfake(str(temp_path))
            return DecisionResult(
                **multimodal,
                c2pa_status=c2pa_status,
                on_chain_match=False,
                phash_distance=phash_distance,
                registry_status=registry_status,
            )

        result = decide(
            c2pa_status=c2pa_status,
            manifest_hash=manifest_hash,
            falcon_key_hash=falcon_key_hash,
            on_chain_record=on_chain_record,
            phash_distance=phash_distance,
        )
        result.registry_status = registry_status
        return result
    finally:
        file.file.close()
        temp_path.unlink(missing_ok=True)
