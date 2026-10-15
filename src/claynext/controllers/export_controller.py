"""
Export controller.

Handles video and audio export configuration, encoder profile recommendation, and progress tracking.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from claynext.models.hardware import CodecProfile
from claynext.services.export_service import ExportService

logger = logging.getLogger("claynext.controllers.export")


class ExportController:
    def __init__(self) -> None:
        self._current_profile: CodecProfile | None = None

    def get_recommended_encoder(self, prefer_hevc: bool = True) -> CodecProfile:
        """Query native Rust hardware codecs backend for optimal encoder profile."""
        profile = ExportService.get_optimal_video_profile(prefer_hevc=prefer_hevc)
        self._current_profile = profile
        return profile

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
        return ExportService.build_export_command(
            input_file=input_file,
            output_file=output_file,
            profile=active_prof,
            width=width,
            height=height,
            crf=crf,
        )
