from pathlib import Path

import cv2
import imagehash
from PIL import Image


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


def compute_image_phash(file_path: str) -> str:
    with Image.open(file_path) as image:
        return str(imagehash.phash(image.convert("RGB")))


def compute_video_phash(file_path: str, num_frames: int = 5) -> str:
    if num_frames <= 0:
        raise ValueError("num_frames must be positive")

    capture = cv2.VideoCapture(file_path)
    try:
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            raise ValueError(f"Unable to read frames from video file: {file_path}")

        frame_indices = [int(i * (total_frames - 1) / max(num_frames - 1, 1)) for i in range(num_frames)]
        hashes = []
        for index in frame_indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            success, frame = capture.read()
            if success:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                hashes.append(imagehash.phash(Image.fromarray(rgb_frame)))
    finally:
        capture.release()

    if not hashes:
        raise ValueError("Failed to extract any valid frames for video pHash calculation")
    return str(hashes[len(hashes) // 2])


def compute_phash(file_path: str) -> str:
    if Path(file_path).suffix.lower() in VIDEO_EXTENSIONS:
        return compute_video_phash(file_path)
    return compute_image_phash(file_path)


def hamming_distance(hash1_hex: str, hash2_hex: str) -> int:
    return imagehash.hex_to_hash(hash1_hex) - imagehash.hex_to_hash(hash2_hex)
