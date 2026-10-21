"""Registry of consented / synthetic character voices for inference."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claynext.voice_training.paths import VOICE_CACHE_DIR, ensure_voice_dirs


def registry_path() -> Path:
    ensure_voice_dirs()
    return VOICE_CACHE_DIR / "voice_registry.json"


def load_registry() -> dict[str, Any]:
    path = registry_path()
    if not path.is_file():
        return {"voices": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(data: dict[str, Any]) -> Path:
    path = registry_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def register_voice(
    voice_id: str,
    *,
    display_name: str,
    speaker_id: str = "",
    consent_id: str = "",
    synthetic: bool = True,
    notes: str = "",
) -> dict[str, Any]:
    """
    Register a voice for inference. Recognizable cloning requires consent_id.
    Synthetic character voices are preferred when consent is limited.
    """
    if not synthetic and not consent_id:
        raise PermissionError(
            "Non-synthetic (recognizable) voices require a documented consent_id."
        )
    data = load_registry()
    voices = list(data.get("voices") or [])
    entry = {
        "voice_id": voice_id,
        "display_name": display_name,
        "speaker_id": speaker_id,
        "consent_id": consent_id,
        "synthetic": synthetic,
        "notes": notes,
    }
    voices = [v for v in voices if v.get("voice_id") != voice_id]
    voices.append(entry)
    data["voices"] = voices
    save_registry(data)
    return entry
