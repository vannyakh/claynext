"""Right-dock properties for the selected track or clip."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QPushButton,
    QButtonGroup,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage

from claynext.constants.theme_constants import COLOR_TEXT_SUB
from claynext.gui.components.inspector.fx import FxInspector
from claynext.gui.components.overlay.inspector import OverlayInspector
from claynext.gui.components.controls.scrub_spin import ScrubSpinBox
from claynext.gui.components.controls.tabs import SegmentTabs
from claynext.gui.components.inspector.text import TextInspector
from claynext.gui.components.timeline.models import TimelineClip, TimelineTrack
from claynext.gui.icons import icon
from claynext.models.adjust import ADJUST_FIELDS, FILTER_PRESETS

from claynext.gui.components.inspector.properties.audio import PropsAudio
from claynext.gui.components.inspector.properties.bind import PropsBind
from claynext.gui.components.inspector.properties.canvas import PropsCanvas
from claynext.gui.components.inspector.properties.chrome import PropsChrome
from claynext.gui.components.inspector.properties.const import DB_MAX, DB_MIN, VIDEO_TABS, db_text

class TrackPropsPage(PropsCanvas, PropsChrome, PropsAudio, PropsBind, QWidget):
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
        self.spin_db.setRange(DB_MIN, DB_MAX)
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
