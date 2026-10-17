"""Project cards for list/grid modes on Project Home."""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt, QSize, QThreadPool, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from claynext.constants.theme_constants import COLOR_TEXT_MUTED
from claynext.gui.icons import icon
from claynext.gui.worker import Worker
from claynext.models.thumbnails import IMAGE_EXTS, VIDEO_EXTS, ensure_thumbnail

LIST_CARD_H = 64
GRID_CARD_W = 168
GRID_CARD_H = 148
GRID_CELL = QSize(184, 168)

_LIST_THUMB = QSize(40, 40)
_GRID_THUMB = QSize(148, 88)


def fmt_project_mtime(mtime: float, saved_at: str = "") -> str:
    if saved_at:
        text = saved_at.replace("T", " ").replace("+00:00", " UTC")
        return text[:16] if len(text) > 16 else text
    if not mtime:
        return "—"
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


def _thumb_source(row: dict) -> str:
    """Prefer project media path; fall back to nested project.media."""
    for key in ("media",):
        path = str(row.get(key) or "").strip()
        if path and os.path.isfile(path):
            return path
    return ""


def _make_thumb_file(media_path: str, width: int, progress_callback=None) -> str | None:
    """Worker target: return cached/extracted thumb path (or image path)."""
    del progress_callback  # injected by Worker
    if not media_path or not os.path.isfile(media_path):
        return None
    ext = os.path.splitext(media_path)[1].lower()
    if ext in IMAGE_EXTS:
        return media_path
    if ext in VIDEO_EXTS:
        return ensure_thumbnail(media_path, width=width)
    return None


class HomeProjectCard(QWidget):
    """Single recent-project card (list or grid layout). Click anywhere to open."""

    open_requested = Signal(str)

    def __init__(self, row: dict, *, mode: str = "list", parent=None):
        super().__init__(parent)
        self.setObjectName("home_project_card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._path = str(row.get("path") or "")
        self._media = _thumb_source(row)
        self._thumb_lbl: QLabel | None = None
        self._thumb_size = _LIST_THUMB
        self.setToolTip(self._path)
        if mode == "grid":
            self._build_grid(row)
        else:
            self._build_list(row)
        self._start_thumb_load()

    def _build_list(self, row: dict):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(12)

        self._thumb_size = _LIST_THUMB
        thumb = QLabel()
        thumb.setObjectName("home_card_thumb_list")
        thumb.setFixedSize(_LIST_THUMB)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setPixmap(icon("video", color=COLOR_TEXT_MUTED, size=18).pixmap(18, 18))
        self._thumb_lbl = thumb
        lay.addWidget(thumb)

        col = QVBoxLayout()
        col.setSpacing(4)
        name = QLabel(row.get("name") or "Untitled")
        name.setObjectName("home_card_name")
        col.addWidget(name)
        meta = QLabel(
            f"{fmt_project_mtime(row.get('mtime') or 0.0, row.get('saved_at') or '')}"
            f"  ·  {os.path.basename(self._path)}"
        )
        meta.setObjectName("home_card_meta")
        col.addWidget(meta)
        lay.addLayout(col, 1)

    def _build_grid(self, row: dict):
        self.setFixedSize(GRID_CARD_W, GRID_CARD_H)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        self._thumb_size = _GRID_THUMB
        thumb = QLabel()
        thumb.setObjectName("home_card_thumb_grid")
        thumb.setFixedSize(_GRID_THUMB)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setPixmap(icon("video", color=COLOR_TEXT_MUTED, size=28).pixmap(28, 28))
        self._thumb_lbl = thumb
        lay.addWidget(thumb)

        name = QLabel(row.get("name") or "Untitled")
        name.setObjectName("home_card_name_grid")
        name.setWordWrap(True)
        name.setMaximumHeight(34)
        lay.addWidget(name)

        meta = QLabel(fmt_project_mtime(row.get("mtime") or 0.0, row.get("saved_at") or ""))
        meta.setObjectName("home_card_meta")
        lay.addWidget(meta)
        lay.addStretch(1)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._path:
            self.open_requested.emit(self._path)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _start_thumb_load(self):
        if not self._media or self._thumb_lbl is None:
            return
        width = max(160, self._thumb_size.width() * 2)
        worker = Worker(_make_thumb_file, self._media, width)
        worker.signals.result.connect(self._on_thumb_ready)
        QThreadPool.globalInstance().start(worker)

    def _on_thumb_ready(self, path: object):
        if not isinstance(path, str) or not path or self._thumb_lbl is None:
            return
        pix = QPixmap(path)
        if pix.isNull():
            return
        scaled = pix.scaled(
            self._thumb_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (scaled.width() - self._thumb_size.width()) // 2)
        y = max(0, (scaled.height() - self._thumb_size.height()) // 2)
        cropped = scaled.copy(x, y, self._thumb_size.width(), self._thumb_size.height())
        self._thumb_lbl.setPixmap(cropped)
