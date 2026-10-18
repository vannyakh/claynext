"""Right-dock properties: project info, or the selected track / clip."""
from __future__ import annotations

import math

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QCheckBox, QPushButton, QButtonGroup, QSizePolicy, QToolButton,
    QColorDialog, QSlider, QFrame,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

from claynext.constants.theme_constants import (
    COLOR_ACCENT_PURPLE, COLOR_BG_CARD, COLOR_BG_CARD_HOVER, COLOR_BG_INPUT,
    COLOR_BORDER, COLOR_BORDER_FOCUS, COLOR_PRIMARY, COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED, COLOR_TEXT_SUB,
)
from claynext.constants.timeline_constants import FX_KINDS, OVERLAY_KINDS
from claynext.gui.icons import icon
from claynext.models.adjust import (
    ADJUST_FIELDS, FILTER_PRESETS, clean_adjust, filter_sample_rgb, grade_filter_preview,
)
from claynext.models.canvas import (
    BLUR_LEVELS, CANVAS_BACKGROUNDS, CANVAS_COLORS, CANVAS_RATIOS, DEFAULT_CANVAS, POSITION_RANGE,
    SCALE_RANGE, clean_canvas,
)
from claynext.gui.components.collapsible_section import CollapsibleSection
from claynext.gui.components.field_controls import SelectField
from claynext.gui.components.fx_inspector import FxInspector
from claynext.gui.components.media_preview import blur_image
from claynext.gui.components.scrub_spin import ScrubSpinBox
from claynext.gui.components.segment_tabs import SegmentTabs
from claynext.gui.components.timeline.models import TimelineClip, TimelineTrack
from claynext.gui.components.overlay_canvas import TEXT_KINDS, OverlayInspector, OverlayItem
from claynext.gui.components.text_inspector import TextInspector
from claynext.gui.dialogs.project_settings_dialog import ProjectInfoPage

__all__ = ["ProjectInfoPage", "TrackPropsPage"]

AUDIO_KINDS = {"video", "voice", "audio"}
VIDEO_TABS = ("video", "audio", "adjust")
_DB_MIN, _DB_MAX = -400, 60


def pct_to_db10(pct: float) -> int:
    if pct <= 0.5:
        return _DB_MIN
    return max(_DB_MIN, min(_DB_MAX, round(200 * math.log10(pct / 100.0))))


def db10_to_pct(value: int) -> float:
    if value <= _DB_MIN:
        return 0.0
    return min(200.0, 100.0 * 10 ** (value / 200.0))


def db_text(value: int) -> str:
    return "-∞ dB" if value <= _DB_MIN else f"{value / 10:+.1f} dB"


class TrackPropsPage(QWidget):
    changed = Signal()
    overlay_changed = Signal()
    overlay_delete = Signal()
    text_animation = Signal(str)
    text_align = Signal(str)
    clear_keys = Signal()
    adjust_changed = Signal(dict, str)
    tab_changed = Signal(str)
    level_changed = Signal(float)
    key_toggle = Signal()
    key_step = Signal(int)
    fades_changed = Signal(int, int)
    auto_key_changed = Signal(dict)
    canvas_changed = Signal(dict)
    fx_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("track_props_page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._block = False
        self.track: TimelineTrack | None = None
        self.clip: TimelineClip | None = None
        self._tab = "video"
        self._has_bed = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._root = lay

        # Title lives in the sticky shelf header (outside the scroll area).
        self.title = QLabel("Track")
        self.title.hide()

        self.tab_bar = SegmentTabs(
            [key.title() for key in VIDEO_TABS],
            chrome=False,
            size="sm",
            fill=True,
            current=VIDEO_TABS.index(self._tab) if self._tab in VIDEO_TABS else 0,
        )
        self.tab_group = self.tab_bar.group
        self.tab_bar.changed.connect(lambda i: self._set_tab(VIDEO_TABS[i]))
        # tab_bar is hosted under the Properties header by InspectorTools.

        # --- AUDIO SECTION ---
        self.sec_audio, aud = self._section("Audio")
        aud.setSpacing(6)

        vol_head = QHBoxLayout()
        vol_head.setContentsMargins(0, 0, 0, 0)
        vol_head.setSpacing(4)
        vol_lbl = QLabel("VOLUME")
        vol_lbl.setObjectName("asr_field_label")
        self.lbl_db = QLabel("0.0 dB")
        self.lbl_db.setObjectName("asr_field_label")
        self.btn_key_prev = self._key_btn("‹", "Previous key point", icon_name="chevron-left")
        self.btn_key = self._key_btn("◇", "Add or remove key point at playhead")
        self.btn_key_next = self._key_btn("›", "Next key point", icon_name="chevron-right")
        self.btn_key_prev.clicked.connect(lambda: self.key_step.emit(-1))
        self.btn_key.clicked.connect(self.key_toggle.emit)
        self.btn_key_next.clicked.connect(lambda: self.key_step.emit(1))
        vol_head.addWidget(vol_lbl)
        vol_head.addStretch(1)
        vol_head.addWidget(self.btn_key_prev)
        vol_head.addWidget(self.btn_key)
        vol_head.addWidget(self.btn_key_next)
        vol_head.addSpacing(4)
        self.spin_db = ScrubSpinBox()
        self.spin_db.setRange(_DB_MIN, _DB_MAX)
        self.spin_db.setFormat(db_text)
        self.spin_db.setToolTip("Clip volume at playhead (0.1 dB units)")
        self.spin_db.setFixedWidth(78)
        self.spin_db.valueChanged.connect(self._on_db)
        vol_head.addWidget(self.spin_db)
        aud.addLayout(vol_head)

        fades_row = QHBoxLayout()
        fades_row.setContentsMargins(0, 4, 0, 0)
        fades_row.setSpacing(6)
        cell_fi, self.lbl_fade_in, self.spin_fade_in = self._paired_spin_cell("Fade In", 0, 100, suffix="s")
        self.spin_fade_in.setFormat(lambda v: f"{v/10:.1f}s")
        cell_fo, self.lbl_fade_out, self.spin_fade_out = self._paired_spin_cell("Fade Out", 0, 100, suffix="s")
        self.spin_fade_out.setFormat(lambda v: f"{v/10:.1f}s")
        self.spin_fade_in.valueChanged.connect(self._on_fade)
        self.spin_fade_out.valueChanged.connect(self._on_fade)
        fades_row.addWidget(cell_fi, 1)
        fades_row.addWidget(cell_fo, 1)
        aud.addLayout(fades_row)

        # --- AUTO KEY / DUCKING SECTION ---
        self.sec_autokey, ak = self._section("Auto key")
        ak.setSpacing(6)
        self.chk_autokey = QCheckBox("Duck original speech under the dub")
        self.chk_autokey.setObjectName("dub_switch")
        self.chk_autokey.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_autokey.setToolTip(
            "Pins source volume down wherever a dub line plays. Music & SFX stay."
        )
        self.chk_autokey.toggled.connect(self._on_autokey)
        ak.addWidget(self.chk_autokey)

        duck_head = QHBoxLayout()
        duck_head.setContentsMargins(0, 2, 0, 0)
        self.lbl_duck = QLabel("Duck to · 15%")
        self.lbl_duck.setObjectName("asr_field_label")
        self.spin_duck = ScrubSpinBox()
        self.spin_duck.setRange(0, 60)
        self.spin_duck.setSuffix("%")
        self.spin_duck.setFixedWidth(64)
        self.spin_duck.valueChanged.connect(self._on_duck)
        duck_head.addWidget(self.lbl_duck, 1)
        duck_head.addWidget(self.spin_duck)
        ak.addLayout(duck_head)

        self.chk_detect = QCheckBox("Also find original voices with no dub line")
        self.chk_detect.setObjectName("dub_switch")
        self.chk_detect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_detect.setToolTip(
            "When no music bed is ready, the whole source dips to the duck level."
        )
        self.chk_detect.toggled.connect(self._on_autokey)
        ak.addWidget(self.chk_detect)

        keys_row = QHBoxLayout()
        keys_row.setContentsMargins(0, 0, 0, 0)
        self.lbl_keys = self._hint("")
        self.btn_clear_keys = QPushButton("Clear")
        self.btn_clear_keys.setObjectName("dub_props_ghost_btn")
        self.btn_clear_keys.setIcon(icon("trash", color="#f87171", size=12))
        self.btn_clear_keys.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_keys.setToolTip("Remove every volume key point on the source")
        self.btn_clear_keys.clicked.connect(self.clear_keys.emit)
        keys_row.addWidget(self.lbl_keys, 1)
        keys_row.addWidget(self.btn_clear_keys)
        self.keys_row = QWidget()
        self.keys_row.setLayout(keys_row)
        ak.addWidget(self.keys_row)

        self._build_canvas_section()

        self.sec_filter, flt = self._section("Filter")
        self.preset_group = QButtonGroup(self)
        self.preset_group.setExclusive(True)
        self._preset_keys = list(FILTER_PRESETS)
        self._filter_source: QImage | None = None
        flt.addWidget(self._filter_grid())
        self.preset_group.idClicked.connect(self._on_preset)
        self._refresh_filter_thumbs()

        self.sec_color, col = self._section("Color")
        col.setSpacing(6)
        self._adjust_spins: dict[str, tuple[QLabel, ScrubSpinBox, str]] = {}
        for i in range(0, len(ADJUST_FIELDS), 2):
            pair_row = QHBoxLayout()
            pair_row.setContentsMargins(0, 0, 0, 0)
            pair_row.setSpacing(6)
            k1, l1, low1, high1 = ADJUST_FIELDS[i]
            cell1, lbl1, spin1 = self._paired_spin_cell(l1, low1, high1)
            spin1.valueChanged.connect(lambda v, k=k1: self._on_adjust_spin(k, v))
            self._adjust_spins[k1] = (lbl1, spin1, l1)
            pair_row.addWidget(cell1, 1)
            if i + 1 < len(ADJUST_FIELDS):
                k2, l2, low2, high2 = ADJUST_FIELDS[i + 1]
                cell2, lbl2, spin2 = self._paired_spin_cell(l2, low2, high2)
                spin2.valueChanged.connect(lambda v, k=k2: self._on_adjust_spin(k, v))
                self._adjust_spins[k2] = (lbl2, spin2, l2)
                pair_row.addWidget(cell2, 1)
            col.addLayout(pair_row)

        self.btn_reset_adjust = QPushButton("Reset adjustments")
        self.btn_reset_adjust.setObjectName("dub_props_ghost_btn")
        self.btn_reset_adjust.setIcon(icon("refresh", color=COLOR_TEXT_SUB, size=12))
        self.btn_reset_adjust.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_adjust.clicked.connect(lambda: self._on_preset(self._preset_keys.index("none")))
        col.addWidget(self.btn_reset_adjust, 0, Qt.AlignmentFlag.AlignLeft)

        # Overlay chrome only (logo / image) — no clip-name field.
        self.sec_clip, clip_l = self._section("Clip", bare=True)
        self.inspector = OverlayInspector()
        self.inspector.changed.connect(self.overlay_changed.emit)
        self.inspector.delete_requested.connect(self.overlay_delete.emit)
        clip_l.addWidget(self.inspector)

        self.sec_text, txt = self._section("Text", bare=True)
        self.text_inspector = TextInspector()
        self.text_inspector.changed.connect(self.overlay_changed.emit)
        self.text_inspector.animation_picked.connect(self.text_animation.emit)
        self.text_inspector.align_requested.connect(self.text_align.emit)
        txt.addWidget(self.text_inspector)
        self._root.removeWidget(self.sec_text)
        self._root.insertWidget(self._root.indexOf(self.sec_clip), self.sec_text)

        self.sec_shape, shp = self._section("Element", bare=True)
        self.shape_inspector = TextInspector(shape=True)
        self.shape_inspector.changed.connect(self.overlay_changed.emit)
        self.shape_inspector.animation_picked.connect(self.text_animation.emit)
        self.shape_inspector.align_requested.connect(self.text_align.emit)
        shp.addWidget(self.shape_inspector)
        self._root.removeWidget(self.sec_shape)
        self._root.insertWidget(self._root.indexOf(self.sec_clip), self.sec_shape)

        self.sec_fx, fxl = self._section("Effect")
        self.fx_inspector = FxInspector()
        self.fx_inspector.changed.connect(self.fx_changed.emit)
        fxl.addWidget(self.fx_inspector)
        self._root.removeWidget(self.sec_fx)
        self._root.insertWidget(self._root.indexOf(self.sec_clip), self.sec_fx)

        lay.addStretch(1)

    def _build_canvas_section(self):
        self._canvas_color = DEFAULT_CANVAS["color"]
        # Aspect ratio is project-level (project settings); keep value for canvas emit only.
        self._canvas_ratio = DEFAULT_CANVAS["ratio"]
        self._ratio_keys = [key for key, _label, _value in CANVAS_RATIOS]
        self.sec_canvas, cv = self._section("Canvas", bare=True)
        cv.setSpacing(6)

        tr_head = QHBoxLayout()
        tr_head.setContentsMargins(0, 0, 0, 0)
        lbl_tr = self._field_label("TRANSFORM")
        self.btn_reset_canvas = QPushButton("Reset")
        self.btn_reset_canvas.setObjectName("dub_props_ghost_btn")
        self.btn_reset_canvas.setIcon(icon("refresh", color=COLOR_TEXT_SUB, size=10))
        self.btn_reset_canvas.setIconSize(QSize(10, 10))
        self.btn_reset_canvas.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_canvas.setToolTip("Centre the video and reset scale to 100%")
        self.btn_reset_canvas.clicked.connect(self._reset_canvas_transform)
        tr_head.addWidget(lbl_tr, 1)
        tr_head.addWidget(self.btn_reset_canvas)
        cv.addLayout(tr_head)

        scale_row = QHBoxLayout()
        scale_row.setContentsMargins(0, 0, 0, 0)
        scale_row.setSpacing(6)
        self.lbl_scale = QLabel("Scale")
        self.lbl_scale.setObjectName("asr_field_label")
        self.slider_scale = QSlider(Qt.Orientation.Horizontal)
        self.slider_scale.setRange(SCALE_RANGE[0], SCALE_RANGE[1])
        self.slider_scale.setValue(100)
        self.slider_scale.valueChanged.connect(self._on_scale_slider)
        self.spin_scale = ScrubSpinBox()
        self.spin_scale.setRange(*SCALE_RANGE)
        self.spin_scale.setSuffix("%")
        self.spin_scale.setFixedWidth(64)
        self.spin_scale.valueChanged.connect(self._on_canvas_spin)
        self.btn_scale_100 = QPushButton("100%")
        self.btn_scale_100.setObjectName("dub_props_ghost_btn")
        self.btn_scale_100.setFixedWidth(40)
        self.btn_scale_100.setToolTip("Reset scale to 100%")
        self.btn_scale_100.clicked.connect(lambda: self.spin_scale.setValue(100))
        scale_row.addWidget(self.lbl_scale)
        scale_row.addWidget(self.slider_scale, 1)
        scale_row.addWidget(self.spin_scale)
        scale_row.addWidget(self.btn_scale_100)
        cv.addLayout(scale_row)

        pos_row = QHBoxLayout()
        pos_row.setContentsMargins(0, 4, 0, 0)
        pos_row.setSpacing(6)
        cell_px, self.lbl_pos_x, self.spin_pos_x = self._paired_spin_cell("Position X", *POSITION_RANGE, prefix="X ", suffix="%")
        cell_py, self.lbl_pos_y, self.spin_pos_y = self._paired_spin_cell("Position Y", *POSITION_RANGE, prefix="Y ", suffix="%")
        self.spin_pos_x.valueChanged.connect(self._on_canvas_spin)
        self.spin_pos_y.valueChanged.connect(self._on_canvas_spin)
        pos_row.addWidget(cell_px, 1)
        pos_row.addWidget(cell_py, 1)
        cv.addLayout(pos_row)

        cv.addWidget(self._field_label("BACKGROUND"))
        self._bg_keys = [key for key, _label in CANVAS_BACKGROUNDS]
        self.bg_select = SelectField(size="sm", width=None)
        self.bg_select.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for key, label in CANVAS_BACKGROUNDS:
            self.bg_select.addItem(label, key)
        self.bg_select.setToolTip("Canvas background fill")
        self.bg_select.value_changed.connect(self._emit_canvas)
        cv.addWidget(self.bg_select)

        self.blur_row = QWidget()
        blur_l = QHBoxLayout(self.blur_row)
        blur_l.setContentsMargins(0, 0, 0, 0)
        blur_l.setSpacing(6)
        self.blur_group = QButtonGroup(self)
        self.blur_group.setExclusive(True)
        for level in BLUR_LEVELS:
            btn = self._swatch_btn(f"Blur strength {level}", QSize(56, 34))
            self.blur_group.addButton(btn, level)
            blur_l.addWidget(btn)
        blur_l.addStretch(1)
        self.blur_group.idClicked.connect(self._emit_canvas)
        cv.addWidget(self.blur_row)

        self.color_row = QWidget()
        color_l = QGridLayout(self.color_row)
        color_l.setContentsMargins(0, 0, 0, 0)
        color_l.setSpacing(6)
        self.color_group = QButtonGroup(self)
        self.color_group.setExclusive(True)
        for i, color in enumerate(CANVAS_COLORS):
            btn = self._swatch_btn(color, QSize(26, 26))
            btn.setIcon(self._color_icon(color, 18))
            btn.setIconSize(QSize(18, 18))
            self.color_group.addButton(btn, i)
            color_l.addWidget(btn, 0, i)
        self.btn_color_custom = self._swatch_btn("Custom colour…", QSize(26, 26))
        self.btn_color_custom.setCheckable(False)
        self.btn_color_custom.setText("+")
        self.btn_color_custom.clicked.connect(self._pick_canvas_color)
        color_l.addWidget(self.btn_color_custom, 0, len(CANVAS_COLORS))
        color_l.setColumnStretch(len(CANVAS_COLORS) + 1, 1)
        self.color_group.idClicked.connect(self._on_canvas_swatch)
        cv.addWidget(self.color_row)
        self.lbl_canvas_hint = self._hint("")
        cv.addWidget(self.lbl_canvas_hint)

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("asr_field_label")
        return label

    @staticmethod
    def _swatch_btn(tip: str, size: QSize) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("dub_canvas_swatch")
        btn.setCheckable(True)
        btn.setToolTip(tip)
        btn.setFixedSize(size)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    @staticmethod
    def _color_icon(color: str, side: int) -> QIcon:
        pix = QPixmap(side, side)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QColor(COLOR_BORDER))
        p.setBrush(QColor(color))
        p.drawRoundedRect(0, 0, side - 1, side - 1, 4, 4)
        p.end()
        return QIcon(pix)

    def set_blur_source(self, image: QImage):
        """Blur + filter thumbnails rendered from a frame of the footage."""
        self._filter_source = None if image.isNull() else image
        self._refresh_filter_thumbs()
        for level in BLUR_LEVELS:
            btn = self.blur_group.button(level)
            big = blur_image(image, QSize(320, 192), level) if not image.isNull() else QPixmap()
            if big.isNull():
                btn.setIcon(QIcon())
                btn.setText(str(level))
                continue
            btn.setText("")
            btn.setIcon(QIcon(big.scaled(52, 30, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)))
            btn.setIconSize(QSize(52, 30))

    def _filter_grid(self) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("dub_props_filter_grid")
        grid = QGridLayout(wrap)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(5)
        grid.setVerticalSpacing(5)
        cols = 3
        for i, key in enumerate(self._preset_keys):
            label = FILTER_PRESETS[key][0]
            btn = QToolButton()
            btn.setObjectName("dub_props_filter")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setText(label)
            btn.setToolTip(f"{label} look")
            btn.setIconSize(QSize(72, 42))
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.preset_group.addButton(btn, i)
            grid.addWidget(btn, i // cols, i % cols)
        for c in range(cols):
            grid.setColumnStretch(c, 1)
        return wrap

    def _refresh_filter_thumbs(self):
        """Bake graded samples onto each preset tile (footage frame or synthetic)."""
        rgb = self._filter_rgb()
        for i, key in enumerate(self._preset_keys):
            btn = self.preset_group.button(i)
            if btn is None:
                continue
            pix = self._rgb_thumb(grade_filter_preview(rgb, key), 72, 42)
            btn.setIcon(QIcon(pix))
            btn.setIconSize(QSize(72, 42))

    def _filter_rgb(self):
        src = self._filter_source
        if src is not None and not src.isNull():
            scaled = src.scaled(72, 42, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                               Qt.TransformationMode.SmoothTransformation)
            x = max(0, (scaled.width() - 72) // 2)
            y = max(0, (scaled.height() - 42) // 2)
            crop = scaled.copy(x, y, 72, 42).convertToFormat(QImage.Format.Format_RGB888)
            w, h = crop.width(), crop.height()
            bpl = crop.bytesPerLine()
            buf = bytes(crop.constBits())
            # QImage may pad rows — reshape via bytes-per-line.
            import numpy as np
            arr = np.frombuffer(buf, dtype=np.uint8)
            if bpl == w * 3:
                return arr.reshape(h, w, 3).copy()
            rows = [arr[r * bpl:r * bpl + w * 3] for r in range(h)]
            return np.asarray(rows, dtype=np.uint8).reshape(h, w, 3).copy()
        return filter_sample_rgb(42, 72).copy()

    @staticmethod
    def _rgb_thumb(rgb, w: int, h: int) -> QPixmap:
        import numpy as np
        data = np.ascontiguousarray(rgb, dtype=np.uint8)
        image = QImage(data.data, data.shape[1], data.shape[0], data.shape[1] * 3, QImage.Format.Format_RGB888).copy()
        return QPixmap.fromImage(image.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))

    def canvas_state(self) -> dict:
        ratio = self._canvas_ratio if self._canvas_ratio in self._ratio_keys else DEFAULT_CANVAS["ratio"]
        bg = self.bg_select.current_value() or self._bg_keys[0]
        return clean_canvas({
            "ratio": ratio,
            "scale": self.spin_scale.value(),
            "x": self.spin_pos_x.value(),
            "y": self.spin_pos_y.value(),
            "bg": bg,
            "blur": self.blur_group.checkedId() if self.blur_group.checkedId() > 0 else 2,
            "color": self._canvas_color,
        })

    def set_canvas_state(self, canvas: dict | None):
        c = clean_canvas(canvas)
        was = self._block
        self._block = True
        self._canvas_ratio = c["ratio"]
        self.bg_select.blockSignals(True)
        self.bg_select.set_value(c["bg"])
        self.bg_select.blockSignals(False)
        self.blur_group.button(c["blur"]).setChecked(True)
        self._canvas_color = c["color"]
        self._check_color_swatch()
        self.show_transform(c)
        self._block = was
        self._sync_canvas_rows()

    def show_transform(self, transform: dict):
        """Mirror a drag on the preview handles without re-emitting."""
        for spin, key in ((self.spin_scale, "scale"), (self.spin_pos_x, "x"), (self.spin_pos_y, "y")):
            if key in transform:
                spin.blockSignals(True)
                spin.setValue(int(transform[key]))
                spin.blockSignals(False)
        if hasattr(self, "slider_scale") and "scale" in transform:
            self.slider_scale.blockSignals(True)
            self.slider_scale.setValue(int(transform["scale"]))
            self.slider_scale.blockSignals(False)
        self._relabel_canvas()

    def show_canvas_hint(self, covered: bool):
        bg = self.bg_select.current_value() or "none"
        self.lbl_canvas_hint.setVisible(covered and bg != "none")
        self.lbl_canvas_hint.setText("The video fills the canvas · scale it down to see the background.")

    def _relabel_canvas(self):
        self.lbl_scale.setText("Scale")
        self.lbl_pos_x.setText("Position X")
        self.lbl_pos_y.setText("Position Y")

    def _sync_canvas_rows(self):
        bg = self.bg_select.current_value() or "none"
        self.blur_row.setVisible(bg == "blur")
        self.color_row.setVisible(bg == "color")

    def _check_color_swatch(self):
        self.color_group.setExclusive(False)
        for i, btn in enumerate(self.color_group.buttons()):
            btn.setChecked(CANVAS_COLORS[i] == self._canvas_color)
        self.color_group.setExclusive(True)
        custom = self._canvas_color not in CANVAS_COLORS
        self.btn_color_custom.setIcon(self._color_icon(self._canvas_color, 18) if custom else QIcon())
        self.btn_color_custom.setText("" if custom else "+")

    def _on_canvas_spin(self, *_):
        if hasattr(self, "slider_scale"):
            self.slider_scale.blockSignals(True)
            self.slider_scale.setValue(self.spin_scale.value())
            self.slider_scale.blockSignals(False)
        self._emit_canvas()

    def _on_scale_slider(self, value: int):
        self.spin_scale.setValue(value)

    def _on_canvas_swatch(self, index: int):
        self._canvas_color = CANVAS_COLORS[index]
        self._check_color_swatch()
        self._emit_canvas()

    def _pick_canvas_color(self):
        color = QColorDialog.getColor(QColor(self._canvas_color), self, "Canvas background colour")
        if color.isValid():
            self._canvas_color = color.name().lower()
            self._check_color_swatch()
            self._emit_canvas()

    def _reset_canvas_transform(self):
        self.show_transform({"scale": 100, "x": 0, "y": 0})
        self._emit_canvas()

    def _emit_canvas(self, *_):
        self._sync_canvas_rows()
        if not self._block:
            self.canvas_changed.emit(self.canvas_state())

    def _section(
        self,
        title: str,
        *,
        open: bool = True,
        bare: bool = False,
        divider: bool = False,
        collapsible: bool = True,
    ) -> tuple[QWidget, QVBoxLayout]:
        """Clean inspector block — purple header + optional chevron."""
        if bare:
            box = QWidget()
            box.setObjectName("dub_config_section")
            body_l = QVBoxLayout(box)
            body_l.setContentsMargins(0, 0, 0, 4)
            body_l.setSpacing(6)
            self._root.addWidget(box)
            return box, body_l
        sec = CollapsibleSection(title, open=open, divider=divider, collapsible=collapsible)
        self._root.addWidget(sec)
        return sec, sec.body_layout

    @staticmethod
    def _hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("dub_switch_hint")
        label.setStyleSheet("padding-left: 0;")
        label.setWordWrap(True)
        return label

    def _paired_spin_cell(
        self, label_text: str, low: int, high: int, prefix: str = "", suffix: str = "",
    ) -> tuple[QWidget, QLabel, ScrubSpinBox]:
        cell = QWidget()
        l = QVBoxLayout(cell)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(2)
        lbl = QLabel(label_text)
        lbl.setObjectName("asr_field_label")
        spin = ScrubSpinBox()
        spin.setRange(low, high)
        if prefix:
            spin.setPrefix(prefix)
        if suffix:
            spin.setSuffix(suffix)
        spin.setMaximumWidth(16777215)
        spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        l.addWidget(lbl)
        l.addWidget(spin)
        return cell, lbl, spin

    def _spin_row(
        self, layout: QVBoxLayout, text: str, low: int, high: int, suffix: str = "",
    ) -> tuple[QLabel, ScrubSpinBox]:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        label = QLabel(text)
        label.setObjectName("asr_field_label")
        spin = ScrubSpinBox()
        spin.setRange(low, high)
        spin.setSuffix(suffix)
        spin.setToolTip("Drag up/down to scrub · click to type · ▲▼ to step")
        row.addWidget(label, 1)
        row.addWidget(spin, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(row)
        return label, spin

    @staticmethod
    def _key_btn(text: str, tip: str, icon_name: str = "") -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("timeline_tool_btn")
        if icon_name:
            btn.setIcon(icon(icon_name, color=COLOR_TEXT_SUB, size=12))
        else:
            btn.setText(text)
        btn.setToolTip(tip)
        btn.setFixedSize(24, 24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def show_level(self, level: float, on_key: bool, has_prev: bool, has_next: bool):
        """Reflect the clip level under the playhead (called as the playhead moves)."""
        value = pct_to_db10(level)
        self.spin_db.blockSignals(True)
        self.spin_db.setValue(value)
        self.spin_db.blockSignals(False)
        self.lbl_db.setText(db_text(value))
        self.btn_key.setText("◆" if on_key else "◇")
        self.btn_key_prev.setEnabled(has_prev)
        self.btn_key_next.setEnabled(has_next)

    def show_key_count(self, count: int):
        self.keys_row.setVisible(count > 0)
        self.lbl_keys.setText(f"{count} key point{'s' if count != 1 else ''} on the source")

    def show_bed_state(self, has_bed: bool):
        self._has_bed = has_bed
        self._sync_autokey_enabled()

    def auto_key_state(self) -> dict:
        return {
            "on": self.chk_autokey.isChecked(),
            "detect": self.chk_detect.isChecked(),
            "level": self.spin_duck.value(),
        }

    def _on_db(self, value: int):
        self.lbl_db.setText(db_text(value))
        if not self._block:
            self.level_changed.emit(db10_to_pct(value))

    def _on_fade(self, *_):
        fade_in = self.spin_fade_in.value() * 100
        fade_out = self.spin_fade_out.value() * 100
        self.lbl_fade_in.setText(f"Fade in · {fade_in / 1000:.1f}s")
        self.lbl_fade_out.setText(f"Fade out · {fade_out / 1000:.1f}s")
        if not self._block:
            self.fades_changed.emit(fade_in, fade_out)

    def _on_duck(self, value: int):
        self.lbl_duck.setText(f"Duck to · {value}%")
        if not self._block and self.chk_autokey.isChecked():
            self.auto_key_changed.emit(self.auto_key_state())

    def _sync_autokey_enabled(self):
        on = self.chk_autokey.isChecked()
        self.chk_detect.setEnabled(on)
        duck_enabled = on and not self._has_bed
        self.spin_duck.setEnabled(duck_enabled)
        self.lbl_duck.setEnabled(duck_enabled)

    def _on_autokey(self, *_):
        self._sync_autokey_enabled()
        if not self._block:
            self.auto_key_changed.emit(self.auto_key_state())

    def _relabel(self, label: QLabel, name: str, value: str):
        label.setText(f"{name} · {value}")
        self._emit()

    def current_tab(self) -> str:
        return self._tab if self.track is not None and self.track.kind == "video" else ""

    def _set_tab(self, tab: str):
        self._tab = tab
        self.tab_group.button(VIDEO_TABS.index(tab)).setChecked(True)
        self._sync_sections()
        self.tab_changed.emit(tab)

    def _sync_sections(self):
        track, clip = self.track, self.clip
        if track is None:
            return
        kind = track.kind
        is_master = bool(clip and clip.extra.get("master"))
        has_audio = kind in AUDIO_KINDS
        if kind == "video":
            tab = self._tab
            show = {
                self.sec_text: False,
                self.sec_shape: False,
                self.sec_fx: clip is not None and (
                    bool(clip.extra.get("transition")) or bool(clip.extra.get("applied_fx"))
                ),
                self.sec_canvas: tab == "video" and clip is not None,
                self.sec_clip: False,
                self.sec_audio: tab == "audio",
                self.sec_autokey: tab == "audio",
                self.sec_filter: tab == "adjust",
                self.sec_color: tab == "adjust",
            }
        else:
            show = {
                self.sec_text: clip is not None and clip.kind in TEXT_KINDS,
                self.sec_shape: clip is not None and clip.kind in {"shape", "mask"},
                self.sec_fx: clip is not None and clip.kind in FX_KINDS,
                self.sec_canvas: False,
                self.sec_clip: clip is not None and not is_master
                    and clip.kind in OVERLAY_KINDS
                    and clip.kind not in TEXT_KINDS | FX_KINDS | {"shape", "mask"},
                self.sec_audio: has_audio,
                self.sec_autokey: False,
                self.sec_filter: False,
                self.sec_color: False,
            }
        for widget, visible in show.items():
            widget.setVisible(visible)

    def bind(self, track: TimelineTrack | None, clip: TimelineClip | None = None, source_path: str = ""):
        del source_path  # kept for call-site compatibility
        self.track = track
        self.clip = clip
        if not track:
            return
        self._block = True
        kind = track.kind
        is_master = bool(clip and clip.extra.get("master"))
        self.title.setText(clip.label if clip and not is_master else track.name)
        fade_in = int(clip.extra.get("fade_in") or 0) if clip else 0
        fade_out = int(clip.extra.get("fade_out") or 0) if clip else 0
        self.spin_fade_in.setValue(round(fade_in / 100))
        self.spin_fade_out.setValue(round(fade_out / 100))
        self.lbl_fade_in.setText(f"Fade in · {fade_in / 1000:.1f}s")
        self.lbl_fade_out.setText(f"Fade out · {fade_out / 1000:.1f}s")
        for widget in (self.lbl_fade_in, self.spin_fade_in, self.lbl_fade_out, self.spin_fade_out,
                       self.spin_db, self.btn_key, self.btn_key_prev, self.btn_key_next):
            widget.setEnabled(clip is not None)

        auto = dict(clip.extra.get("auto_key") or {}) if clip else {}
        self.chk_autokey.setChecked(bool(auto.get("on")))
        self.chk_detect.setChecked(bool(auto.get("detect")))
        duck_val = int(auto.get("level", 0))
        self.spin_duck.setValue(duck_val)
        self.lbl_duck.setText(f"Duck to · {duck_val}%")
        self.show_key_count(len(clip.extra.get("keys") or []) if clip else 0)
        self._sync_autokey_enabled()

        self.set_canvas_state(clip.extra.get("canvas") if clip and kind == "video" else None)

        adjust = clean_adjust(clip.extra.get("adjust") if clip else None)
        for key, (lbl, spin, label) in self._adjust_spins.items():
            spin.setValue(adjust.get(key, 0))
            lbl.setText(label)
        self._check_preset(str(clip.extra.get("filter") or "custom") if adjust else "none")

        overlay = None
        if clip and clip.kind in OVERLAY_KINDS:
            data = dict(clip.extra.get("overlay") or {})
            data["id"] = clip.id
            data["kind"] = clip.kind
            data["start_ms"] = clip.start_ms
            data["duration_ms"] = clip.duration_ms
            overlay = OverlayItem.from_dict(data)
        is_text = overlay is not None and overlay.kind in TEXT_KINDS
        is_shape = overlay is not None and overlay.kind in {"shape", "mask"}
        styled = is_text or is_shape
        self.inspector.bind(None if styled else overlay)
        self.inspector.setVisible(overlay is not None and not styled)
        self.text_inspector.bind(overlay if is_text else None)
        self.shape_inspector.bind(overlay if is_shape else None)
        is_fx = clip is not None and clip.kind in FX_KINDS
        has_tr = clip is not None and bool(clip.extra.get("transition"))
        applied = list(clip.extra.get("applied_fx") or []) if clip is not None else []
        applied = [row for row in applied if isinstance(row, dict)]
        if applied:
            last = applied[-1]
            kind = str(last.get("kind") or "effect")
            self.fx_inspector.bind(kind if kind in {"effect", "filter"} else "effect", last)
            if isinstance(self.sec_fx, CollapsibleSection):
                self.sec_fx.set_title("Filter" if kind == "filter" else "Effect")
        elif is_fx:
            self.fx_inspector.bind(clip.kind, clip.extra.get("fx"))
            if isinstance(self.sec_fx, CollapsibleSection):
                self.sec_fx.set_title("Filter" if clip.kind == "filter" else "Effect")
        elif has_tr:
            self.fx_inspector.bind("transition", clip.extra.get("transition"))
            if isinstance(self.sec_fx, CollapsibleSection):
                self.sec_fx.set_title("Transition")

        self._sync_sections()
        self._block = False

    def apply_to(self, track: TimelineTrack, clip: TimelineClip | None = None):
        """Kept for inspector hook; mute and clip rename stay on the timeline."""
        del track, clip

    def adjust_values(self) -> dict[str, int]:
        return clean_adjust({key: spin.value() for key, (_l, spin, _n) in self._adjust_spins.items()})

    def _check_preset(self, key: str):
        self.preset_group.setExclusive(False)
        for i, name in enumerate(self._preset_keys):
            btn = self.preset_group.button(i)
            if btn is not None:
                btn.setChecked(name == key)
        self.preset_group.setExclusive(True)

    def _on_preset(self, index: int):
        key = self._preset_keys[index]
        values = FILTER_PRESETS[key][1]
        self._block = True
        for name, (lbl, spin, label) in self._adjust_spins.items():
            spin.setValue(values.get(name, 0))
            lbl.setText(label)
        self._block = False
        self._check_preset(key)
        self.adjust_changed.emit(self.adjust_values(), key)

    def _on_adjust_spin(self, key: str, value: int):
        lbl, _spin, label = self._adjust_spins[key]
        lbl.setText(label)
        if self._block:
            return
        values = self.adjust_values()
        self._check_preset("none" if not values else "")
        self.adjust_changed.emit(values, "none" if not values else "custom")

    def _emit(self, *_):
        if not self._block:
            self.changed.emit()

