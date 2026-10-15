"""
Media Adapter: Native Rust media inspection and audio extraction operations.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from claynext.adapters.rust_core_adapter import get_rust_core

logger = logging.getLogger("claynext.adapters.media")


class MediaAdapter:
    """Provides high-performance media probe and inspection via native Rust core."""

    def __init__(self) -> None:
        self._rust = get_rust_core()

    def probe(self, file_path: str | Path) -> dict[str, Any] | None:
        """Deep metadata probe of audio/video container via native Rust FFmpeg backend."""
        try:
            return self._rust.probe_media(file_path)
        except Exception as e:
            logger.exception("Failed to probe media %s via Rust core: %s", file_path, e)
            return None

    def get_duration(self, file_path: str | Path) -> float:
        """Extract exact duration in seconds from media file."""
        meta = self.probe(file_path)
        if meta and "duration_seconds" in meta:
            return float(meta["duration_seconds"])
        return 0.0

    def extract_pcm_stream(
        self,
        media_path: str | Path,
        sample_rate: int = 44100,
        channels: int = 2,
    ) -> bytes:
        """Extract raw 32-bit floating point PCM audio stream from video/audio container."""
        return self._rust.extract_pcm_stream(media_path, sample_rate=sample_rate, channels=channels)


_media_adapter: MediaAdapter | None = None


def get_media_adapter() -> MediaAdapter:
    global _media_adapter
    if _media_adapter is None:
        _media_adapter = MediaAdapter()
    return _media_adapter
