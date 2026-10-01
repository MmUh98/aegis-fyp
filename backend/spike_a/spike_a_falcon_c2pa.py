#!/usr/bin/env python3
"""
Aegis - Spike A: Falcon-512 inside a C2PA manifest (hybrid signing feasibility test)

Question this spike answers
    Can a Falcon-512 signature travel inside a C2PA manifest as a CUSTOM ASSERTION,
    and can we verify it independently of c2pa-python?

Hybrid design being tested
    * The C2PA claim itself is signed with a standard ES256 test certificate
      (the C2PA signing-algorithm list does not include Falcon).
    * A Falcon-512 signature over a small payload (author, time, SHA-256 of the
      source file, SHA-256 of the Falcon verification key) is stored in the custom
      assertion `com.aegis.falcon512`. The assertion is part of the claim, so the
      ES256 signature protects it from modification.
    * ONLY the Falcon verification key (vk) and the signature are embedded.
      The Falcon secret key never leaves memory and is never written to disk.

Run from the `backend/spike_a` folder (or anywhere):  python spike_a_falcon_c2pa.py
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import io
import json
import sys
import time
from importlib.metadata import version as pkg_version
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
FALCON_DIR = (HERE.parent / "third_party" / "falcon_py").resolve()
FIXTURES = HERE / "fixtures"
OUT = HERE / "out"

ASSERTION_LABEL = "com.aegis.falcon512"
FALCON512_SIG_LEN = 666  # fixed (zero-padded) signature length for Falcon-512
FALCON512_HEADER = 0x39  # 0x30 + log2(512)

# --- import tprest/falcon.py from the vendored folder -------------------------------
# NOTE: do NOT `pip install falcon` - that is an unrelated web framework with the same name.
if not (FALCON_DIR / "falcon.py").exists():
    sys.exit(f"tprest/falcon.py not found in {FALCON_DIR}. Clone it there first (see the guide).")
sys.path.insert(0, str(FALCON_DIR))
import falcon as _falcon_module  # type: ignore  # noqa: E402

if Path(_falcon_module.__file__).resolve().parent != FALCON_DIR:
    sys.exit(f"Imported the wrong 'falcon' module from {_falcon_module.__file__}")
from falcon import Falcon  # type: ignore  # noqa: E402

sys.path.remove(str(FALCON_DIR))  # its generic module names (common, fft, ...) are already loaded

import c2pa  # noqa: E402
from cryptography.hazmat.backends import default_backend  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

FALCON = Falcon(512)


# ------------------------------------------------------------------ small helpers ---
def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_dummy_jpeg(path: Path) -> None:
    """Create a small synthetic JPEG so the spike needs no external files."""
    w, h = 640, 400
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (x * 255 // w, y * 255 // h, (x + y) * 255 // (w + h))
    ImageDraw.Draw(img).text((20, 20), "Aegis Spike A - dummy image", fill=(255, 255, 255))
    img.save(path, "JPEG", quality=90)


# ------------------------------------------------------------------ Falcon layer ----
def falcon_verify(vk: bytes, message: bytes, signature: bytes) -> bool:
    """Never raises: any malformed input counts as 'invalid'. Silences falcon.py's prints."""
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return bool(FALCON.verify(vk, message, signature))
    except Exception:
        return False


def build_payload(vk: bytes, source_sha256: str) -> bytes:
    """Exact bytes that get Falcon-signed. Stored verbatim (base64) so there is no
    JSON-canonicalisation ambiguity at verification time."""
    payload = {
        "v": 1,
        "alg": "Falcon-512",
        "author": "aegis-test-creator",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_sha256": source_sha256,
        "vk_sha256": sha256_hex(vk),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_assertion(data: dict) -> tuple[bool, str]:
    """Independent verification of the custom assertion (does not use c2pa at all)."""
    try:
        if data.get("alg") != "Falcon-512":
            return False, "unexpected alg"
        vk, payload, sig = b64d(data["vk_b64"]), b64d(data["payload_b64"]), b64d(data["sig_b64"])
        if len(sig) != FALCON512_SIG_LEN or sig[0] != FALCON512_HEADER:
            return False, "unexpected Falcon-512 signature length/header"
        meta = json.loads(payload)
        if meta.get("vk_sha256") != sha256_hex(vk):
            return False, "vk fingerprint in payload does not match the embedded vk"
    except Exception as exc:  # malformed / missing fields
        return False, f"malformed assertion: {exc}"
    if not falcon_verify(vk, payload, sig):
        return False, "Falcon signature invalid"
    return True, "ok"


# ------------------------------------------------------------------ C2PA layer ------
def sign_with_c2pa(src: Path, dst: Path, assertion_data: dict, tsa_url: str | None) -> None:
    certs = (FIXTURES / "es256_certs.pem").read_bytes().decode("utf-8")
    es256_key = serialization.load_pem_private_key(
        (FIXTURES / "es256_private.key").read_bytes(), password=None, backend=default_backend()
    )

    def es256_callback(data: bytes) -> bytes:
        return es256_key.sign(data, ec.ECDSA(hashes.SHA256()))

    manifest = {
        "claim_generator_info": [{"name": "aegis-spike-a", "version": "0.1.0"}],
        "format": "image/jpeg",
        "title": "Aegis Spike A dummy",
        "ingredients": [],
        "assertions": [
            {
                "label": "c2pa.actions",
                "data": {
                    "actions": [
                        {
                            "action": "c2pa.created",
                            "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/digitalCreation",
                        }
                    ]
                },
            },
            {"label": ASSERTION_LABEL, "data": assertion_data},
        ],
    }
    with c2pa.Context() as ctx:
        with c2pa.Signer.from_callback(es256_callback, c2pa.C2paSigningAlg.ES256, certs, tsa_url) as signer:
            with c2pa.Builder(manifest, ctx) as builder:
                builder.sign_file(str(src), str(dst), signer)


def read_report(path: Path) -> dict:
    with c2pa.Context() as ctx:
        with open(path, "rb") as fh:
            with c2pa.Reader("image/jpeg", fh, context=ctx) as reader:
                return json.loads(reader.json())


def active_manifest(report: dict) -> dict:
    return report["manifests"][report["active_manifest"]]


def find_assertion(report: dict, label: str) -> dict | None:
    for assertion in active_manifest(report).get("assertions", []):
        if assertion.get("label", "").startswith(label):
            return assertion.get("data")
    return None


def strip_jumbf_jpeg(jpeg: bytes) -> bytes:
    """Remove every APP11 (0xFFEB) segment - where C2PA's JUMBF manifest lives - so the hash of the
    ORIGINAL bytes can be re-derived from a signed JPEG (verified to be byte-identical for this spike)."""
    if jpeg[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    out, i = bytearray(jpeg[:2]), 2
    while i < len(jpeg):
        if jpeg[i] != 0xFF:
            out += jpeg[i:]
            break
        marker = jpeg[i + 1]
        if marker == 0xDA:  # start of scan: the rest is image data, copy verbatim
            out += jpeg[i:]
            break
        seg_len = int.from_bytes(jpeg[i + 2 : i + 4], "big")
        if marker != 0xEB:
            out += jpeg[i : i + 2 + seg_len]
        i += 2 + seg_len
    return bytes(out)


def binding_ok(signed_bytes: bytes, assertion_data: dict) -> bool:
    """Does the Falcon-signed payload refer to the content this file actually carries?"""
    meta = json.loads(b64d(assertion_data["payload_b64"]))
    return sha256_hex(strip_jumbf_jpeg(signed_bytes)) == meta["source_sha256"]


def status_codes(report: dict) -> list[str]:
    return [s.get("code", "") for s in report.get("validation_status", []) or []]


# ------------------------------------------------------------------ the spike -------
class Results:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append((name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if detail else ""))

    def info(self, text: str) -> None:
        print(f"  [INFO] {text}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tsa-url", default=None, help="optional RFC3161 timestamp authority URL (needs internet)")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    res = Results()
    print(f"c2pa-python {pkg_version('c2pa-python')} / native SDK {c2pa.sdk_version()}")

    # 1. dummy asset ------------------------------------------------------------------
    src, signed = OUT / "dummy.jpg", OUT / "signed.jpg"
    make_dummy_jpeg(src)
    source_sha = sha256_hex(src.read_bytes())
    print(f"\n[1] dummy JPEG written: {src.name} ({src.stat().st_size} bytes)")

    # 2. Falcon-512 keypair -----------------------------------------------------------
    print("\n[2] Falcon-512 keygen (pure Python - takes a few seconds)...")
    t0 = time.perf_counter()
    sk, vk = FALCON.keygen()
    t_keygen = time.perf_counter() - t0
    payload = build_payload(vk, source_sha)
    t0 = time.perf_counter()
    sig = FALCON.sign(sk, payload)
    t_sign = time.perf_counter() - t0
    t0 = time.perf_counter()
    sig_ok = falcon_verify(vk, payload, sig)
    t_verify = time.perf_counter() - t0
    print(f"    keygen {t_keygen:.2f}s | sign {t_sign * 1000:.0f}ms | verify {t_verify * 1000:.0f}ms | "
          f"vk {len(vk)} B | sig {len(sig)} B")
    res.check("Falcon sign/verify round-trip (in memory)", sig_ok)
    del sk  # the secret key is never embedded or written anywhere

    # 3. embed as custom assertion + sign the C2PA claim with ES256 -------------------
    assertion_data = {"alg": "Falcon-512", "vk_b64": b64e(vk), "payload_b64": b64e(payload), "sig_b64": b64e(sig)}
    print(f"\n[3] signing C2PA manifest (ES256 test cert) with custom assertion '{ASSERTION_LABEL}' "
          f"({len(json.dumps(assertion_data))} B of JSON)")
    sign_with_c2pa(src, signed, assertion_data, args.tsa_url)
    res.check("signed file written", signed.exists(), f"{signed.stat().st_size} bytes")

    # 4. read back, verify independently ---------------------------------------------
    print("\n[4] reading the signed file back")
    report = read_report(signed)
    (OUT / "manifest_report.json").write_text(json.dumps(report, indent=2))
    codes = status_codes(report)
    print(f"    validation_state={report.get('validation_state')}  validation_status codes={codes or 'none'}")
    embedded = find_assertion(report, ASSERTION_LABEL)
    res.check("custom assertion survives sign -> read", embedded is not None)
    if embedded is not None:
        ok, why = verify_assertion(embedded)
        res.check("Falcon signature verifies from the embedded assertion", ok, why)
        res.check("embedded data identical to what we signed", embedded == assertion_data)
        res.check("Falcon payload is bound to the file content (APP11-stripped SHA-256 == source_sha256)",
                  binding_ok(signed.read_bytes(), embedded))
    res.check("no hash-mismatch codes on the untouched file", not any("mismatch" in c for c in codes), str(codes))

    # 5. negative tests on the Falcon layer ------------------------------------------
    print("\n[5] negative tests - Falcon layer")
    if embedded is not None:
        bad_payload = dict(embedded)
        raw = bytearray(b64d(embedded["payload_b64"]))
        raw[10] ^= 0x01
        bad_payload["payload_b64"] = b64e(bytes(raw))
        res.check("modified payload is rejected", not verify_assertion(bad_payload)[0])

        bad_key = dict(embedded)
        raw_vk = bytearray(b64d(embedded["vk_b64"]))
        raw_vk[0] ^= 0x01
        bad_key["vk_b64"] = b64e(bytes(raw_vk))
        res.check("modified verification key is rejected", not verify_assertion(bad_key)[0])

        bad_sig = dict(embedded)
        raw_sig = bytearray(b64d(embedded["sig_b64"]))
        raw_sig[100] ^= 0x01  # inside the compressed signature body
        bad_sig["sig_b64"] = b64e(bytes(raw_sig))
        res.check("modified signature is rejected", not verify_assertion(bad_sig)[0])

        pad_sig = dict(embedded)
        raw_pad = bytearray(b64d(embedded["sig_b64"]))
        raw_pad[-1] ^= 0x01  # last byte is zero padding
        pad_sig["sig_b64"] = b64e(bytes(raw_pad))
        padding_malleable = verify_assertion(pad_sig)[0]
        res.info(f"flipping a trailing PADDING byte of the signature still verifies: {padding_malleable} "
                 "(falcon.py does not enforce canonical encoding - never use raw signature bytes as an ID)")

    # 6. negative tests on the C2PA layer ---------------------------------------------
    print("\n[6] negative tests - C2PA layer")
    tampered = OUT / "tampered.jpg"
    data = bytearray(signed.read_bytes())
    data[-2000] ^= 0xFF  # flip a byte inside the image data
    tampered.write_bytes(bytes(data))
    try:
        t_report = read_report(tampered)
        t_codes = status_codes(t_report)
        res.check("pixel tamper is detected by c2pa", any("mismatch" in c for c in t_codes), str(t_codes))
        if embedded is not None:
            res.check("pixel tamper also breaks the Falcon content binding",
                      not binding_ok(tampered.read_bytes(), embedded))
    except Exception as exc:
        res.check("pixel tamper is detected by c2pa", True, f"Reader raised {type(exc).__name__}")

    stripped = OUT / "stripped.jpg"
    Image.open(signed).save(stripped, "JPEG", quality=90)  # re-encode: manifest is lost
    try:
        s_report = read_report(stripped)
        gone = not s_report.get("manifests")
        res.check("re-encoding strips the manifest (expected - triggers the AI fallback path)", gone)
    except Exception as exc:
        res.check("re-encoding strips the manifest (expected - triggers the AI fallback path)", True,
                  f"Reader raised {type(exc).__name__}")

    # 7. summary -----------------------------------------------------------------------
    failed = [r for r in res.rows if not r[1]]
    summary = {
        "c2pa_python": pkg_version("c2pa-python"),
        "falcon_keygen_s": round(t_keygen, 2),
        "falcon_sign_ms": round(t_sign * 1000),
        "falcon_verify_ms": round(t_verify * 1000),
        "vk_bytes": len(vk),
        "sig_bytes": len(sig),
        "assertion_json_bytes": len(json.dumps(assertion_data)),
        "validation_state": report.get("validation_state"),
        "validation_status_codes": codes,
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in res.rows],
    }
    (OUT / "spike_a_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\n{len(res.rows) - len(failed)}/{len(res.rows)} checks passed. Summary: {OUT / 'spike_a_summary.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
