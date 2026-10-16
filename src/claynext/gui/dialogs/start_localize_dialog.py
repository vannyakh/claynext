"""Confirm and configure options before starting a localization job."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QStackedWidget, QVBoxLayout, QWidget,
)

from claynext.models.asr_service import ASREngine
from claynext.models.features import stem_status_label
from claynext.models.text_style import CAPTION_ANIMS
from claynext.models.tts_service import TTSEngine
from claynext.models.translate_service import TranslateEngine
from claynext.gui.components.scrub_spin import ScrubSpinBox
from claynext.gui.components.segment_tabs import SegmentTabs
from claynext.gui.views.studio.captions import CAPTION_STYLES, CaptionLookGrid, CaptionMotionGrid
from claynext.gui.views.studio.constants import SOURCE_LANGS

_TAB_LABELS = ["Cast", "Mix", "Captions", "Template", "Engine"]
_TAB_TIPS = [
    "Languages & voices",
    "Timing & mix",
    "Use captions · layout & export",
    "Package look & motion · auto-apply",
    "Speech & translation engines",
]


class StartLocalizeDialog(QDialog):
    """Review the selected movies and tweak localization settings before the job runs."""

    def __init__(self, parent=None, *, sources: list[str], defaults: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Start Localization")
        self.setObjectName("startLocalizeDialog")
        self.setMinimumWidth(560)
        self.setMinimumHeight(580)
        self.setModal(True)
        self._sources = [p for p in (sources or []) if p and os.path.isfile(p)]
        defaults = dict(defaults or {})

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        n = len(self._sources)
        chrome = QFrame()
        chrome.setObjectName("start_dub_chrome")
        chrome.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        chrome_l = QVBoxLayout(chrome)
        chrome_l.setContentsMargins(12, 8, 12, 8)
        chrome_l.setSpacing(0)
        self.tabs = SegmentTabs(
            _TAB_LABELS,
            variant="segment",
            size="sm",
            fill=True,
            tips=_TAB_TIPS,
        )
        self.tabs.changed.connect(self._show_tab)
        chrome_l.addWidget(self.tabs)
        root.addWidget(chrome)

        body = QWidget()
        body.setObjectName("start_dub_body")
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(16, 12, 16, 16)
        body_l.setSpacing(12)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_cast_page(defaults))
        self.stack.addWidget(self._build_mix_page(defaults))
        self.stack.addWidget(self._build_captions_page(defaults))
        self.stack.addWidget(self._build_template_page(defaults))
        self.stack.addWidget(self._build_engine_page(defaults))
        body_l.addWidget(self.stack, 1)
        self._sync_caption_controls()

        self._batch_group: QButtonGroup | None = None
        if n >= 2:
            body_l.addWidget(self._build_batch_box(defaults, n))

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 4, 0, 0)
        actions.setSpacing(10)
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("start_localize_btn")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setFixedHeight(34)
        cancel.setMinimumWidth(96)
        cancel.clicked.connect(self.reject)
        self.btn_start = QPushButton(
            "Start Localization" if n <= 1 else f"Start Localization · {n}"
        )
        self.btn_start.setObjectName("start_localize_btn_primary")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setFixedHeight(34)
        self.btn_start.setMinimumWidth(148)
        self.btn_start.setDefault(True)
        self.btn_start.setEnabled(n > 0)
        self.btn_start.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(self.btn_start)
        body_l.addLayout(actions)
        root.addWidget(body, 1)

        self._voice_prim = defaults.get("voice", "")
        self._voice_sec = defaults.get("secondary_voice", "")
        self._refill_voices(self.combo_target.currentText())

    def _show_tab(self, index: int):
        self.stack.setCurrentIndex(max(0, int(index)))

    def _build_batch_box(self, defaults: dict, n: int) -> QWidget:
        """Episode batch: separate dedicated tasks (default) or merge to one movie."""
        box = QFrame()
        box.setObjectName("start_dub_batch")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        head = QLabel(f"Batch · {n} episodes")
        head.setObjectName("start_dub_sources_head")
        lay.addWidget(head)

        self.radio_separate = QRadioButton("Separate episodes")
        self.radio_separate.setObjectName("dub_switch")
        self.radio_separate.setToolTip(
            "Localize each episode as its own task and script. Best when episodes stay separate."
        )
        self.radio_merge = QRadioButton("Merge to one movie")
        self.radio_merge.setObjectName("dub_switch")
        self.radio_merge.setToolTip(
            "Join episodes in order first, then run one transcription/translate/speak pass "
            "and land one combined movie on the timeline."
        )
        self._batch_group = QButtonGroup(self)
        self._batch_group.addButton(self.radio_separate)
        self._batch_group.addButton(self.radio_merge)
        # Default: dedicated tasks (not merge).
        prefer = str(defaults.get("batch_mode") or "separate")
        if prefer == "merge":
            self.radio_merge.setChecked(True)
        else:
            self.radio_separate.setChecked(True)
        lay.addWidget(self.radio_separate)
        lay.addWidget(self.radio_merge)
        return box

    def _page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("start_dub_tab_page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 8, 2, 4)
        lay.setSpacing(10)
        return page, lay

    def _grid(self, parent_lay: QVBoxLayout) -> QGridLayout:
        box = QFrame()
        box.setObjectName("dub_config_section")
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 2, 0, 2)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        parent_lay.addWidget(box)
        return grid

    def _combo(self) -> QComboBox:
        """Compact dropdown matched to ScrubSpinBox height (30px)."""
        combo = QComboBox()
        combo.setObjectName("start_localize_combo")
        combo.setFixedHeight(30)
        return combo

    def _section_divider(self, title: str) -> QWidget:
        """Labeled divider between config sessions (fields → options)."""
        wrap = QWidget()
        wrap.setObjectName("start_localize_divider")
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 6, 0, 2)
        lay.setSpacing(8)
        label = QLabel(title.upper())
        label.setObjectName("start_localize_divider_label")
        rule = QFrame()
        rule.setObjectName("start_localize_divider_rule")
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setFixedHeight(1)
        lay.addWidget(label, 0)
        lay.addWidget(rule, 1)
        return wrap

    def _build_cast_page(self, defaults: dict) -> QWidget:
        page, lay = self._page()
        lay.addWidget(self._section_divider("Languages"))
        grid = self._grid(lay)

        self.combo_source = self._combo()
        self.combo_source.addItems(list(SOURCE_LANGS))
        self._set_text(self.combo_source, defaults.get("source_lang", "Chinese"))
        grid.addWidget(self._label("Source"), 0, 0)
        grid.addWidget(self.combo_source, 0, 1)

        self.combo_target = self._combo()
        self.combo_target.addItems(list(TranslateEngine.TARGET_LANGUAGES))
        self._set_text(self.combo_target, defaults.get("target_lang", "Khmer"))
        self.combo_target.currentTextChanged.connect(self._refill_voices)
        grid.addWidget(self._label("Target"), 1, 0)
        grid.addWidget(self.combo_target, 1, 1)

        self.combo_voice = self._combo()
        grid.addWidget(self._label("Lead voice"), 2, 0)
        grid.addWidget(self.combo_voice, 2, 1)

        self.combo_voice_sec = self._combo()
        grid.addWidget(self._label("Co-star"), 3, 0)
        grid.addWidget(self.combo_voice_sec, 3, 1)

        lay.addWidget(self._section_divider("Options"))
        opts = QVBoxLayout()
        opts.setContentsMargins(0, 0, 0, 0)
        opts.setSpacing(8)
        self.chk_auto_chain = self._option(
            opts, "Character chain", "Cast → translate → speak with lead & co-star",
            bool(defaults.get("auto_chain", True)),
        )
        lay.addLayout(opts)
        lay.addStretch(1)
        return page

    def _build_captions_page(self, defaults: dict) -> QWidget:
        """Enable captions, layout, and export — applied when the job finishes."""
        page, lay = self._page()

        opts = QVBoxLayout()
        opts.setContentsMargins(0, 0, 0, 0)
        opts.setSpacing(8)
        self.chk_auto_captions = self._option(
            opts,
            "Use captions",
            "Auto-apply the Template package when localization finishes. Uncheck to skip captions.",
            bool(defaults.get("auto_captions", True)),
        )
        lay.addLayout(opts)

        lay.addWidget(self._section_divider("Layout"))
        grid = self._grid(lay)
        self.spin_caption_y = ScrubSpinBox()
        self.spin_caption_y.setRange(60, 95)
        self.spin_caption_y.setSuffix("%")
        try:
            self.spin_caption_y.setValue(int(defaults.get("caption_y", 86)))
        except (TypeError, ValueError):
            self.spin_caption_y.setValue(86)
        y_row = QHBoxLayout()
        y_row.setContentsMargins(0, 0, 0, 0)
        y_row.setSpacing(10)
        self.lbl_caption_y = self._label("Vertical position")
        y_row.addWidget(self.lbl_caption_y, 1)
        y_row.addWidget(self.spin_caption_y, 0, Qt.AlignmentFlag.AlignRight)
        grid.addLayout(y_row, 0, 0, 1, 2)

        lay.addWidget(self._section_divider("Options"))
        more = QVBoxLayout()
        more.setContentsMargins(0, 0, 0, 0)
        more.setSpacing(8)
        self.chk_caption_fit = self._option(
            more,
            "Safe-area fit",
            "Center captions and keep them inside the title-safe width",
            bool(defaults.get("caption_fit", True)),
        )
        self.chk_export_srt = self._option(
            more,
            "Export SRT on finish",
            "Write a sidecar .srt next to the project output when the job completes",
            bool(defaults.get("export_srt", False)),
        )
        lay.addLayout(more)
        lay.addStretch(1)

        self.chk_auto_captions.toggled.connect(self._sync_caption_controls)
        return page

    def _build_template_page(self, defaults: dict) -> QWidget:
        """Package look + motion presets — auto-applied when Use captions is on."""
        page, lay = self._page()

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        head.addWidget(self._section_divider("Look"), 1)
        self.chk_caption_lock = QCheckBox("Lock package")
        self.chk_caption_lock.setObjectName("dub_switch")
        self.chk_caption_lock.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_caption_lock.setChecked(bool(defaults.get("caption_lock", False)))
        self.chk_caption_lock.setToolTip(
            "Keep this package selected — previews stay visible, look tiles cannot be changed"
        )
        head.addWidget(self.chk_caption_lock, 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(head)

        look = str(defaults.get("caption_look") or "")
        pick = next(
            (i for i, s in enumerate(CAPTION_STYLES) if str(s.get("name") or "") == look),
            0,
        )
        self.caption_look_grid = CaptionLookGrid(CAPTION_STYLES)
        self.caption_look_grid.setObjectName("start_localize_look_grid")
        self.caption_look_grid.set_current(pick)
        lay.addWidget(self.caption_look_grid)

        lay.addWidget(self._section_divider("Motion"))
        saved_anim = str(defaults.get("caption_anim") or "none")
        anim_pick = next(
            (i for i, (key, _) in enumerate(CAPTION_ANIMS) if key == saved_anim),
            0,
        )
        self.caption_motion_grid = CaptionMotionGrid(list(CAPTION_ANIMS))
        self.caption_motion_grid.setObjectName("start_localize_motion_grid")
        self.caption_motion_grid.set_current(anim_pick)
        lay.addWidget(self.caption_motion_grid)
        lay.addStretch(1)

        self.chk_caption_lock.toggled.connect(self._sync_caption_lock)
        return page

    def _caption_look_name(self) -> str:
        idx = self.caption_look_grid.current() if hasattr(self, "caption_look_grid") else 0
        if 0 <= idx < len(CAPTION_STYLES):
            return str(CAPTION_STYLES[idx].get("name") or "")
        return ""

    def _caption_anim_key(self) -> str:
        idx = self.caption_motion_grid.current() if hasattr(self, "caption_motion_grid") else 0
        if 0 <= idx < len(CAPTION_ANIMS):
            return CAPTION_ANIMS[idx][0]
        return "none"

    def _sync_caption_lock(self, *_args):
        locked = bool(getattr(self, "chk_caption_lock", None) and self.chk_caption_lock.isChecked())
        use = bool(getattr(self, "chk_auto_captions", None) and self.chk_auto_captions.isChecked())
        if hasattr(self, "caption_look_grid"):
            self.caption_look_grid.setEnabled(use and not locked)

    def _sync_caption_controls(self, *_args):
        on = bool(getattr(self, "chk_auto_captions", None) and self.chk_auto_captions.isChecked())
        for w in (
            getattr(self, "lbl_caption_y", None),
            getattr(self, "spin_caption_y", None),
            getattr(self, "chk_caption_fit", None),
            getattr(self, "chk_export_srt", None),
            getattr(self, "chk_caption_lock", None),
            getattr(self, "caption_motion_grid", None),
        ):
            if w is not None:
                w.setEnabled(on)
        timer = getattr(getattr(self, "caption_motion_grid", None), "_timer", None)
        if timer is not None and not on:
            timer.stop()
        self._sync_caption_lock()

    def _build_mix_page(self, defaults: dict) -> QWidget:
        page, lay = self._page()
        lay.addWidget(self._section_divider("Timing"))
        grid = self._grid(lay)

        self.combo_sync = self._combo()
        self.combo_sync.addItem("Smart tempo · 0.65×–1.85×", "stretch")
        self.combo_sync.addItem("Subtle tempo · 0.85×–1.25×", "subtle")
        self.combo_sync.addItem("Natural speed · 1.0×", "natural")
        self._set_data(self.combo_sync, defaults.get("sync_mode", "stretch"))
        grid.addWidget(self._label("Timing"), 0, 0)
        grid.addWidget(self.combo_sync, 0, 1)

        duck_row = QHBoxLayout()
        duck_row.setContentsMargins(0, 0, 0, 0)
        duck_row.setSpacing(10)
        duck_lbl = QLabel("Dialogue ducking")
        duck_lbl.setObjectName("asr_field_label")
        self.spin_duck = ScrubSpinBox()
        self.spin_duck.setRange(5, 50)
        self.spin_duck.setSuffix("%")
        try:
            self.spin_duck.setValue(int(defaults.get("background", 20)))
        except (TypeError, ValueError):
            self.spin_duck.setValue(20)
        duck_row.addWidget(duck_lbl, 1)
        duck_row.addWidget(self.spin_duck, 0, Qt.AlignmentFlag.AlignRight)
        grid.addLayout(duck_row, 1, 0, 1, 2)

        self.spin_center = self._spin_row(grid, 2, "Original speech fade", 0, 100, "%", defaults.get("center_attenuation", 70))
        self.spin_vo = self._spin_row(grid, 3, "New voice level", 80, 160, "%", defaults.get("voiceover_boost", 115))
        self.spin_fade = self._spin_row(grid, 4, "Ducking fade", 50, 350, " ms", defaults.get("fade_ms", 150))

        lay.addWidget(self._section_divider("Options"))
        opts = QVBoxLayout()
        opts.setContentsMargins(0, 0, 0, 0)
        opts.setSpacing(8)
        self.chk_auto_mix = self._option(
            opts, "Auto mix", "Duck only original speech; keep music & effects",
            bool(defaults.get("auto_mix", True)),
        )
        self.chk_vocal_master = self._option(
            opts, "Studio vocal chain", "Presence lift and peak limiter on new voices",
            bool(defaults.get("vocal_master", True)),
        )
        lay.addLayout(opts)
        lay.addStretch(1)
        return page

    def _build_engine_page(self, defaults: dict) -> QWidget:
        page, lay = self._page()
        lay.addWidget(self._section_divider("Engines"))
        grid = self._grid(lay)

        self.combo_model = self._combo()
        self.combo_model.addItems(list(ASREngine.MODELS))
        self._set_text(self.combo_model, defaults.get("asr_model", "whisper-small"))
        grid.addWidget(self._label("Speech"), 0, 0)
        grid.addWidget(self.combo_model, 0, 1)

        self.combo_translator = self._combo()
        for eid, label in TranslateEngine.ENGINES:
            self.combo_translator.addItem(label, eid)
        self._set_data(self.combo_translator, defaults.get("translator", "auto"))
        self.combo_translator.currentIndexChanged.connect(self._sync_ollama)
        grid.addWidget(self._label("Translate"), 1, 0)
        grid.addWidget(self.combo_translator, 1, 1)

        self.edit_ollama = QLineEdit()
        self.edit_ollama.setObjectName("start_localize_field")
        self.edit_ollama.setFixedHeight(30)
        self.edit_ollama.setPlaceholderText("qwen2.5:7b")
        self.edit_ollama.setText(str(defaults.get("ollama_model") or "qwen2.5:7b"))
        grid.addWidget(self._label("Ollama"), 2, 0)
        grid.addWidget(self.edit_ollama, 2, 1)
        self._sync_ollama()

        lay.addWidget(self._section_divider("Options"))
        opts = QVBoxLayout()
        opts.setContentsMargins(0, 0, 0, 0)
        opts.setSpacing(8)
        self.chk_gender_detect = self._option(
            opts,
            "Speaker gender assist",
            "Infer Female / Male cues from audio to speed up cast assignment",
            bool(defaults.get("gender_detect", True)),
        )
        lay.addLayout(opts)

        stem = QLabel(stem_status_label())
        stem.setObjectName("start_dub_sources_head")
        stem.setWordWrap(True)
        stem.setToolTip("Music / effects bed used when Auto mix is on (Mix tab).")
        lay.addWidget(stem)

        lay.addStretch(1)
        return page

    def _spin_row(self, grid: QGridLayout, row: int, title: str, low: int, high: int, suffix: str, value) -> ScrubSpinBox:
        lbl = QLabel(title)
        lbl.setObjectName("asr_field_label")
        spin = ScrubSpinBox()
        spin.setRange(low, high)
        spin.setSuffix(suffix)
        try:
            spin.setValue(int(value))
        except (TypeError, ValueError):
            spin.setValue(low)
        row_l = QHBoxLayout()
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.setSpacing(10)
        row_l.addWidget(lbl, 1)
        row_l.addWidget(spin, 0, Qt.AlignmentFlag.AlignRight)
        grid.addLayout(row_l, row, 0, 1, 2)
        return spin

    def _sync_ollama(self, *_args):
        eid = self.combo_translator.currentData() or "auto"
        self.edit_ollama.setEnabled(eid in {"auto", "ollama"})

    @staticmethod
    def _option(layout: QVBoxLayout, title: str, hint: str, checked: bool) -> QCheckBox:
        chk = QCheckBox(title)
        chk.setObjectName("dub_switch")
        chk.setCursor(Qt.CursorShape.PointingHandCursor)
        chk.setChecked(checked)
        if hint:
            chk.setToolTip(hint)
        layout.addWidget(chk)
        return chk

    def options(self) -> dict:
        batch_mode = "separate"
        if self._batch_group is not None and self.radio_merge.isChecked():
            batch_mode = "merge"
        return {
            "source_lang": self.combo_source.currentText(),
            "target_lang": self.combo_target.currentText(),
            "voice": self.combo_voice.currentData() or "",
            "secondary_voice": self.combo_voice_sec.currentData() or "",
            "asr_model": self.combo_model.currentText(),
            "translator": self.combo_translator.currentData() or "auto",
            "ollama_model": self.edit_ollama.text().strip() or "qwen2.5:7b",
            "sync_mode": self.combo_sync.currentData() or "stretch",
            "background": self.spin_duck.value(),
            "center_attenuation": self.spin_center.value(),
            "voiceover_boost": self.spin_vo.value(),
            "fade_ms": self.spin_fade.value(),
            "auto_chain": self.chk_auto_chain.isChecked(),
            "auto_captions": self.chk_auto_captions.isChecked(),
            "caption_look": self._caption_look_name(),
            "caption_lock": self.chk_caption_lock.isChecked(),
            "caption_anim": self._caption_anim_key(),
            "caption_fit": self.chk_caption_fit.isChecked(),
            "caption_y": self.spin_caption_y.value(),
            "export_srt": self.chk_export_srt.isChecked(),
            "gender_detect": self.chk_gender_detect.isChecked(),
            "auto_mix": self.chk_auto_mix.isChecked(),
            "vocal_master": self.chk_vocal_master.isChecked(),
            "batch_mode": batch_mode,
        }

    def _refill_voices(self, lang: str):
        voice_lang = "Chinese" if str(lang).startswith("Chinese") else lang
        voices = [v for v in TTSEngine.VOICE_PRESETS if v.get("lang") == voice_lang]
        if not voices:
            voices = list(TTSEngine.VOICE_PRESETS)

        keep_prim = self.combo_voice.currentData() or self._voice_prim
        keep_sec = self.combo_voice_sec.currentData() or self._voice_sec

        self.combo_voice.blockSignals(True)
        self.combo_voice_sec.blockSignals(True)
        self.combo_voice.clear()
        self.combo_voice_sec.clear()
        pick_prim = 0
        pick_sec = min(1, len(voices) - 1) if len(voices) > 1 else 0
        for i, voice in enumerate(voices):
            self.combo_voice.addItem(voice["name"], voice["id"])
            self.combo_voice_sec.addItem(voice["name"], voice["id"])
            if voice["id"] == keep_prim:
                pick_prim = i
            if voice["id"] == keep_sec:
                pick_sec = i
        if lang == "Khmer":
            for i, voice in enumerate(voices):
                if "Sreymom" in voice["name"] and not keep_prim:
                    pick_prim = i
                elif "Piseth" in voice["name"] and not keep_sec:
                    pick_sec = i
        self.combo_voice.setCurrentIndex(pick_prim)
        self.combo_voice_sec.setCurrentIndex(pick_sec)
        self.combo_voice.blockSignals(False)
        self.combo_voice_sec.blockSignals(False)

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("asr_field_label")
        return label

    @staticmethod
    def _set_text(combo: QComboBox, value: str):
        index = combo.findText(value or "")
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _set_data(combo: QComboBox, value):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

