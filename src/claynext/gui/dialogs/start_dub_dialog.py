"""Confirm and configure options before starting a dubbing job."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QStackedWidget, QVBoxLayout, QWidget,
)

from claynext.models.asr_service import ASREngine
from claynext.models.tts_service import TTSEngine
from claynext.models.translate_service import TranslateEngine
from claynext.gui.components.scrub_spin import ScrubSpinBox
from claynext.gui.components.segment_tabs import SegmentTabs
from claynext.gui.views.studio.constants import SOURCE_LANGS


class StartDubDialog(QDialog):
    """Review the selected movies and tweak dub settings before the job runs."""

    def __init__(self, parent=None, *, sources: list[str], defaults: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Start Dubbing")
        self.setObjectName("startDubDialog")
        self.setMinimumWidth(520)
        self.setMinimumHeight(420)
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
        chrome_l.setContentsMargins(12, 8, 12, 0)
        chrome_l.setSpacing(0)
        self.tabs = SegmentTabs(
            ["Cast", "Mix", "Engine"],
            variant="chrome",
            tips=["Languages & voices", "Timing & mix", "Speech & translation"],
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
        self.stack.addWidget(self._build_engine_page(defaults))
        body_l.addWidget(self.stack, 1)

        self._batch_group: QButtonGroup | None = None
        if n >= 2:
            body_l.addWidget(self._build_batch_box(defaults, n))

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("api_keys_btn")
        cancel.clicked.connect(self.reject)
        self.btn_start = QPushButton("Start Dubbing" if n <= 1 else f"Start Dubbing · {n}")
        self.btn_start.setObjectName("api_keys_btn_primary")
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
            "Dub each episode as its own task and script. Best when episodes stay separate."
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
        lay.setContentsMargins(2, 10, 2, 4)
        lay.setSpacing(12)
        return page, lay

    def _grid(self, parent_lay: QVBoxLayout) -> QGridLayout:
        box = QFrame()
        box.setObjectName("dub_config_section")
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 4, 0, 4)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        parent_lay.addWidget(box)
        return grid

    def _build_cast_page(self, defaults: dict) -> QWidget:
        page, lay = self._page()
        grid = self._grid(lay)

        self.combo_source = QComboBox()
        self.combo_source.setObjectName("asr_option_combo")
        self.combo_source.addItems(list(SOURCE_LANGS))
        self._set_text(self.combo_source, defaults.get("source_lang", "Chinese"))
        grid.addWidget(self._label("Source"), 0, 0)
        grid.addWidget(self.combo_source, 0, 1)

        self.combo_target = QComboBox()
        self.combo_target.setObjectName("asr_option_combo")
        self.combo_target.addItems(list(TranslateEngine.TARGET_LANGUAGES))
        self._set_text(self.combo_target, defaults.get("target_lang", "Khmer"))
        self.combo_target.currentTextChanged.connect(self._refill_voices)
        grid.addWidget(self._label("Target"), 1, 0)
        grid.addWidget(self.combo_target, 1, 1)

        self.combo_voice = QComboBox()
        self.combo_voice.setObjectName("asr_option_combo")
        grid.addWidget(self._label("Lead voice"), 2, 0)
        grid.addWidget(self.combo_voice, 2, 1)

        self.combo_voice_sec = QComboBox()
        self.combo_voice_sec.setObjectName("asr_option_combo")
        grid.addWidget(self._label("Co-star"), 3, 0)
        grid.addWidget(self.combo_voice_sec, 3, 1)

        opts = QVBoxLayout()
        opts.setContentsMargins(0, 4, 0, 0)
        opts.setSpacing(10)
        self.chk_auto_chain = self._option(
            opts, "Character chain", "Cast → translate → speak with lead & co-star",
            bool(defaults.get("auto_chain", True)),
        )
        self.chk_auto_captions = self._option(
            opts, "Auto captions", "Add caption clips when the dub finishes",
            bool(defaults.get("auto_captions", True)),
        )
        lay.addLayout(opts)
        lay.addStretch(1)
        return page

    def _build_mix_page(self, defaults: dict) -> QWidget:
        page, lay = self._page()
        grid = self._grid(lay)

        self.combo_sync = QComboBox()
        self.combo_sync.setObjectName("asr_option_combo")
        self.combo_sync.addItem("Smart tempo · 0.65×–1.85×", "stretch")
        self.combo_sync.addItem("Subtle tempo · 0.85×–1.25×", "subtle")
        self.combo_sync.addItem("Natural speed · 1.0×", "natural")
        self._set_data(self.combo_sync, defaults.get("sync_mode", "stretch"))
        grid.addWidget(self._label("Timing"), 0, 0)
        grid.addWidget(self.combo_sync, 0, 1)

        duck_row = QHBoxLayout()
        duck_row.setContentsMargins(0, 2, 0, 2)
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

        opts = QVBoxLayout()
        opts.setContentsMargins(0, 4, 0, 0)
        opts.setSpacing(10)
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
        grid = self._grid(lay)

        self.combo_model = QComboBox()
        self.combo_model.setObjectName("asr_option_combo")
        self.combo_model.addItems(list(ASREngine.MODELS))
        self._set_text(self.combo_model, defaults.get("asr_model", "whisper-small"))
        grid.addWidget(self._label("Speech"), 0, 0)
        grid.addWidget(self.combo_model, 0, 1)

        self.combo_translator = QComboBox()
        self.combo_translator.setObjectName("asr_option_combo")
        for eid, label in TranslateEngine.ENGINES:
            self.combo_translator.addItem(label, eid)
        self._set_data(self.combo_translator, defaults.get("translator", "auto"))
        self.combo_translator.currentIndexChanged.connect(self._sync_ollama)
        grid.addWidget(self._label("Translate"), 1, 0)
        grid.addWidget(self.combo_translator, 1, 1)

        self.edit_ollama = QLineEdit()
        self.edit_ollama.setObjectName("dub_setting_field")
        self.edit_ollama.setPlaceholderText("qwen2.5:7b")
        self.edit_ollama.setText(str(defaults.get("ollama_model") or "qwen2.5:7b"))
        grid.addWidget(self._label("Ollama"), 2, 0)
        grid.addWidget(self.edit_ollama, 2, 1)
        self._sync_ollama()

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

