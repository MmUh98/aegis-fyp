from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
import torch
from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

logger = logging.getLogger(__name__)

AUDIO_MODEL_ID = "Hemgg/Deepfake-audio-detection"
META_PATH = Path(__file__).resolve().parent / "models" / "wav2vec2-audio" / "audio_meta.json"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
SAMPLE_RATE = 16000
CHUNK_SECONDS = 10
MIN_CHUNK_SECONDS = 2
SILENCE_RMS = 0.005
TOP_K = 2

_lock = threading.Lock()
_model = None
_extractor = None
_fake_idx: Optional[int] = None
_threshold = 0.50
_margin = 0.15


def load_audio_detector() -> None:
    global _model, _extractor, _fake_idx, _threshold, _margin
    with _lock:
        if _model is not None:
            return
        if not META_PATH.exists():
            raise FileNotFoundError(f"Missing {META_PATH}. Run audio label verification first.")
        meta = json.loads(META_PATH.read_text())
        if not meta.get("verified") or meta.get("fake_label_index") not in (0, 1):
            raise RuntimeError("audio_meta.json has no verified fake_label_index.")
        revision = meta.get("model_revision")
        extractor = AutoFeatureExtractor.from_pretrained(AUDIO_MODEL_ID, revision=revision)
        model = AutoModelForAudioClassification.from_pretrained(AUDIO_MODEL_ID, revision=revision)
        if model.config.num_labels != 2:
            raise RuntimeError(f"Expected 2 audio labels, got {model.config.num_labels}.")
        if int(getattr(extractor, "sampling_rate", SAMPLE_RATE)) != SAMPLE_RATE:
            raise RuntimeError("Audio extractor sampling rate is not 16 kHz.")
        model.to(DEVICE).eval()
        _fake_idx = int(meta["fake_label_index"])
        _threshold = float(meta.get("threshold", 0.50))
        _margin = float(meta.get("uncertain_margin", 0.15))
        _extractor, _model = extractor, model
        logger.info("Audio detector loaded on %s (fake_label_index=%s)", DEVICE, _fake_idx)


def is_loaded() -> bool:
    return _model is not None


def _verdict(score: float) -> str:
    if score >= _threshold + _margin:
        return "LIKELY_FAKE"
    if score <= _threshold - _margin:
        return "LIKELY_REAL"
    return "UNCERTAIN"


def evaluate_audio_deepfake(wav_path: str) -> dict:
    if not is_loaded():
        return {"status": "disabled", "verdict": None, "score": None}
    try:
        speech, rate = sf.read(wav_path, dtype="float32", always_2d=False)
        if rate != SAMPLE_RATE:
            raise ValueError(f"Unexpected sample rate {rate}")
        if speech.ndim > 1:
            speech = speech.mean(axis=1)

        chunk_length = CHUNK_SECONDS * SAMPLE_RATE
        chunks = []
        for start in range(0, len(speech), chunk_length):
            chunk = speech[start : start + chunk_length]
            if len(chunk) < MIN_CHUNK_SECONDS * SAMPLE_RATE:
                continue
            if float(np.sqrt(np.mean(np.square(chunk)))) < SILENCE_RMS:
                continue
            chunks.append(chunk)
        if not chunks:
            return {"status": "no_usable_audio", "verdict": None, "score": None}

        scores = []
        for chunk in chunks:
            inputs = _extractor(chunk, sampling_rate=SAMPLE_RATE, return_tensors="pt")
            inputs = {key: value.to(DEVICE) for key, value in inputs.items()}
            with torch.inference_mode():
                probabilities = torch.softmax(_model(**inputs).logits, dim=-1)[0]
            scores.append(float(probabilities[_fake_idx]))

        top_scores = sorted(scores, reverse=True)[:TOP_K]
        aggregate = sum(top_scores) / len(top_scores)
        return {
            "status": "ran",
            "score": round(aggregate, 4),
            "verdict": _verdict(aggregate),
            "threshold_used": _threshold,
            "uncertain_margin": _margin,
            "chunks_analyzed": len(scores),
            "chunk_scores": [round(score, 4) for score in scores],
        }
    except Exception:
        logger.exception("Audio evaluation failed")
        return {"status": "error", "verdict": None, "score": None}
