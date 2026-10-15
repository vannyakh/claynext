"""Timecode and drop helpers for the timeline widgets."""
from __future__ import annotations

import os

from claynext.constants.timeline_constants import AUDIO_EXTS, IMAGE_EXTS
from claynext.services.thumbnails import VIDEO_EXTS
from claynext.gui.components.text_styles_panel import TEXT_STYLE_MIME


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
