"""Emotion / style conditioning stub for expressive TTS training."""
from __future__ import annotations

from typing import Any

from claynext.voice_training.datasets.speech_schema import EMOTIONS, SPEAKING_STYLES


def plan_emotion_conditioning(
    *,
    emotions: list[str] | None = None,
    styles: list[str] | None = None,
) -> dict[str, Any]:
    emos = sorted({e for e in (emotions or list(EMOTIONS)) if e})
    stys = sorted({s for s in (styles or list(SPEAKING_STYLES)) if s})
    return {
        "method": "style_token_stub",
        "emotions": emos,
        "speaking_styles": stys,
        "note": "Emotion conditioning is metadata-only until the trainer is available.",
    }
