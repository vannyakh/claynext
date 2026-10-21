"""Emotion-Aware Dialogue Naturalizer (milestone 1: constraints only).

Milestone 1 does not rewrite text. It turns a line's emotion, the
character's register, and the level decision into constraints the
``movie.khmer_natural_dialogue`` skill receives. A rewrite pass that proposes
naturalized variants and checks them against meaning is planned for a later
milestone (see docs/khmer-localization/DESIGN.md).
"""
from __future__ import annotations

from typing import Any

from claynext.models.khmer_localization.slang import LevelDecision
from claynext.models.khmer_localization.speech_profile import SpeechProfile

_INTENSE = {"angry", "furious", "rage", "shouting", "terrified", "sobbing", "ecstatic"}
_SOFT = {"whisper", "sad", "tender", "affectionate", "shy", "tired"}


def line_constraints(
    *,
    emotion: str,
    register: str,
    levels: LevelDecision,
    profile: SpeechProfile | None = None,
) -> dict[str, Any]:
    emotion = (emotion or "neutral").strip().lower()
    intensity = "high" if emotion in _INTENSE else "low" if emotion in _SOFT else "medium"
    return {
        "emotion": emotion,
        "intensity": intensity,
        "register": register,
        "slang_max": levels.allowed_slang,
        "profanity_max": levels.allowed_profanity,
        "source_profanity": levels.source_profanity,
        "keep_intensity": True,
        "catchphrases": list((profile.catchphrases if profile else [])[:3]),
    }


class EmotionAwareNaturalizer:
    """Interface for the later rewrite pass."""

    def naturalize(self, line: dict[str, Any], constraints: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError("Naturalizer rewrites are planned after milestone 1")
