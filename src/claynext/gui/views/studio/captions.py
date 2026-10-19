"""Caption config shelf: auto captions, word animation, fit, and apply."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QScrollArea,
    QButtonGroup, QToolButton, QGridLayout, QCheckBox, QSizePolicy, QColorDialog,
)

from claynext.constants.theme_constants import COLOR_BORDER
from claynext.gui.icons import icon
from claynext.models.text_style import CAPTION_ANIMS, CAPTION_WIDTH_RANGE, TEXT_COLORS, clean_text_style
from claynext.gui.components.scrub_spin import ScrubSpinBox
from claynext.gui.components.text_render import anim_loop_ms, anim_preview_pixmap, template_pixmap
from claynext.gui.components.text_styles_panel import TEXT_STYLES


CAPTION_STYLES: list[dict] = [
    dict(style) for style in TEXT_STYLES
    if style.get("kind") == "caption" or style.get("live") or "subtitle" in style["name"].lower()
]
if not CAPTION_STYLES:
    CAPTION_STYLES = [dict(next((s for s in TEXT_STYLES if s.get("live")), TEXT_STYLES[0]))]

_HIGHLIGHT_SWATCHES = (
    "#facc15", "#22c55e", "#06b6d4", "#f97316",
    "#ec4899", "#a855f7", "#38bdf8", "#ffffff",
)

_SHORT_NAMES = {
    "Subtitle": "Subtitle",
    "Yellow subtitle": "Yellow",
    "Boxed caption": "Boxed",
    "Live caption": "Live",
    "Word karaoke": "Words",
    "Highlight caption": "Karaoke",
    "Lower third": "Lower 3rd",
}

_PREVIEW_W, _PREVIEW_H = 72, 28
_TILE_MIN_W = 72
_TILE_GAP = 6
_TILE_H = 56
_LOOK_MAX_COLS = 4
_LABEL_MAX = 10

_MOTION_PREVIEW_W, _MOTION_PREVIEW_H = 44, 24
_MOTION_TILE_MIN_W = 48
_MOTION_TILE_H = 50
_MOTION_MAX_COLS = 5

_MOTION_SHORT = {
    "none": "Static",
    "words": "Words",
    "highlight": "Karaoke",
    "typewriter": "Type",
    "fade": "Fade",
}

_SWATCH_SIDE = 22
_SWATCH_GAP = 6


def is_managed_caption(clip) -> bool:
    """Auto-built caption segments (and legacy single live caption tracks)."""
    if getattr(clip, "kind", "") != "caption":
        return False
    ov = clip.extra.get("overlay") or {}
    return bool(ov.get("auto_caption") or ov.get("live"))


def _swatch_icon(color: str, side: int = 18) -> QIcon:
    pix = QPixmap(side * 2, side * 2)
    pix.setDevicePixelRatio(2.0)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    fill = QColor(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(fill)
    p.drawEllipse(1, 1, side - 2, side - 2)
    p.end()
    icon = QIcon()
    icon.addPixmap(pix, QIcon.Mode.Normal)
    icon.addPixmap(pix, QIcon.Mode.Disabled)
    return icon


def _short_label(style: dict | str) -> str:
    """Single-line tile label — keeps every card the same height."""
    if isinstance(style, dict):
        name = str(style.get("name") or "")
        label = str(style.get("display_label") or _SHORT_NAMES.get(name, name) or "Style")
    else:
        label = _SHORT_NAMES.get(style, style) or "Style"
    label = " ".join(str(label).split())
    if len(label) > _LABEL_MAX:
        return label[: _LABEL_MAX - 1] + "…"
    return label


class CaptionLookGrid(QWidget):
    """Responsive look-preset grid — uniform tile height across all rows."""

    style_picked = Signal(int)

    def __init__(self, styles: list[dict], parent=None):
        super().__init__(parent)
        self.setObjectName("caption_look_grid")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._styles = styles
        self._cols = 0
        self._cell_w = _TILE_MIN_W
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(_TILE_GAP)
        self._grid.setVerticalSpacing(_TILE_GAP)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._btns: list[QToolButton] = []
        for i, style in enumerate(styles):
            name = style.get("name") or f"Style {i + 1}"
            sample = "Words" if style.get("name") == "Word karaoke" else (style.get("text") or "Aa")
            btn = QToolButton(self)
            btn.setObjectName("caption_look_tile")
            btn.setCheckable(True)
            btn.setAutoRaise(False)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setIcon(QIcon(template_pixmap(style, sample, _PREVIEW_W, _PREVIEW_H, fill=0.86, plate=False)))
            btn.setIconSize(QSize(_PREVIEW_W, _PREVIEW_H))
            btn.setText(_short_label(style))
            btn.setToolTip(str(style.get("display_label") or name))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.setFixedSize(_TILE_MIN_W, _TILE_H)
            self._group.addButton(btn, i)
            self._btns.append(btn)
        self._group.idClicked.connect(self.style_picked.emit)
        self._reflow(force=True)

    def set_current(self, index: int):
        btn = self._group.button(max(0, index))
        if btn is not None:
            btn.setChecked(True)

    def current(self) -> int:
        return max(0, self._group.checkedId())

    def _rows(self) -> int:
        cols = max(1, self._cols or 2)
        return max(1, (len(self._btns) + cols - 1) // cols)

    def sizeHint(self) -> QSize:
        cols = max(2, self._cols or 3)
        h = self._rows() * _TILE_H + max(0, self._rows() - 1) * _TILE_GAP
        return QSize(cols * _TILE_MIN_W + max(0, cols - 1) * _TILE_GAP, h)

    def minimumSizeHint(self) -> QSize:
        return QSize(_TILE_MIN_W * 2 + _TILE_GAP, _TILE_H * 2 + _TILE_GAP)

    def heightForWidth(self, width: int) -> int:
        cols = 4 if width >= 400 else (3 if width >= 240 else 2)
        rows = max(1, (len(self._btns) + cols - 1) // cols)
        return rows * _TILE_H + max(0, rows - 1) * _TILE_GAP

    def hasHeightForWidth(self) -> bool:
        return True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    def _reflow(self, force: bool = False):
        width = max(160, self.width())
        cols = 4 if width >= 400 else (3 if width >= 240 else 2)
        cell_w = max(_TILE_MIN_W, (width - _TILE_GAP * max(0, cols - 1)) // cols)
        if not force and cols == self._cols and cell_w == self._cell_w:
            return
        self._cols = cols
        self._cell_w = cell_w
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().setParent(self)
        for c in range(_LOOK_MAX_COLS + 1):
            self._grid.setColumnStretch(c, 0)
            self._grid.setColumnMinimumWidth(c, cell_w if c < cols else 0)
        rows = self._rows()
        for r in range(rows + 1):
            self._grid.setRowStretch(r, 0)
            self._grid.setRowMinimumHeight(r, _TILE_H if r < rows else 0)
        for i, btn in enumerate(self._btns):
            btn.setFixedSize(cell_w, _TILE_H)
            self._grid.addWidget(btn, i // cols, i % cols, Qt.AlignmentFlag.AlignTop)
        total_h = rows * _TILE_H + max(0, rows - 1) * _TILE_GAP
        self.setFixedHeight(total_h)
        self.updateGeometry()


class CaptionMotionGrid(QWidget):
    """Card grid of caption motion presets with live looping animation previews."""

    anim_picked = Signal(int)

    def __init__(self, anims: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setObjectName("caption_motion_grid")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._anims = anims
        self._cols = 0
        self._cell_w = _MOTION_TILE_MIN_W
        self._t = 0
        self._hl = "#facc15"
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(_TILE_GAP)
        self._grid.setVerticalSpacing(_TILE_GAP)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._btns: list[QToolButton] = []
        self._kinds: list[str] = []
        for i, (key, label) in enumerate(anims):
            btn = QToolButton(self)
            btn.setObjectName("caption_motion_tile")
            btn.setCheckable(True)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setIconSize(QSize(_MOTION_PREVIEW_W, _MOTION_PREVIEW_H))
            btn.setText(_MOTION_SHORT.get(key, label))
            btn.setToolTip(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.setFixedSize(_MOTION_TILE_MIN_W, _MOTION_TILE_H)
            self._group.addButton(btn, i)
            self._btns.append(btn)
            self._kinds.append(key)
        self._group.idClicked.connect(self.anim_picked.emit)
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        self._paint_frames(0)
        self._reflow(force=True)

    def set_current(self, index: int):
        btn = self._group.button(max(0, index))
        if btn is not None:
            btn.setChecked(True)

    def current(self) -> int:
        return max(0, self._group.checkedId())

    def set_highlight_color(self, color: str):
        self._hl = color or "#facc15"
        self._paint_frames(self._t)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    def showEvent(self, event):
        super().showEvent(event)
        self._reflow(force=True)
        if any(anim_loop_ms(k) for k in self._kinds):
            self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self):
        self._t = (self._t + self._timer.interval()) % 100_000
        self._paint_frames(self._t)

    def _paint_frames(self, t_ms: int):
        for btn, kind in zip(self._btns, self._kinds):
            hold = 350
            loop = anim_loop_ms(kind)
            if loop <= 0:
                pix = anim_preview_pixmap(
                    kind, 0, _MOTION_PREVIEW_W, _MOTION_PREVIEW_H, highlight_color=self._hl, plate=False,
                )
            else:
                cycle = loop + hold
                local = t_ms % cycle
                frame_t = min(local, loop - 1)
                pix = anim_preview_pixmap(
                    kind, frame_t, _MOTION_PREVIEW_W, _MOTION_PREVIEW_H, highlight_color=self._hl, plate=False,
                )
            btn.setIcon(QIcon(pix))

    def _reflow(self, force: bool = False):
        if not self._btns:
            return
        width = max(160, self.width())
        cols = 5 if width >= 260 else 3
        cell_w = max(_MOTION_TILE_MIN_W, (width - _TILE_GAP * max(0, cols - 1)) // cols)
        if not force and cols == self._cols and cell_w == self._cell_w:
            return
        self._cols = cols
        self._cell_w = cell_w
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().setParent(self)
        for c in range(_MOTION_MAX_COLS + 1):
            self._grid.setColumnStretch(c, 0)
            self._grid.setColumnMinimumWidth(c, cell_w if c < cols else 0)
        rows = max(1, (len(self._btns) + cols - 1) // cols)
        for r in range(rows + 1):
            self._grid.setRowStretch(r, 0)
            self._grid.setRowMinimumHeight(r, _MOTION_TILE_H if r < rows else 0)
        for i, btn in enumerate(self._btns):
            btn.setFixedSize(cell_w, _MOTION_TILE_H)
            self._grid.addWidget(btn, i // cols, i % cols, Qt.AlignmentFlag.AlignTop)
        total_h = rows * _MOTION_TILE_H + max(0, rows - 1) * _TILE_GAP
        self.setFixedHeight(total_h)
        self.updateGeometry()


class CaptionColorPick(QWidget):
    """Responsive highlight colour swatches with custom color picker dialog."""

    color_picked = Signal(int)
    color_changed = Signal(str)

    def __init__(self, colors: tuple[str, ...], parent=None):
        super().__init__(parent)
        self.setObjectName("caption_color_pick")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._colors = colors
        self._current_hex = colors[0] if colors else "#facc15"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)

        lbl = QLabel("Highlight colour")
        lbl.setObjectName("asr_field_label")
        head.addWidget(lbl)
        head.addStretch(1)

        self.btn_hex = QPushButton(self._current_hex.upper())
        self.btn_hex.setObjectName("caption_color_hex")
        self.btn_hex.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_hex.setToolTip("Click to choose a custom highlight colour")
        self.btn_hex.clicked.connect(self._pick_custom)
        head.addWidget(self.btn_hex)
        outer.addLayout(head)

        swatch_row = QHBoxLayout()
        swatch_row.setContentsMargins(0, 0, 0, 0)
        swatch_row.setSpacing(_SWATCH_GAP)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._btns: list[QToolButton] = []
        for i, color in enumerate(colors):
            btn = QToolButton(self)
            btn.setObjectName("caption_color_swatch")
            btn.setCheckable(True)
            btn.setFixedSize(QSize(_SWATCH_SIDE + 4, _SWATCH_SIDE + 4))
            btn.setIcon(_swatch_icon(color, _SWATCH_SIDE - 4))
            btn.setIconSize(QSize(_SWATCH_SIDE - 4, _SWATCH_SIDE - 4))
            btn.setToolTip(color.upper())
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._group.addButton(btn, i)
            self._btns.append(btn)
            swatch_row.addWidget(btn)

        self.btn_custom = QToolButton(self)
        self.btn_custom.setObjectName("caption_color_custom")
        self.btn_custom.setFixedSize(QSize(_SWATCH_SIDE + 4, _SWATCH_SIDE + 4))
        self.btn_custom.setIcon(icon("plus", color="#94a3b8", size=11))
        self.btn_custom.setIconSize(QSize(11, 11))
        self.btn_custom.setToolTip("Custom colour...")
        self.btn_custom.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_custom.clicked.connect(self._pick_custom)
        swatch_row.addWidget(self.btn_custom)
        swatch_row.addStretch(1)

        outer.addLayout(swatch_row)
        self._group.idClicked.connect(self._on_pick)

    def set_current(self, index_or_color: int | str):
        if isinstance(index_or_color, int):
            idx = max(0, min(index_or_color, len(self._btns) - 1))
            btn = self._group.button(idx)
            if btn is not None:
                btn.setChecked(True)
                self._current_hex = self._colors[idx]
                self.btn_hex.setText(self._current_hex.upper())
        else:
            color = str(index_or_color).lower()
            self._current_hex = color
            self.btn_hex.setText(color.upper())
            match = next((i for i, c in enumerate(self._colors) if c.lower() == color), -1)
            if match >= 0:
                self._group.button(match).setChecked(True)
            else:
                self._group.setExclusive(False)
                for b in self._btns:
                    b.setChecked(False)
                self._group.setExclusive(True)

    def current(self) -> int:
        return max(0, self._group.checkedId())

    def current_color(self) -> str:
        return self._current_hex

    def _on_pick(self, index: int):
        if 0 <= index < len(self._colors):
            self._current_hex = self._colors[index]
            self.btn_hex.setText(self._current_hex.upper())
            self.color_picked.emit(index)
            self.color_changed.emit(self._current_hex)

    def _pick_custom(self):
        c = QColorDialog.getColor(QColor(self._current_hex), self, "Highlight Colour")
        if c.isValid():
            hex_val = c.name().lower()
            self.set_current(hex_val)
            self.color_changed.emit(hex_val)
            match = next((i for i, col in enumerate(self._colors) if col.lower() == hex_val), -1)
            if match >= 0:
                self.color_picked.emit(match)


class CaptionFieldGrid(QWidget):
    """Label + spin pairs that reflow 1–3 columns with the panel width."""

    def __init__(self, pairs: list[tuple[QLabel, ScrubSpinBox]], parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._pairs = pairs
        self._cols = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 2, 0, 0)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(8)
        self._cells: list[QWidget] = []
        for lbl, spin in pairs:
            cell = QWidget(self)
            cell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row = QHBoxLayout(cell)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            spin.setMinimumWidth(84)
            spin.setMaximumWidth(16777215)
            row.addWidget(lbl, 0)
            row.addWidget(spin, 1)
            self._cells.append(cell)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    def showEvent(self, event):
        super().showEvent(event)
        self._reflow(force=True)

    def _reflow(self, force: bool = False):
        n = len(self._cells)
        if not n:
            return
        width = max(160, self.width())
        if width >= 480:
            cols = min(3, n)
        elif width >= 260:
            cols = min(2, n)
        else:
            cols = 1
        if not force and cols == self._cols:
            return
        self._cols = cols
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().setParent(self)
        for c in range(4):
            self._grid.setColumnStretch(c, 1 if c < cols else 0)
        for i, cell in enumerate(self._cells):
            self._grid.addWidget(cell, i // cols, i % cols)
        self.updateGeometry()


class CaptionTools:
    """Caption look / motion / layout — shown in the Inspector when a Caption track is selected."""

    def _caption_section(self, layout: QVBoxLayout, title: str, divider: bool = True) -> QVBoxLayout:
        box = QWidget()
        box_lay = QVBoxLayout(box)
        box_lay.setContentsMargins(0, 0, 0, 0)
        box_lay.setSpacing(8)
        if divider:
            line = QFrame()
            line.setObjectName("caption_sec_divider")
            line.setFixedHeight(1)
            box_lay.addWidget(line)
        head = QLabel(title.upper())
        head.setObjectName("dub_config_header")
        box_lay.addWidget(head)
        layout.addWidget(box)
        return box_lay

    def _build_caption_body(self) -> QWidget:
        """Scrollable Captions controls for the right-dock Inspector (no shelf header)."""
        scroll = QScrollArea()
        scroll.setObjectName("dub_caption_inspector")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        page = QWidget()
        page.setObjectName("dub_caption_page")
        page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 8, 12, 16)
        lay.setSpacing(12)

        # ── Look (responsive tile grid) ────────────────────────────
        look = self._caption_section(lay, "Look", divider=False)
        saved = self.store.get_setting("dub", "caption_style", "Live caption")
        pick = next((i for i, s in enumerate(CAPTION_STYLES) if s["name"] == saved), 0)
        self.caption_look_grid = CaptionLookGrid(CAPTION_STYLES)
        self.caption_look_grid.set_current(pick)
        self.caption_look_grid.style_picked.connect(self._on_caption_style)
        look.addWidget(self.caption_look_grid)

        # ── Motion (preview cards + highlight colour) ──────────────
        motion = self._caption_section(lay, "Motion", divider=True)
        saved_anim = self.store.get_setting("dub", "caption_anim", "highlight")
        anim_pick = next((i for i, (key, _) in enumerate(CAPTION_ANIMS) if key == saved_anim), 0)
        self.caption_motion_grid = CaptionMotionGrid(list(CAPTION_ANIMS))
        self.caption_motion_grid.set_current(anim_pick)
        self.caption_motion_grid.anim_picked.connect(self._on_caption_anim)
        motion.addWidget(self.caption_motion_grid)
        self.caption_anim_group = self.caption_motion_grid._group

        saved_hl = self.store.get_setting("dub", "caption_highlight", "#22c55e").lower()
        self.caption_color_pick = CaptionColorPick(_HIGHLIGHT_SWATCHES)
        self.caption_color_pick.set_current(saved_hl)
        self.caption_color_pick.color_picked.connect(self._on_caption_highlight)
        self.caption_color_pick.color_changed.connect(self._on_caption_highlight)
        self.caption_hl_group = self.caption_color_pick._group
        motion.addWidget(self.caption_color_pick)
        self.caption_motion_grid.set_highlight_color(self.caption_color_pick.current_color())
        self._sync_caption_color_visibility()

        # ── Layout (Placement Presets + Fit Width + Controls) ──────
        place = self._caption_section(lay, "Layout", divider=True)

        pos_box = QWidget()
        pos_box_l = QVBoxLayout(pos_box)
        pos_box_l.setContentsMargins(0, 0, 0, 0)
        pos_box_l.setSpacing(4)
        pos_lbl = QLabel("Placement")
        pos_lbl.setObjectName("asr_field_label")
        pos_box_l.addWidget(pos_lbl)

        pos_row = QHBoxLayout()
        pos_row.setContentsMargins(0, 0, 0, 0)
        pos_row.setSpacing(6)
        self.pos_group = QButtonGroup(page)
        self.pos_group.setExclusive(True)

        for idx, (label, icon_name, y_val) in enumerate([
            ("Top", "pos-top", 12),
            ("Center", "pos-vcenter", 50),
            ("Bottom", "pos-bottom", 86),
        ]):
            btn = QToolButton()
            btn.setObjectName("caption_pos_preset")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setIcon(icon(icon_name, color="#cbd5e1", size=13))
            btn.setIconSize(QSize(13, 13))
            btn.setText(label)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _, y=y_val: self.spin_caption_y.setValue(y))
            self.pos_group.addButton(btn, idx)
            pos_row.addWidget(btn)
        pos_box_l.addLayout(pos_row)
        place.addWidget(pos_box)

        self.chk_caption_fit = self._caption_check(
            place,
            "Auto centre · fit width",
            "Centre captions. Font stays at the chosen size and shrinks if a line is wider than the frame",
            self.store.get_setting("dub", "caption_fit", "1") == "1",
            self._on_caption_fit,
        )

        try:
            width = int(self.store.get_setting("dub", "caption_width", "80"))
        except ValueError:
            width = 80
        width = max(CAPTION_WIDTH_RANGE[0], min(CAPTION_WIDTH_RANGE[1], width))
        self.lbl_caption_width, self.spin_caption_width = self._caption_spin(
            "Width", CAPTION_WIDTH_RANGE[0], CAPTION_WIDTH_RANGE[1], width, "%",
            "Caption frame width — text wraps inside it",
        )
        self.spin_caption_width.valueChanged.connect(self._on_caption_width)

        try:
            y = int(float(self.store.get_setting("dub", "caption_y", "86")))
        except ValueError:
            y = 86
        y = max(10, min(95, y))
        self.lbl_caption_y, self.spin_caption_y = self._caption_spin(
            "Pos Y", 10, 95, y, "%", "Vertical position on the picture",
        )
        self.spin_caption_y.valueChanged.connect(self._on_caption_y)

        try:
            size = int(self.store.get_setting("dub", "caption_size", "10"))
        except ValueError:
            size = 10
        size = max(6, min(48, size))
        self.lbl_caption_size, self.spin_caption_size = self._caption_spin(
            "Font Size", 6, 48, size, "",
            "Manual font size when auto-fit is off",
        )
        self.spin_caption_size.valueChanged.connect(self._on_caption_size)

        field_row = QHBoxLayout()
        field_row.setContentsMargins(0, 0, 0, 0)
        field_row.setSpacing(10)

        w_cell = QHBoxLayout()
        w_cell.setSpacing(6)
        w_cell.addWidget(self.lbl_caption_width)
        w_cell.addWidget(self.spin_caption_width, 1)

        y_cell = QHBoxLayout()
        y_cell.setSpacing(6)
        y_cell.addWidget(self.lbl_caption_y)
        y_cell.addWidget(self.spin_caption_y, 1)

        field_row.addLayout(w_cell, 1)
        field_row.addLayout(y_cell, 1)
        place.addLayout(field_row)

        self.size_row = QWidget()
        size_l = QHBoxLayout(self.size_row)
        size_l.setContentsMargins(0, 0, 0, 0)
        size_l.setSpacing(10)
        size_cell = QHBoxLayout()
        size_cell.setSpacing(6)
        size_cell.addWidget(self.lbl_caption_size)
        size_cell.addWidget(self.spin_caption_size, 1)
        size_l.addLayout(size_cell, 1)
        size_l.addStretch(1)
        place.addWidget(self.size_row)

        self._sync_pos_preset(y)

        # ── Actions ────────────────────────────────────────────────
        actions = self._caption_section(lay, "Actions", divider=True)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)

        self.btn_apply_captions = QPushButton("Apply to All")
        self.btn_apply_captions.setObjectName("caption_apply_btn")
        self.btn_apply_captions.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply_captions.setIcon(icon("sparkles", color="#ffffff", size=13))
        self.btn_apply_captions.setIconSize(QSize(13, 13))
        self.btn_apply_captions.setToolTip("Update look and motion on every caption segment")
        self.btn_apply_captions.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_apply_captions.clicked.connect(self._apply_caption_style)

        self.btn_add_captions = QPushButton("Sync Segments")
        self.btn_add_captions.setObjectName("caption_sync_btn")
        self.btn_add_captions.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_captions.setIcon(icon("refresh", color="#cbd5e1", size=13))
        self.btn_add_captions.setIconSize(QSize(13, 13))
        self.btn_add_captions.setToolTip("Rebuild one caption clip per voice line · trim and split each independently")
        self.btn_add_captions.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_add_captions.clicked.connect(self._add_live_captions)

        btn_row.addWidget(self.btn_apply_captions, 1)
        btn_row.addWidget(self.btn_add_captions, 1)
        actions.addLayout(btn_row)

        lay.addStretch(1)
        scroll.setWidget(page)
        self._sync_caption_fit_controls()
        return scroll

    @staticmethod
    def _caption_check(layout: QVBoxLayout, title: str, tip: str, checked: bool, on_toggle) -> QCheckBox:
        chk = QCheckBox(title)
        chk.setObjectName("dub_switch")
        chk.setCursor(Qt.CursorShape.PointingHandCursor)
        chk.setChecked(checked)
        chk.setToolTip(tip)
        chk.toggled.connect(on_toggle)
        layout.addWidget(chk)
        return chk

    @staticmethod
    def _caption_spin(label: str, low: int, high: int, value: int, suffix: str, tip: str):
        lbl = QLabel(label)
        lbl.setObjectName("asr_field_label")
        spin = ScrubSpinBox()
        spin.setRange(low, high)
        spin.setSuffix(suffix)
        spin.setValue(value)
        spin.setToolTip(tip)
        spin.setMinimumWidth(80)
        spin.setMaximumWidth(16777215)
        return lbl, spin

    def caption_style(self) -> dict:
        """Default caption overlay from the Captions tab (style + motion + placement)."""
        index = self.caption_look_grid.current() if hasattr(self, "caption_look_grid") else -1
        if index < 0 or index >= len(CAPTION_STYLES):
            index = next((i for i, s in enumerate(CAPTION_STYLES) if s.get("live")), 0)
        style = dict(CAPTION_STYLES[max(0, index)])
        style["kind"] = "caption"
        style["live"] = False
        style["auto_caption"] = True
        anim = CAPTION_ANIMS[max(0, self.caption_anim_group.checkedId())][0] if hasattr(self, "caption_anim_group") else "none"
        style["anim_in"] = anim
        style["anim_out"] = "none"
        style["anim_loop"] = "none"
        if anim in {"words", "highlight", "typewriter", "fade"}:
            style["anim_in_ms"] = 800 if anim == "fade" else 1200
        hl_color = (
            self.caption_color_pick.current_color()
            if hasattr(self, "caption_color_pick")
            else _HIGHLIGHT_SWATCHES[0]
        )
        style["highlight_color"] = hl_color
        fit = bool(getattr(self, "chk_caption_fit", None) and self.chk_caption_fit.isChecked())
        style["caption_fit"] = fit
        if hasattr(self, "spin_caption_width"):
            style["caption_width"] = self.spin_caption_width.value()
        if fit:
            style["x"] = 0.5
            style["align"] = "center"
        style["font_size"] = self.spin_caption_size.value() if hasattr(self, "spin_caption_size") else 10
        if hasattr(self, "spin_caption_y"):
            style["y"] = self.spin_caption_y.value() / 100.0
        return clean_text_style(style) | {
            "kind": "caption",
            "live": False,
            "auto_caption": True,
            "name": style.get("name") or "Caption",
            "text": style.get("text") or "Caption",
            "x": style.get("x", 0.5),
            "y": style.get("y", 0.86),
            "caption_fit": fit,
            "caption_width": int(style.get("caption_width") or 80),
            "highlight_color": hl_color,
            "anim_in": anim,
            "anim_out": "none",
            "anim_loop": "none",
        }

    def _sync_caption_fit_controls(self):
        fit = bool(getattr(self, "chk_caption_fit", None) and self.chk_caption_fit.isChecked())
        if hasattr(self, "spin_caption_width"):
            self.spin_caption_width.setEnabled(fit)
            self.lbl_caption_width.setEnabled(fit)
        if hasattr(self, "size_row"):
            self.size_row.setVisible(not fit)

    def _sync_pos_preset(self, y: int):
        if hasattr(self, "pos_group"):
            self.pos_group.setExclusive(False)
            btn_top = self.pos_group.button(0)
            btn_center = self.pos_group.button(1)
            btn_bottom = self.pos_group.button(2)
            if btn_top:
                btn_top.setChecked(10 <= y <= 18)
            if btn_center:
                btn_center.setChecked(45 <= y <= 55)
            if btn_bottom:
                btn_bottom.setChecked(82 <= y <= 90)
            self.pos_group.setExclusive(True)

    def _sync_caption_color_visibility(self):
        """Highlight colour matters for karaoke / words; keep it visible but dim for others."""
        if not hasattr(self, "caption_color_pick"):
            return
        anim_id = self.caption_motion_grid.current() if hasattr(self, "caption_motion_grid") else -1
        key = CAPTION_ANIMS[anim_id][0] if 0 <= anim_id < len(CAPTION_ANIMS) else "none"
        on = key in {"highlight", "words"}
        self.caption_color_pick.setEnabled(on)
        self.caption_color_pick.setVisible(True)

    def _on_caption_style(self, index: int):
        if 0 <= index < len(CAPTION_STYLES):
            self.store.set_setting("dub", "caption_style", CAPTION_STYLES[index]["name"])

    def _on_caption_anim(self, index: int):
        if 0 <= index < len(CAPTION_ANIMS):
            self.store.set_setting("dub", "caption_anim", CAPTION_ANIMS[index][0])
        self._sync_caption_color_visibility()

    def _on_caption_highlight(self, val: int | str):
        if isinstance(val, int):
            color = _HIGHLIGHT_SWATCHES[val] if 0 <= val < len(_HIGHLIGHT_SWATCHES) else _HIGHLIGHT_SWATCHES[0]
        else:
            color = str(val)
        self.store.set_setting("dub", "caption_highlight", color)
        if hasattr(self, "caption_motion_grid"):
            self.caption_motion_grid.set_highlight_color(color)

    def _on_caption_fit(self, checked: bool):
        self.store.set_setting("dub", "caption_fit", "1" if checked else "0")
        self._sync_caption_fit_controls()

    def _on_caption_width(self, value: int):
        self.store.set_setting("dub", "caption_width", str(value))

    def _on_caption_y(self, value: int):
        self.store.set_setting("dub", "caption_y", str(value))
        self._sync_pos_preset(value)

    def _on_caption_size(self, value: int):
        self.store.set_setting("dub", "caption_size", str(value))

    def _apply_caption_style(self):
        """Push Captions-tab look/motion onto every caption segment (keeps text + timing)."""
        canvas = self.timeline.canvas
        style = self.caption_style()
        updated = 0
        for clip in canvas.clips:
            if clip.kind != "caption":
                continue
            ov = dict(clip.extra.get("overlay") or {})
            keep_text = str(ov.get("text") or clip.label or style.get("text") or "Caption").strip()
            keep_voice = ov.get("voice_id")
            ov.update(style)
            ov["text"] = keep_text
            ov["live"] = False
            ov["auto_caption"] = True
            ov["kind"] = "caption"
            if keep_voice:
                ov["voice_id"] = keep_voice
            clip.extra["overlay"] = ov
            clip.label = keep_text if len(keep_text) <= 48 else f"{keep_text[:47]}…"
            updated += 1
        if updated:
            self.timeline.rail.rebuild(canvas.tracks)
            self._sync_preview_overlays(force=True)
            self.log.info(f"Captions · applied look to {updated} segment(s)")
            return
        self._add_live_captions()

    def _add_live_captions(self):
        """Rebuild one caption clip per current voice line (sync from dub timeline)."""
        canvas = self.timeline.canvas
        had = any(is_managed_caption(c) for c in canvas.clips)
        self._ensure_auto_captions(force=True)
        if not any(is_managed_caption(c) for c in canvas.clips):
            if had:
                canvas.clips = [c for c in canvas.clips if not is_managed_caption(c)]
                self.timeline.rail.rebuild(canvas.tracks)
                self._sync_preview_overlays(force=True)
            self.log.warn("Captions · dub some lines first, then sync segments")

