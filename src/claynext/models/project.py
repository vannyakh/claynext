"""Project domain models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ProjectSettings:
    name: str = "Untitled Project"
    save_to: str = ""
    media_path: str = ""
    target_language: str = "Khmer"
    source_language: str = "English"
    import_mode: str = "copy"  # copy | link
    width: int = 1920
    height: int = 1080
    fps: float = 30.0


@dataclass
class ProjectDocument:
    name: str
    format: str = "claynext-studio-lite"
    version: int = 2
    saved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    settings: ProjectSettings = field(default_factory=ProjectSettings)
    media: str = ""
    tracks: list[dict[str, Any]] = field(default_factory=list)
    segments: list[dict[str, Any]] = field(default_factory=list)
    overlays: list[dict[str, Any]] = field(default_factory=list)
    fx: list[dict[str, Any]] = field(default_factory=list)
    tasks: list[dict[str, Any]] = field(default_factory=list)
    takes: list[dict[str, Any]] = field(default_factory=list)
