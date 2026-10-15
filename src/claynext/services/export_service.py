"""
Video and audio export service.

Coordinates transcode jobs using optimal hardware encoders (NVENC/QSV/AMF) via Rust core.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from claynext.adapters.hardware_codecs_adapter import get_recommended_encoder
from claynext.models.hardware import CodecProfile

logger = logging.getLogger("claynext.services.export")


class ExportService:
    @staticmethod
    def get_optimal_video_profile(prefer_hevc: bool = True) -> CodecProfile:
        """Select best hardware encoder profile available on system."""
        return get_recommended_encoder(prefer_hevc=prefer_hevc)

    @staticmethod
    def build_export_command(
        input_file: str | Path,
        output_file: str | Path,
        profile: CodecProfile,
        width: int | None = None,
        height: int | None = None,
        crf: int = 22,
    ) -> list[str]:
        """Construct full FFmpeg arguments utilizing the hardware profile."""
        cmd = ["ffmpeg", "-y", "-hide_banner", "-i", str(input_file)]
        cmd.extend(profile.encoder_args)

        if width and height:
            cmd.extend(["-vf", f"scale={width}:{height}"])

        cmd.extend(["-c:a", "aac", "-b:a", "192k", str(output_file)])
        return cmd
