"""Emotion / speaking-style annotation helpers for segment rows."""
from __future__ import annotations

from typing import Any

from claynext.voice_training.datasets.speech_schema import EMOTIONS, SPEAKING_STYLES


def normalize_emotion(value: str | None) -> str:
    text = (value or "neutral").strip().lower()
    aliases = {
        "happy": "excited",
        "joy": "excited",
        "mad": "angry",
        "anger": "angry",
        "sorrow": "sad",
        "love": "romantic",
        "funny": "comedy",
        "humor": "comedy",
        "fear": "fearful",
        "": "neutral",
    }
    text = aliases.get(text, text)
    return text if text in EMOTIONS else "other"


def normalize_style(value: str | None) -> str:
    text = (value or "spoken").strip().lower()
    aliases = {
        "colloquial": "spoken",
        "casual": "spoken",
        "slang": "youth_slang",
        "youth": "youth_slang",
        "polite": "formal",
        "general": "normal",
    }
    text = aliases.get(text, text)
    return text if text in SPEAKING_STYLES else "spoken"


def apply_annotation(
    segment: dict[str, Any],
    *,
    emotion: str | None = None,
    speaking_style: str | None = None,
    speaker_id: str | None = None,
    dialect: str | None = None,
    slang_level: float | None = None,
    rudeness_level: float | None = None,
) -> dict[str, Any]:
    row = dict(segment)
    if emotion is not None:
        row["emotion"] = normalize_emotion(emotion)
    if speaking_style is not None:
        row["speaking_style"] = normalize_style(speaking_style)
    if speaker_id is not None:
        row["speaker_id"] = str(speaker_id)
    if dialect is not None:
        row["dialect"] = str(dialect)
    if slang_level is not None:
        row["slang_level"] = max(0.0, min(1.0, float(slang_level)))
    if rudeness_level is not None:
        row["rudeness_level"] = max(0.0, min(1.0, float(rudeness_level)))
    return row
