"""Effects, filters and shapes shelves: drag or add a tile onto its timeline track."""
from __future__ import annotations

from functools import lru_cache
import math
import os

import numpy as np
from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListView,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from claynext.constants.theme_constants import COLOR_BORDER, COLOR_PRIMARY, COLOR_TEXT_MAIN
from claynext.services.video_fx import DEFAULT_INTENSITY, EFFECTS, FILTER_LOOKS, apply_fx
from claynext.services.video_transitions import DEFAULT_DURATION_MS, DEFAULT_INTENSITY as TR_INTENSITY, TRANSITIONS
from claynext.gui.components.shape_render import (
    BLUR_SHAPES, ELEMENTS, SHAPES, element_tile_icon, sample_cinematic_image, shape_size,
)
from claynext.gui.components.shelf_header import make_shelf_header
from claynext.gui.components.text_styles_panel import TILE, StyleList
from claynext.utils.paths import BASE_DIR

_PREVIEW_MS = {"flash": 100, "fade_in": 300, "fade_out": 700, "zoom": 999}
_TEXTS = {
    "effect": ("Effects", "Search effects…"),
    "filter": ("Filters", "Search filters…"),
    "transition": ("Transitions", "Search transitions…"),
    "shape": ("Elements", "Search elements…"),
    "elements": ("Elements", "Search elements…"),
}
CATEGORIES_ELEMENTS: list[tuple[str, str]] = [
    ("all", "All"),
    ("blur", "Blur & Masks"),
    ("shapes", "Basic"),
    ("arrows", "Arrows"),
    ("callouts", "Callouts"),
    ("icons", "Icons"),
]
_LOOP_STEPS = 8


def _sample() -> np.ndarray:
    """A realistic cinematic movie still used for backdrop of fx tiles and cards."""
    return sample_cinematic_image()


def _pixmap(rgb: np.ndarray, radius: float = 6.0, divider_x: int | None = None) -> QPixmap:
    rgb = np.ascontiguousarray(rgb)
    h, w = rgb.shape[:2]
    src_pix = QPixmap.fromImage(QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy())

    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    r = radius * 2.0
    path = QPainterPath()
    path.addRoundedRect(0, 0, w, h, r, r)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, src_pix)

    if divider_x is not None and 6 < divider_x < w - 6:
        painter.setPen(QPen(QColor(255, 255, 255, 210), 2.0))
        painter.drawLine(divider_x, 0, divider_x, h)

    # Subtle inner border to make thumbnail pop on dark theme
    painter.setClipping(False)
    painter.setPen(QColor(255, 255, 255, 28))
    painter.drawRoundedRect(0.5, 0.5, w - 1, h - 1, r, r)
    painter.end()

    out.setDevicePixelRatio(2.0)
    return out


@lru_cache(maxsize=64)
def fx_tile(kind: str, key: str) -> QIcon:
    """Default static preview icon for shelf and inspector."""
    if kind == "transition":
        intensity = TR_INTENSITY
    elif kind == "filter":
        intensity = DEFAULT_INTENSITY["filter"]
    else:
        intensity = 80
    span = {"kind": kind, kind: key, "intensity": intensity, "start_ms": 0, "end_ms": 1000}
    preview_ms = _PREVIEW_MS.get(key, 500)
    if kind == "transition":
        preview_ms = 550
    return QIcon(_pixmap(apply_fx(_sample().copy(), [span], preview_ms)))


@lru_cache(maxsize=512)
def fx_tile_frame(kind: str, key: str, frame_idx: int) -> QIcon:
    """Dynamic animated preview frame for hover loop."""
    base = _sample().copy()
    h, w = base.shape[:2]
    step = frame_idx % _LOOP_STEPS

    if kind == "filter":
        # Smooth wipe loop: wipe sweep line moving left to right showing before/after
        ratio = (step + 1) / _LOOP_STEPS
        span = {"kind": "filter", "filter": key, "intensity": DEFAULT_INTENSITY["filter"], "start_ms": 0, "end_ms": 1000}
        graded = apply_fx(base.copy(), [span], 500)
        split_x = int(round(w * ratio))
        frame = base.copy()
        if split_x > 0:
            frame[:, :split_x] = graded[:, :split_x]
        div_x = split_x if step < _LOOP_STEPS - 1 else None
        return QIcon(_pixmap(frame, divider_x=div_x))

    if kind == "effect":
        span = {"kind": "effect", "effect": key, "intensity": 80, "start_ms": 0, "end_ms": 1000}
        if key in ("shake", "zoom", "flash", "fade_in", "fade_out", "grain", "glitch"):
            now_ms = int((step / _LOOP_STEPS) * 1000)
            return QIcon(_pixmap(apply_fx(base, [span], now_ms)))
        else:
            pulse = 0.5 + 0.5 * math.sin((step / _LOOP_STEPS) * 2 * math.pi)
            span["intensity"] = int(round(40 + 60 * pulse))
            return QIcon(_pixmap(apply_fx(base, [span], 500)))

    if kind == "transition":
        span = {
            "kind": "transition",
            "transition": key,
            "intensity": TR_INTENSITY,
            "start_ms": 0,
            "end_ms": 1000,
        }
        now_ms = int((step / _LOOP_STEPS) * 1000)
        return QIcon(_pixmap(apply_fx(base, [span], now_ms)))

    return fx_tile(kind, key)


def shelf_items(kind: str) -> list[tuple[str, dict, QIcon, str]]:
    if kind == "effect":
        return [(label, {"kind": "effect", "effect": key, "intensity": DEFAULT_INTENSITY["effect"], "name": label},
                 fx_tile("effect", key), hint) for key, label, hint in EFFECTS]
    if kind == "filter":
        return [(label, {"kind": "filter", "filter": key, "intensity": DEFAULT_INTENSITY["filter"], "name": label},
                 fx_tile("filter", key), label) for key, label in FILTER_LOOKS]
    if kind == "transition":
        return [
            (
                label,
                {
                    "kind": "transition",
                    "transition": key,
                    "intensity": TR_INTENSITY,
                    "name": label,
                    "duration_ms": DEFAULT_DURATION_MS,
                },
                fx_tile("transition", key),
                hint,
            )
            for key, label, hint in TRANSITIONS
        ]
    out = []
    for key, label, cat, (w, h), hint in ELEMENTS:
        is_blur = key in BLUR_SHAPES
        style = {
            "kind": "shape",
            "shape": key,
            "name": label,
            "text": label,
            "w": w,
            "h": h,
            "color": "#f8fafc",
            "opacity": 100,
            "rotation": 0,
            "category": cat,
            "blur_on": is_blur,
            "blur_radius": 24 if is_blur else 20,
        }
        out.append((label, style, element_tile_icon(key), hint))
    return out


class FxShelfList(StyleList):
    """List with interactive hover preview loop for effects and filters."""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setMouseTracking(True)
        self._hover_item: QListWidgetItem | None = None
        self._hover_frame = 0
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(125)  # ~8 fps preview loop
        self._hover_timer.timeout.connect(self._on_hover_tick)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        item = self.itemAt(event.pos())
        if item is not self._hover_item:
            self._stop_hover()
            if item is not None and self.kind in ("effect", "filter", "transition"):
                self._hover_item = item
                self._hover_frame = 0
                self._hover_timer.start()

    def leaveEvent(self, event):
        self._stop_hover()
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._stop_hover()
        super().hideEvent(event)

    def startDrag(self, supported):
        self._stop_hover()
        super().startDrag(supported)

    def _stop_hover(self):
        self._hover_timer.stop()
        if self._hover_item is not None:
            data = self._hover_item.data(Qt.ItemDataRole.UserRole)
            if data:
                key = data.get(self.kind)
                if key:
                    self._hover_item.setIcon(fx_tile(self.kind, key))
            self._hover_item = None
            self._hover_frame = 0

    def _on_hover_tick(self):
        if self._hover_item is None:
            self._hover_timer.stop()
            return
        data = self._hover_item.data(Qt.ItemDataRole.UserRole)
        if not data:
            self._stop_hover()
            return
        key = data.get(self.kind)
        if not key:
            self._stop_hover()
            return
        self._hover_frame = (self._hover_frame + 1) % _LOOP_STEPS
        icon = fx_tile_frame(self.kind, key, self._hover_frame)
        self._hover_item.setIcon(icon)


class FxShelfPanel(QWidget):
    add_requested = Signal(dict)

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setObjectName("text_styles_panel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._active_category = "all"
        title_text, search_text = _TEXTS.get(kind, ("Elements", "Search elements…"))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(make_shelf_header(title_text))
        body = QWidget()
        body.setObjectName("text_styles_body")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        self.search = QLineEdit()
        self.search.setObjectName("dub_setting_field")
        self.search.setPlaceholderText(search_text)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)

        if kind in ("shape", "elements"):
            pill_scroll = QScrollArea()
            pill_scroll.setWidgetResizable(True)
            pill_scroll.setFrameShape(QFrame.Shape.NoFrame)
            pill_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            pill_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            pill_scroll.setFixedHeight(28)
            pill_scroll.setStyleSheet("background: transparent; border: none;")
            pill_box = QWidget()
            pill_box.setStyleSheet("background: transparent;")
            pill_lay = QHBoxLayout(pill_box)
            pill_lay.setContentsMargins(0, 0, 0, 0)
            pill_lay.setSpacing(6)
            self.pill_group = QButtonGroup(self)
            self.pill_group.setExclusive(True)

            for idx, (cat_id, cat_label) in enumerate(CATEGORIES_ELEMENTS):
                btn = QPushButton(cat_label.replace("&", "&&"))
                btn.setObjectName("text_cat_pill")
                btn.setCheckable(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                if idx == 0:
                    btn.setChecked(True)
                self.pill_group.addButton(btn, idx)
                pill_lay.addWidget(btn)
                btn.clicked.connect(lambda _, c=cat_id: self._set_category(c))

            pill_lay.addStretch(1)
            pill_scroll.setWidget(pill_box)
            lay.addWidget(pill_scroll)

        self.list = FxShelfList(kind)
        self.list.setObjectName("text_style_list")
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setIconSize(TILE)
        self.list.setGridSize(QSize(TILE.width() + 10, TILE.height() + 34))
        self.list.setWordWrap(True)
        self.list.setUniformItemSizes(True)
        self.list.setDragEnabled(True)
        self.list.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.list.itemDoubleClicked.connect(self._emit_current)
        for label, data, tile, tip in shelf_items(kind):
            item = QListWidgetItem(tile, label)
            item.setData(Qt.ItemDataRole.UserRole, data)
            item.setToolTip(f"{tip} · double-click or drag onto the timeline")
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.list.addItem(item)
        self.list.setCurrentRow(0)
        lay.addWidget(self.list, 1)
        outer.addWidget(body, 1)

    def _set_category(self, cat_id: str):
        self._active_category = cat_id
        self._filter(self.search.text())

    def _filter(self, query: str = ""):
        needle = (query if isinstance(query, str) else self.search.text()).strip().lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole) or {}
            item_cat = data.get("category", "")
            cat_match = (self._active_category == "all" or item_cat == self._active_category)
            text_match = (
                not needle
                or needle in item.text().lower()
                or needle in data.get("name", "").lower()
                or needle in data.get("hint", "").lower()
            )
            item.setHidden(not (cat_match and text_match))

    def _emit_current(self, *_):
        item = self.list.currentItem()
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        if data:
            self.add_requested.emit(dict(data))

