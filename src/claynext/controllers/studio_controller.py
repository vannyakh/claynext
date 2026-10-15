"""
Studio workspace controller.

Bridges PySide6 UI views with native Rust engine for timeline editing, track management, and ducking.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from claynext.adapters.dubbing import get_dubbing_adapter
from claynext.adapters.media import get_media_adapter
from claynext.adapters.rust_engine import get_rust_engine
from claynext.adapters.timeline import get_timeline_adapter
from claynext.models.media import MediaMetadata
from claynext.services.media_service import MediaService
from claynext.services.project_service import ProjectService

logger = logging.getLogger("claynext.controllers.studio")


class StudioController:
    """Orchestrates studio editing workflow delegating heavy timeline state to native Rust engine."""

    def __init__(self) -> None:
        self.active_project_path: str | None = None
        self.active_media_meta: MediaMetadata | None = None
        self._engine = get_rust_engine()
        self._timeline = get_timeline_adapter()
        self._dubbing = get_dubbing_adapter()
        self._media = get_media_adapter()

    def load_project(self, project_path: str | Path) -> dict[str, Any]:
        """Load a project file into the studio controller and synchronize Rust engine."""
        path_str = str(project_path)
        data = ProjectService.load_project_file(path_str)
        self.active_project_path = path_str

        # Synchronize Rust engine
        if self._engine.is_available():
            self._engine.open_project(path_str)

        media_path = str(data.get("media") or "")
        if media_path and Path(media_path).is_file():
            self.active_media_meta = MediaService.inspect(media_path)

        return data

    def inspect_media(self, media_path: str | Path) -> MediaMetadata:
        """Inspect media file properties using native Rust backend."""
        meta = MediaService.inspect(media_path)
        self.active_media_meta = meta
        return meta

    # --- Authoritative Rust Timeline Operations ---

    def add_track(self, kind: str, name: str) -> str | None:
        """Add a timeline track via Rust editor-timeline engine."""
        return self._timeline.add_track(kind, name)

    def remove_track(self, track_id: str) -> bool:
        """Remove a timeline track via Rust editor-timeline engine."""
        return self._timeline.remove_track(track_id)

    def add_clip(
        self,
        track_id: str,
        media_path: str,
        media_type: str,
        start_seconds: float,
        duration_seconds: float,
        source_in_seconds: float = 0.0,
    ) -> str | None:
        """Add a media clip via Rust editor-timeline engine."""
        return self._timeline.add_clip(
            track_id=track_id,
            media_path=media_path,
            media_type=media_type,
            start_seconds=start_seconds,
            duration_seconds=duration_seconds,
            source_in_seconds=source_in_seconds,
        )

    def split_clip(self, clip_id: str, split_seconds: float) -> tuple[str, str] | None:
        """Split a clip into two instances via Rust editor-timeline engine."""
        return self._timeline.split_clip(clip_id, split_seconds)

    def remove_clip(self, clip_id: str) -> bool:
        """Remove a clip via Rust editor-timeline engine."""
        return self._timeline.remove_clip(clip_id)

    def set_audio_ducking(
        self,
        music_track_id: str,
        voice_track_id: str,
        ducking_db: float = -14.0,
        attack_ms: float = 150.0,
        release_ms: float = 400.0,
    ) -> bool:
        """Set automated audio ducking parameters via Rust editor-audio engine."""
        return self._dubbing.set_ducking(
            music_track_id=music_track_id,
            voice_track_id=voice_track_id,
            ducking_db=ducking_db,
            attack_ms=attack_ms,
            release_ms=release_ms,
        )
