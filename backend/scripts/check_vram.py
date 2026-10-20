from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from spike_c.audio_evaluator import load_audio_detector
from spike_c.evaluator import evaluate_multimodal_deepfake, load_detector

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Load both Aegis detectors and measure peak CUDA memory.")
    parser.add_argument("video", help="Path to a video file to analyze")
    args = parser.parse_args()

    load_detector()
    load_audio_detector()
    result = evaluate_multimodal_deepfake(args.video)
    logger.info("multimodal result: %s", result["verdict"])
    if not torch.cuda.is_available():
        logger.info("CPU-only environment; CUDA VRAM measurement unavailable.")
        return 0
    logger.info("peak CUDA memory: %.1f MB", torch.cuda.max_memory_allocated() / 2**20)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
