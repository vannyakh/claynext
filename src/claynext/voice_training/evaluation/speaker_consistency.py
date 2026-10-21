"""Speaker-consistency stub (embedding similarity deferred)."""
from __future__ import annotations

from collections import Counter
from typing import Any


def score_speaker_consistency(speaker_ids: list[str]) -> dict[str, Any]:
    """
    Offline stub: prefer few, well-populated speakers over fragmented labels.

    Real embedding cosine similarity lands when a speaker encoder is available.
    """
    ids = [s for s in speaker_ids if s]
    if not ids:
        return {"score": 0.0, "method": "label_balance_stub", "speakers": 0}
    counts = Counter(ids)
    n = len(ids)
    # Entropy-ish balance: one dominant speaker scores high for booth recordings.
    top = counts.most_common(1)[0][1] / n
    score = 0.5 * top + 0.5 * (1.0 / max(len(counts), 1))
    return {
        "score": round(min(1.0, score), 4),
        "method": "label_balance_stub",
        "speakers": len(counts),
        "counts": dict(counts),
    }
