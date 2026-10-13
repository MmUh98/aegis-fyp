"""aegis_common.py - the Aegis deepfake-detector INFERENCE CONTRACT.

This exact file is written by the training notebook and must be copied into the
backend next to the exported weights. Training and serving import the same code,
so frame sampling, face cropping, JPEG round-trip, preprocessing, model wiring and
score aggregation cannot drift apart.

CLI (local test / benchmark):
    python aegis_common.py --bundle ./aegis_bundle --image face.jpg
    python aegis_common.py --bundle ./aegis_bundle --video clip.mp4
    python aegis_common.py --bundle ./aegis_bundle --benchmark
"""
import argparse
import gc
import inspect
import io
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from PIL import Image, ImageOps

CONTRACT_VERSION = 1
LABELS = {"real": 0, "fake": 1}
JPEG_QUALITY = 95
BATCH_KEYS = ("pixel_values", "pixel_attention_mask", "spatial_shapes")


# ----------------------------------------------------------------------------- faces
class FaceDetector:
    """MTCNN (facenet-pytorch) when installed, otherwise an OpenCV Haar cascade."""

    def __init__(self, device="cpu", max_side=640, min_conf=0.90):
        self.max_side, self.min_conf = max_side, min_conf
        self.kind, self.mtcnn, self.haar = "haar", None, None
        try:
            from facenet_pytorch import MTCNN

            self.mtcnn = MTCNN(keep_all=True, device=device, post_process=False)
            self.kind = "mtcnn"
        except Exception:
            if hasattr(cv2, "CascadeClassifier"):
                self.haar = cv2.CascadeClassifier(
                    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                )
            else:  # OpenCV 5.x dropped the cascade classifier
                import warnings

                warnings.warn("No face detector available (install facenet-pytorch or opencv<5): centre crops only")
                self.kind = "none"

    def detect(self, rgb):
        """Largest face as [x1, y1, x2, y2] in original pixel coordinates, or None."""
        if self.kind == "none":
            return None
        h, w = rgb.shape[:2]
        s = min(1.0, self.max_side / max(h, w))
        small = cv2.resize(rgb, (max(1, int(w * s)), max(1, int(h * s)))) if s < 1 else rgb
        if self.kind == "mtcnn":
            boxes, probs = self.mtcnn.detect(Image.fromarray(small))
            if boxes is None:
                return None
            keep = [b for b, p in zip(boxes, probs) if p is not None and p >= self.min_conf]
            if not keep:
                return None
            b = max(keep, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        else:
            gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
            faces = self.haar.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
            if len(faces) == 0:
                return None
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            b = [x, y, x + fw, y + fh]
        return [float(v) / s for v in b]


def crop_square(rgb, box, margin=0.3, size=224):
    """Square crop around the face box (+margin); centre crop of the frame if box is None."""
    h, w = rgb.shape[:2]
    if box is None:
        side = min(h, w)
        cx, cy = w / 2.0, h / 2.0
        half = side / 2.0
        x1, y1 = int(round(cx - half)), int(round(cy - half))
        crop = rgb[y1 : y1 + side, x1 : x1 + side]
    else:
        bx1, by1, bx2, by2 = box
        cx, cy = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0
        half = max(bx2 - bx1, by2 - by1) * (1.0 + margin) / 2.0
        x1, y1 = int(round(cx - half)), int(round(cy - half))
        x2, y2 = int(round(cx + half)), int(round(cy + half))
        pad = int(half) + 2
        padded = cv2.copyMakeBorder(rgb, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        crop = padded[y1 + pad : y2 + pad, x1 + pad : x2 + pad]
    if crop.size == 0:
        crop = rgb
    interp = cv2.INTER_AREA if crop.shape[0] > size else cv2.INTER_CUBIC
    return cv2.resize(crop, (size, size), interpolation=interp)


def prepare_crop(rgb, detector, margin=0.3, size=224):
    box = detector.detect(rgb) if detector is not None else None
    return crop_square(rgb, box, margin, size), box is not None


def encode_jpeg(rgb, quality=JPEG_QUALITY):
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return buf.tobytes()


def decode_jpeg(data):
    return Image.open(io.BytesIO(data)).convert("RGB")


def load_rgb(src):
    """Path / bytes / PIL image -> RGB uint8 array (EXIF orientation applied)."""
    if isinstance(src, Image.Image):
        img = src
    elif isinstance(src, (bytes, bytearray)):
        img = Image.open(io.BytesIO(src))
    else:
        img = Image.open(src)
    return np.array(ImageOps.exif_transpose(img).convert("RGB"))


# ----------------------------------------------------------------------------- video
def sample_indices(n_frames, k):
    if n_frames <= 0:
        return []
    k = min(k, n_frames)
    return sorted(set(np.linspace(0, n_frames - 1, k).round().astype(int).tolist()))


def read_video_frames(path, k=16):
    """k uniformly spaced RGB frames. Returns (frames, frame_indices)."""
    cap = cv2.VideoCapture(str(path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if n <= 0:  # unknown length: count by decoding
        n = 0
        while cap.grab():
            n += 1
        cap.release()
        cap = cv2.VideoCapture(str(path))
    want = set(sample_indices(n, k))
    frames, idxs, i = [], [], 0
    last = max(want) if want else -1
    while i <= last:
        if not cap.grab():
            break
        if i in want:
            ok, bgr = cap.retrieve()
            if ok:
                frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                idxs.append(i)
        i += 1
    cap.release()
    return frames, idxs


def aggregate(probs, method="mean", topk_frac=0.3):
    p = np.asarray(probs, dtype=float)
    if p.size == 0:
        return float("nan")
    if method == "mean":
        return float(p.mean())
    if method == "median":
        return float(np.median(p))
    if method == "topk":
        k = max(1, int(math.ceil(topk_frac * len(p))))
        return float(np.sort(p)[-k:].mean())
    raise ValueError(f"unknown aggregator {method}")


# ----------------------------------------------------------------------------- model
def load_backbone_and_processor(model_id, revision=None):
    """SigLIP-2 vision tower only (text tower is dropped) + its image processor."""
    from transformers import AutoImageProcessor, AutoModel

    full = AutoModel.from_pretrained(model_id, revision=revision)
    backbone = full.vision_model
    del full
    gc.collect()
    processor = AutoImageProcessor.from_pretrained(model_id, revision=revision)
    return backbone, processor


def to_batch(processor, images):
    enc = processor(images=images, return_tensors="pt")
    return {k: enc[k] for k in BATCH_KEYS if k in enc}


def to_device(batch, device):
    return {k: v.to(device, non_blocking=True) for k, v in batch.items()}


def forward_backbone(backbone, batch):
    """Pooled image feature (B, hidden). Adapts to the checkpoint family:
    fixed-resolution SigLIP-2 checkpoints use the plain SigLIP vision tower (pixel_values only), NaFlex
    checkpoints also need pixel_attention_mask + spatial_shapes (the mask argument is called
    pixel_attention_mask or attention_mask depending on the transformers version)."""
    params = inspect.signature(backbone.forward).parameters
    kw = {"pixel_values": batch["pixel_values"]}
    if "spatial_shapes" in params and "spatial_shapes" in batch:
        kw["spatial_shapes"] = batch["spatial_shapes"]
    mask = batch.get("pixel_attention_mask")
    if mask is not None:
        for key in ("pixel_attention_mask", "attention_mask"):
            if key in params:
                kw[key] = mask
                break
    out = backbone(**kw)
    pooled = getattr(out, "pooler_output", None)
    if pooled is None:  # model built without the attention-pooling head
        h = out.last_hidden_state
        if mask is not None:
            m = mask.unsqueeze(-1).to(h.dtype)
            pooled = (h * m).sum(1) / m.sum(1).clamp(min=1)
        else:
            pooled = h.mean(1)
    return pooled


def build_head(kind, hidden, p_drop=0.3):
    if kind == "linear":
        return nn.Sequential(nn.LayerNorm(hidden), nn.Linear(hidden, 1))
    if kind == "mlp":
        return nn.Sequential(
            nn.LayerNorm(hidden), nn.Linear(hidden, 256), nn.GELU(), nn.Dropout(p_drop), nn.Linear(256, 1)
        )
    raise ValueError(kind)


class AegisModel(nn.Module):
    """frame batch -> one logit per frame (>0 means 'fake')."""

    def __init__(self, backbone, head):
        super().__init__()
        self.backbone, self.head = backbone, head

    def forward(self, batch):
        return self.head(forward_backbone(self.backbone, batch).float()).squeeze(-1)


# ----------------------------------------------------------------------------- predictor
class AegisPredictor:
    def __init__(self, bundle_dir, device=None, backbone=None, processor=None, detector=None, batch_size=32):
        self.dir = Path(bundle_dir)
        self.meta = json.loads((self.dir / "aegis_meta.json").read_text())
        assert self.meta["contract_version"] == CONTRACT_VERSION, "contract version mismatch"
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        if backbone is None or processor is None:
            backbone, processor = load_backbone_and_processor(self.meta["model_id"], self.meta.get("revision"))
        if self.meta.get("finetuned_state"):
            state = torch.load(self.dir / self.meta["finetuned_state"], map_location="cpu")
            res = backbone.load_state_dict(state, strict=False)
            assert not res.unexpected_keys, f"unexpected keys: {res.unexpected_keys}"
        head = build_head(self.meta["head"]["kind"], self.meta["head"]["hidden"])
        head.load_state_dict(torch.load(self.dir / "head.pt", map_location="cpu"))
        self.model = AegisModel(backbone, head).to(self.device).eval()
        self.processor = processor
        self.detector = detector if detector is not None else FaceDetector(device=str(self.device))
        self.batch_size = batch_size
        self.pre = self.meta["preprocessing"]

    @torch.no_grad()
    def predict_pils(self, pils):
        out = []
        for i in range(0, len(pils), self.batch_size):
            batch = to_device(to_batch(self.processor, pils[i : i + self.batch_size]), self.device)
            with torch.autocast(self.device.type, dtype=torch.float16, enabled=self.device.type == "cuda"):
                logits = self.model(batch)
            out.append(torch.sigmoid(logits.float()).cpu().numpy())
        return np.concatenate(out) if out else np.zeros(0)

    def _crop(self, rgb):
        crop, found = prepare_crop(rgb, self.detector, self.pre["face_margin"], self.pre["crop_size"])
        return decode_jpeg(encode_jpeg(crop, self.pre["jpeg_quality"])), found

    def predict_image(self, image):
        pil, found = self._crop(load_rgb(image))
        p = float(self.predict_pils([pil])[0])
        thr = self.meta["thresholds"]["frame"]
        return {"prob_fake": p, "is_fake": p >= thr, "threshold": thr, "face_found": found}

    def predict_video(self, path):
        frames, _ = read_video_frames(path, self.pre["frames_per_video"])
        pils, found = [], 0
        for rgb in frames:
            pil, f = self._crop(rgb)
            if self.pre["drop_no_face_frames"] and not f:
                continue
            pils.append(pil)
            found += int(f)
        if len(pils) < 1:
            return {"prob_fake": None, "is_fake": None, "reason": "no_usable_frames", "n_frames": 0}
        probs = self.predict_pils(pils)
        agg = self.meta["video_aggregator"]
        score = aggregate(probs, agg)
        thr = self.meta["thresholds"]["video"]
        return {
            "prob_fake": score, "is_fake": score >= thr, "threshold": thr, "aggregator": agg,
            "n_frames": len(pils), "faces_found": found, "frame_probs": probs.tolist(),
        }


def benchmark(pred, n=50):
    pil = Image.fromarray(np.random.randint(0, 255, (pred.pre["crop_size"],) * 2 + (3,), dtype=np.uint8))
    pred.predict_pils([pil] * pred.batch_size)  # warm-up
    if pred.device.type == "cuda":
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
    t = time.perf_counter()
    for _ in range(n):
        pred.predict_pils([pil] * pred.batch_size)
    if pred.device.type == "cuda":
        torch.cuda.synchronize()
    dt = (time.perf_counter() - t) / (n * pred.batch_size)
    res = {"ms_per_frame": round(dt * 1000, 2), "batch_size": pred.batch_size, "device": str(pred.device)}
    if pred.device.type == "cuda":
        res["peak_vram_mb"] = round(torch.cuda.max_memory_allocated() / 2**20, 1)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--image")
    ap.add_argument("--video")
    ap.add_argument("--benchmark", action="store_true")
    a = ap.parse_args()
    pred = AegisPredictor(a.bundle)
    if a.image:
        print(json.dumps(pred.predict_image(a.image), indent=2))
    if a.video:
        r = pred.predict_video(a.video)
        r.pop("frame_probs", None)
        print(json.dumps(r, indent=2))
    if a.benchmark:
        print(json.dumps(benchmark(pred), indent=2))


if __name__ == "__main__":
    main()
