"""Filesystem layout for the Khmer Spoken Language Dataset (KSLD) workspace.

All generated artefacts live under ``data/khmer_spoken/`` — never the project root.

Platform note
-------------
- **Google AI Studio / Gemini API** (this package's teacher path): generate and
  evaluate Khmer dialogue candidates; optional Gemini TTS previews. Does **not**
  retrain a base model by uploading a dataset.
- **Google Cloud Vertex AI**: supervised fine-tuning of eligible Gemini models —
  separate credentials/project. See ``training/vertex_tuning_client.py``.
- **Local LoRA/QLoRA**: open-weight training stub — separate from Vertex.
- **Speech audio / voice cloning**: ``src/claynext/voice_training/`` (owned by
  another package). KSLD stores *what to say*; voice datasets store *how to sound*.
"""
from __future__ import annotations

from pathlib import Path

from claynext.utils.paths import DATA_DIR

KHMER_SPOKEN_DIR = DATA_DIR / "khmer_spoken"
FIXTURES_DIR = KHMER_SPOKEN_DIR / "fixtures"
VERSIONS_DIR = KHMER_SPOKEN_DIR / "versions"
EVALS_DIR = KHMER_SPOKEN_DIR / "evals"
WORKSPACE_DIR = KHMER_SPOKEN_DIR / "workspace"
TTS_PREVIEW_DIR = KHMER_SPOKEN_DIR / "tts_previews"
JOBS_DIR = KHMER_SPOKEN_DIR / "jobs"

DEFAULT_FIXTURE = FIXTURES_DIR / "dialogue_100.jsonl"
WORKSPACE_CANDIDATES = WORKSPACE_DIR / "candidates.jsonl"
WORKSPACE_REVIEW = WORKSPACE_DIR / "review_queue.jsonl"

# Link (docs only) — do not import voice_training from this package's hot path.
VOICE_TRAINING_PACKAGE = "claynext.voice_training"
VOICE_DATASETS_HINT = "data/voice_datasets/"


def ensure_khmer_spoken_dirs() -> None:
    for folder in (
        KHMER_SPOKEN_DIR,
        FIXTURES_DIR,
        VERSIONS_DIR,
        EVALS_DIR,
        WORKSPACE_DIR,
        TTS_PREVIEW_DIR,
        JOBS_DIR,
    ):
        folder.mkdir(parents=True, exist_ok=True)
