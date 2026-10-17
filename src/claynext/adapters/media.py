"""
Media Adapter: Native Rust media inspection and audio extraction operations.
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

from claynext.adapters.rust_core_adapter import RustCpuAdapter, RustFfmpegAdapter, get_rust_core
from claynext.models.media import MediaMetadata
from claynext.utils.paths import PLAYBACK_DIR, PROXY_DIR, THUMB_DIR

logger = logging.getLogger("claynext.adapters.media")

_SAFE_EXTS = {".mp3", ".wav", ".flac", ".ogg"}


def _cache_path(media_path: str, suffix: str = "aaclc-v3") -> Path:
    abs_path = os.path.abspath(media_path)
    try:
        stamp = f"{os.path.getmtime(abs_path)}|{os.path.getsize(abs_path)}"
    except OSError:
        stamp = "0"
    key = hashlib.sha1(f"{abs_path}|{stamp}|{suffix}".encode()).hexdigest()
    return PLAYBACK_DIR / f"{key}.mp4"


def ready_playback_path(media_path: str) -> str | None:
    """Return a Qt-safe path if one is already available."""
    if not media_path or not os.path.isfile(media_path):
        return None
    abs_path = os.path.abspath(media_path)
    ext = os.path.splitext(abs_path)[1].lower()
    if ext in _SAFE_EXTS:
        return abs_path
    cached = _cache_path(abs_path)
    if cached.is_file() and cached.stat().st_size > 0:
        return str(cached)
    return None


def ensure_playback_file(media_path: str, progress_callback=None) -> str:
    """Ensure media file is in a safe format for fluid playback via Rust transcode."""
    ready = ready_playback_path(media_path)
    if ready:
        return ready

    abs_path = os.path.abspath(media_path)
    cached = _cache_path(abs_path)
    PLAYBACK_DIR.mkdir(parents=True, exist_ok=True)

    success = RustFfmpegAdapter.transcode_video(
        input_path=abs_path,
        output_path=cached,
        video_codec="libx264",
        crf=23,
        preset="veryfast",
        progress_callback=progress_callback,
    )
    if success and cached.is_file() and cached.stat().st_size > 0:
        return str(cached)
    raise RuntimeError("Playback convert failed — could not create Qt-safe H.264/AAC file")


def ensure_proxy_render(media_path: str, progress_callback=None) -> str:
    """Generate 720p lightweight H.264 proxy via Rust transcode (edit preview recovery)."""
    abs_path = os.path.abspath(media_path)
    try:
        stamp = f"{os.path.getmtime(abs_path)}|{os.path.getsize(abs_path)}"
    except OSError:
        stamp = "0"
    key = hashlib.sha1(f"{abs_path}|{stamp}|proxy_720p_v2".encode()).hexdigest()
    PROXY_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROXY_DIR / f"{key}.mp4"
    if out_path.is_file() and out_path.stat().st_size > 0:
        return str(out_path)

    ok = RustFfmpegAdapter.transcode_video(
        input_path=abs_path,
        output_path=out_path,
        video_codec="libx264",
        crf=26,
        height=720,
        preset="ultrafast",
        progress_callback=progress_callback,
    )
    if ok and out_path.is_file() and out_path.stat().st_size > 0:
        return str(out_path)
    return abs_path


def inspect_media(file_path: str | Path) -> MediaMetadata:
    """Inspect media format and stream details using native Rust core."""
    from claynext.adapters.ffmpeg_adapter import probe_media
    return probe_media(file_path)


class MediaAdapter:
    """Provides high-performance media probe, waveform and inspection via native Rust core."""

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

    def generate_waveform_peaks(self, raw_pcm_f32: bytes, target_bins: int = 2000) -> list[dict[str, float]]:
        """Compute visualizer waveform peaks using native Rust CPU downsampler."""
        return RustCpuAdapter.downsample_waveform(raw_pcm_f32, target_bins=target_bins)


_media_adapter: MediaAdapter | None = None


def get_media_adapter() -> MediaAdapter:
    global _media_adapter
    if _media_adapter is None:
        _media_adapter = MediaAdapter()
    return _media_adapter

