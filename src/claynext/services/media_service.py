"""
Media management service.

Handles media inspection, proxy generation, and waveform extraction powered by native Rust backends.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from claynext.adapters.media import get_media_adapter
from claynext.adapters.rust_core_adapter import RustCpuAdapter
from claynext.models.media import MediaMetadata
from claynext.utils.paths import PLAYBACK_DIR, PROXY_DIR, THUMB_DIR

logger = logging.getLogger("claynext.services.media")


class MediaService:
    """Delegates media inspection, audio extraction, and waveform calculation to native Rust backends."""

    @staticmethod
    def inspect(file_path: str | Path) -> MediaMetadata:
        """Inspect media format and stream details using native Rust core."""
        adapter = get_media_adapter()
        raw = adapter.probe(file_path)
        if raw:
            from claynext.adapters.ffmpeg_adapter import probe_media
            return probe_media(file_path)
        from claynext.adapters.ffmpeg_adapter import probe_media
        return probe_media(file_path)

    @staticmethod
    def get_duration(file_path: str | Path) -> float:
        """Query exact media duration via native Rust probe."""
        return get_media_adapter().get_duration(file_path)

    @staticmethod
    def extract_pcm_stream(file_path: str | Path, sample_rate: int = 44100, channels: int = 2) -> bytes:
        """Extract raw PCM audio stream using native Rust stream extractor."""
        return get_media_adapter().extract_pcm_stream(file_path, sample_rate=sample_rate, channels=channels)

    @staticmethod
    def generate_waveform_peaks(raw_pcm_f32: bytes, target_bins: int = 2000) -> list[dict[str, float]]:
        """Compute visualizer waveform peaks using native Rust CPU downsampler."""
        return RustCpuAdapter.downsample_waveform(raw_pcm_f32, target_bins=target_bins)

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
