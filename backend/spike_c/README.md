# Spike C: AI Verification

AI verification layer using Google's SigLIP-2 model through Hugging Face Transformers.

The module accepts images, extracts frames from videos, and returns a zero-shot probability score indicating whether an image is likely manipulated.

## Model

- Model: `google/siglip2-base-patch16-224`
- Runtime: PyTorch
- Video processing: OpenCV
- Image processing: Pillow

## Installation

From the repository root:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
cd spike_c
pip install -r requirements.txt
```

## Usage

Run the benchmark test:

```bash
cd backend/spike_c
python spike_c_siglip2.py
```

The first run downloads the SigLIP-2 model from Hugging Face and caches it locally.

## Image Inference

```python
from PIL import Image
from spike_c_siglip2 import calculate_deepfake_score

image = Image.open("path/to/image.jpg").convert("RGB")
score = calculate_deepfake_score(image)

print(f"Deepfake probability: {score:.4f}")
```

A score closer to `1.0` indicates a higher likelihood of manipulation.

## Video Frame Extraction

```python
from spike_c_siglip2 import (
    extract_frame_from_video,
    calculate_deepfake_score,
)

frame = extract_frame_from_video(
    "path/to/video.mp4",
    frame_position=0.5,
)

score = calculate_deepfake_score(frame)
print(f"Deepfake probability: {score:.4f}")
```

`frame_position` must be between `0.0` and `1.0`:

- `0.0`: first frame
- `0.5`: middle frame
- `1.0`: final frame

## Hardware

The module automatically uses:

- CUDA GPU when available
- CPU otherwise

## Project Structure

```text
spike_c/
├── README.md
├── requirements.txt
├── spike_c_siglip2.py
└── sample_data/
```

## Notes

This is a zero-shot research benchmark. The returned probability is based on the model's text-image similarity and should not be treated as a production forensic determination without dataset-specific validation.
