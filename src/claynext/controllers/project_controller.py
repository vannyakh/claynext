"""
Project controller.

Controls project creation, loading, template preset instantiation, and persistence.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from claynext.models.project import ProjectDocument, ProjectSettings
from claynext.services.project_service import ProjectService
from claynext.utils.paths import PROJECT_DIR

logger = logging.getLogger("claynext.controllers.project")


class ProjectController:
    @staticmethod
    def create_project(settings: ProjectSettings) -> str:
        """Create a new project document on disk."""
        slug = "".join(c.lower() if c.isalnum() else "_" for c in settings.name).strip("_") or "project"
        folder = Path(settings.save_to) if settings.save_to else PROJECT_DIR
        dest = folder / f"{slug}.claynext.json"

        doc = ProjectDocument(
            name=settings.name,
            settings=settings,
            media=settings.media_path,
        )
        saved_path = ProjectService.save_project_file(dest, doc)
        return str(saved_path)

    @staticmethod
    def load_project(file_path: str | Path) -> dict[str, Any]:
        """Load an existing project."""
        return ProjectService.load_project_file(file_path)
