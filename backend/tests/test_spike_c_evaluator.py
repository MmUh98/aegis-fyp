from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.services.decide import C2PAStatus, OnChainRecord
from spike_c import evaluator
from spike_c.classifier import AegisBaseDetector


BUNDLE = Path(__file__).parents[1] / "spike_c" / "models" / "siglip2_base"
SAMPLE = Path(__file__).parents[1] / "spike_c" / "sample_data" / "test_face.png"


def test_weight_load_report_is_clean():
    detector = AegisBaseDetector()
    report = detector.load_fine_tuned_weights(
        str(BUNDLE / "vision_finetuned_tensors.pt"), str(BUNDLE / "head.pt")
    )
    assert report["vision_unexpected_keys"] == 0
    assert report["vision_tensors_applied"] > 0


def test_deterministic_score():
    evaluator.load_detector()
    first = evaluator.evaluate_ai_deepfake(str(SAMPLE))
    second = evaluator.evaluate_ai_deepfake(str(SAMPLE))
    assert first["ai_score"] == second["ai_score"]


@pytest.mark.parametrize("filename", ["real.jpg", "fake.jpg"])
def test_known_examples_if_present(filename):
    path = SAMPLE.parent / filename
    if not path.exists():
        pytest.skip(f"fixture not present: {path}")
    evaluator.load_detector()
    result = evaluator.evaluate_ai_deepfake(str(path))
    assert result["ai_score"] is not None


def test_bad_inputs_are_inconclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluator, "_model", object())
    corrupt = tmp_path / "corrupt.jpg"
    corrupt.write_bytes(b"not an image")
    oversized = tmp_path / "large.jpg"
    oversized.write_bytes(b"0" * (evaluator.MAX_FILE_BYTES + 1))
    for path in (corrupt, tmp_path / "missing.jpg", oversized):
        result = evaluator.evaluate_ai_deepfake(str(path))
        assert result["verdict"] == "INCONCLUSIVE"
        assert result["ai_score"] is None


def _upload() -> UploadFile:
    return UploadFile(
        file=io.BytesIO(b"test"),
        filename="sample.jpg",
        headers=Headers({"content-type": "image/jpeg"}),
    )


def test_c2pa_precedence_skips_ai(monkeypatch):
    from app import main

    called = False

    def fail_ai(_path):
        nonlocal called
        called = True
        raise AssertionError("AI should not run for valid C2PA")

    monkeypatch.setattr(main, "compute_phash", lambda _path: "a" * 16)
    monkeypatch.setattr(main, "verify_c2pa_file", lambda _path: {
        "status": C2PAStatus.VALID,
        "manifest_hash": "manifest",
        "falcon_key_hash": "key",
    })
    monkeypatch.setattr(main, "lookup_on_chain_by_manifest", lambda _hash: OnChainRecord(
        creator_address="0x0", falcon_key_hash="key", manifest_hash="manifest", phash_hex="a" * 16, timestamp=1
    ))
    monkeypatch.setattr(main, "evaluate_multimodal_deepfake", fail_ai)
    result = main.verify_media(_upload())
    assert result.verdict.value == "VERIFIED_AUTHENTIC"
    assert called is False


def test_registry_precedence_skips_ai(monkeypatch):
    from app import main

    called = False

    def fail_ai(_path):
        nonlocal called
        called = True
        raise AssertionError("AI should not run for a registry hit")

    monkeypatch.setattr(main, "compute_phash", lambda _path: "a" * 16)
    monkeypatch.setattr(main, "verify_c2pa_file", lambda _path: {"status": C2PAStatus.ABSENT})
    monkeypatch.setattr(main, "lookup_on_chain_by_manifest", lambda _hash: None)
    monkeypatch.setattr(main, "lookup_on_chain_by_phash", lambda _hash: OnChainRecord(
        creator_address="0x0", falcon_key_hash="key", manifest_hash="manifest", phash_hex="a" * 16, timestamp=1
    ))
    monkeypatch.setattr(main, "evaluate_multimodal_deepfake", fail_ai)
    result = main.verify_media(_upload())
    assert result.verdict.value == "PROVENANCE_STRIPPED"
    assert called is False


def test_missing_weights_raises(tmp_path, monkeypatch):
    original = (evaluator.MODEL_DIR, evaluator.VISION_WEIGHTS, evaluator.HEAD_WEIGHTS, evaluator.META_PATH)
    monkeypatch.setattr(evaluator, "_model", None)
    monkeypatch.setattr(evaluator, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(evaluator, "VISION_WEIGHTS", tmp_path / "vision.pt")
    monkeypatch.setattr(evaluator, "HEAD_WEIGHTS", tmp_path / "head.pt")
    monkeypatch.setattr(evaluator, "META_PATH", tmp_path / "aegis_meta.json")
    with pytest.raises(FileNotFoundError):
        evaluator.load_detector()
    assert original[0] != tmp_path
