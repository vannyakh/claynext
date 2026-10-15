"""
Media management service.

Handles media inspection, proxy generation, and waveform extraction.
"""
from __future__ import annotations

import logging
from pathlib import Path

from claynext.adapters.ffmpeg_adapter import probe_media
from claynext.adapters.rust_core_adapter import RustCpuAdapter, RustFfmpegAdapter
from claynext.models.media import MediaMetadata
from claynext.utils.paths import PLAYBACK_DIR, PROXY_DIR, THUMB_DIR

logger = logging.getLogger("claynext.services.media")


class MediaService:
    @staticmethod
    def inspect(file_path: str | Path) -> MediaMetadata:
        """Inspect media format and stream details."""
        return probe_media(file_path)

    @staticmethod
    def get_thumbnail_path(file_path: str | Path) -> Path:
        """Resolve thumbnail cache path for given media."""
        p = Path(file_path)
        stem = p.stem
        return THUMB_DIR / f"{stem}_thumb.jpg"

    @staticmethod
    def is_playback_safe(metadata: MediaMetadata) -> bool:
        """Determine if media is natively safe for fluid Qt AV playback."""
        if not metadata.video_stream:
            return True
        v = metadata.video_stream
        return v.width <= 1920 and v.height <= 1080 and not v.is_vfr
