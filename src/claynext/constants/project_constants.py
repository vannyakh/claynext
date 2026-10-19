"""New Project presets and canvas sizes."""
from __future__ import annotations

from dataclasses import dataclass


NEW_PROJECT_FIELD_H = 28

ASPECT_RATIOS: dict[str, float] = {
    "16:9": 16 / 9,
    "9:16": 9 / 16,
    "1:1": 1.0,
    "4:3": 4 / 3,
    "4:5": 4 / 5,
}

RESOLUTION_HEIGHTS: dict[str, int] = {
    "2160p": 2160,
    "1080p": 1080,
    "720p": 720,
    "Adapted": 1080,
}


@dataclass(frozen=True)
class ProjectTemplate:
    id: str
    title: str
    size_label: str
    icon: str
    aspect: str
    resolution: str
    fps: str

    @property
    def label(self) -> str:
        """Short chip text. Cinema stays 16:9, marked 4K so it does not match YouTube."""
        if self.id == "blank":
            return "Custom"
        if self.id == "cinema_4k":
            return "4K"
        return self.aspect

    @property
    def hint(self) -> str:
        return f"{self.title} · {self.aspect} · {self.size_label}"


TEMPLATES: tuple[ProjectTemplate, ...] = (
    ProjectTemplate("hd_landscape", "YouTube", "1080p · 30fps", "video", "16:9", "1080p", "30.00 fps"),
    ProjectTemplate("vertical_shorts", "TikTok Reels", "1080p · 30fps", "aspect", "9:16", "1080p", "30.00 fps"),
    ProjectTemplate("cinema_4k", "Cinema 4K", "2160p · 24fps", "sparkles", "16:9", "2160p", "24.00 fps"),
    ProjectTemplate("square_post", "Instagram", "1080p · 30fps", "grid", "1:1", "1080p", "30.00 fps"),
    ProjectTemplate("portrait_feed", "Portrait", "1080p · 30fps", "image", "4:5", "1080p", "30.00 fps"),
    ProjectTemplate("blank", "Custom", "Original · Adapted", "plus", "Original", "Adapted", "Original"),
)


def template_by_id(template_id: str) -> ProjectTemplate:
    return next((item for item in TEMPLATES if item.id == template_id), TEMPLATES[0])


def canvas_dimensions(aspect: str, resolution: str) -> tuple[int, int]:
    base_h = RESOLUTION_HEIGHTS.get(resolution, 1080)
    if aspect == "16:9":
        return int(round(base_h * 16 / 9)), base_h
    if aspect == "9:16":
        return base_h, int(round(base_h * 16 / 9))
    if aspect == "1:1":
        return base_h, base_h
    if aspect == "4:3":
        return int(round(base_h * 4 / 3)), base_h
    if aspect == "4:5":
        return base_h, int(round(base_h * 5 / 4))
    return 1920, 1080
