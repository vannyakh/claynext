"""CapCut-style text and shape properties: Basic (content, font, style, transform, stroke, box, shadow) and Animation."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QColorDialog, QFontComboBox, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from claynext.constants.theme_constants import COLOR_BORDER, COLOR_PRIMARY, COLOR_TEXT_MUTED
from claynext.gui.icons import icon
from claynext.models.text_style import (
    ANIM_IN, ANIM_LOOP, ANIM_OUT, CASES, FONT_RANGE, IN_OUT_MS_RANGE, LETTER_RANGE, LOOP_MS_RANGE,
    SCALE_RANGE, SHADOW_RANGE, STROKE_RANGE, STYLE_PRESETS, TEXT_COLORS, clean_text_style, preset_values,
)
from claynext.gui.components.collapsible_section import CollapsibleSection
from claynext.gui.components.scrub_spin import ScrubSpinBox
from claynext.gui.components.segment_tabs import SegmentTabs
from claynext.gui.components.shape_render import BLUR_SHAPES, SHAPES, shape_icon, shape_size
from claynext.gui.components.text_render import anim_icon, preset_icon

_ANIM_SLOTS = (("anim_in", "In", ANIM_IN), ("anim_out", "Out", ANIM_OUT), ("anim_loop", "Loop", ANIM_LOOP))
_ALIGN_TO_CANVAS = (
    ("left", "pos-left", "Align left"), ("hcenter", "pos-hcenter", "Centre horizontally"),
    ("right", "pos-right", "Align right"), ("top", "pos-top", "Align top"),
    ("vcenter", "pos-vcenter", "Centre vertically"), ("bottom", "pos-bottom", "Align bottom"),
)


def _swatch_icon(color: str, side: int = 16) -> QIcon:
    pix = QPixmap(side * 2, side * 2)
    pix.setDevicePixelRatio(2.0)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor(COLOR_BORDER))
    p.setBrush(QColor(color))
    p.drawRoundedRect(0, 0, side - 1, side - 1, 4, 4)
    p.end()
    return QIcon(pix)


class TextInspector(QWidget):
    changed = Signal()
    animation_picked = Signal(str)
    align_requested = Signal(str)

    def __init__(self, parent=None, shape: bool = False):
        super().__init__(parent)
        self.setObjectName("overlay_inspector")
        self._shape_mode = shape
        self._shape = "rect"
        self._item = None
        self._style = clean_text_style(None)
        self._block = False
        self._aspect_ratio = 1.0
        self._anim_slot = "anim_in"
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self.tab_bar = SegmentTabs(["Basic", "Animation"])
        self.tab_group = self.tab_bar.group
        root.addWidget(self.tab_bar)
        self.pages = QStackedWidget()
        self.tab_bar.changed.connect(self.pages.setCurrentIndex)
        root.addWidget(self.pages)
        self.pages.addWidget(self._build_basic())
        self.pages.addWidget(self._build_animation())
        self.setEnabled(False)

    # ── building blocks ────────────────────────────────────────────
    @staticmethod
    def _label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("asr_field_label")
        return lbl

    def _section(
        self,
        parent: QVBoxLayout,
        title: str,
        *,
        open: bool = True,
        feature: str = "",
        divider: bool = False,
    ) -> tuple[QVBoxLayout, QCheckBox | None]:
        """Click header to expand/collapse; optional feature checkbox is independent."""
        sec = CollapsibleSection(title, open=open, divider=divider, feature=bool(feature))
        chk = sec.feature_check
        if feature and chk is not None:
            chk.toggled.connect(lambda on, k=feature: self._on_feature_toggle(k, on))
        parent.addWidget(sec)
        return sec.body_layout, chk

    def _on_feature_toggle(self, key: str, on: bool):
        if not self._block:
            self._set(key, bool(on))

    def _spin(self, low: int, high: int, suffix: str = "") -> ScrubSpinBox:
        spin = ScrubSpinBox()
        spin.setRange(low, high)
        spin.setSuffix(suffix)
        spin.setToolTip("Drag up/down to scrub · click to type · ▲▼ to step")
        return spin

    def _spin_row(self, layout: QVBoxLayout, title: str, low: int, high: int, key: str, suffix: str = "") -> ScrubSpinBox:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self._label(title), 1)
        spin = self._spin(low, high, suffix)
        spin.valueChanged.connect(lambda v, k=key: self._set(k, int(v)))
        row.addWidget(spin, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(row)
        return spin

    def _toggle(self, text: str = "", tip: str = "", icon_name: str = "") -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("dub_text_toggle")
        btn.setCheckable(True)
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(30, 26)
        if icon_name:
            btn.setIcon(icon(icon_name, color="#cbd5e1", size=14))
            btn.setIconSize(QSize(14, 14))
        else:
            btn.setText(text)
        return btn

    def _color_button(self, key: str, title: str) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("dub_canvas_swatch")
        btn.setToolTip(title)
        btn.setFixedSize(QSize(30, 26))
        btn.setIconSize(QSize(16, 16))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _=False, k=key, t=title: self._pick_color(k, t))
        return btn

    @staticmethod
    def _group(layout: QVBoxLayout, visible: bool) -> QVBoxLayout:
        box = QWidget()
        inner = QVBoxLayout(box)
        inner.setContentsMargins(2, 0, 2, 0)
        inner.setSpacing(8)
        box.setVisible(visible)
        layout.addWidget(box)
        return inner

    def _build_shape(self, lay: QVBoxLayout):
        lay.addWidget(self._label("Element"))
        grid = QGridLayout()
        grid.setSpacing(4)
        self.shape_group = QButtonGroup(self)
        for i, (key, label) in enumerate(SHAPES):
            btn = QToolButton()
            btn.setObjectName("dub_canvas_swatch")
            btn.setCheckable(True)
            btn.setFixedSize(QSize(36, 36))
            btn.setIcon(shape_icon(key, "#cbd5e1", 24))
            btn.setIconSize(QSize(22, 22))
            btn.setToolTip(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.shape_group.addButton(btn, i)
            grid.addWidget(btn, i // 6, i % 6)
        self.shape_group.idClicked.connect(self._on_shape)
        lay.addLayout(grid)
        size = QHBoxLayout()
        size.setSpacing(6)
        size.addWidget(self._label("Size"))
        size.addStretch(1)
        self.spin_w = self._spin(1, 200, "%")
        self.spin_w.setPrefix("W ")
        self.spin_w.setToolTip("Width as a share of the picture height")
        self.spin_w.valueChanged.connect(self._on_spin_w_changed)

        self.btn_lock = self._toggle("", "Lock aspect ratio", "lock")
        self.btn_lock.setChecked(True)
        self.btn_lock.setFixedSize(26, 26)
        self.btn_lock.toggled.connect(self._on_lock_toggled)
        self._sync_lock_icon()

        self.spin_h = self._spin(1, 200, "%")
        self.spin_h.setPrefix("H ")
        self.spin_h.setToolTip("Height as a share of the picture height")
        self.spin_h.valueChanged.connect(self._on_spin_h_changed)

        size.addWidget(self.spin_w)
        size.addWidget(self.btn_lock)
        size.addWidget(self.spin_h)
        lay.addLayout(size)

    # ── Basic ──────────────────────────────────────────────────────
    def _build_basic(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        shape = self._shape_mode

        content, _ = self._section(root, "Element" if shape else "Content", open=True, divider=False)
        if shape:
            self._build_shape(content)
        else:
            self.chk_live = QCheckBox("Live caption from script")
            self.chk_live.setObjectName("dub_switch")
            self.chk_live.toggled.connect(self._emit)
            content.addWidget(self.chk_live)
            content.addWidget(self._label("Font"))
            self.font_box = QFontComboBox()
            self.font_box.setObjectName("dub_setting_field")
            self.font_box.currentFontChanged.connect(lambda f: self._set("font", f.family()))
            content.addWidget(self.font_box)
            self.spin_size = self._spin_row(content, "Font size", *FONT_RANGE, "font_size")
            pattern = QHBoxLayout()
            pattern.setSpacing(6)
            pattern.addWidget(self._label("Pattern"))
            pattern.addStretch(1)
            self.btn_bold = self._toggle("B", "Bold")
            self.btn_italic = self._toggle("I", "Italic")
            self.btn_underline = self._toggle("U", "Underline")
            for btn, key in ((self.btn_bold, "bold"), (self.btn_italic, "italic"), (self.btn_underline, "underline")):
                font = btn.font()
                font.setBold(key == "bold")
                font.setItalic(key == "italic")
                font.setUnderline(key == "underline")
                btn.setFont(font)
                btn.toggled.connect(lambda on, k=key: self._set(k, bool(on)))
                pattern.addWidget(btn)
            content.addLayout(pattern)
            case_row = QHBoxLayout()
            case_row.setSpacing(6)
            case_row.addWidget(self._label("Case"))
            case_row.addStretch(1)
            self.case_group = QButtonGroup(self)
            for i, (_key, glyph, tip) in enumerate(CASES):
                btn = self._toggle(glyph, tip)
                self.case_group.addButton(btn, i)
                case_row.addWidget(btn)
            self.case_group.idClicked.connect(lambda i: self._set("case", CASES[i][0]))
            content.addLayout(case_row)

        # Shape mode still needs stubs referenced by bind/apply
        if shape:
            self.chk_live = QCheckBox()
            self.chk_live.hide()
            self.font_box = QFontComboBox()
            self.font_box.hide()
            self.spin_size = self._spin(*FONT_RANGE)
            self.btn_bold = self._toggle("B")
            self.btn_italic = self._toggle("I")
            self.btn_underline = self._toggle("U")
            self.case_group = QButtonGroup(self)
            for i, (_key, glyph, tip) in enumerate(CASES):
                btn = self._toggle(glyph, tip)
                btn.hide()
                self.case_group.addButton(btn, i)
        else:
            self.spin_w = self._spin(1, 200, "%")
            self.spin_h = self._spin(1, 200, "%")
            self.btn_lock = self._toggle()
            self.btn_lock.hide()
            self.shape_group = QButtonGroup(self)

        style, _ = self._section(root, "Style", open=True)
        style.addWidget(self._label("Fill" if shape else "Color"))
        colors = QGridLayout()
        colors.setSpacing(6)
        self.color_group = QButtonGroup(self)
        for i, color in enumerate(TEXT_COLORS):
            btn = QToolButton()
            btn.setObjectName("dub_canvas_swatch")
            btn.setCheckable(True)
            btn.setFixedSize(QSize(26, 22))
            btn.setIcon(_swatch_icon(color, 14))
            btn.setIconSize(QSize(14, 14))
            btn.setToolTip(color)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.color_group.addButton(btn, i)
            colors.addWidget(btn, i // 7, i % 7)
        self.btn_color_more = self._color_button("color", "Fill colour" if shape else "Text colour")
        self.btn_color_more.setFixedSize(QSize(26, 22))
        colors.addWidget(self.btn_color_more, len(TEXT_COLORS) // 7, len(TEXT_COLORS) % 7)
        self.color_group.idClicked.connect(lambda i: self._set("color", TEXT_COLORS[i]))
        style.addLayout(colors)

        if not shape:
            spacing = QHBoxLayout()
            spacing.setSpacing(8)
            spacing.addWidget(self._label("Character"))
            self.spin_letter = self._spin(*LETTER_RANGE)
            self.spin_letter.valueChanged.connect(lambda v: self._set("letter", int(v)))
            spacing.addWidget(self.spin_letter)
            spacing.addStretch(1)
            self.align_group = QButtonGroup(self)
            for i, key in enumerate(("left", "center", "right")):
                btn = self._toggle(tip=f"Align {key}", icon_name=f"align-{key}")
                self.align_group.addButton(btn, i)
                spacing.addWidget(btn)
            self.align_group.idClicked.connect(lambda i: self._set("align", ("left", "center", "right")[i]))
            style.addLayout(spacing)
            style.addWidget(self._label("Preset style"))
            grid = QGridLayout()
            grid.setSpacing(6)
            self.preset_group = QButtonGroup(self)
            for i, (key, values) in enumerate(STYLE_PRESETS):
                btn = QToolButton()
                btn.setObjectName("dub_canvas_swatch")
                btn.setCheckable(True)
                btn.setFixedSize(QSize(36, 36))
                btn.setIcon(preset_icon(key, values, 32))
                btn.setIconSize(QSize(32, 32))
                btn.setToolTip("No style" if key == "none" else key.replace("_", " ").title())
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                self.preset_group.addButton(btn, i)
                grid.addWidget(btn, i // 6, i % 6)
            self.preset_group.idClicked.connect(self._on_preset)
            style.addLayout(grid)
        else:
            self.spin_letter = self._spin(*LETTER_RANGE)
            self.align_group = QButtonGroup(self)
            self.preset_group = QButtonGroup(self)

        xform, _ = self._section(root, "Transform", open=True)
        self.spin_scale = self._spin_row(xform, "Scale", *SCALE_RANGE, "scale", "%")
        xform.addWidget(self._label("Position"))
        pos = QHBoxLayout()
        pos.setContentsMargins(0, 0, 0, 0)
        pos.setSpacing(8)
        self.spin_x = self._spin(-100, 100)
        self.spin_x.setPrefix("X ")
        self.spin_x.setMinimumWidth(88)
        self.spin_x.setMaximumWidth(16777215)
        self.spin_x.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.spin_y = self._spin(-100, 100)
        self.spin_y.setPrefix("Y ")
        self.spin_y.setMinimumWidth(88)
        self.spin_y.setMaximumWidth(16777215)
        self.spin_y.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.spin_x.valueChanged.connect(self._emit)
        self.spin_y.valueChanged.connect(self._emit)
        pos.addWidget(self.spin_x, 1)
        pos.addWidget(self.spin_y, 1)
        xform.addLayout(pos)
        rot = QHBoxLayout()
        rot.setContentsMargins(0, 0, 0, 0)
        rot.setSpacing(8)
        rot.addWidget(self._label("Rotation"), 1)
        self.spin_rot = self._spin(-180, 180, "°")
        self.spin_rot.setMinimumWidth(88)
        self.spin_rot.valueChanged.connect(self._emit)
        rot.addWidget(self.spin_rot, 0, Qt.AlignmentFlag.AlignRight)
        xform.addLayout(rot)
        aligns = QHBoxLayout()
        aligns.setSpacing(6)
        for key, icon_name, tip in _ALIGN_TO_CANVAS:
            btn = self._toggle(tip=tip, icon_name=icon_name)
            btn.setCheckable(False)
            btn.clicked.connect(lambda _=False, k=key: self.align_requested.emit(k))
            aligns.addWidget(btn)
        aligns.addStretch(1)
        xform.addLayout(aligns)
        self.spin_op = self._spin_row(xform, "Opacity", 0, 100, "opacity", "%")

        stroke, self.chk_stroke = self._section(root, "Stroke", open=True, feature="stroke_on")
        stroke_row = QHBoxLayout()
        stroke_row.setSpacing(10)
        self.btn_stroke_color = self._color_button("stroke_color", "Stroke colour")
        stroke_row.addWidget(self.btn_stroke_color)
        stroke_row.addStretch(1)
        self.spin_stroke = self._spin(*STROKE_RANGE)
        self.spin_stroke.setToolTip("Stroke width")
        self.spin_stroke.valueChanged.connect(lambda v: self._set("stroke_width", int(v), turn_on="stroke_on"))
        stroke_row.addWidget(self.spin_stroke)
        stroke.addLayout(stroke_row)

        if not shape:
            bg, self.chk_bg = self._section(root, "Background", open=True, feature="bg_on")
            bg_row = QHBoxLayout()
            bg_row.setSpacing(10)
            self.btn_bg_color = self._color_button("bg_color", "Background colour")
            bg_row.addWidget(self.btn_bg_color)
            bg_row.addStretch(1)
            self.spin_bg = self._spin(0, 100, "%")
            self.spin_bg.setToolTip("Background opacity")
            self.spin_bg.valueChanged.connect(lambda v: self._set("bg_opacity", int(v), turn_on="bg_on"))
            bg_row.addWidget(self.spin_bg)
            bg.addLayout(bg_row)
        else:
            self.chk_bg = QCheckBox()
            self.chk_bg.hide()
            self.btn_bg_color = self._color_button("bg_color", "Background colour")
            self.spin_bg = self._spin(0, 100, "%")

        shadow, self.chk_shadow = self._section(root, "Shadow", open=True, feature="shadow_on")
        shadow_row = QHBoxLayout()
        shadow_row.setSpacing(10)
        self.btn_shadow_color = self._color_button("shadow_color", "Shadow colour")
        shadow_row.addWidget(self.btn_shadow_color)
        shadow_row.addStretch(1)
        self.spin_shadow = self._spin(*SHADOW_RANGE)
        self.spin_shadow.setToolTip("Shadow distance")
        self.spin_shadow.valueChanged.connect(lambda v: self._set("shadow_dist", int(v), turn_on="shadow_on"))
        shadow_row.addWidget(self.spin_shadow)
        shadow.addLayout(shadow_row)

        if shape:
            blur_sec, self.chk_blur = self._section(root, "Blur & Frosted Glass", open=True, feature="blur_on")
            self.spin_blur = self._spin_row(blur_sec, "Blur radius", 1, 100, "blur_radius", "px")
        else:
            self.chk_blur = QCheckBox()
            self.chk_blur.hide()
            self.spin_blur = self._spin(1, 100, "px")

        return page

    # ── Animation ──────────────────────────────────────────────────
    def _build_animation(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        slots = QHBoxLayout()
        slots.setSpacing(4)
        self.slot_group = QButtonGroup(self)
        for i, (_key, label, _items) in enumerate(_ANIM_SLOTS):
            btn = QPushButton(label)
            btn.setObjectName("dub_option_btn")
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.slot_group.addButton(btn, i)
            slots.addWidget(btn, 1)
        self.slot_group.idClicked.connect(self._on_slot)
        lay.addLayout(slots)

        self.anim_stack = QStackedWidget()
        self.anim_groups: dict[str, QButtonGroup] = {}
        for key, _label, items in _ANIM_SLOTS:
            grid_page = QWidget()
            grid = QGridLayout(grid_page)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(6)
            group = QButtonGroup(self)
            for i, (anim, name) in enumerate(items):
                btn = QToolButton()
                btn.setObjectName("dub_text_tile")
                btn.setCheckable(True)
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                btn.setIcon(anim_icon(key, anim))
                btn.setIconSize(QSize(56, 44))
                btn.setText(name)
                btn.setFixedSize(QSize(72, 70))
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                group.addButton(btn, i)
                grid.addWidget(btn, i // 4, i % 4)
            group.idClicked.connect(lambda i, k=key, opts=items: self._on_anim(k, opts[i][0]))
            self.anim_groups[key] = group
            self.anim_stack.addWidget(grid_page)
        lay.addWidget(self.anim_stack)

        anim_ms = QHBoxLayout()
        anim_ms.setContentsMargins(0, 0, 0, 0)
        anim_ms.setSpacing(8)
        self.lbl_anim_ms = self._label("Duration · 0.5s")
        anim_ms.addWidget(self.lbl_anim_ms, 1)
        self.spin_anim_ms = self._spin(*IN_OUT_MS_RANGE, " ms")
        self.spin_anim_ms.setSingleStep(100)
        self.spin_anim_ms.setMinimumWidth(96)
        self.spin_anim_ms.setMaximumWidth(120)
        self.spin_anim_ms.valueChanged.connect(self._on_anim_ms)
        anim_ms.addWidget(self.spin_anim_ms, 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(anim_ms)
        self.lbl_anim_hint = QLabel("")
        self.lbl_anim_hint.setObjectName("dub_switch_hint")
        self.lbl_anim_hint.setStyleSheet("padding-left: 0;")
        self.lbl_anim_hint.setWordWrap(True)
        lay.addWidget(self.lbl_anim_hint)
        lay.addStretch(1)
        return page

    # ── state ──────────────────────────────────────────────────────
    def current(self):
        return self._item

    def bind(self, item):
        self._item = item
        self.setEnabled(item is not None)
        if item is None:
            return
        self._style = item.style()
        self._block = True
        self.chk_live.setChecked(bool(item.live))
        self.chk_live.setVisible(item.kind == "caption")
        self.spin_x.setValue(round((float(item.x) - 0.5) * 200))
        self.spin_y.setValue(round((float(item.y) - 0.5) * 200))
        self.spin_rot.setValue(round(float(item.rotation)))
        self._shape = str(getattr(item, "shape", "rect") or "rect")
        self.spin_w.setValue(round(float(item.w) * 100))
        self.spin_h.setValue(round(float(item.h) * 100))
        if hasattr(self, "btn_lock"):
            self.btn_lock.setChecked(bool(getattr(item, "lock_aspect", True)))
            self._sync_lock_icon()
        if float(item.h) > 0:
            self._aspect_ratio = float(item.w) / float(item.h)
        else:
            self._aspect_ratio = 1.0
        if hasattr(item, "blur_on"):
            self._style["blur_on"] = bool(item.blur_on)
        if hasattr(item, "blur_radius"):
            self._style["blur_radius"] = int(item.blur_radius)
        self._sync_widgets()
        self._block = False

    def _sync_widgets(self):
        s = self._style
        blocked = self._block
        self._block = True
        self.font_box.setCurrentFont(QFont(s["font"]))
        self.spin_size.setValue(s["font_size"])
        self.btn_bold.setChecked(s["bold"])
        self.btn_italic.setChecked(s["italic"])
        self.btn_underline.setChecked(s["underline"])
        self._check(self.case_group, [key for key, _g, _t in CASES].index(s["case"]))
        self._check(self.color_group, TEXT_COLORS.index(s["color"]) if s["color"] in TEXT_COLORS else -1)
        self.btn_color_more.setIcon(_swatch_icon(s["color"]) if s["color"] not in TEXT_COLORS else QIcon())
        self.btn_color_more.setText("" if s["color"] not in TEXT_COLORS else "+")
        self.spin_letter.setValue(s["letter"])
        self._check(self.align_group, ("left", "center", "right").index(s["align"]))
        keys = [key for key, _v in STYLE_PRESETS]
        self._check(self.preset_group, keys.index(s["preset"]) if s["preset"] in keys else -1)
        self.spin_scale.setValue(s["scale"])
        self.spin_op.setValue(s["opacity"])
        self.chk_stroke.setChecked(s["stroke_on"])
        self.btn_stroke_color.setIcon(_swatch_icon(s["stroke_color"]))
        self.spin_stroke.setValue(s["stroke_width"])
        self.chk_bg.setChecked(s["bg_on"])
        self.btn_bg_color.setIcon(_swatch_icon(s["bg_color"]))
        self.spin_bg.setValue(s["bg_opacity"])
        self.chk_shadow.setChecked(s["shadow_on"])
        self.btn_shadow_color.setIcon(_swatch_icon(s["shadow_color"]))
        self.spin_shadow.setValue(s["shadow_dist"])
        if hasattr(self, "chk_blur"):
            self.chk_blur.setChecked(bool(s.get("blur_on", False)))
        if hasattr(self, "spin_blur"):
            self.spin_blur.setValue(int(s.get("blur_radius", 20)))
        keys = [key for key, _l in SHAPES]
        self._check(self.shape_group, keys.index(self._shape) if self._shape in keys else -1)
        for key, _label, items in _ANIM_SLOTS:
            names = [anim for anim, _n in items]
            self._check(self.anim_groups[key], names.index(s[key]) if s[key] in names else 0)
        self._sync_anim_slot()
        self._block = blocked

    @staticmethod
    def _check(group: QButtonGroup, index: int):
        group.setExclusive(False)
        for i, btn in enumerate(group.buttons()):
            btn.setChecked(i == index)
        group.setExclusive(True)

    def _sync_anim_slot(self):
        slot = self._anim_slot
        loop = slot == "anim_loop"
        self.spin_anim_ms.blockSignals(True)
        self.spin_anim_ms.setRange(*(LOOP_MS_RANGE if loop else IN_OUT_MS_RANGE))
        self.spin_anim_ms.setValue(self._style[f"{slot}_ms"])
        self.spin_anim_ms.blockSignals(False)
        active = self._style[slot] != "none"
        self.spin_anim_ms.setEnabled(active)
        self.lbl_anim_ms.setText(f"{'Speed' if loop else 'Duration'} · {self._style[f'{slot}_ms'] / 1000:.1f}s")
        if loop:
            self.lbl_anim_hint.setText("A loop animation plays for the whole clip and replaces In and Out.")
        elif self._style["anim_loop"] != "none":
            self.lbl_anim_hint.setText("Picking an In or Out animation turns the loop off.")
        else:
            self.lbl_anim_hint.setText("")

    def apply_to(self, item):
        for key, value in self._style.items():
            setattr(item, key, value)
        item.live = self.chk_live.isChecked()
        item.x = min(0.98, max(0.02, 0.5 + self.spin_x.value() / 200.0))
        item.y = min(0.98, max(0.02, 0.5 + self.spin_y.value() / 200.0))
        item.rotation = float(self.spin_rot.value())
        if self._shape_mode:
            item.shape = self._shape
            item.w = self.spin_w.value() / 100.0
            item.h = self.spin_h.value() / 100.0
            item.lock_aspect = self.btn_lock.isChecked() if hasattr(self, "btn_lock") else True
            item.blur_on = bool(self._style.get("blur_on", False))
            item.blur_radius = int(self._style.get("blur_radius", 20))

    def sync_live(self, item):
        """Update inspector controls in real time during canvas dragging without full rebuild."""
        if self._item is None or getattr(self._item, "id", "") != getattr(item, "id", ""):
            return
        self._block = True
        self.spin_x.setValue(round((float(item.x) - 0.5) * 200))
        self.spin_y.setValue(round((float(item.y) - 0.5) * 200))
        self.spin_rot.setValue(round(float(item.rotation)))
        if self._shape_mode:
            self.spin_w.setValue(round(float(item.w) * 100))
            self.spin_h.setValue(round(float(item.h) * 100))
            if hasattr(self, "btn_lock") and hasattr(item, "lock_aspect"):
                self.btn_lock.setChecked(bool(item.lock_aspect))
                self._sync_lock_icon()
            if float(item.h) > 0:
                self._aspect_ratio = float(item.w) / float(item.h)
        self.spin_scale.setValue(int(item.scale))
        self._block = False

    def set_position(self, x: float, y: float):
        self._block = True
        self.spin_x.setValue(round((x - 0.5) * 200))
        self.spin_y.setValue(round((y - 0.5) * 200))
        self._block = False
        self._emit()

    # ── edits ──────────────────────────────────────────────────────
    def _emit(self, *_):
        if not self._block and self._item is not None:
            self.changed.emit()

    def _set(self, key: str, value, turn_on: str = ""):
        if self._block:
            return
        self._style[key] = value
        if turn_on and not self._style[turn_on]:
            self._style[turn_on] = True
        if key in {"color", "stroke_on", "stroke_color", "stroke_width", "bg_on", "bg_color", "bg_opacity",
                   "shadow_on", "shadow_color", "shadow_dist"}:
            self._style["preset"] = ""
        self._style = clean_text_style(self._style)
        self._sync_widgets()
        self._emit()

    def _pick_color(self, key: str, title: str):
        color = QColorDialog.getColor(QColor(self._style[key]), self, title)
        if color.isValid():
            on = {"stroke_color": "stroke_on", "bg_color": "bg_on", "shadow_color": "shadow_on"}.get(key, "")
            self._set(key, color.name().lower(), turn_on=on)

    def _on_preset(self, index: int):
        key, _values = STYLE_PRESETS[index]
        self._style.update(preset_values(key))
        self._style["preset"] = key
        self._style = clean_text_style(self._style)
        self._sync_widgets()
        self._emit()

    def _sync_lock_icon(self):
        locked = getattr(self, "btn_lock", None) is not None and self.btn_lock.isChecked()
        name = "lock" if locked else "unlock"
        col = COLOR_PRIMARY if locked else COLOR_TEXT_MUTED
        if hasattr(self, "btn_lock"):
            self.btn_lock.setIcon(icon(name, color=col, size=14))
            self.btn_lock.setToolTip("Lock aspect ratio" if locked else "Aspect ratio unlocked")

    def _on_lock_toggled(self, locked: bool):
        self._sync_lock_icon()
        if self._item is not None:
            self._item.lock_aspect = locked
        if locked and self.spin_h.value() > 0:
            self._aspect_ratio = self.spin_w.value() / max(1, self.spin_h.value())
        if not self._block:
            self.changed.emit()

    def _on_spin_w_changed(self, new_w: int):
        if not self._block:
            if getattr(self, "btn_lock", None) is not None and self.btn_lock.isChecked() and self._aspect_ratio > 0:
                self._block = True
                new_h = max(1, min(200, int(round(new_w / self._aspect_ratio))))
                self.spin_h.setValue(new_h)
                self._block = False
            elif self.spin_h.value() > 0:
                self._aspect_ratio = new_w / max(1, self.spin_h.value())
        self._emit()

    def _on_spin_h_changed(self, new_h: int):
        if not self._block:
            if getattr(self, "btn_lock", None) is not None and self.btn_lock.isChecked() and self._aspect_ratio > 0:
                self._block = True
                new_w = max(1, min(200, int(round(new_h * self._aspect_ratio))))
                self.spin_w.setValue(new_w)
                self._block = False
            elif new_h > 0:
                self._aspect_ratio = self.spin_w.value() / max(1, new_h)
        self._emit()

    def _on_shape(self, index: int):
        if self._block:
            return
        self._shape = SHAPES[index][0]
        w, h = shape_size(self._shape)
        if self._shape in BLUR_SHAPES and not self._style.get("blur_on"):
            self._style["blur_on"] = True
            if self._style.get("blur_radius", 0) < 5:
                self._style["blur_radius"] = 24
        self._block = True
        self.spin_w.setValue(round(w * 100))
        self.spin_h.setValue(round(h * 100))
        if h > 0:
            self._aspect_ratio = w / h
        self._block = False
        self._sync_widgets()
        self._emit()

    def _on_slot(self, index: int):
        self._anim_slot = _ANIM_SLOTS[index][0]
        self.anim_stack.setCurrentIndex(index)
        self._sync_anim_slot()

    def _on_anim(self, slot: str, anim: str):
        if self._block:
            return
        self._style[slot] = anim
        if anim != "none":
            if slot == "anim_loop":
                self._style["anim_in"] = self._style["anim_out"] = "none"
            else:
                self._style["anim_loop"] = "none"
        self._sync_widgets()
        self._emit()
        if anim != "none":
            self.animation_picked.emit(slot)

    def _on_anim_ms(self, value: int):
        self._style[f"{self._anim_slot}_ms"] = int(value)
        self.lbl_anim_ms.setText(
            f"{'Speed' if self._anim_slot == 'anim_loop' else 'Duration'} · {int(value) / 1000:.1f}s"
        )
        self._emit()
