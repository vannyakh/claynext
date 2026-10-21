"""Watermark shelf: pick a mark and place it across the movie."""
from __future__ import annotations

import os
from functools import lru_cache

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from claynext.constants.theme_constants import COLOR_BORDER, COLOR_TEXT_MAIN

from claynext.gui.components.inspector.styles import TILE
from claynext.gui.components.render.text import template_pixmap
from claynext.gui.components.shell.shelf_header import make_shelf_button, make_shelf_header
from claynext.models.text_style import WATERMARK_LOOPS

_IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)"

CATEGORIES: list[tuple[str, str]] = [
    ("all", "All"),
    ("corner", "Corner"),
    ("center", "Center"),
    ("bar", "Bar"),
    ("motion", "Motion"),
]

_COLORS = (
    "#f8fafc", "#000000", "#facc15", "#22d3ee",
    "#f472b6", "#a3e635", "#fb7185", "#c4b5fd",
)
_SPEEDS = (("Slow", 4000), ("Medium", 2400), ("Fast", 1200))


def _mark(
    name: str,
    text: str,
    *,
    category: str,
    x: float,
    y: float,
    size: int = 18,
    opacity: int = 55,
    kind: str = "text",
    rotation: float = 0,
    w: float = 0.34,
    h: float = 0.08,
    color: str = "#f8fafc",
    anim_loop: str = "none",
    anim_loop_ms: int = 4000,
) -> dict:
    return {
        "name": name,
        "text": text,
        "kind": kind,
        "category": category,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "font_size": size,
        "opacity": opacity,
        "rotation": rotation,
        "color": color,
        "bold": True,
        "watermark": True,
        "live": False,
        "anim_in": "none",
        "anim_out": "none",
        "anim_loop": anim_loop,
        "anim_loop_ms": anim_loop_ms,
    }


def _motion(name: str, loop: str) -> dict:
    return _mark(
        name,
        "STUDIO",
        category="motion",
        x=0.5,
        y=0.5,
        size=16,
        opacity=72,
        w=0.3,
        anim_loop=loop,
        anim_loop_ms=4000,
    )


WATERMARKS: list[dict] = [
    _mark("Corner", "STUDIO", category="corner", x=0.84, y=0.08, size=16, opacity=62, w=0.28),
    _mark("Logo", "LOGO", category="corner", kind="logo", x=0.88, y=0.10, size=14, opacity=88, w=0.16, h=0.10),
    _mark("Copyright", "© Studio", category="corner", x=0.78, y=0.93, size=13, opacity=48, w=0.36),
    _mark("Preview", "PREVIEW", category="center", x=0.5, y=0.48, size=36, opacity=26, w=0.7, h=0.16),
    _mark("Draft", "DRAFT", category="center", x=0.5, y=0.5, size=42, opacity=24, rotation=-24, w=0.72, h=0.18),
    _mark("Sample", "SAMPLE", category="center", x=0.5, y=0.5, size=34, opacity=30, w=0.64, h=0.14),
    _mark("Top bar", "Claynext", category="bar", x=0.5, y=0.07, size=18, opacity=70, w=0.46),
    _mark("Bottom bar", "Khmer Dub", category="bar", x=0.5, y=0.93, size=16, opacity=58, w=0.46),
    _motion("Slide bottom", "slide_bottom"),
    _motion("Slide top", "slide_top"),
    _motion("Slide left", "slide_left"),
    _motion("Slide right", "slide_right"),
    _motion("Curve", "curve"),
]


class WatermarkStyleDialog(QDialog):
    """Tools for the words, colour, and travel of one watermark."""

    def __init__(self, style: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Watermark")
        self.setObjectName("watermark_style_dialog")
        self.setModal(True)
        self._base = dict(style)
        self._color = str(style.get("color") or "#f8fafc")
        self.setMinimumWidth(380)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        self.text = QLineEdit(str(style.get("text") or ""))
        self.text.setObjectName("dub_setting_field")
        self.text.setPlaceholderText("Watermark text")
        root.addWidget(self._row("Text", self.text))

        self.size = QSpinBox()
        self.size.setRange(8, 72)
        self.size.setValue(int(style.get("font_size") or 18))
        self.opacity = QSpinBox()
        self.opacity.setRange(8, 100)
        self.opacity.setSuffix("%")
        self.opacity.setValue(int(style.get("opacity") or 60))
        numbers = QHBoxLayout()
        numbers.setSpacing(8)
        numbers.addWidget(self._row("Size", self.size), 1)
        numbers.addWidget(self._row("Opacity", self.opacity), 1)
        root.addLayout(numbers)

        swatches = QHBoxLayout()
        swatches.setSpacing(6)
        self._colors = QButtonGroup(self)
        self._colors.setExclusive(True)
        for hex_color in _COLORS:
            chip = QPushButton()
            chip.setFixedSize(22, 22)
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip(hex_color)
            chip.setStyleSheet(
                f"QPushButton {{ background: {hex_color}; border: 1px solid {COLOR_BORDER}; border-radius: 11px; }}"
                f"QPushButton:checked {{ border: 2px solid {COLOR_TEXT_MAIN}; }}"
            )
            self._colors.addButton(chip)
            swatches.addWidget(chip)
            chip.clicked.connect(lambda _=False, color=hex_color: self._set_color(color))
            if hex_color.lower() == self._color.lower():
                chip.setChecked(True)
        swatches.addStretch(1)
        root.addWidget(self._row("Color", swatches))

        self.motion = QComboBox()
        self.motion.setObjectName("asr_option_combo")
        self.motion.addItem("Still", "none")
        for key, label in WATERMARK_LOOPS:
            self.motion.addItem(label, key)
        current = str(style.get("anim_loop") or "none")
        index = self.motion.findData(current)
        self.motion.setCurrentIndex(index if index >= 0 else 0)
        self.motion.currentIndexChanged.connect(self._sync_speed)
        root.addWidget(self._row("Motion", self.motion))

        self.speed = QComboBox()
        self.speed.setObjectName("asr_option_combo")
        for label, ms in _SPEEDS:
            self.speed.addItem(label, ms)
        loop_ms = int(style.get("anim_loop_ms") or 4000)
        speed_index = min(range(len(_SPEEDS)), key=lambda i: abs(_SPEEDS[i][1] - loop_ms))
        self.speed.setCurrentIndex(speed_index)
        root.addWidget(self._row("Speed", self.speed))
        self._sync_speed()

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("btn_secondary")
        cancel.clicked.connect(self.reject)
        apply = QPushButton("Apply")
        apply.setObjectName("btn_primary")
        apply.setDefault(True)
        apply.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(apply)
        root.addLayout(actions)

    def result_style(self) -> dict:
        out = dict(self._base)
        text = self.text.text().strip()
        if text:
            out["text"] = text
        out["font_size"] = int(self.size.value())
        out["opacity"] = int(self.opacity.value())
        out["color"] = self._color
        out["anim_loop"] = str(self.motion.currentData() or "none")
        out["anim_loop_ms"] = int(self.speed.currentData() or 4000)
        out["anim_in"] = "none"
        out["anim_out"] = "none"
        out["watermark"] = True
        out["live"] = False
        return out

    def _set_color(self, color: str):
        self._color = color

    def _sync_speed(self, *_args):
        self.speed.setEnabled(str(self.motion.currentData() or "none") != "none")

    @staticmethod
    def _row(title: str, field) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        label = QLabel(title)
        label.setObjectName("prop_key")
        lay.addWidget(label)
        if isinstance(field, QHBoxLayout):
            lay.addLayout(field)
        else:
            lay.addWidget(field)
        return wrap


def edit_watermark_style(parent, style: dict) -> dict | None:
    """Open the watermark tools. Returns the edited style, or None when cancelled."""
    dialog = WatermarkStyleDialog(style, parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.result_style()


@lru_cache(maxsize=32)
def watermark_tile(name: str) -> QIcon:
    style = next((row for row in WATERMARKS if row["name"] == name), None)
    if style is None:
        return QIcon()
    return QIcon(template_pixmap(style, style["text"], TILE.width(), TILE.height(), fill=0.7))


class WatermarkPanel(QWidget):
    """Templates for a mark that stays on screen for the whole movie."""

    apply_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("text_styles_panel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._category = "all"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.btn_image = make_shelf_button(
            "Image",
            tip="Use a picture as the watermark",
            icon_name="image",
        )
        self.btn_apply = make_shelf_button(
            "Apply",
            tip="Place the selected watermark across the movie",
        )
        self.btn_image.clicked.connect(self._pick_image)
        self.btn_apply.clicked.connect(self._emit_current)
        outer.addWidget(make_shelf_header("Watermark", self.btn_image, self.btn_apply))

        body = QWidget()
        body.setObjectName("text_styles_body")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        self.search = QLineEdit()
        self.search.setObjectName("dub_setting_field")
        self.search.setPlaceholderText("Search watermarks…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        lay.addWidget(self.search)

        pills = QHBoxLayout()
        pills.setContentsMargins(0, 0, 0, 0)
        pills.setSpacing(6)
        self.pill_group = QButtonGroup(self)
        self.pill_group.setExclusive(True)
        for index, (key, label) in enumerate(CATEGORIES):
            btn = QPushButton(label)
            btn.setObjectName("text_cat_pill")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if index == 0:
                btn.setChecked(True)
            self.pill_group.addButton(btn, index)
            pills.addWidget(btn)
            btn.clicked.connect(lambda _=False, cat=key: self._set_category(cat))
        pills.addStretch(1)
        lay.addLayout(pills)

        self.list = QListWidget()
        self.list.setObjectName("text_style_list")
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setIconSize(TILE)
        self.list.setGridSize(QSize(TILE.width() + 10, TILE.height() + 32))
        self.list.setWordWrap(True)
        self.list.setUniformItemSizes(True)
        self.list.setDragEnabled(False)
        self.list.itemDoubleClicked.connect(lambda *_: self._emit_current())
        for style in WATERMARKS:
            item = QListWidgetItem(watermark_tile(style["name"]), style["name"])
            item.setData(Qt.ItemDataRole.UserRole, style)
            item.setToolTip(f"{style['text']} · double-click to apply")
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.list.addItem(item)
        self.list.setCurrentRow(0)
        lay.addWidget(self.list, 1)
        outer.addWidget(body, 1)

    def current_style(self) -> dict | None:
        item = self.list.currentItem()
        if item is None or item.isHidden():
            return None
        style = item.data(Qt.ItemDataRole.UserRole)
        return dict(style) if isinstance(style, dict) else None

    def _set_category(self, category: str):
        self._category = category
        self._apply_filter()

    def _apply_filter(self, *_args):
        query = self.search.text().strip().lower()
        for index in range(self.list.count()):
            item = self.list.item(index)
            style = item.data(Qt.ItemDataRole.UserRole) or {}
            cat = str(style.get("category") or "")
            visible = (self._category == "all" or cat == self._category) and (
                not query or query in item.text().lower() or query in str(style.get("text") or "").lower()
            )
            item.setHidden(not visible)

    def _emit_current(self, *_args):
        style = self.current_style()
        if not style:
            return
        edited = edit_watermark_style(self, style)
        if edited:
            self.apply_requested.emit(edited)

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Watermark image", "", _IMAGE_FILTER)
        if not path or not os.path.isfile(path):
            return
        base = self.current_style() or WATERMARKS[1]
        style = dict(base)
        style["kind"] = "logo"
        style["path"] = path
        style["text"] = os.path.splitext(os.path.basename(path))[0]
        style["name"] = style["text"]
        style["watermark"] = True
        style.setdefault("w", 0.16)
        style.setdefault("h", 0.12)
        style.setdefault("opacity", 88)
        edited = edit_watermark_style(self, style)
        if edited:
            self.apply_requested.emit(edited)
