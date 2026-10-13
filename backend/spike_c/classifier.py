from __future__ import annotations

import logging
from typing import Dict

import torch
import torch.nn as nn
from transformers import AutoModel

from spike_c.models.siglip2_base.aegis_common import build_head, forward_backbone

logger = logging.getLogger(__name__)

_STRIP_PREFIXES = ("module.", "vision_model.", "backbone.")


def _normalize_keys(state_dict: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
    normalized = {}
    for key, value in state_dict.items():
        changed = True
        while changed:
            changed = False
            for prefix in _STRIP_PREFIXES:
                if key.startswith(prefix):
                    key = key[len(prefix):]
                    changed = True
        normalized[key] = value
    return normalized


class AegisBaseDetector(nn.Module):
    """The fine-tuned vision tower and MLP head from the Aegis bundle."""

    def __init__(self, model_id: str = "google/siglip2-base-patch16-224"):
        super().__init__()
        full_model = AutoModel.from_pretrained(model_id)
        self.backbone = full_model.vision_model
        del full_model
        hidden_size = self.backbone.config.hidden_size
        self.classifier = build_head("mlp", hidden_size)

    def load_fine_tuned_weights(self, vision_tensors_path: str, head_path: str) -> dict[str, int]:
        raw = torch.load(vision_tensors_path, map_location="cpu", weights_only=True)
        if not isinstance(raw, dict):
            raise TypeError("Vision checkpoint must contain a state-dict mapping")
        vision_sd = _normalize_keys(raw)
        result = self.backbone.load_state_dict(vision_sd, strict=False)
        matched = len(vision_sd) - len(result.unexpected_keys)
        if result.unexpected_keys:
            raise RuntimeError(
                f"{len(result.unexpected_keys)} unexpected vision keys: {result.unexpected_keys[:5]}"
            )
        if matched == 0:
            raise RuntimeError("Vision weight file matched zero backbone parameters")

        head_sd = torch.load(head_path, map_location="cpu", weights_only=True)
        self.classifier.load_state_dict(head_sd, strict=True)
        logger.info(
            "Fine-tuned weights loaded: %d vision tensors applied, %d vision keys left pretrained",
            matched,
            len(result.missing_keys),
        )
        return {
            "vision_tensors_applied": matched,
            "vision_missing_keys": len(result.missing_keys),
            "vision_unexpected_keys": 0,
        }

    def forward(self, **inputs) -> torch.Tensor:
        pooled = forward_backbone(self.backbone, inputs)
        return self.classifier(pooled.float()).squeeze(-1)
