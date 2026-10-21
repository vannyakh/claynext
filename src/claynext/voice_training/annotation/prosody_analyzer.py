"""Prosody features — reuse character_intel / AI adapter when present."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("claynext.voice_training.prosody_analyzer")


def analyze_prosody(audio_path: str | Path, *, start_sec: float = 0.0, end_sec: float = 0.0) -> dict[str, Any]:
    """
    Return a prosody feature dict. Prefer AI adapter / character_intel when available;
    otherwise return a stub with duration only.
    """
    path = Path(audio_path)
    duration = max(0.0, float(end_sec) - float(start_sec)) if end_sec > start_sec else 0.0

    try:
        from claynext.adapters.ai import get_ai_adapter

        adapter = get_ai_adapter()
        # Future: adapter.analyze_prosody(...). Milestone stub keeps soft discovery.
        analyze = getattr(adapter, "analyze_prosody", None)
        if callable(analyze):
            result = analyze(str(path), start_sec=start_sec, end_sec=end_sec)
            if isinstance(result, dict) and result:
                result.setdefault("source", "ai_adapter")
                return result
    except Exception as exc:
        logger.debug("Prosody via AI adapter unavailable: %s", exc)

    if not duration and path.is_file():
        try:
            from claynext.voice_training.ingestion.audio_extractor import probe_duration_sec

            duration = probe_duration_sec(path)
        except Exception:
            duration = 0.0

    return {
        "duration_sec": round(duration, 3),
        "pitch_mean_hz": None,
        "pitch_std_hz": None,
        "energy_mean": None,
        "speaking_rate": None,
        "source": "stub",
    }
