"""ASR wrapper for Khmer transcript drafts — human correction happens in the UI."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("claynext.voice_training.khmer_transcriber")

Ping = Callable[[int, str], None] | None


def draft_transcript(
    audio_path: str | Path,
    *,
    language: str = "km",
    progress_callback: Ping = None,
) -> list[dict[str, Any]]:
    """
    Return draft lines ``[{text, start, end}, …]`` via ASREngine when available.
    On failure returns an empty list (UI still allows manual entry).
    """
    path = Path(audio_path)
    if not path.is_file():
        return []
    try:
        from claynext.models.asr_service import ASREngine

        if progress_callback:
            progress_callback(10, "Running ASR draft…")
        # Prefer Khmer when the backend supports language hints.
        lang = "Khmer" if language.lower() in {"km", "khmer"} else language
        result = ASREngine.transcribe(
            str(path), language=lang, progress_callback=progress_callback
        )
        lines: list[dict[str, Any]] = []
        if isinstance(result, list):
            for row in result:
                if isinstance(row, dict):
                    lines.append({
                        "text": str(row.get("text") or row.get("transcript") or ""),
                        "start": float(row.get("start", row.get("start_sec", 0.0)) or 0.0),
                        "end": float(row.get("end", row.get("end_sec", 0.0)) or 0.0),
                    })
                else:
                    lines.append({"text": str(row), "start": 0.0, "end": 0.0})
        elif isinstance(result, dict):
            for row in result.get("segments") or result.get("lines") or []:
                lines.append({
                    "text": str(row.get("text") or ""),
                    "start": float(row.get("start", 0.0) or 0.0),
                    "end": float(row.get("end", 0.0) or 0.0),
                })
        elif isinstance(result, str) and result.strip():
            lines.append({"text": result.strip(), "start": 0.0, "end": 0.0})
        return lines
    except Exception as exc:
        logger.info("ASR draft unavailable (%s); use manual transcript.", exc)
        return []
