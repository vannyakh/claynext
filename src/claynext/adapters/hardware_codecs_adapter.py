"""
Hardware codecs infrastructure adapter.

Leverages native Rust GPU detection and optimal hardware codec flag selection.
"""
from __future__ import annotations

from typing import Any
from claynext.adapters.rust_core_adapter import RustHardwareCodecsAdapter
from claynext.models.hardware import CodecProfile, GpuCapability


def detect_system_gpus() -> list[GpuCapability]:
    """Detect available GPUs on the system via Rust core."""
    return RustHardwareCodecsAdapter.detect_gpus()


def get_recommended_encoder(prefer_hevc: bool = True) -> CodecProfile:
    """Get the recommended hardware or software video encoder profile."""
    args = RustHardwareCodecsAdapter.get_optimal_encoder_args(prefer_hevc=prefer_hevc)
    codec = "libx264"
    for i, a in enumerate(args):
        if a == "-c:v" and i + 1 < len(args):
            codec = args[i + 1]
            break

    is_hw = any(tag in codec for tag in ("nvenc", "qsv", "amf", "mf", "videotoolbox"))
    return CodecProfile(
        codec_name=codec,
        is_hardware=is_hw,
        encoder_args=args,
    )
