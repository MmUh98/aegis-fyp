from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_DURATION_SECONDS = 120
N_FRAMES = 8
PROBE_TIMEOUT = 20
FFMPEG_TIMEOUT = 60
ALLOWED_CONTAINER_TOKENS = {"mov", "mp4", "matroska", "webm"}


class MediaError(Exception):
    """A client-safe error for unusable media."""


@dataclass
class MediaInfo:
    duration: float
    has_video: bool
    has_audio: bool


def _run(command: list[str], timeout: int) -> bytes:
    try:
        process = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        logger.error("%s timed out: %s", command[0], command)
        raise MediaError("Media processing timed out.") from error
    if process.returncode != 0:
        logger.error(
            "%s failed (rc=%s): %s",
            command[0],
            process.returncode,
            process.stderr.decode("utf-8", "replace")[-500:],
        )
        raise MediaError("The media file could not be processed.")
    return process.stdout


def probe_media(path: str) -> MediaInfo:
    output = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            path,
        ],
        PROBE_TIMEOUT,
    )
    try:
        data = json.loads(output)
    except json.JSONDecodeError as error:
        raise MediaError("Could not inspect the media file.") from error

    media_format = data.get("format", {})
    tokens = set(str(media_format.get("format_name", "")).split(","))
    if not tokens & ALLOWED_CONTAINER_TOKENS:
        raise MediaError("Unsupported video container.")
    streams = data.get("streams", [])
    has_video = any(
        stream.get("codec_type") == "video" and not stream.get("disposition", {}).get("attached_pic")
        for stream in streams
    )
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    if not has_video:
        raise MediaError("No video stream found.")
    try:
        duration = float(media_format["duration"])
    except (KeyError, TypeError, ValueError) as error:
        raise MediaError("Could not determine video duration.") from error
    if duration <= 0:
        raise MediaError("Invalid video duration.")
    if duration > MAX_DURATION_SECONDS:
        raise MediaError(f"Video is too long. Maximum is {MAX_DURATION_SECONDS} seconds.")
    return MediaInfo(duration=duration, has_video=True, has_audio=has_audio)


def extract_frames(path: str, workdir: str, duration: float, n: int = N_FRAMES) -> list[Path]:
    frames: list[Path] = []
    for index in range(n):
        timestamp = duration * (index + 0.5) / n
        output = Path(workdir) / f"frame_{index:02d}.png"
        try:
            _run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-protocol_whitelist",
                    "file",
                    "-ss",
                    f"{timestamp:.3f}",
                    "-i",
                    path,
                    "-frames:v",
                    "1",
                    "-y",
                    str(output),
                ],
                FFMPEG_TIMEOUT,
            )
        except MediaError:
            continue
        if output.exists() and output.stat().st_size > 0:
            frames.append(output)
    if not frames:
        raise MediaError("Could not extract any frames from the video.")
    return frames


def extract_audio(path: str, workdir: str) -> Path:
    output = Path(workdir) / "audio.wav"
    _run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-i",
            path,
            "-vn",
            "-map",
            "0:a:0",
            "-t",
            str(MAX_DURATION_SECONDS),
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-y",
            str(output),
        ],
        FFMPEG_TIMEOUT,
    )
    if not output.exists() or output.stat().st_size < 1000:
        raise MediaError("The audio track could not be extracted.")
    return output
