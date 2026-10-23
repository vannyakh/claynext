"""Fixed human rubric. Scores stay empty until reviewers submit them."""
from __future__ import annotations

from typing import Any

RUBRIC_VERSION = "khmer-movie-rubric-1"
DIMENSIONS = (
    "meaning",
    "natural_khmer",
    "pronoun",
    "emotion_register",
    "terminology",
    "structured_output",
)
NATURAL_PASS_MIN = 4


def empty_uncertainty() -> dict[str, Any]:
    return {"n": None, "agreement": None, "reviewers": []}


def reviewer_ids(items: list[dict[str, Any]]) -> list[str]:
    found: list[str] = []
    for item in items:
        for score in item.get("scores") or []:
            reviewer = str(score.get("reviewer_id") or "")
            if reviewer and reviewer not in found:
                found.append(reviewer)
    return found


def item_disagreements(item: dict[str, Any]) -> list[str]:
    """Dimensions where reviewers differ and nobody has adjudicated."""
    adjudication = item.get("adjudication") or {}
    by_dim: dict[str, list[Any]] = {}
    for score in item.get("scores") or []:
        dim = str(score.get("dimension") or "")
        if not dim:
            continue
        if dim == "natural_khmer":
            value = score.get("rating")
        else:
            value = score.get("passed")
        if value is None:
            continue
        by_dim.setdefault(dim, []).append(value)
    open_dims: list[str] = []
    for dim, values in by_dim.items():
        if len(set(values)) > 1 and dim not in adjudication:
            open_dims.append(dim)
    return sorted(open_dims)


def agreement(items: list[dict[str, Any]]) -> float | None:
    """Share of reviewer pairs that match. Null when no human scores exist."""
    if not items or not reviewer_ids(items):
        return None
    compared = 0
    matched = 0
    for item in items:
        by_dim: dict[str, list[Any]] = {}
        for score in item.get("scores") or []:
            dim = str(score.get("dimension") or "")
            value = score.get("rating") if dim == "natural_khmer" else score.get("passed")
            if dim and value is not None:
                by_dim.setdefault(dim, []).append(value)
        for values in by_dim.values():
            if len(values) < 2:
                continue
            compared += 1
            if len(set(values)) == 1:
                matched += 1
    if compared == 0:
        return None
    return matched / compared


def uncertainty(items: list[dict[str, Any]] | None) -> dict[str, Any]:
    if not items:
        return empty_uncertainty()
    reviewers = reviewer_ids(items)
    if not reviewers:
        return empty_uncertainty()
    return {
        "n": len(items),
        "agreement": agreement(items),
        "reviewers": reviewers,
    }
