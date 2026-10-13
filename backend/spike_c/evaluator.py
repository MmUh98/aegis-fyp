from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional

import torch
from PIL import Image, ImageOps
from transformers import AutoImageProcessor

from spike_c.classifier import AegisBaseDetector
from spike_c.models.siglip2_base.aegis_common import FaceDetector, decode_jpeg, encode_jpeg, load_rgb, prepare_crop

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent / "models" / "siglip2_base"
VISION_WEIGHTS = MODEL_DIR / "vision_finetuned_tensors.pt"
HEAD_WEIGHTS = MODEL_DIR / "head.pt"
META_PATH = MODEL_DIR / "aegis_meta.json"
MODEL_ID = "google/siglip2-base-patch16-224"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MAX_FILE_BYTES = 15 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 50_000_000
DEFAULT_THRESHOLD = 0.50
DEFAULT_UNCERTAIN_MARGIN = 0.10

_lock = threading.Lock()
_model: Optional[AegisBaseDetector] = None
_processor = None
_face_detector = None
_threshold = DEFAULT_THRESHOLD
_margin = DEFAULT_UNCERTAIN_MARGIN
_preprocessing = {"face_margin": 0.3, "crop_size": 224, "jpeg_quality": 95}


def load_detector() -> None:
    global _model, _processor, _face_detector, _threshold, _margin, _preprocessing
    with _lock:
        if _model is not None:
            return
        for path in (VISION_WEIGHTS, HEAD_WEIGHTS, META_PATH):
            if not path.exists():
                raise FileNotFoundError(f"Missing detector bundle file: {path}")

        meta = json.loads(META_PATH.read_text())
        if meta.get("model_id") != MODEL_ID:
            raise RuntimeError(f"Model ID mismatch: metadata has {meta.get('model_id')!r}, expected {MODEL_ID!r}")
        if meta.get("contract_version") != 1:
            raise RuntimeError(f"Unsupported detector contract version: {meta.get('contract_version')}")

        _threshold = float(meta.get("thresholds", {}).get("frame", DEFAULT_THRESHOLD))
        _margin = float(meta.get("uncertain_margin", DEFAULT_UNCERTAIN_MARGIN))
        _preprocessing = meta.get("preprocessing", _preprocessing)
        logger.info("Loading fine-tuned SigLIP-2 detector on %s", DEVICE)
        processor = AutoImageProcessor.from_pretrained(MODEL_ID)
        model = AegisBaseDetector(model_id=MODEL_ID)
        report = model.load_fine_tuned_weights(str(VISION_WEIGHTS), str(HEAD_WEIGHTS))
        if report["vision_tensors_applied"] <= 0 or report["vision_unexpected_keys"] != 0:
            raise RuntimeError(f"Invalid detector weight report: {report}")
        model.to(DEVICE).eval()
        _face_detector = FaceDetector(device=str(DEVICE))
        _processor, _model = processor, model
        logger.info("Detector ready: %s", report)


def _load_image(image_path: str) -> Image.Image:
    path = Path(image_path)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"File exceeds {MAX_FILE_BYTES // (1024 * 1024)} MB limit")
    with Image.open(path) as probe:
        probe.verify()
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        if getattr(image, "is_animated", False):
            image.seek(0)
        return image.convert("RGB")


def _verdict(probability: float) -> str:
    if probability >= _threshold + _margin:
        return "LIKELY_FAKE"
    if probability <= _threshold - _margin:
        return "LIKELY_REAL"
    return "UNCERTAIN"


def evaluate_ai_deepfake(image_path: str) -> dict:
    try:
        if _model is None:
            load_detector()
        image = _load_image(image_path)
        rgb = load_rgb(image)
        crop, _ = prepare_crop(
            rgb,
            _face_detector,
            float(_preprocessing.get("face_margin", 0.3)),
            int(_preprocessing.get("crop_size", 224)),
        )
        prepared = decode_jpeg(encode_jpeg(crop, int(_preprocessing.get("jpeg_quality", 95))))
        inputs = _processor(images=prepared, return_tensors="pt")
        inputs = {key: value.to(DEVICE) for key, value in inputs.items() if hasattr(value, "to")}
        with torch.inference_mode():
            probability = torch.sigmoid(_model(**inputs)).item()
        verdict = _verdict(probability)
        return {
            "ai_score": round(probability, 4),
            "verdict": verdict,
            "threshold_used": _threshold,
            "uncertain_margin": _margin,
            "reason": (
                f"Fine-tuned SigLIP-2 detector score {probability:.4f}; "
                f"threshold {_threshold:.4f}. This is evidence, not proof."
            ),
        }
    except Exception as error:
        logger.exception("AI deepfake evaluation failed for %s", image_path)
        return {
            "ai_score": None,
            "verdict": "INCONCLUSIVE",
            "reason": f"AI evaluation error: {type(error).__name__}: {error}",
        }
