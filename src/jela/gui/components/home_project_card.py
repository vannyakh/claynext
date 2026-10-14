"""Project cards for list/grid modes on Project Home."""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from jela.constants.theme_constants import COLOR_TEXT_MUTED
from jela.core.icons import icon

LIST_CARD_H = 64
GRID_CARD_W = 168
GRID_CARD_H = 172
GRID_CELL = QSize(184, 196)


def fmt_project_mtime(mtime: float, saved_at: str = "") -> str:
    if saved_at:
        text = saved_at.replace("T", " ").replace("+00:00", " UTC")
        return text[:16] if len(text) > 16 else text
    if not mtime:
        return "—"
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


class HomeProjectCard(QWidget):
    """Single recent-project card (list or grid layout)."""

    open_requested = Signal(str)

    def __init__(self, row: dict, *, mode: str = "list", parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._path = str(row.get("path") or "")
        self.setToolTip(self._path)
        if mode == "grid":
            self._build_grid(row)
        else:
            self._build_list(row)

    def _build_list(self, row: dict):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(12)

        thumb = QLabel()
        thumb.setObjectName("home_card_thumb_list")
        thumb.setFixedSize(40, 40)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setPixmap(icon("video", color=COLOR_TEXT_MUTED, size=18).pixmap(18, 18))
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

        btn = QPushButton("Open")
        btn.setObjectName("home_card_open")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedWidth(64)
        btn.clicked.connect(lambda: self.open_requested.emit(self._path))
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)

    def _build_grid(self, row: dict):
        self.setFixedSize(GRID_CARD_W, GRID_CARD_H)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        thumb = QLabel()
        thumb.setObjectName("home_card_thumb_grid")
        thumb.setFixedHeight(88)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setPixmap(icon("video", color=COLOR_TEXT_MUTED, size=28).pixmap(28, 28))
        lay.addWidget(thumb)

        name = QLabel(row.get("name") or "Untitled")
        name.setObjectName("home_card_name_grid")
        name.setWordWrap(True)
        name.setMaximumHeight(34)
        lay.addWidget(name)

        meta = QLabel(fmt_project_mtime(row.get("mtime") or 0.0, row.get("saved_at") or ""))
        meta.setObjectName("home_card_meta")
        lay.addWidget(meta)

        btn = QPushButton("Open")
        btn.setObjectName("home_card_open")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self.open_requested.emit(self._path))
        lay.addWidget(btn)
