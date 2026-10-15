"""
Video and audio export service.

Coordinates transcode jobs using optimal hardware encoders (NVENC/QSV/AMF) via native Rust backends.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from claynext.adapters.hardware_codecs_adapter import get_recommended_encoder
from claynext.adapters.rendering import get_rendering_adapter
from claynext.models.hardware import CodecProfile

logger = logging.getLogger("claynext.services.export")


class ExportService:
    """Manages composition rendering and hardware encoder selection via native Rust core."""

    @staticmethod
    def get_optimal_video_profile(prefer_hevc: bool = True) -> CodecProfile:
        """Select best hardware encoder profile available on system via Rust hardware codecs."""
        return get_recommended_encoder(prefer_hevc=prefer_hevc)

    @staticmethod
    def render_export(
        input_path: str | Path,
        output_path: str | Path,
        video_codec: str | None = None,
        crf: int = 21,
        progress_callback: Callable[[float], None] | None = None,
    ) -> bool:
        """Execute composition export directly via native Rust rendering pipeline."""
        return get_rendering_adapter().render_file(
            input_path=input_path,
            output_path=output_path,
            video_codec=video_codec,
            crf=crf,
            progress_callback=progress_callback,
        )

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
