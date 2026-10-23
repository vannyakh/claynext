"""Meaning, naturalness, and emotion/register. No score without human ratings."""
from __future__ import annotations

from typing import Any

from claynext.models.benchmarks.metrics.common import not_scored

_REASON = "no human scores; no string-overlap or model-judge number is computed"


def meaning_metric(human: dict[str, Any] | None = None) -> dict[str, Any]:
    if not human or human.get("value") is None:
        return not_scored("meaning", _REASON)
    return _from_human("meaning", human)


def naturalness_metric(human: dict[str, Any] | None = None) -> dict[str, Any]:
    if not human or human.get("value") is None:
        return not_scored(
            "naturalness",
            "no human ratings; the 4-or-5 naturalness gate is not filled",
        )
    return _from_human("naturalness", human)


def emotion_metric(human: dict[str, Any] | None = None) -> dict[str, Any]:
    if not human or human.get("value") is None:
        return not_scored("emotion_register", _REASON)
    return _from_human("emotion_register", human)


def _from_human(name: str, human: dict[str, Any]) -> dict[str, Any]:
    from claynext.models.benchmarks.metrics.common import metric

    return metric(
        name,
        value=float(human["value"]),
        n=human.get("n"),
        agreement=human.get("agreement"),
        method="human",
        reason="recorded from a supplied human review, not computed by this module",
        details={"source": "human_review"},
    )
