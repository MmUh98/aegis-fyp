from __future__ import annotations

import argparse
import csv
import json
import logging
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spike_c.audio_evaluator import SAMPLE_RATE, SILENCE_RMS, make_windows

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _load(model_id: str, revision: str):
    extractor = AutoFeatureExtractor.from_pretrained(model_id, revision=revision, trust_remote_code=False)
    model, loading = AutoModelForAudioClassification.from_pretrained(
        model_id, revision=revision, trust_remote_code=False, output_loading_info=True
    )
    missing = loading.get("missing_keys", [])
    head_missing = [key for key in missing if key.startswith(("classifier.", "projector."))]
    if head_missing:
        raise RuntimeError(f"Classification head was newly initialized: {head_missing[:5]}")
    if model.config.num_labels != 2:
        raise RuntimeError(f"Expected two labels, got {model.config.num_labels}")
    model.eval()
    return extractor, model


def _scores(path: Path, extractor, model) -> list[dict]:
    speech, rate = sf.read(path, dtype="float32", always_2d=False)
    if speech.ndim > 1:
        speech = speech.mean(axis=1)
    if rate != SAMPLE_RATE:
        raise ValueError(f"{path.name} has sample rate {rate}, expected {SAMPLE_RATE}")
    result = []
    for start, end in make_windows(len(speech), 4.0, 2.0, 2.0):
        chunk = speech[start:end]
        if float(np.sqrt(np.mean(np.square(chunk)))) < SILENCE_RMS:
            continue
        inputs = extractor(chunk, sampling_rate=SAMPLE_RATE, return_tensors="pt")
        with torch.inference_mode():
            probabilities = torch.softmax(model(**inputs).logits, dim=-1)[0].tolist()
        result.append({"start": start / SAMPLE_RATE, "end": end / SAMPLE_RATE, "class_scores": probabilities})
    return result


def _aggregate(windows: list[dict], index: int, mode: str) -> float:
    scores = [window["class_scores"][index] for window in windows]
    if not scores:
        return float("nan")
    if mode == "max":
        return max(scores)
    if mode == "mean":
        return float(np.mean(scores))
    return float(np.mean(sorted(scores, reverse=True)[:2]))


def _auc(labels: list[int], scores: list[float]) -> float:
    pairs = [(score, label) for score, label in zip(scores, labels) if np.isfinite(score)]
    positives = sum(label for _, label in pairs)
    negatives = len(pairs) - positives
    if not positives or not negatives:
        return float("nan")
    wins = sum(1 for positive_score, positive_label in pairs if positive_label == 1 for negative_score, negative_label in pairs if negative_label == 0 if positive_score > negative_score)
    ties = sum(1 for positive_score, positive_label in pairs if positive_label == 1 for negative_score, negative_label in pairs if negative_label == 0 if positive_score == negative_score)
    return (wins + 0.5 * ties) / (positives * negatives)


def _remux_aac(source: Path, target: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "color=size=16x16:rate=1", "-i", str(source), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "128k", "-shortest", "-y", str(target)],
        check=True,
        capture_output=True,
    )


def _resample_pcm(source: Path, target: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", "-y", str(target)],
        check=True,
        capture_output=True,
    )


def _extract_runtime_audio(source: Path, target: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-vn", "-map", "0:a:0", "-acodec", "pcm_s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", "-y", str(target)],
        check=True,
        capture_output=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--data-dir", default="sample_data/audio")
    parser.add_argument("--window", type=float, default=4)
    parser.add_argument("--hop", type=float, default=2)
    parser.add_argument("--out", default="reports")
    parser.add_argument("--write-meta", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    extractor, model = _load(args.model_id, args.revision)
    rows = []
    with tempfile.TemporaryDirectory(prefix="aegis_eval_") as work:
        for label, numeric_label in (("real", 0), ("fake", 1)):
            for source in sorted((data_dir / label).glob("*.wav")):
                remuxed = Path(work) / f"{label}_{source.stem}.mp4"
                lossless = Path(work) / f"{label}_{source.stem}_16k.wav"
                aac_audio = Path(work) / f"{label}_{source.stem}_aac.wav"
                _resample_pcm(source, lossless)
                _remux_aac(source, remuxed)
                _extract_runtime_audio(remuxed, aac_audio)
                lossless_windows = _scores(lossless, extractor, model)
                remux_windows = _scores(aac_audio, extractor, model)
                row = {"clip": source.name, "label": label, "numeric_label": numeric_label, "lossless_windows": lossless_windows, "aac_windows": remux_windows}
                for media_key, windows in (("lossless", lossless_windows), ("aac", remux_windows)):
                    for index in (0, 1):
                        for mode in ("max", "top_k_mean", "mean"):
                            row[f"{media_key}_class{index}_{mode}"] = _aggregate(windows, index, mode)
                rows.append(row)

    print("clip,label,lossless_class0_top_k_mean,aac_class0_top_k_mean,lossless_class1_top_k_mean,aac_class1_top_k_mean")
    for row in rows:
        print(f"{row['clip']},{row['label']},{row['lossless_class0_top_k_mean']:.4f},{row['aac_class0_top_k_mean']:.4f},{row['lossless_class1_top_k_mean']:.4f},{row['aac_class1_top_k_mean']:.4f}")

    aucs = {}
    labels = [row["numeric_label"] for row in rows]
    for media_key in ("lossless", "aac"):
        for mode in ("max", "top_k_mean", "mean"):
            for index in (0, 1):
                scores = [row[f"{media_key}_class{index}_{mode}"] for row in rows]
                aucs[f"{media_key}_class{index}_{mode}"] = _auc(labels, scores)
    best_key = max(aucs, key=lambda key: -1 if np.isnan(aucs[key]) else aucs[key])
    fake_index = int(best_key.split("class")[1].split("_")[0])
    best_mode = best_key.split("_")[-1]
    best_media = best_key.split("_")[0]
    best_scores = [row[f"{best_media}_class{fake_index}_{best_mode}"] for row in rows]
    real_scores = [score for row, score in zip(rows, best_scores) if row["label"] == "real"]
    fake_scores = [score for row, score in zip(rows, best_scores) if row["label"] == "fake"]
    if max(real_scores) < min(fake_scores):
        threshold = (max(real_scores) + min(fake_scores)) / 2
        margin = min(0.15, max(0.05, (min(fake_scores) - max(real_scores)) / 4))
    else:
        threshold = sorted({score for score in best_scores if np.isfinite(score)})[len(best_scores) // 2]
        margin = 0.15
        logger.warning("Audio classes overlap; threshold is a minimum-error heuristic on only %d+%d clips.", len(real_scores), len(fake_scores))
    report = {"model_id": args.model_id, "model_revision": args.revision, "window_seconds": args.window, "hop_seconds": args.hop, "clip_count": {"real": len(real_scores), "fake": len(fake_scores)}, "aucs": aucs, "best": {"media": best_media, "mode": best_mode, "fake_label_index": fake_index, "auc_pair_count": len(real_scores) * len(fake_scores), "threshold": threshold, "uncertain_margin": margin}, "rows": rows}
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    stem = out / f"audio_eval_{args.model_id.replace('/', '_')}_{date.today().isoformat()}"
    stem.with_suffix(".json").write_text(json.dumps(report, indent=2, default=lambda value: None if isinstance(value, float) and np.isnan(value) else value))
    with stem.with_suffix(".csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["clip", "label"] + [key for key in rows[0] if key.startswith(("lossless_", "aac_"))])
        writer.writeheader()
        writer.writerows([{key: row.get(key) for key in writer.fieldnames} for row in rows])
    print(json.dumps(report["best"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
