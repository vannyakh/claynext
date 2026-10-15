"""
Project service.

Manages saving, loading, and autosaving of studio project files.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from claynext.models.project import ProjectDocument, ProjectSettings
from claynext.utils.paths import PROJECT_DIR

logger = logging.getLogger("claynext.services.project")


class ProjectService:
    @staticmethod
    def load_project_file(file_path: str | Path) -> dict[str, Any]:
        """Load and parse .claynext.json or legacy .jela.json project."""
        p = Path(file_path)
        if not p.is_file():
            raise FileNotFoundError(f"Project not found: {p}")
        return json.loads(p.read_text(encoding="utf-8"))

    @staticmethod
    def save_project_file(file_path: str | Path, document: ProjectDocument) -> Path:
        """Write project document to disk."""
        dest = Path(file_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "name": document.name,
            "format": document.format,
            "version": document.version,
            "saved_at": document.saved_at,
            "media": document.media,
            "tracks": document.tracks,
            "segments": document.segments,
            "overlays": document.overlays,
            "fx": document.fx,
            "tasks": document.tasks,
            "takes": document.takes,
        }
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return dest
