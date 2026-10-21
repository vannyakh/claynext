"""Prebuilt Gemini TTS voices suitable for Khmer preview experiments.

Voice names are documented by Google speech-generation docs and marked
``unverified`` until a successful preview call on this machine.
Does not replace Edge / VoxCPM / OmniVoice Studio TTS engines.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GeminiVoice:
    name: str
    gender: str
    notes: str = ""
    khmer_status: str = "unverified"


# Subset of Google prebuilt voices commonly used with Gemini TTS previews.
_VOICES: tuple[GeminiVoice, ...] = (
    GeminiVoice("Kore", "female", "Clear default; probe Khmer at call time"),
    GeminiVoice("Puck", "male", "Bright; probe Khmer at call time"),
    GeminiVoice("Charon", "male", "Informative"),
    GeminiVoice("Fenrir", "male", "Excitable"),
    GeminiVoice("Aoede", "female", "Breezy"),
)


def list_preview_voices() -> list[dict[str, Any]]:
    return [
        {
            "name": v.name,
            "gender": v.gender,
            "notes": v.notes,
            "khmer_status": v.khmer_status,
            "provider": "google_ai_studio_gemini_tts",
            "docs": "https://ai.google.dev/gemini-api/docs/speech-generation",
        }
        for v in _VOICES
    ]


def default_voice() -> str:
    return _VOICES[0].name
