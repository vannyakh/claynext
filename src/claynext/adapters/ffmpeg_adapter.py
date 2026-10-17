"""
FFmpeg infrastructure adapter.

Coordinates between the native Rust FFmpeg backend and imageio-ffmpeg subprocess fallback.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from claynext.adapters.rust_bridge import RustFfmpegAdapter
from claynext.models.media import MediaMetadata, MediaType

logger = logging.getLogger("claynext.adapters.ffmpeg")


def probe_media(file_path: str | Path) -> MediaMetadata:
    """Probe media metadata using Rust core probe when available, with fallback to ffprobe subprocess."""
    p = Path(file_path)
    if not p.is_file():
        return MediaMetadata(path=str(p), media_type=MediaType.UNKNOWN)

    # 1. Attempt high-speed Rust backend probe
    rust_meta = RustFfmpegAdapter.probe(p)
    if rust_meta:
        return rust_meta

    # 2. Fallback to ffprobe
    try:
        import imageio_ffmpeg
        probe_bin = "ffprobe"
        res = subprocess.run(
            [probe_bin, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(p)],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(res.stdout)
        return RustFfmpegAdapter._parse_metadata({"filepath": str(p), **data})
    except Exception as e:
        logger.warning(f"Fallback probe error on {p}: {e}")
        return MediaMetadata(path=str(p), media_type=MediaType.UNKNOWN)


def probe_duration(file_path: str | Path) -> float:
    """Return exact duration in seconds from native Rust probe."""
    meta = probe_media(file_path)
    return meta.duration if meta else 0.0


def run_ffmpeg(args: list[str]) -> bool:
    """Convenience bool wrapper over ffmpeg_service.run_ffmpeg (bundled binary)."""
    try:
        from claynext.adapters.ffmpeg_service import run_ffmpeg as _run

        # Ensure -y is present for overwrite-friendly model callers.
        argv = list(args)
        if "-y" not in argv:
            argv = ["-y", *argv]
        res = _run(argv)
        return res.returncode == 0
    except Exception as e:
        logger.warning(f"run_ffmpeg error: {e}")
        return False


class FFmpegAdapter:
    """Orchestrates media probing and stream processing via Rust core."""

    @staticmethod
    def probe(file_path: str | Path) -> MediaMetadata:
        return probe_media(file_path)

    @staticmethod
    def duration(file_path: str | Path) -> float:
        return probe_duration(file_path)

    @staticmethod
    def extract_still(
        file_path: str | Path,
        output_path: str | Path,
        *,
        timestamp_secs: float = 1.0,
        max_width: int | None = 160,
    ) -> bool:
        """Still frame via claynext-ffmpeg."""
        return RustFfmpegAdapter.extract_still(
            file_path,
            output_path,
            timestamp_secs=timestamp_secs,
            max_width=max_width,
        )

    @staticmethod
    def demux_audio(
        media_path: str | Path,
        output_wav: str | Path,
        *,
        sample_rate: int = 48000,
        channels: int = 2,
    ) -> bool:
        """PCM WAV demux via claynext-ffmpeg."""
        return RustFfmpegAdapter.demux_audio(
            media_path, output_wav, sample_rate=sample_rate, channels=channels
        )

    @staticmethod
    def decode_audio_pcm_f32(
        file_path: str | Path,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
    ):
        """PCM f32 decode via claynext-ffmpeg (None if unavailable)."""
        return RustFfmpegAdapter.decode_audio_pcm_f32(
            file_path, sample_rate=sample_rate, channels=channels
        )

    @staticmethod
    def is_rust_available() -> bool:
        return RustFfmpegAdapter.is_available()


_ffmpeg_adapter: FFmpegAdapter | None = None


def get_ffmpeg_adapter() -> FFmpegAdapter:
    global _ffmpeg_adapter
    if _ffmpeg_adapter is None:
        _ffmpeg_adapter = FFmpegAdapter()
    return _ffmpeg_adapter


# Re-export audio and video transcoding utilities from ffmpeg_service
from claynext.adapters.ffmpeg_service import (
    demux_wav,
    dynamic_duck_audio,
    ensure_speech_bed,
    fit_duration,
    master_voiceover_track,
    mix_wavs,
    compose_overlays,
    mux_video,
    overlay_clips,
    volume_wav,
    make_silence,
    concat_videos,
    mix_timeline_audio,
    render_timeline,
)


