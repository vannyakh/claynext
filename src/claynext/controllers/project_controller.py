"""
Project controller.

Controls project creation, loading, template preset instantiation, and persistence
delegating state and file operations to native Rust engine.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from claynext.adapters.rust_engine import get_rust_engine
from claynext.models.project import ProjectDocument, ProjectSettings
from claynext.utils.paths import PROJECT_DIR

logger = logging.getLogger("claynext.controllers.project")


class ProjectController:
    """Orchestrates project lifecycle delegating project state to Rust engine."""

    @staticmethod
    def create_project(settings: ProjectSettings) -> str:
        """Create a new project document on disk and register with Rust engine."""
        slug = "".join(c.lower() if c.isalnum() else "_" for c in settings.name).strip("_") or "project"
        folder = Path(settings.save_to) if settings.save_to else PROJECT_DIR
        dest = folder / f"{slug}.claynext.json"

        # Create through Rust engine when available
        engine = get_rust_engine()
        if engine.is_available():
            engine.create_project(
                name=settings.name,
                width=settings.width,
                height=settings.height,
                fps_num=int(settings.fps),
                fps_den=1,
            )

        doc = ProjectDocument(
            name=settings.name,
            settings=settings,
            media=settings.media_path,
        )
        payload = {
            "name": doc.name,
            "format": doc.format,
            "version": doc.version,
            "saved_at": doc.saved_at,
            "media": doc.media,
            "tracks": doc.tracks,
            "segments": doc.segments,
            "overlays": doc.overlays,
            "fx": doc.fx,
            "tasks": doc.tasks,
            "takes": doc.takes,
        }
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(dest)

    @staticmethod
    def load_project(file_path: str | Path) -> dict[str, Any]:
        """Load an existing project and notify Rust engine."""
        engine = get_rust_engine()
        if engine.is_available():
            engine.open_project(str(file_path))
        p = Path(file_path)
        if not p.is_file():
            raise FileNotFoundError(f"Project not found: {p}")
        return json.loads(p.read_text(encoding="utf-8"))
