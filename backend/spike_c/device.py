from __future__ import annotations

import logging
import os

import torch

logger = logging.getLogger(__name__)


def resolve_device() -> torch.device:
    choice = os.getenv("AEGIS_DEVICE", "auto").strip().lower()
    if choice not in {"auto", "cpu", "cuda"}:
        raise ValueError(f"AEGIS_DEVICE must be auto, cpu or cuda, got {choice!r}")
    if choice == "cpu":
        return torch.device("cpu")
    if choice == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("AEGIS_DEVICE=cuda but no usable CUDA device was found.")
        return torch.device("cuda")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


DEVICE = resolve_device()


def describe_device() -> dict:
    info = {"device": str(DEVICE), "torch": torch.__version__, "torch_cuda_build": torch.version.cuda}
    if DEVICE.type == "cuda":
        info["gpu"] = torch.cuda.get_device_name(0)
        info["vram_total_mb"] = int(torch.cuda.get_device_properties(0).total_memory / 2**20)
    return info


def log_device_banner() -> None:
    info = describe_device()
    logger.info("Aegis inference device: %s", info)
    if DEVICE.type == "cpu" and torch.version.cuda is not None and os.getenv("AEGIS_DEVICE", "auto") == "auto":
        logger.warning(
            "PyTorch is a CUDA build but no GPU is usable. Running on CPU. "
            "Check the NVIDIA driver (nvidia-smi) if you expected the GPU."
        )
