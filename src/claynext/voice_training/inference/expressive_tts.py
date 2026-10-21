"""Expressive TTS inference stubs — reuse TTSEngine when a voice exists."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("claynext.voice_training.expressive_tts")

Ping = Callable[[int, str], None] | None


def synthesize_preview(
    text: str,
    voice_id: str,
    output_path: str | Path,
    *,
    emotion: str = "neutral",
    speaking_style: str = "spoken",
    progress_callback: Ping = None,
) -> dict[str, Any]:
    """
    Try TTSEngine for a preview. Returns ``{ok, path, skipped, reason}``.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not (text or "").strip():
        return {"ok": False, "path": None, "skipped": True, "reason": "empty_text"}
    if not (voice_id or "").strip():
        return {"ok": False, "path": None, "skipped": True, "reason": "no_voice"}

    try:
        from claynext.models.tts_service import TTSEngine

        performance = {"emotion": emotion, "style": speaking_style}
        if progress_callback:
            progress_callback(20, "Synthesizing preview…")
        TTSEngine.synthesize(
            text,
            voice_id,
            str(out),
            progress_callback=progress_callback,
            performance=performance,
        )
        if out.is_file() and out.stat().st_size > 0:
            return {"ok": True, "path": str(out), "skipped": False, "reason": ""}
        return {"ok": False, "path": None, "skipped": True, "reason": "empty_output"}
    except Exception as exc:
        logger.info("TTS preview skipped: %s", exc)
        return {"ok": False, "path": None, "skipped": True, "reason": str(exc)}
