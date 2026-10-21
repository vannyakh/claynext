"""Extract audio from authorized media via FFmpeg adapters (never reinvent FFmpeg)."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Callable

logger = logging.getLogger("claynext.voice_training.audio_extractor")

Ping = Callable[[int, str], None] | None

AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}


def extract_audio_wav(
    media_path: str | Path,
    output_wav: str | Path,
    *,
    sample_rate: int = 22050,
    channels: int = 1,
    progress_callback: Ping = None,
) -> Path:
    """
    Demux / convert media to PCM WAV using ``get_ffmpeg_adapter`` / ``demux_wav``.

    Copies already-compatible WAV files when sample rate is left flexible.
    """
    src = Path(media_path)
    dst = Path(output_wav)
    if not src.is_file():
        raise FileNotFoundError(f"Media not found: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(5, f"Extracting audio from {src.name}…")

    # Prefer Rust demux when available; fall back to ffmpeg_service.demux_wav.
    try:
        from claynext.adapters.ffmpeg_adapter import get_ffmpeg_adapter

        adapter = get_ffmpeg_adapter()
        ok = adapter.demux_audio(src, dst, sample_rate=sample_rate, channels=channels)
        if ok and dst.is_file() and dst.stat().st_size > 0:
            if progress_callback:
                progress_callback(100, "Audio extracted")
            return dst
    except Exception as exc:
        logger.debug("Rust demux failed (%s); trying ffmpeg_service", exc)

    try:
        from claynext.adapters.ffmpeg_service import demux_wav

        demux_wav(str(src), str(dst), rate=sample_rate, channels=channels)
        if dst.is_file() and dst.stat().st_size > 0:
            if progress_callback:
                progress_callback(100, "Audio extracted")
            return dst
    except Exception as exc:
        logger.debug("demux_wav failed: %s", exc)

    # Last resort: copy wav as-is (annotation can still proceed).
    if src.suffix.lower() == ".wav":
        shutil.copy2(src, dst)
        if progress_callback:
            progress_callback(100, "WAV copied")
        return dst

    raise RuntimeError(
        f"Could not extract audio from {src}. Ensure claynext-ffmpeg or imageio-ffmpeg is available."
    )


def probe_duration_sec(media_path: str | Path) -> float:
    try:
        from claynext.adapters.ffmpeg_adapter import get_ffmpeg_adapter

        return float(get_ffmpeg_adapter().duration(media_path) or 0.0)
    except Exception:
        return 0.0
