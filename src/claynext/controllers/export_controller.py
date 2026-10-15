"""
Export controller.

Handles video and audio export configuration, encoder profile recommendation, and progress tracking
powered directly by native Rust hardware backends.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from claynext.adapters.hardware_codecs_adapter import get_hardware_codecs
from claynext.adapters.rendering import get_rendering_adapter
from claynext.models.hardware import CodecProfile

logger = logging.getLogger("claynext.controllers.export")


class ExportController:
    """Manages render and export pipeline delegating execution to native Rust core."""

    def __init__(self) -> None:
        self._current_profile: CodecProfile | None = None
        self._rendering = get_rendering_adapter()
        self._codecs = get_hardware_codecs()

    def get_recommended_encoder(self, prefer_hevc: bool = True) -> CodecProfile:
        """Query native Rust hardware codecs backend for optimal encoder profile."""
        from claynext.adapters.hardware_codecs_adapter import get_recommended_encoder

        profile = get_recommended_encoder(prefer_hevc=prefer_hevc)
        self._current_profile = profile
        return profile

    def render_composition(
        self,
        input_file: str | Path,
        output_file: str | Path,
        video_codec: str | None = None,
        crf: int = 21,
        progress_callback: Callable[[float], None] | None = None,
    ) -> bool:
        """Execute hardware-accelerated video render via native Rust rendering pipeline."""
        return self._rendering.render_file(
            input_path=input_file,
            output_path=output_file,
            video_codec=video_codec or self._rendering.get_optimal_encoder(),
            crf=crf,
            progress_callback=progress_callback,
        )

    def build_export_arguments(
        self,
        input_file: str | Path,
        output_file: str | Path,
        profile: CodecProfile | None = None,
        width: int | None = None,
        height: int | None = None,
        crf: int = 22,
    ) -> list[str]:
        """Construct full FFmpeg arguments using recommended hardware encoder."""
        active_prof = profile or self._current_profile or self.get_recommended_encoder()
        cmd = ["ffmpeg", "-y", "-hide_banner", "-i", str(input_file)]
        cmd.extend(active_prof.encoder_args)
        if width and height:
            cmd.extend(["-vf", f"scale={width}:{height}"])
        cmd.extend(["-c:a", "aac", "-b:a", "192k", str(output_file)])
        return cmd
