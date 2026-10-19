"""Timecode and drop helpers for the timeline widgets."""
from __future__ import annotations

import os

from claynext.constants.timeline_constants import AUDIO_EXTS, IMAGE_EXTS
from claynext.models.thumbnails import VIDEO_EXTS
from claynext.gui.components.inspector.styles import TEXT_STYLE_MIME


def fmt_ms(ms: int) -> str:
    s = max(0, int(ms)) // 1000
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:02d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def fmt_tc(ms: int) -> str:
    ms = max(0, int(ms))
    s, milli = divmod(ms, 1000)
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    fr = milli // 40
    if h:
        return f"{h:02d}:{m:02d}:{sec:02d}:{fr:02d}"
    return f"{m:02d}:{sec:02d}:{fr:02d}"


def paths_from_mime(mime) -> list[str]:
    if mime is None or not mime.hasUrls():
        return []
    out = []
    for url in mime.urls():
        path = url.toLocalFile()
        if path and os.path.isfile(path):
            out.append(os.path.abspath(path))
    return out


def has_drop(mime) -> bool:
    return bool(paths_from_mime(mime) or (mime and mime.hasFormat(TEXT_STYLE_MIME)))


def kind_for_path(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    return ""


def image_frame(path: str, canvas_aspect: float = 16 / 9, max_frac: float = 0.62) -> tuple[float, float]:
    """Normalized width and height so the element frame matches the picture on the canvas."""
    from PySide6.QtGui import QImageReader

    aspect = canvas_aspect if canvas_aspect and canvas_aspect > 0 else 16 / 9
    size = QImageReader(path).size()
    pw, ph = size.width(), size.height()
    if pw <= 0 or ph <= 0:
        return 0.42, 0.42
    img_aspect = pw / float(ph)
    if img_aspect >= aspect:
        width = max_frac
        height = width * aspect / img_aspect
    else:
        height = max_frac
        width = height * img_aspect / aspect
    return round(max(0.08, min(0.92, width)), 4), round(max(0.08, min(0.92, height)), 4)

