"""KSLD AI providers (Google AI Studio Gemini teacher + Gemini TTS)."""
from __future__ import annotations

from claynext.models.khmer_spoken.providers.google_gemini_provider import (
    GeminiTeacherProvider,
    GeminiTeacherResult,
)
from claynext.models.khmer_spoken.providers.google_tts_provider import (
    GeminiTtsPreviewResult,
    GeminiTtsProvider,
)

__all__ = [
    "GeminiTeacherProvider",
    "GeminiTeacherResult",
    "GeminiTtsProvider",
    "GeminiTtsPreviewResult",
]
