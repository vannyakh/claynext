"""Unified facade over all Rust backend bridges."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from claynext.adapters.rust_bridge.ai import RustAiAdapter
from claynext.adapters.rust_bridge.codecs import RustHardwareCodecsAdapter
from claynext.adapters.rust_bridge.cpu import RustCpuAdapter
from claynext.adapters.rust_bridge.ffmpeg import RustFfmpegAdapter
from claynext.adapters.rust_bridge.wgpu import RustWgpuAdapter


class RustCoreAdapter:
    """Unified access to all native Rust backend capabilities."""

    def __init__(self) -> None:
        self.ffmpeg = RustFfmpegAdapter
        self.codecs = RustHardwareCodecsAdapter
        self.cpu = RustCpuAdapter
        self.ai = RustAiAdapter
        self.wgpu = RustWgpuAdapter

    def probe_media(self, file_path: str | Path) -> dict[str, Any] | None:
        meta = self.ffmpeg.probe(file_path)
        if meta:
            return {
                "filepath": meta.path,
                "duration_seconds": meta.duration_seconds,
                "width": meta.width,
                "height": meta.height,
                "fps": meta.fps,
                "video_codec": meta.video_codec,
                "audio_codec": meta.audio_codec,
            }
        return None

    def extract_pcm_stream(self, media_path: str | Path, sample_rate: int = 44100, channels: int = 2) -> bytes:
        chunk = self.ffmpeg.extract_audio_pcm(media_path, sample_rate=sample_rate, channels=channels)
        return chunk.raw_pcm if chunk else b""

    def transcode_video(
        self,
        input_path: str | Path,
        output_path: str | Path,
        video_codec: str = "libx264",
        crf: int = 21,
        *,
        width: int | None = None,
        height: int | None = None,
        preset: str = "veryfast",
        start_time_secs: float | None = None,
        duration_secs: float | None = None,
        prefer_hardware: bool = False,
        progress_callback: Callable[[float], None] | None = None,
    ) -> bool:
        return self.ffmpeg.transcode_video(
            input_path=input_path,
            output_path=output_path,
            video_codec=video_codec,
            crf=crf,
            width=width,
            height=height,
            preset=preset,
            start_time_secs=start_time_secs,
            duration_secs=duration_secs,
            prefer_hardware=prefer_hardware,
            progress_callback=progress_callback,
        )

    def extract_still(
        self,
        file_path: str | Path,
        output_path: str | Path,
        *,
        timestamp_secs: float = 1.0,
        max_width: int | None = 160,
    ) -> bool:
        return self.ffmpeg.extract_still(
            file_path,
            output_path,
            timestamp_secs=timestamp_secs,
            max_width=max_width,
        )



_rust_core: RustCoreAdapter | None = None


def get_rust_core() -> RustCoreAdapter:
    global _rust_core
    if _rust_core is None:
        _rust_core = RustCoreAdapter()
    return _rust_core
