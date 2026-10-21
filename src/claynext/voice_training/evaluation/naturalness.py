"""Naturalness / MOS-proxy stub (no listening panel required)."""
from __future__ import annotations

from typing import Any


def score_naturalness(
    *,
    quality_score: float = 0.5,
    duration_sec: float = 1.0,
    has_transcript: bool = True,
) -> dict[str, Any]:
    """Heuristic naturalness proxy from segment metadata."""
    score = 0.4 + 0.4 * max(0.0, min(1.0, quality_score))
    if 0.3 <= duration_sec <= 8.0:
        score += 0.1
    if has_transcript:
        score += 0.1
    score = max(0.0, min(1.0, score))
    return {
        "score": round(score, 4),
        "mos_proxy": round(1.0 + 4.0 * score, 2),
        "method": "metadata_proxy_stub",
    }
