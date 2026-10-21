"""
Khmer Cinematic Voice Training — licensed speech datasets and expressive TTS prep.

Language datasets (what to say) live under ``claynext.models.datasets`` /
Khmer Spoken Language Dataset. This package owns speech audio datasets
(how to sound): ingestion, rights gates, annotation, training dry-runs,
and offline evaluation stubs.

Voice-identity training and cloning are blocked unless source licensing
and performer consent are documented (see ``ingestion.rights_validator``).
"""
from __future__ import annotations

from claynext.voice_training.paths import VOICE_DATASETS_DIR, ensure_voice_dirs

__all__ = [
    "VOICE_DATASETS_DIR",
    "ensure_voice_dirs",
]
