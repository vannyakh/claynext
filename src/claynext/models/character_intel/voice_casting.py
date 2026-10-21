"""Voice-profile descriptors used for casting.

A voice cannot establish sex, exact age, or gender identity. These are
optional, uncertain descriptors of how a recording sounds, each with a
confidence, and ``uncertain`` / ``unknown`` are always valid answers.
"""
from __future__ import annotations

from typing import Any

PRESENTATIONS = ("masculine_sounding", "feminine_sounding", "uncertain")
AGE_RANGES = ("child", "teen", "adult", "elder", "unknown")

# How far each gender source can be trusted as a *voice presentation* cue.
_SOURCE_WEIGHT = {
    "manual": 1.0,
    "editor": 1.0,
    "text_intro": 0.75,
    "audio": 0.7,
    "llm": 0.6,
    "text": 0.5,
}
_FALLBACK_WEIGHT = 0.25
UNCERTAIN_BELOW = 0.45


def presentation_from_gender(gender: str) -> str:
    g = str(gender or "").strip().lower()
    if g.startswith("f"):
        return "feminine_sounding"
    if g.startswith("m"):
        return "masculine_sounding"
    return "uncertain"


def gender_from_presentation(presentation: str) -> str:
    """Casting hint only; the studio voice catalog is labelled Female / Male."""
    return {"feminine_sounding": "Female", "masculine_sounding": "Male"}.get(str(presentation or ""), "Unknown")


def line_presentation_weight(seg: dict[str, Any]) -> float:
    if seg.get("gender_manual"):
        return 1.0
    source = str(seg.get("gender_source") or "")
    if source == "audio" or seg.get("audio_gender"):
        try:
            conf = float(seg.get("audio_gender_confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        return max(0.4, min(0.85, conf)) if conf else _SOURCE_WEIGHT["audio"]
    return _SOURCE_WEIGHT.get(source, _FALLBACK_WEIGHT)


def estimate_presentation(lines: list[dict[str, Any]]) -> tuple[str, float]:
    """Weighted vote over a character's lines. Low agreement stays ``uncertain``."""
    votes: dict[str, float] = {}
    total = 0.0
    for seg in lines:
        label = presentation_from_gender(str(seg.get("gender") or ""))
        weight = line_presentation_weight(seg)
        total += weight
        if label != "uncertain":
            votes[label] = votes.get(label, 0.0) + weight
    if not votes or total <= 0:
        return "uncertain", 0.0
    label, score = max(votes.items(), key=lambda kv: kv[1])
    agreement = score / total
    strongest = max(line_presentation_weight(s) for s in lines
                    if presentation_from_gender(str(s.get("gender") or "")) == label)
    confidence = round(min(1.0, agreement * strongest), 3)
    if confidence < UNCERTAIN_BELOW:
        return "uncertain", confidence
    return label, confidence


def pitch_band(pitch_hz: float) -> str:
    try:
        hz = float(pitch_hz or 0.0)
    except (TypeError, ValueError):
        return "unknown"
    if hz <= 0:
        return "unknown"
    if hz < 140:
        return "low"
    if hz < 210:
        return "mid"
    return "high"
