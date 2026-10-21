from __future__ import annotations

import json
import logging
import tempfile
import threading
from pathlib import Path
from typing import Optional

import torch
from PIL import Image, ImageOps
from transformers import AutoImageProcessor

from spike_c import audio_evaluator
from spike_c.classifier import AegisBaseDetector
from spike_c.device import DEVICE
from spike_c.media_utils import MediaError, extract_audio, extract_frames, probe_media
from spike_c.models.siglip2_base.aegis_common import FaceDetector, decode_jpeg, encode_jpeg, load_rgb, prepare_crop

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent / "models" / "siglip2_base"
VISION_WEIGHTS = MODEL_DIR / "vision_finetuned_tensors.pt"
HEAD_WEIGHTS = MODEL_DIR / "head.pt"
META_PATH = MODEL_DIR / "aegis_meta.json"
MODEL_ID = "google/siglip2-base-patch16-224"
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
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".webm"}
FRAME_TOP_K = 3
_analysis_slots = threading.BoundedSemaphore(2)


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


def _score_pil(image: Image.Image) -> float:
    if _model is None:
        load_detector()
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
        return torch.sigmoid(_model(**inputs)).item()


def evaluate_ai_deepfake(image_path: str) -> dict:
    try:
        image = _load_image(image_path)
        probability = _score_pil(image)
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


def evaluate_video_frames(frame_paths) -> dict:
    if _model is None:
        load_detector()
    scores = []
    for frame_path in frame_paths:
        with Image.open(frame_path) as image:
            scores.append(_score_pil(image.convert("RGB")))
    if not scores:
        return {"status": "error", "verdict": None, "score": None}
    top_scores = sorted(scores, reverse=True)[:FRAME_TOP_K]
    aggregate = sum(top_scores) / len(top_scores)
    return {
        "status": "ran",
        "score": round(aggregate, 4),
        "verdict": _verdict(aggregate),
        "threshold_used": _threshold,
        "uncertain_margin": _margin,
        "frames_analyzed": len(scores),
        "frame_scores": [round(score, 4) for score in scores],
    }


def fuse_modalities(visual: dict, audio: dict) -> dict:
    modalities = {"visual": visual, "audio": audio}
    triggered = [name for name, modality in modalities.items() if modality.get("verdict") == "LIKELY_FAKE"]
    ran = [name for name, modality in modalities.items() if modality.get("status") == "ran"]
    failed = [name for name, modality in modalities.items() if modality.get("status") in {"error", "disabled"}]
    uncertain = [name for name in ran if modalities[name].get("verdict") == "UNCERTAIN"]
    if triggered:
        verdict = "LIKELY_FAKE"
    elif not ran:
        verdict = "INCONCLUSIVE"
    elif failed or uncertain:
        verdict = "UNCERTAIN"
    else:
        verdict = "LIKELY_REAL"
    return {"verdict": verdict, "triggered_by": triggered, "failed": failed}


_AUDIO_NOTES = {
    "no_audio_track": "The video has no audio track, so only the visual detector was used.",
    "no_usable_audio": "The audio was silent or too short to analyze, so only the visual detector was used.",
    "disabled": "The audio detector is offline, so the result is incomplete.",
    "error": "Audio analysis failed, so the result is incomplete.",
}
_AUDIO_ABSENT = {"not_applicable", "no_audio_track", "no_usable_audio"}
_DIAGNOSIS = {
    ("REAL", "REAL"): "Authentic",
    ("REAL", "FAKE"): "Audio Substitution",
    ("FAKE", "REAL"): "AI Visual",
    ("FAKE", "FAKE"): "Full Deepfake",
}


def _side(modality: dict):
    if modality.get("status") != "ran":
        return None
    return {"LIKELY_REAL": "REAL", "LIKELY_FAKE": "FAKE"}.get(modality.get("verdict"))


def diagnose(visual: dict, audio: dict) -> dict:
    visual_side = _side(visual)
    if visual_side is None:
        return {"diagnosis": None, "audio_assessed": False}
    if audio.get("status") in _AUDIO_ABSENT:
        return {"diagnosis": "Authentic" if visual_side == "REAL" else "AI Visual", "audio_assessed": False}
    audio_side = _side(audio)
    if audio_side is None:
        return {"diagnosis": None, "audio_assessed": audio.get("status") == "ran"}
    return {"diagnosis": _DIAGNOSIS[(visual_side, audio_side)], "audio_assessed": True}


def _build_reason(visual: dict, audio: dict, fused: dict) -> str:
    parts = []
    if visual.get("status") == "ran":
        parts.append(f"Visual detector score {visual['score']:.2f} (threshold {visual['threshold_used']:.2f}).")
    elif visual.get("status") == "error":
        parts.append("Visual analysis failed.")
    if audio.get("status") == "ran":
        parts.append(f"Audio detector score {audio['score']:.2f} (threshold {audio['threshold_used']:.2f}).")
    elif audio.get("status") in _AUDIO_NOTES:
        parts.append(_AUDIO_NOTES[audio["status"]])
    if audio.get("status") != "ran":
        parts.append("Audio was not assessed.")
    elif audio.get("calibration_status") in {None, "none", "provisional"}:
        parts.append("Audio threshold is provisional or uncalibrated.")
    if fused["triggered_by"]:
        parts.append("Flagged by: " + ", ".join(fused["triggered_by"]) + ". Either detector can flag the file.")
    parts.append("Scores are uncalibrated model outputs, not proof.")
    return " ".join(parts)


def _modality_from_image_result(result: dict) -> dict:
    if result.get("ai_score") is None:
        return {"status": "error", "verdict": None, "score": None}
    return {
        "status": "ran",
        "score": result["ai_score"],
        "verdict": result["verdict"],
        "threshold_used": result.get("threshold_used"),
        "uncertain_margin": result.get("uncertain_margin"),
    }


def _response(media_type: str, visual: dict, audio: dict, media_duration_seconds: float | None = None) -> dict:
    fused = fuse_modalities(visual, audio)
    diagnosis = diagnose(visual, audio)
    output = {
        "verdict": fused["verdict"],
        "reason": _build_reason(visual, audio, fused),
        "media_type": media_type,
        "fusion_rule": "OR_FAIL_CLOSED",
        "triggered_by": fused["triggered_by"],
        "diagnosis": diagnosis["diagnosis"],
        "audio_assessed": diagnosis["audio_assessed"],
        "media_duration_seconds": media_duration_seconds,
        "visual": visual,
        "audio": audio,
        "ai_score": visual.get("score"),
        "threshold_used": visual.get("threshold_used"),
    }
    if audio.get("status") == "ran":
        output["audio_score"] = audio["score"]
    return output


def _inconclusive(media_type: str, reason: str) -> dict:
    output = _response(
        media_type,
        {"status": "error", "verdict": None, "score": None},
        {"status": "not_applicable", "verdict": None, "score": None},
    )
    output["reason"] = reason
    return output


def evaluate_multimodal_deepfake(media_path: str) -> dict:
    """Blocking multimodal analysis for an image or bounded video."""
    extension = Path(media_path).suffix.lower()
    try:
        if extension in IMAGE_EXTS:
            visual = _modality_from_image_result(evaluate_ai_deepfake(media_path))
            return _response("image", visual, {"status": "not_applicable", "verdict": None, "score": None})
        if extension in VIDEO_EXTS:
            with _analysis_slots, tempfile.TemporaryDirectory(prefix="aegis_") as workdir:
                info = probe_media(media_path)
                frames = extract_frames(media_path, workdir, info.duration)
                visual = evaluate_video_frames(frames)
                if info.has_audio:
                    try:
                        audio = audio_evaluator.evaluate_audio_deepfake(str(extract_audio(media_path, workdir)))
                    except MediaError:
                        audio = {"status": "error", "verdict": None, "score": None}
                else:
                    audio = {"status": "no_audio_track", "verdict": None, "score": None}
            return _response("video", visual, audio, info.duration)
        return _inconclusive("unknown", "Unsupported media type.")
    except MediaError as error:
        return _inconclusive("video", str(error))
    except Exception:
        logger.exception("Multimodal evaluation failed for %s", Path(media_path).name)
        return _inconclusive("video" if extension in VIDEO_EXTS else "image", "Analysis failed unexpectedly.")
