import os
import warnings

import cv2
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor

warnings.filterwarnings("ignore", category=UserWarning)

MODEL_ID = "google/siglip2-base-patch16-224"
LABELS = [
    "a real, authentic photograph of a human face",
    "a manipulated deepfake or AI-generated face",
]

print(f"Loading SigLIP-2 model ({MODEL_ID}) into memory...")
processor = AutoProcessor.from_pretrained(MODEL_ID)
model = AutoModel.from_pretrained(MODEL_ID)
model.eval()

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
print(f"Model loaded successfully on {device.type.upper()}.")


def extract_frame_from_video(
    video_path: str, frame_position: float = 0.5
) -> Image.Image:
    """Extract one RGB frame from a video at a fractional position."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not 0.0 <= frame_position <= 1.0:
        raise ValueError("frame_position must be between 0.0 and 1.0")

    capture = cv2.VideoCapture(video_path)
    try:
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            raise ValueError(f"Video has no readable frames: {video_path}")

        target_frame = min(int(total_frames * frame_position), total_frames - 1)
        capture.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        success, frame = capture.read()
    finally:
        capture.release()

    if not success:
        raise ValueError(f"Failed to extract frame from video: {video_path}")

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return Image.fromarray(frame_rgb)


def calculate_deepfake_score(image: Image.Image) -> float:
    """Return the zero-shot probability that an image is manipulated."""
    inputs = processor(
        text=LABELS,
        images=image,
        padding="max_length",
        truncation=True,
        return_tensors="pt",
    ).to(device)

    with torch.no_grad():
        outputs = model(**inputs)

    probabilities = torch.nn.functional.softmax(outputs.logits_per_image, dim=1)
    return probabilities[0][1].item()


if __name__ == "__main__":
    print("\n--------------------------------------------------")
    print("Initializing Spike C benchmark test...")

    test_image_path = os.path.join("sample_data", "test_face.png")
    if not os.path.exists(test_image_path):
        dummy_image = Image.new("RGB", (224, 224), color=(192, 128, 128))
        dummy_image.save(test_image_path)
        print(f"Created placeholder image at {test_image_path}")

    try:
        image = Image.open(test_image_path).convert("RGB")
        score = calculate_deepfake_score(image)

        print("Inference complete:")
        print(f"   Target: {test_image_path}")
        print(f"   Deepfake probability: {score:.4f} ({score * 100:.2f}%)")
        if score > 0.5:
            print("   Verdict: MANIPULATED (failed AI verification)")
        else:
            print("   Verdict: AUTHENTIC (passed AI verification)")
    except Exception as error:
        print(f"Error during inference: {error}")
