"""
Studio workspace controller.

Bridges PySide6 UI views with domain services and native Rust backends.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from claynext.models.media import MediaMetadata
from claynext.services.media_service import MediaService
from claynext.services.project_service import ProjectService

logger = logging.getLogger("claynext.controllers.studio")


class StudioController:
    def __init__(self) -> None:
        self.active_project_path: str | None = None
        self.active_media_meta: MediaMetadata | None = None

    def load_project(self, project_path: str | Path) -> dict[str, Any]:
        """Load a project file into the studio controller."""
        path_str = str(project_path)
        data = ProjectService.load_project_file(path_str)
        self.active_project_path = path_str

        media_path = str(data.get("media") or "")
        if media_path and Path(media_path).is_file():
            self.active_media_meta = MediaService.inspect(media_path)

        return data

    def inspect_media(self, media_path: str | Path) -> MediaMetadata:
        """Inspect media file properties using the native Rust media service."""
        meta = MediaService.inspect(media_path)
        self.active_media_meta = meta
        return meta
