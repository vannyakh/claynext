"""Infrastructure adapters."""
from __future__ import annotations

from claynext.adapters.ffmpeg_adapter import probe_media
from claynext.adapters.hardware_codecs_adapter import detect_system_gpus, get_recommended_encoder
from claynext.adapters.rust_core_adapter import (
    RustAiAdapter,
    RustCpuAdapter,
    RustFfmpegAdapter,
    RustHardwareCodecsAdapter,
    RustWgpuAdapter,
)

__all__ = [
    "RustAiAdapter",
    "RustCpuAdapter",
    "RustFfmpegAdapter",
    "RustHardwareCodecsAdapter",
    "RustWgpuAdapter",
    "detect_system_gpus",
    "get_recommended_encoder",
    "probe_media",
]
