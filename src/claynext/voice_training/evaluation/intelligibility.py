"""Intelligibility metric stub (offline, fixture-safe)."""
from __future__ import annotations

from typing import Any


def score_intelligibility(
    reference_text: str,
    hypothesis_text: str,
    *,
    language: str = "km",
) -> dict[str, Any]:
    """
    Character-level similarity stub (not a production ASR WER).

    Suitable for offline harnesses on consented fixtures.
    """
    ref = (reference_text or "").strip()
    hyp = (hypothesis_text or "").strip()
    if not ref and not hyp:
        return {"score": 1.0, "method": "char_overlap_stub", "language": language}
    if not ref or not hyp:
        return {"score": 0.0, "method": "char_overlap_stub", "language": language}

    ref_set = set(ref)
    hyp_set = set(hyp)
    overlap = len(ref_set & hyp_set) / max(len(ref_set | hyp_set), 1)
    # Length ratio soft penalty.
    ratio = min(len(hyp), len(ref)) / max(len(hyp), len(ref), 1)
    score = 0.7 * overlap + 0.3 * ratio
    return {
        "score": round(score, 4),
        "method": "char_overlap_stub",
        "language": language,
        "ref_len": len(ref),
        "hyp_len": len(hyp),
    }
