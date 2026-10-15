"""
Rendering Adapter: Hardware-accelerated composition export via Rust core backends.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from claynext.adapters.rust_core_adapter import get_rust_core
from claynext.adapters.hardware_codecs_adapter import get_hardware_codecs

logger = logging.getLogger("claynext.adapters.rendering")


class RenderingAdapter:
    """Coordinates video export rendering using native Rust hardware-accelerated pipeline."""

    def __init__(self) -> None:
        self._rust = get_rust_core()
        self._codecs = get_hardware_codecs()

    def get_optimal_encoder(self) -> str:
        """Query GPU hardware capabilities and select the fastest available encoder."""
        return self._codecs.get_recommended_encoder()

    def render_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
        video_codec: str | None = None,
        crf: int = 21,
        progress_callback: Callable[[float], None] | None = None,
    ) -> bool:
        """Render transcode using native Rust FFmpeg backend."""
        codec = video_codec or self.get_optimal_encoder()
        return self._rust.transcode_video(
            input_path=input_path,
            output_path=output_path,
            video_codec=codec,
            crf=crf,
            progress_callback=progress_callback,
        )


_rendering_adapter: RenderingAdapter | None = None


def get_rendering_adapter() -> RenderingAdapter:
    global _rendering_adapter
    if _rendering_adapter is None:
        _rendering_adapter = RenderingAdapter()
    return _rendering_adapter
