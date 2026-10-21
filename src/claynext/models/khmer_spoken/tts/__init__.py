"""Gemini TTS voice registry and Khmer pronunciation checks for KSLD previews."""
from __future__ import annotations

from claynext.models.khmer_spoken.tts.gemini_voice_registry import list_preview_voices
from claynext.models.khmer_spoken.tts.khmer_pronunciation_evaluator import (
    evaluate_pronunciation_text,
)

__all__ = ["list_preview_voices", "evaluate_pronunciation_text"]
