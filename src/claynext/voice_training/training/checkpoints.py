"""Checkpoint / experiment manifest helpers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claynext.voice_training.paths import VOICE_CHECKPOINTS_DIR, ensure_voice_dirs


def new_experiment_id(prefix: str = "exp") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}"


def experiment_dir(experiment_id: str) -> Path:
    ensure_voice_dirs()
    path = VOICE_CHECKPOINTS_DIR / experiment_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_manifest(experiment_id: str, payload: dict[str, Any]) -> Path:
    root = experiment_dir(experiment_id)
    path = root / "manifest.json"
    data = dict(payload)
    data.setdefault("experiment_id", experiment_id)
    data.setdefault("written_at", datetime.now(timezone.utc).replace(microsecond=0).isoformat())
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_manifest(experiment_id: str) -> dict[str, Any] | None:
    path = VOICE_CHECKPOINTS_DIR / experiment_id / "manifest.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
