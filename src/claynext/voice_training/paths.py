"""Filesystem roots for voice-training datasets and caches."""
from __future__ import annotations

from pathlib import Path

from claynext.utils.paths import CACHE_DIR, DATA_DIR

VOICE_DATASETS_DIR = DATA_DIR / "voice_datasets"
VOICE_CACHE_DIR = CACHE_DIR / "voice_training"
VOICE_CHECKPOINTS_DIR = VOICE_CACHE_DIR / "checkpoints"
VOICE_IMPORT_DIR = VOICE_CACHE_DIR / "imports"
DEMO_CONSENTED_DIR = VOICE_DATASETS_DIR / "demo_consented"

_DIRS = (
    VOICE_DATASETS_DIR,
    VOICE_CACHE_DIR,
    VOICE_CHECKPOINTS_DIR,
    VOICE_IMPORT_DIR,
    DEMO_CONSENTED_DIR,
)


def ensure_voice_dirs() -> None:
    for folder in _DIRS:
        folder.mkdir(parents=True, exist_ok=True)


ensure_voice_dirs()
