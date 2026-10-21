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

from spike_c.device import DEVICE

logger = logging.getLogger(__name__)

AUDIO_MODEL_ID = "Hemgg/Deepfake-audio-detection"
META_PATH = Path(__file__).resolve().parent / "models" / "wav2vec2-audio" / "audio_meta.json"
SAMPLE_RATE = 16000
SILENCE_RMS = 0.005
BATCH_SIZE = 8

_lock = threading.Lock()
_model = None
_extractor = None
_fake_idx: Optional[int] = None
_threshold = 0.50
_margin = 0.15
_window_seconds = 4.0
_hop_seconds = 2.0
_min_window_seconds = 2.0
_aggregation_mode = "top_k_mean"
_aggregation_k = 2
_calibration_status = "none"
_model_label = "Wav2Vec2 audio-classification fine-tune"


def load_audio_detector() -> None:
    global _model, _extractor, _fake_idx, _threshold, _margin
    global _window_seconds, _hop_seconds, _min_window_seconds, _aggregation_mode
    global _aggregation_k, _calibration_status, _model_label
    with _lock:
        if _model is not None:
            return
        if not META_PATH.exists():
            raise FileNotFoundError(f"Missing {META_PATH}. Run audio label verification first.")
        meta = json.loads(META_PATH.read_text())
        if not meta.get("verified") or meta.get("fake_label_index") not in (0, 1):
            raise RuntimeError("audio_meta.json has no verified fake_label_index.")
        revision = meta.get("model_revision")
        extractor = AutoFeatureExtractor.from_pretrained(
            AUDIO_MODEL_ID, revision=revision, trust_remote_code=False
        )
        loaded = AutoModelForAudioClassification.from_pretrained(
            AUDIO_MODEL_ID, revision=revision, trust_remote_code=False, output_loading_info=True
        )
        model, loading_info = loaded
        missing = loading_info.get("missing_keys", [])
        newly_initialized = [key for key in missing if key.startswith(("classifier.", "projector."))]
        if newly_initialized:
            raise RuntimeError(f"Audio classification head was newly initialized: {newly_initialized[:5]}")
        if model.config.num_labels != 2:
            raise RuntimeError(f"Expected 2 audio labels, got {model.config.num_labels}.")
        if int(getattr(extractor, "sampling_rate", SAMPLE_RATE)) != SAMPLE_RATE:
            raise RuntimeError("Audio extractor sampling rate is not 16 kHz.")
        model.to(DEVICE).eval()
        _fake_idx = int(meta["fake_label_index"])
        _threshold = float(meta.get("threshold", 0.50))
        _margin = float(meta.get("uncertain_margin", 0.15))
        _window_seconds = float(meta.get("window_seconds", 4.0))
        _hop_seconds = float(meta.get("hop_seconds", 2.0))
        _min_window_seconds = float(meta.get("min_window_seconds", 2.0))
        aggregation = meta.get("aggregation", {})
        _aggregation_mode = aggregation.get("mode", "top_k_mean")
        _aggregation_k = int(aggregation.get("k", 2))
        _calibration_status = meta.get("calibration_status", "none")
        _model_label = meta.get("architecture_label", "Wav2Vec2 audio-classification fine-tune")
        _extractor, _model = extractor, model
        logger.info(
            "Audio detector loaded on %s: model=%s fake_label_index=%s calibration=%s",
            DEVICE,
            _model_label,
            _fake_idx,
            _calibration_status,
        )
        if _calibration_status != "calibrated":
            logger.warning("Audio threshold calibration status is %s", _calibration_status)


def is_loaded() -> bool:
    return _model is not None


def make_windows(n_samples: int, window_s: float | None = None, hop_s: float | None = None, min_s: float | None = None) -> list[tuple[int, int]]:
    window_s = _window_seconds if window_s is None else window_s
    hop_s = _hop_seconds if hop_s is None else hop_s
    min_s = _min_window_seconds if min_s is None else min_s
    window = int(window_s * SAMPLE_RATE)
    hop = int(hop_s * SAMPLE_RATE)
    minimum = int(min_s * SAMPLE_RATE)
    if n_samples < minimum:
        return []
    if n_samples <= window:
        return [(0, n_samples)]
    starts = list(range(0, n_samples - window + 1, hop))
    if starts[-1] + window < n_samples:
        starts.append(n_samples - window)
    return [(start, start + window) for start in starts]


def _verdict(score: float) -> str:
    if score >= _threshold + _margin:
        return "LIKELY_FAKE"
    if score <= _threshold - _margin:
        return "LIKELY_REAL"
    return "UNCERTAIN"


def _aggregate(scores: list[float]) -> float:
    if _aggregation_mode == "max":
        return max(scores)
    if _aggregation_mode == "mean":
        return float(np.mean(scores))
    if _aggregation_mode == "top_k_mean":
        return float(np.mean(sorted(scores, reverse=True)[:_aggregation_k]))
    raise RuntimeError(f"Unsupported audio aggregation mode: {_aggregation_mode}")


def _score_batch(chunks: list[np.ndarray]) -> list[float]:
    inputs = _extractor(chunks, sampling_rate=SAMPLE_RATE, return_tensors="pt")
    inputs = {key: value.to(DEVICE) for key, value in inputs.items()}
    with torch.inference_mode():
        probabilities = torch.softmax(_model(**inputs).logits, dim=-1)[:, _fake_idx]
    return [float(score) for score in probabilities]


def evaluate_audio_deepfake(wav_path: str) -> dict:
    if not is_loaded():
        return {"status": "disabled", "verdict": None, "score": None}
    try:
        speech, rate = sf.read(wav_path, dtype="float32", always_2d=False)
        if rate != SAMPLE_RATE:
            raise ValueError(f"Unexpected sample rate {rate}")
        if speech.ndim > 1:
            speech = speech.mean(axis=1)
        window_ranges = make_windows(len(speech))
        scored = []
        skipped_silent = 0
        for start in range(0, len(window_ranges), BATCH_SIZE):
            batch_ranges = window_ranges[start : start + BATCH_SIZE]
            usable = []
            usable_ranges = []
            for begin, end in batch_ranges:
                chunk = speech[begin:end]
                if float(np.sqrt(np.mean(np.square(chunk)))) < SILENCE_RMS:
                    skipped_silent += 1
                    continue
                usable.append(chunk)
                usable_ranges.append((begin, end))
            if not usable:
                continue
            for (begin, end), score in zip(usable_ranges, _score_batch(usable)):
                scored.append({"start": begin / SAMPLE_RATE, "end": end / SAMPLE_RATE, "score": round(score, 4)})
        if not scored:
            return {
                "status": "no_usable_audio", "verdict": None, "score": None,
                "windows": [], "windows_skipped_silent": skipped_silent,
                "window_seconds": _window_seconds, "hop_seconds": _hop_seconds,
                "chunks_analyzed": 0, "calibration_status": _calibration_status,
                "model_label": _model_label, "aggregation": f"{_aggregation_mode}(k={_aggregation_k})",
            }
        scores = [window["score"] for window in scored]
        aggregate = _aggregate(scores)
        return {
            "status": "ran", "score": round(aggregate, 4), "verdict": _verdict(aggregate),
            "threshold_used": _threshold, "uncertain_margin": _margin,
            "calibration_status": _calibration_status, "model_label": _model_label,
            "aggregation": f"{_aggregation_mode}(k={_aggregation_k})",
            "windows": scored, "windows_skipped_silent": skipped_silent,
            "window_seconds": _window_seconds, "hop_seconds": _hop_seconds,
            "chunks_analyzed": len(scored),
        }
    except Exception:
        logger.exception("Audio evaluation failed")
        return {"status": "error", "verdict": None, "score": None}
