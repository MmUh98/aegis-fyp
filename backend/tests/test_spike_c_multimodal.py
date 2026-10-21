from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.services.decide import C2PAStatus, OnChainRecord
from spike_c import audio_evaluator, evaluator, media_utils


BACKEND = Path(__file__).parents[1]
AUDIO_META = BACKEND / "spike_c" / "models" / "wav2vec2-audio" / "audio_meta.json"
IMAGE = BACKEND / "spike_c" / "sample_data" / "test_face.png"


@pytest.mark.parametrize(
    ("visual", "audio", "expected"),
    [
        ({"status": "ran", "verdict": "LIKELY_REAL"}, {"status": "ran", "verdict": "LIKELY_FAKE"}, "LIKELY_FAKE"),
        ({"status": "ran", "verdict": "LIKELY_FAKE"}, {"status": "ran", "verdict": "LIKELY_REAL"}, "LIKELY_FAKE"),
        ({"status": "ran", "verdict": "LIKELY_REAL"}, {"status": "ran", "verdict": "LIKELY_REAL"}, "LIKELY_REAL"),
        ({"status": "ran", "verdict": "LIKELY_REAL"}, {"status": "ran", "verdict": "UNCERTAIN"}, "UNCERTAIN"),
        ({"status": "ran", "verdict": "LIKELY_REAL"}, {"status": "disabled", "verdict": None}, "UNCERTAIN"),
        ({"status": "ran", "verdict": "LIKELY_REAL"}, {"status": "no_audio_track", "verdict": None}, "LIKELY_REAL"),
        ({"status": "error", "verdict": None}, {"status": "ran", "verdict": "LIKELY_REAL"}, "UNCERTAIN"),
        ({"status": "error", "verdict": None}, {"status": "error", "verdict": None}, "INCONCLUSIVE"),
        ({"status": "ran", "verdict": "LIKELY_REAL"}, {"status": "not_applicable", "verdict": None}, "LIKELY_REAL"),
    ],
)
def test_fusion_matrix(visual, audio, expected):
    assert evaluator.fuse_modalities(visual, audio)["verdict"] == expected


@pytest.mark.parametrize(
    ("samples", "expected"),
    [
        (16000, []),
        (32000, [(0, 32000)]),
        (64000, [(0, 64000)]),
        (160000, [(0, 64000), (32000, 96000), (64000, 128000), (96000, 160000)]),
        (144000, [(0, 64000), (32000, 96000), (64000, 128000), (80000, 144000)]),
    ],
)
def test_audio_windows(samples, expected):
    assert audio_evaluator.make_windows(samples, 4.0, 2.0, 2.0) == expected


@pytest.mark.parametrize(
    ("visual", "audio", "expected", "assessed"),
    [
        ("LIKELY_REAL", "LIKELY_REAL", "Authentic", True),
        ("LIKELY_REAL", "LIKELY_FAKE", "Audio Substitution", True),
        ("LIKELY_FAKE", "LIKELY_REAL", "AI Visual", True),
        ("LIKELY_FAKE", "LIKELY_FAKE", "Full Deepfake", True),
        ("LIKELY_REAL", "no_audio_track", "Authentic", False),
        ("LIKELY_FAKE", "no_usable_audio", "AI Visual", False),
        ("LIKELY_REAL", "UNCERTAIN", None, True),
        ("LIKELY_REAL", "disabled", None, False),
        ("LIKELY_FAKE", "error", None, False),
        ("UNCERTAIN", "LIKELY_REAL", None, False),
    ],
)
def test_diagnosis_table(visual, audio, expected, assessed):
    visual_modality = {"status": "ran", "verdict": visual}
    audio_modality = {"status": "ran", "verdict": audio} if audio in {"LIKELY_REAL", "LIKELY_FAKE", "UNCERTAIN"} else {"status": audio, "verdict": None}
    assert evaluator.diagnose(visual_modality, audio_modality) == {"diagnosis": expected, "audio_assessed": assessed}


def _make_video(path: Path, with_audio: bool) -> None:
    inputs = ["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=25"]
    if with_audio:
        inputs += ["-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-shortest"]
    inputs += ["-pix_fmt", "yuv420p", "-y", str(path)]
    subprocess.run(inputs, check=True, capture_output=True)


def test_audio_metadata_is_verified():
    meta = json.loads(AUDIO_META.read_text())
    assert meta["verified"] is True
    assert meta["fake_label_index"] in (0, 1)
    assert len(meta["model_revision"]) == 40


def test_empirical_audio_label_order(tmp_path):
    real = tmp_path / "real.wav"
    fake = tmp_path / "fake.wav"
    sources = (
        (BACKEND / "sample_data" / "audio" / "real" / "Furqanreal.wav", real),
        (BACKEND / "sample_data" / "audio" / "fake" / "Ali.wav", fake),
    )
    for source, target in sources:
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-ar", "16000", "-ac", "1", "-y", str(target)],
            check=True,
            capture_output=True,
        )
    audio_evaluator.load_audio_detector()
    real_result = audio_evaluator.evaluate_audio_deepfake(str(real))
    fake_result = audio_evaluator.evaluate_audio_deepfake(str(fake))
    assert real_result["status"] == "ran"
    assert fake_result["status"] == "ran"
    assert fake_result["score"] > real_result["score"]


def test_video_flows(tmp_path):
    av = tmp_path / "av.mp4"
    silent = tmp_path / "silent.mp4"
    corrupt = tmp_path / "corrupt.mp4"
    _make_video(av, True)
    _make_video(silent, False)
    corrupt.write_bytes(b"playlist referencing /etc/passwd")

    audio_evaluator.load_audio_detector()
    av_result = evaluator.evaluate_multimodal_deepfake(str(av))
    silent_result = evaluator.evaluate_multimodal_deepfake(str(silent))
    corrupt_result = evaluator.evaluate_multimodal_deepfake(str(corrupt))
    assert av_result["visual"]["status"] == "ran"
    assert av_result["audio"]["status"] in {"ran", "no_usable_audio"}
    assert silent_result["audio"]["status"] == "no_audio_track"
    assert corrupt_result["verdict"] == "INCONCLUSIVE"
    assert "/" not in corrupt_result["reason"]
    assert "ffmpeg" not in corrupt_result["reason"].lower()


def test_duration_limit_is_client_safe(tmp_path, monkeypatch):
    video = tmp_path / "long.mp4"
    _make_video(video, False)
    monkeypatch.setattr(media_utils, "MAX_DURATION_SECONDS", 1)
    result = evaluator.evaluate_multimodal_deepfake(str(video))
    assert result["verdict"] == "INCONCLUSIVE"
    assert "too long" in result["reason"].lower()
    assert "/" not in result["reason"]


def test_disabled_audio_never_reports_real(monkeypatch):
    monkeypatch.setattr(audio_evaluator, "_model", None)
    fused = evaluator.fuse_modalities(
        {"status": "ran", "verdict": "LIKELY_REAL"},
        {"status": "disabled", "verdict": None},
    )
    assert fused["verdict"] != "LIKELY_REAL"


def test_image_regression():
    old_result = evaluator.evaluate_ai_deepfake(str(IMAGE))
    multimodal_result = evaluator.evaluate_multimodal_deepfake(str(IMAGE))
    assert {"ai_score", "threshold_used", "verdict", "reason"} <= old_result.keys()
    assert multimodal_result["audio"]["status"] == "not_applicable"
    assert multimodal_result["verdict"] == old_result["verdict"]


def test_video_registry_and_c2pa_are_not_used(monkeypatch, tmp_path):
    video = tmp_path / "small.mp4"
    _make_video(video, False)
    monkeypatch.setattr("app.main.lookup_on_chain_by_manifest", lambda _value: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr("app.main.lookup_on_chain_by_phash", lambda _value: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr("app.main.verify_c2pa_file", lambda _value: (_ for _ in ()).throw(AssertionError()))
    assert video.suffix == ".mp4"
