"""Leaderboard listing. Rows are not ranked, and nothing is promoted by default."""
from __future__ import annotations

from typing import Any


def leaderboard(entries: list[dict[str, Any]]) -> dict[str, Any]:
    promoted = [
        entry.get("candidate_id")
        for entry in entries
        if (entry.get("promotion") or {}).get("promoted") is True
    ]
    return {
        "ranked": False,
        "reason": "automatic metrics are not a ranking; promotion requires the human gate",
        "rows": list(entries),
        "promoted_model_id": promoted[0] if len(promoted) == 1 else None,
        "promoted_ids": promoted,
    }
