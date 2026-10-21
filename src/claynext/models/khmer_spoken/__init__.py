"""Khmer Spoken Language Dataset (KSLD) — Gemini teacher milestone.

Platform map
------------
1. **Google AI Studio / Gemini API** — teacher + optional TTS previews (this package).
2. **Google Cloud Vertex AI** — supervised fine-tuning stub (separate credentials).
3. **Local LoRA/QLoRA** — separate stub entrypoint.
4. **voice_training** — speech audio / voice cloning (do not import here for training).

Synthetic candidates ≠ gold. Native Khmer human review required for gold export.
"""
from __future__ import annotations

from claynext.models.khmer_spoken.paths import (
    DEFAULT_FIXTURE,
    KHMER_SPOKEN_DIR,
    ensure_khmer_spoken_dirs,
)
from claynext.models.khmer_spoken.schema import DialogueExample, validate_example
from claynext.models.khmer_spoken.workflow import run_milestone_import

__all__ = [
    "DEFAULT_FIXTURE",
    "KHMER_SPOKEN_DIR",
    "DialogueExample",
    "ensure_khmer_spoken_dirs",
    "run_milestone_import",
    "validate_example",
]
