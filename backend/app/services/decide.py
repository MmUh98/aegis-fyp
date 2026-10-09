from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    VERIFIED_AUTHENTIC = "VERIFIED_AUTHENTIC"
    SIGNED_UNVERIFIED_SIGNER = "SIGNED_UNVERIFIED_SIGNER"
    TAMPERED = "TAMPERED"
    PROVENANCE_STRIPPED = "PROVENANCE_STRIPPED"
    LIKELY_REAL = "LIKELY_REAL"
    LIKELY_FAKE = "LIKELY_FAKE"
    INCONCLUSIVE = "INCONCLUSIVE"


class C2PAStatus(str, Enum):
    VALID = "VALID"
    TAMPERED = "TAMPERED"
    ABSENT = "ABSENT"


class OnChainRecord(BaseModel):
    creator_address: str
    falcon_key_hash: str
    manifest_hash: str
    phash_hex: str
    timestamp: int


class DecisionResult(BaseModel):
    verdict: Verdict
    confidence_score: float = Field(ge=0.0, le=1.0)
    reason: str
    c2pa_status: C2PAStatus
    on_chain_match: bool
    phash_distance: Optional[int] = None
    ai_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


def decide(
    c2pa_status: C2PAStatus,
    manifest_hash: Optional[str] = None,
    falcon_key_hash: Optional[str] = None,
    on_chain_record: Optional[OnChainRecord] = None,
    phash_distance: Optional[int] = None,
    phash_threshold: int = 10,
    ai_score: Optional[float] = None,
    ai_error: bool = False,
) -> DecisionResult:
    """Evaluate evidence without I/O, mutation, or exceptions for normal bad input."""
    if c2pa_status == C2PAStatus.TAMPERED:
        return DecisionResult(
            verdict=Verdict.TAMPERED,
            confidence_score=1.0,
            reason="C2PA manifest signature or embedded payload hash digest mismatch.",
            c2pa_status=c2pa_status,
            on_chain_match=False,
        )

    if c2pa_status == C2PAStatus.VALID:
        registered = (
            on_chain_record is not None
            and bool(falcon_key_hash)
            and bool(manifest_hash)
            and on_chain_record.falcon_key_hash.casefold() == falcon_key_hash.casefold()
            and on_chain_record.manifest_hash.casefold() == manifest_hash.casefold()
        )
        if registered:
            return DecisionResult(
                verdict=Verdict.VERIFIED_AUTHENTIC,
                confidence_score=1.0,
                reason="Cryptographic C2PA manifest and Falcon key fingerprint verified against the on-chain registry.",
                c2pa_status=c2pa_status,
                on_chain_match=True,
                phash_distance=phash_distance,
            )
        return DecisionResult(
            verdict=Verdict.SIGNED_UNVERIFIED_SIGNER,
            confidence_score=0.75,
            reason="Valid C2PA signature detected, but signer key or manifest is not registered on AegisRegistry.",
            c2pa_status=c2pa_status,
            on_chain_match=False,
            phash_distance=phash_distance,
        )

    if c2pa_status == C2PAStatus.ABSENT:
        if phash_distance is not None and phash_distance <= phash_threshold:
            return DecisionResult(
                verdict=Verdict.PROVENANCE_STRIPPED,
                confidence_score=0.90,
                reason=(
                    f"Perceptual fingerprint matches a registered original "
                    f"(Hamming distance {phash_distance} <= {phash_threshold}), but the C2PA manifest was removed."
                ),
                c2pa_status=c2pa_status,
                on_chain_match=True,
                phash_distance=phash_distance,
            )
        if ai_error or ai_score is None or not 0.0 <= ai_score <= 1.0:
            return DecisionResult(
                verdict=Verdict.INCONCLUSIVE,
                confidence_score=0.0,
                reason="No usable provenance evidence was found, and AI analysis failed or was skipped.",
                c2pa_status=c2pa_status,
                on_chain_match=False,
            )
        if 0.35 <= ai_score <= 0.65:
            return DecisionResult(
                verdict=Verdict.INCONCLUSIVE,
                confidence_score=round(1.0 - abs(ai_score - 0.5) * 2, 4),
                reason=f"SigLIP-2 manipulation probability ({ai_score:.2f}) is in the ambiguous zone [0.35, 0.65].",
                c2pa_status=c2pa_status,
                on_chain_match=False,
                ai_score=ai_score,
            )
        if ai_score > 0.65:
            return DecisionResult(
                verdict=Verdict.LIKELY_FAKE,
                confidence_score=round(ai_score, 4),
                reason=f"AI model flagged visual manipulation anomalies (SigLIP-2 score: {ai_score:.2f}).",
                c2pa_status=c2pa_status,
                on_chain_match=False,
                ai_score=ai_score,
            )
        return DecisionResult(
            verdict=Verdict.LIKELY_REAL,
            confidence_score=round(1.0 - ai_score, 4),
            reason=f"No manipulation detected by AI model (SigLIP-2 score: {ai_score:.2f}).",
            c2pa_status=c2pa_status,
            on_chain_match=False,
            ai_score=ai_score,
        )

    return DecisionResult(
        verdict=Verdict.INCONCLUSIVE,
        confidence_score=0.0,
        reason="Unhandled verification state.",
        c2pa_status=C2PAStatus.ABSENT,
        on_chain_match=False,
    )
