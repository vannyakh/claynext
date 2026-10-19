"""One overlay on the preview: text, caption, logo, image, or shape."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field, fields

from claynext.gui.components.overlay.const import TEXT_KINDS
from claynext.gui.components.render.shape import shape_size
from claynext.models.text_style import clean_text_style

@dataclass
class OverlayItem:
    id: str
    kind: str
    x: float = 0.5
    y: float = 0.5
    w: float = 0.28
    h: float = 0.10
    rotation: float = 0.0
    color: str = "#f8fafc"
    opacity: int = 100
    text: str = "Text"
    font_size: int = 20
    path: str = ""
    live: bool = False
    font: str = "Arial"
    scale: int = 100
    bold: bool = False
    italic: bool = False
    underline: bool = False
    case: str = "none"
    align: str = "center"
    letter: int = 0
    stroke_on: bool = False
    stroke_color: str = "#000000"
    stroke_width: int = 3
    bg_on: bool = False
    bg_color: str = "#000000"
    bg_opacity: int = 70
    shadow_on: bool = False
    shadow_color: str = "#000000"
    shadow_dist: int = 2
    anim_in: str = "none"
    anim_in_ms: int = 500
    anim_out: str = "none"
    anim_out_ms: int = 500
    anim_loop: str = "none"
    anim_loop_ms: int = 1200
    highlight_color: str = "#facc15"
    caption_fit: bool = True
    caption_width: int = 80
    preset: str = ""
    shape: str = "rect"
    blur_on: bool = False
    blur_radius: int = 20
    lock_aspect: bool = True
    flip_h: bool = False
    flip_v: bool = False
    hidden: bool = False
    start_ms: int = 0
    duration_ms: int = 0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def style(self) -> dict:
        return clean_text_style(asdict(self))

    @classmethod
    def from_dict(cls, data: dict) -> "OverlayItem":
        src = dict(data or {})
        kind = str(src.get("kind") or "text")
        if kind in TEXT_KINDS and "stroke_on" not in src:
            src.setdefault("bold", kind == "text")
            if kind == "caption":
                src.setdefault("bg_on", True)
                src.setdefault("bg_opacity", 47)
        known = {f.name for f in fields(cls)}
        payload = {k: v for k, v in src.items() if k in known}
        payload.setdefault("id", uuid.uuid4().hex[:10])
        payload.setdefault("kind", "text")
        return cls(**payload)


def default_item(kind: str) -> OverlayItem:
    presets = {
        "text": OverlayItem(id=uuid.uuid4().hex[:10], kind="text", x=0.5, y=0.35, w=0.5, h=0.12, text="Title", font_size=28, color="#fbbf24", bold=True),
        "caption": OverlayItem(id=uuid.uuid4().hex[:10], kind="caption", x=0.5, y=0.84, w=0.7, h=0.10, text="Caption", font_size=10, color="#f8fafc", live=True, bg_on=True, bg_opacity=47),
        "logo": OverlayItem(id=uuid.uuid4().hex[:10], kind="logo", x=0.88, y=0.10, w=0.14, h=0.14, text="LOGO", font_size=14, color="#ffffff"),
        "image": OverlayItem(id=uuid.uuid4().hex[:10], kind="image", x=0.22, y=0.18, w=0.22, h=0.22, text="Image", font_size=12, color="#e2e8f0"),
        "shape": OverlayItem(id=uuid.uuid4().hex[:10], kind="shape", w=shape_size("rect")[0], h=shape_size("rect")[1], text="Element"),
    }
    return presets.get(kind, presets["text"])
