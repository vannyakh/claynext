"""Confirm and configure options before starting a localization job."""
from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from claynext.models.asr_service import ASREngine
from claynext.models.features import stem_status_label
from claynext.models.text_style import CAPTION_ANIMS
from claynext.models.tts_service import TTSEngine
from claynext.models.translate_service import TranslateEngine
from claynext.gui.components.controls.scrub_spin import ScrubSpinBox
from claynext.gui.components.controls.tabs import SegmentTabs
from claynext.gui.components.ollama_model_selector import OllamaModelSelector
from claynext.gui.views.studio.captions import CAPTION_STYLES, CaptionLookGrid, CaptionMotionGrid
from claynext.gui.views.studio.constants import SOURCE_LANGS

# Quick / Tune / Captions — fewer clicks to Start.
_TAB_LABELS = ["Quick", "Tune", "Captions"]
_TAB_TIPS = [
    "Speed, languages, voices — start here",
    "Mix, timing, and AI line style",
    "Optional burned-in captions",
]

# Presets cut latency paths (stems / gender ML / slot-fit rewrite / heavy ASR).
_SPEED_PRESETS: dict[str, dict] = {
    "fast": {
        "label": "Fast",
        "tip": "Skip stems + gender ML · literal translate · small ASR",
        "asr_model": "whisper-small",
        "translator": "google",
        "translate_fit_duration": False,
        "translate_slang": False,
        "translate_expression": False,
        "gender_detect": False,
        "auto_mix": False,
        "vocal_master": False,
        "auto_captions": False,
        "auto_chain": True,
        "clone_voices": True,
    },
    "balanced": {
        "label": "Balanced",
        "tip": "Best everyday path · movie translate · stems when available",
        "asr_model": "whisper-small",
        "translator": "auto",
        "translate_fit_duration": True,
        "translate_slang": True,
        "translate_expression": True,
        "gender_detect": True,
        "auto_mix": True,
        "vocal_master": True,
        "auto_captions": True,
        "auto_chain": True,
        "clone_voices": True,
    },
    "best": {
        "label": "Best",
        "tip": "Large ASR · cinematic movie rewrite · full cast assist",
        "asr_model": "whisper-large-v3",
        "translator": "movie",
        "translate_fit_duration": True,
        "translate_slang": True,
        "translate_expression": True,
        "gender_detect": True,
        "auto_mix": True,
        "vocal_master": True,
        "auto_captions": True,
        "auto_chain": True,
        "clone_voices": True,
    },
}

# Slim engine list for Quick (NLLB still used inside Auto/Movie chain).
_QUICK_ENGINES = [
    ("auto", "Auto · best movie path"),
    ("movie", "Movie · cinematic"),
    ("gemini", "Gemini · API"),
    ("qwen", "Qwen · API"),
    ("deepseek", "DeepSeek · API"),
    ("groq", "Groq · API"),
    ("openrouter", "OpenRouter · API"),
    ("openai", "OpenAI · API"),
    ("mistral", "Mistral · API"),
    ("moonshot", "Moonshot · API"),
    ("glm", "GLM · API"),
    ("xai", "xAI · API"),
    ("ollama", "Ollama · local"),
    ("google", "Google · fast literal"),
]


class _CaptionWidthPin(QObject):
    """Keep the captions page exactly as wide as the dialog, so cards cannot slide off."""

    def __init__(self, scroll: QScrollArea, page: QWidget):
        super().__init__(scroll)
        self._scroll = scroll
        self._page = page

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            width = self._scroll.viewport().width()
            if width > 8 and self._page.maximumWidth() != width:
                self._page.setMinimumWidth(0)
                self._page.setMaximumWidth(width)
            bar = self._scroll.horizontalScrollBar()
            if bar.value():
                bar.setValue(0)
        return False


class StartLocalizeDialog(QDialog):
    """Fast-start localization confirm — presets first, details on Tune/Captions."""

    def __init__(self, parent=None, *, sources: list[str], defaults: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Start Localization")
        self.setObjectName("startLocalizeDialog")
        self.setMinimumWidth(480)
        self.setMinimumHeight(360)
        self._fit_to_screen()
        self.setModal(True)
        self._sources = [p for p in (sources or []) if p and os.path.isfile(p)]
        self._defaults = dict(defaults or {})
        self._captions_built = False
        self._applying_preset = False
        self._speed = str(self._defaults.get("speed_preset") or "balanced")
        if self._speed not in _SPEED_PRESETS:
            self._speed = "balanced"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        n = len(self._sources)
        chrome = QFrame()
        chrome.setObjectName("start_dub_chrome")
        chrome.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        chrome_l = QVBoxLayout(chrome)
        chrome_l.setContentsMargins(10, 6, 10, 6)
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
        body_l.setContentsMargins(14, 10, 14, 12)
        body_l.setSpacing(8)

        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.stack.addWidget(self._scroll_page(self._build_quick_page(self._defaults)))
        self.stack.addWidget(self._scroll_page(self._build_tune_page(self._defaults)))
        # Lazy captions page — heavy look grids only when opened.
        self._captions_placeholder = QWidget()
        self.stack.addWidget(self._captions_placeholder)
        body_l.addWidget(self.stack, 1)

        self._batch_group: QButtonGroup | None = None
        if n >= 2:
            body_l.addWidget(self._build_batch_box(self._defaults, n))

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 2, 0, 0)
        actions.setSpacing(8)
        self.lbl_path = QLabel("")
        self.lbl_path.setObjectName("start_dub_sources_head")
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setMaximumHeight(36)
        actions.addWidget(self.lbl_path, 1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("start_localize_btn")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setFixedHeight(28)
        cancel.setMinimumWidth(84)
        cancel.clicked.connect(self.reject)
        self.btn_start = QPushButton(
            "Start" if n <= 1 else f"Start · {n}"
        )
        self.btn_start.setObjectName("start_localize_btn_primary")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setFixedHeight(28)
        self.btn_start.setMinimumWidth(112)
        self.btn_start.setDefault(True)
        self.btn_start.setEnabled(n > 0)
        self.btn_start.clicked.connect(self._accept_if_ready)
        actions.addWidget(cancel)
        actions.addWidget(self.btn_start)
        body_l.addLayout(actions)
        root.addWidget(body, 1)

        self._voice_prim = self._defaults.get("voice", "")
        self._voice_sec = self._defaults.get("secondary_voice", "")
        self._refill_voices(self.combo_target.currentText())
        self._apply_speed_preset(self._speed, force=True)
        self._sync_ollama(defer_refresh=True)
        self._update_path_hint()

    def _fit_to_screen(self):
        """Use the space under the menu bar, and let the form scroll when it is shorter."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(520, 560)
            return
        avail = screen.availableGeometry()
        width = min(560, max(500, int(avail.width() * 0.42)))
        height = min(820, max(440, int(avail.height() * 0.84)))
        self.resize(width, height)
        self.setMaximumHeight(max(self.minimumHeight(), avail.height() - 32))

    def _scroll_page(self, page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("start_dub_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        scroll.setWidget(page)
        return scroll

    def _accept_if_ready(self):
        from claynext.gui.dialogs.env_alert import ensure_job_environment

        voice = str(self.combo_voice.currentData() or "")
        if not voice:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "No voice", "Choose a lead TTS voice first.")
            return
        asr_model = str(self.combo_model.currentText() or "") if hasattr(self, "combo_model") else ""
        if not ensure_job_environment(
            self,
            voice_id=voice,
            secondary_voice_id=str(self.combo_voice_sec.currentData() or ""),
            asr_model=asr_model or None,
            title="Download environment",
        ):
            return
        self.accept()

    def _show_tab(self, index: int):
        idx = max(0, int(index))
        if idx == 2:
            self._ensure_captions_page()
        self.stack.setCurrentIndex(idx)

    def _ensure_captions_page(self):
        if self._captions_built:
            return
        page = self._build_captions_page(self._defaults)
        self.stack.removeWidget(self._captions_placeholder)
        self._captions_placeholder.deleteLater()
        self.stack.insertWidget(2, page)
        self._captions_built = True
        self._sync_caption_controls()

    def _build_batch_box(self, defaults: dict, n: int) -> QWidget:
        box = QFrame()
        box.setObjectName("start_dub_batch")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        head = QLabel(f"Batch · {n} episodes")
        head.setObjectName("start_dub_sources_head")
        lay.addWidget(head)
        self.radio_separate = QRadioButton("Dedicated jobs")
        self.radio_separate.setObjectName("dub_switch")
        self.radio_merge = QRadioButton("Merge to one movie")
        self.radio_merge.setObjectName("dub_switch")
        self._batch_group = QButtonGroup(self)
        self._batch_group.addButton(self.radio_separate)
        self._batch_group.addButton(self.radio_merge)
        if str(defaults.get("batch_mode") or "separate") == "merge":
            self.radio_merge.setChecked(True)
        else:
            self.radio_separate.setChecked(True)
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(self.radio_separate)
        row.addWidget(self.radio_merge)
        row.addStretch(1)
        lay.addLayout(row)
        return box

    def _page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("start_dub_tab_page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 4, 2, 2)
        lay.setSpacing(8)
        return page, lay

    def _grid(self, parent_lay: QVBoxLayout) -> QGridLayout:
        box = QFrame()
        box.setObjectName("dub_config_section")
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        parent_lay.addWidget(box)
        return grid

    def _combo(self) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName("start_localize_combo")
        combo.setFixedHeight(28)
        return combo

    def _spin(self) -> ScrubSpinBox:
        spin = ScrubSpinBox()
        spin.setFixedHeight(28)
        return spin

    def _section_divider(self, title: str) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("start_localize_divider")
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 4, 0, 2)
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

    def _build_quick_page(self, defaults: dict) -> QWidget:
        page, lay = self._page()

        lay.addWidget(self._section_divider("Speed"))
        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)
        self._speed_group = QButtonGroup(self)
        self._speed_group.setExclusive(True)
        for key, meta in _SPEED_PRESETS.items():
            btn = QPushButton(meta["label"])
            btn.setObjectName("start_localize_preset")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(30)
            btn.setToolTip(meta["tip"])
            btn.setProperty("preset", key)
            btn.clicked.connect(lambda _=False, k=key: self._on_speed_clicked(k))
            self._speed_group.addButton(btn)
            preset_row.addWidget(btn, 1)
            if key == self._speed:
                btn.setChecked(True)
        lay.addLayout(preset_row)
        self.lbl_speed_tip = QLabel(_SPEED_PRESETS[self._speed]["tip"])
        self.lbl_speed_tip.setObjectName("start_dub_sources_head")
        self.lbl_speed_tip.setWordWrap(True)
        lay.addWidget(self.lbl_speed_tip)

        lay.addWidget(self._section_divider("Languages & cast"))
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

        lay.addWidget(self._section_divider("Engine"))
        api = self._grid(lay)
        self.combo_translator = self._combo()
        for eid, label in _QUICK_ENGINES:
            self.combo_translator.addItem(label, eid)
        # Map full catalog ids (e.g. nllb) onto closest quick choice.
        tr = str(defaults.get("translator") or "auto")
        if tr == "nllb":
            tr = "auto"
        self._set_data(self.combo_translator, tr)
        self.combo_translator.currentIndexChanged.connect(self._on_translator_changed)
        api.addWidget(self._label("Translate"), 0, 0)
        api.addWidget(self.combo_translator, 0, 1)

        self.edit_ollama = OllamaModelSelector(
            self, default_model=str(defaults.get("ollama_model") or "qwen3:8b")
        )
        # Avoid blocking UI with Ollama ping until local engine is chosen.
        if hasattr(self.edit_ollama, "check_and_refresh"):
            # Selector auto-checks in __init__; stop if Fast/Google won't need it.
            pass
        api.addWidget(self._label("Ollama"), 1, 0)
        api.addWidget(self.edit_ollama, 1, 1)

        opts = QVBoxLayout()
        opts.setSpacing(6)
        self.chk_auto_captions = self._option(
            opts,
            "Captions on finish",
            "Generate burned-in captions after dub. Turn off for a faster job.",
            bool(defaults.get("auto_captions", True)),
        )
        self.chk_clone_voices = self._option(
            opts,
            "Clone character voices",
            "After cast detection, extract each speaker and use that clone for TTS.",
            bool(defaults.get("clone_voices", True)),
        )
        self.chk_auto_captions.toggled.connect(self._update_path_hint)
        self.chk_clone_voices.toggled.connect(self._update_path_hint)
        lay.addLayout(opts)
        lay.addStretch(1)
        return page

    def _build_tune_page(self, defaults: dict) -> QWidget:
        page, lay = self._page()

        lay.addWidget(self._section_divider("Speech & cast"))
        api = self._grid(lay)
        self.combo_model = self._combo()
        self.combo_model.addItems(list(ASREngine.MODELS))
        self._set_text(self.combo_model, defaults.get("asr_model", "whisper-small"))
        self.combo_model.currentTextChanged.connect(lambda _=None: self._update_path_hint())
        api.addWidget(self._label("ASR"), 0, 0)
        api.addWidget(self.combo_model, 0, 1)

        cast_opts = QVBoxLayout()
        cast_opts.setSpacing(6)
        self.chk_auto_chain = self._option(
            cast_opts,
            "Character chain",
            "Cast → translate → speak with lead & co-star",
            bool(defaults.get("auto_chain", True)),
        )
        self.chk_gender_detect = self._option(
            cast_opts,
            "Gender / cast assist",
            "Audio gender + AI naming. Off = faster (skip ML cast).",
            bool(defaults.get("gender_detect", True)),
        )
        self.chk_gender_detect.toggled.connect(self._update_path_hint)
        lay.addLayout(cast_opts)

        lay.addWidget(self._section_divider("AI line style"))
        style = QVBoxLayout()
        style.setSpacing(6)
        self.chk_translate_fit = self._option(
            style,
            "Fit words to the segment",
            "Extra rewrite pass for lines that overrun the slot (uses API).",
            bool(defaults.get("translate_fit_duration", True)),
        )
        self.chk_translate_slang = self._option(
            style,
            "Slang and idioms",
            "Natural spoken meaning, not word-for-word idioms",
            bool(defaults.get("translate_slang", True)),
        )
        self.chk_translate_expression = self._option(
            style,
            "Expression tags",
            "Allow [laugh] [sigh] cues for TTS timing",
            bool(defaults.get("translate_expression", True)),
        )
        for w in (self.chk_translate_fit, self.chk_translate_slang, self.chk_translate_expression):
            w.toggled.connect(self._update_path_hint)
        lay.addLayout(style)

        lay.addWidget(self._section_divider("Mix"))
        edit = self._grid(lay)
        duck_row = QHBoxLayout()
        duck_row.setSpacing(10)
        duck_lbl = QLabel("Dialogue ducking")
        duck_lbl.setObjectName("asr_field_label")
        self.spin_duck = self._spin()
        self.spin_duck.setRange(0, 100)
        self.spin_duck.setSuffix("%")
        try:
            self.spin_duck.setValue(int(defaults.get("background", 0)))
        except (TypeError, ValueError):
            self.spin_duck.setValue(0)
        duck_row.addWidget(duck_lbl, 1)
        duck_row.addWidget(self.spin_duck, 0, Qt.AlignmentFlag.AlignRight)
        edit.addLayout(duck_row, 0, 0, 1, 2)
        self.spin_center = self._spin_row(
            edit, 1, "Original speech fade", 0, 100, "%", defaults.get("center_attenuation", 70)
        )
        self.spin_fade = self._spin_row(
            edit, 2, "Ducking fade", 50, 350, " ms", defaults.get("fade_ms", 150)
        )

        mix_opts = QVBoxLayout()
        mix_opts.setSpacing(6)
        self.chk_auto_mix = self._option(
            mix_opts,
            "Isolate music / effects bed",
            "Demucs stems — slower, cleaner bed. Off skips separation (big speed win).",
            bool(defaults.get("auto_mix", True)),
        )
        self.chk_auto_mix.toggled.connect(self._update_path_hint)
        lay.addLayout(mix_opts)
        stem = QLabel(stem_status_label())
        stem.setObjectName("start_dub_sources_head")
        stem.setWordWrap(True)
        lay.addWidget(stem)

        lay.addWidget(self._section_divider("TTS"))
        voice = self._grid(lay)
        self.combo_sync = self._combo()
        self.combo_sync.addItem("Smart tempo · 0.65×–1.85×", "stretch")
        self.combo_sync.addItem("Subtle tempo · 0.85×–1.25×", "subtle")
        self.combo_sync.addItem("Natural speed · 1.0×", "natural")
        self._set_data(self.combo_sync, defaults.get("sync_mode", "stretch"))
        voice.addWidget(self._label("Timing"), 0, 0)
        voice.addWidget(self.combo_sync, 0, 1)
        self.spin_vo = self._spin_row(
            voice, 1, "New voice level", 80, 160, "%", defaults.get("voiceover_boost", 115)
        )
        voice_opts = QVBoxLayout()
        voice_opts.setSpacing(6)
        self.chk_vocal_master = self._option(
            voice_opts,
            "Improve voice",
            "Presence lift + peak limiter on TTS",
            bool(defaults.get("vocal_master", True)),
        )
        lay.addLayout(voice_opts)
        lay.addStretch(1)
        return page

    def _build_captions_page(self, defaults: dict) -> QWidget:
        page, lay = self._page()
        page.setMinimumWidth(0)
        lay.setSpacing(6)
        tip = QLabel("Optional. Leave off on Fast for a quicker job.")
        tip.setObjectName("start_dub_sources_head")
        tip.setWordWrap(True)
        tip.setMinimumWidth(0)
        lay.addWidget(tip)

        lay.addWidget(self._section_divider("Place"))
        place = QHBoxLayout()
        place.setSpacing(6)
        self._place_group = QButtonGroup(self)
        self._place_group.setExclusive(True)
        self._place_buttons: list[QPushButton] = []
        for label, y in (("Bottom", 86), ("Center", 50), ("Top", 12)):
            btn = QPushButton(label)
            btn.setObjectName("start_localize_preset")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.setProperty("place_y", y)
            btn.setToolTip(f"Place captions at {y}% from the top")
            btn.clicked.connect(lambda _=False, value=y: self.spin_caption_y.setValue(value))
            self._place_group.addButton(btn)
            self._place_buttons.append(btn)
            place.addWidget(btn, 1)
        self.spin_caption_y = self._spin()
        self.spin_caption_y.setRange(8, 95)
        self.spin_caption_y.setSuffix("%")
        self.spin_caption_y.setFixedWidth(78)
        try:
            self.spin_caption_y.setValue(int(defaults.get("caption_y", 86)))
        except (TypeError, ValueError):
            self.spin_caption_y.setValue(86)
        self.spin_caption_y.valueChanged.connect(self._sync_caption_place)
        place.addWidget(self.spin_caption_y)
        lay.addLayout(place)
        self._sync_caption_place(self.spin_caption_y.value())

        checks = QHBoxLayout()
        checks.setSpacing(14)
        self.chk_caption_fit = self._option(
            checks,
            "Safe-area fit",
            "Keep captions inside title-safe width",
            bool(defaults.get("caption_fit", True)),
        )
        self.chk_export_srt = self._option(
            checks,
            "Export SRT",
            "Write a sidecar .srt next to the output",
            bool(defaults.get("export_srt", False)),
        )
        checks.addStretch(1)
        lay.addLayout(checks)

        head = QHBoxLayout()
        head.addWidget(self._section_divider("Look"), 1)
        self.chk_caption_lock = QCheckBox("Lock")
        self.chk_caption_lock.setObjectName("dub_switch")
        self.chk_caption_lock.setToolTip("Keep the current look when this job starts")
        self.chk_caption_lock.setChecked(bool(defaults.get("caption_lock", False)))
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

        scroll = QScrollArea()
        scroll.setObjectName("start_dub_captions")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(page)
        scroll.viewport().installEventFilter(_CaptionWidthPin(scroll, page))
        return scroll

    def _on_speed_clicked(self, key: str):
        self._apply_speed_preset(key, force=True)

    def _apply_speed_preset(self, key: str, *, force: bool = False):
        meta = _SPEED_PRESETS.get(key) or _SPEED_PRESETS["balanced"]
        self._speed = key
        self._applying_preset = True
        try:
            for btn in self._speed_group.buttons():
                btn.setChecked(btn.property("preset") == key)
            if hasattr(self, "lbl_speed_tip"):
                self.lbl_speed_tip.setText(meta["tip"])
            if force or True:
                self._set_text(self.combo_model, meta["asr_model"])
                self._set_data(self.combo_translator, meta["translator"])
                self.chk_translate_fit.setChecked(bool(meta["translate_fit_duration"]))
                self.chk_translate_slang.setChecked(bool(meta["translate_slang"]))
                self.chk_translate_expression.setChecked(bool(meta["translate_expression"]))
                self.chk_gender_detect.setChecked(bool(meta["gender_detect"]))
                self.chk_auto_mix.setChecked(bool(meta["auto_mix"]))
                self.chk_vocal_master.setChecked(bool(meta["vocal_master"]))
                self.chk_auto_captions.setChecked(bool(meta["auto_captions"]))
                self.chk_auto_chain.setChecked(bool(meta["auto_chain"]))
                if hasattr(self, "chk_clone_voices"):
                    self.chk_clone_voices.setChecked(bool(meta.get("clone_voices", True)))
        finally:
            self._applying_preset = False
        self._sync_ollama(defer_refresh=key == "fast")
        self._sync_translate_style()
        self._update_path_hint()

    def _on_translator_changed(self, *_args):
        if not self._applying_preset:
            # Manual engine pick → leave speed label but refresh ollama/path.
            self._sync_ollama(defer_refresh=False)
            self._sync_translate_style()
            self._update_path_hint()

    def _update_path_hint(self, *_args):
        skips = []
        if hasattr(self, "chk_auto_mix") and not self.chk_auto_mix.isChecked():
            skips.append("stems")
        if hasattr(self, "chk_gender_detect") and not self.chk_gender_detect.isChecked():
            skips.append("cast ML")
        if hasattr(self, "chk_translate_fit") and not self.chk_translate_fit.isChecked():
            skips.append("slot-fit API")
        if hasattr(self, "chk_auto_captions") and not self.chk_auto_captions.isChecked():
            skips.append("captions")
        tr = self.combo_translator.currentData() if hasattr(self, "combo_translator") else "auto"
        asr = self.combo_model.currentText() if hasattr(self, "combo_model") else ""
        bits = [f"{_SPEED_PRESETS.get(self._speed, {}).get('label', 'Custom')} path"]
        if asr:
            bits.append(asr.replace("whisper-", ""))
        if tr:
            bits.append(str(tr))
        if hasattr(self, "chk_clone_voices") and self.chk_clone_voices.isChecked():
            bits.append("clone TTS")
        if skips:
            bits.append("skip " + " · ".join(skips))
        self.lbl_path.setText(" · ".join(bits))

    def _caption_look_name(self) -> str:
        if not self._captions_built:
            return str(self._defaults.get("caption_look") or "")
        idx = self.caption_look_grid.current() if hasattr(self, "caption_look_grid") else 0
        if 0 <= idx < len(CAPTION_STYLES):
            return str(CAPTION_STYLES[idx].get("name") or "")
        return ""

    def _caption_anim_key(self) -> str:
        if not self._captions_built:
            return str(self._defaults.get("caption_anim") or "none")
        idx = self.caption_motion_grid.current() if hasattr(self, "caption_motion_grid") else 0
        if 0 <= idx < len(CAPTION_ANIMS):
            return CAPTION_ANIMS[idx][0]
        return "none"

    def _sync_caption_place(self, value: int):
        group = getattr(self, "_place_group", None)
        if group is None:
            return
        group.setExclusive(False)
        for btn in group.buttons():
            target = int(btn.property("place_y") or 0)
            btn.setChecked(abs(target - int(value)) <= 3)
        group.setExclusive(True)

    def _sync_caption_lock(self, *_args):
        locked = bool(getattr(self, "chk_caption_lock", None) and self.chk_caption_lock.isChecked())
        use = bool(getattr(self, "chk_auto_captions", None) and self.chk_auto_captions.isChecked())
        if hasattr(self, "caption_look_grid"):
            self.caption_look_grid.setEnabled(use and not locked)

    def _sync_caption_controls(self, *_args):
        if not self._captions_built:
            return
        on = bool(getattr(self, "chk_auto_captions", None) and self.chk_auto_captions.isChecked())
        for w in (
            getattr(self, "spin_caption_y", None),
            getattr(self, "chk_caption_fit", None),
            getattr(self, "chk_export_srt", None),
            getattr(self, "chk_caption_lock", None),
            getattr(self, "caption_motion_grid", None),
            *list(getattr(self, "_place_buttons", None) or []),
        ):
            if w is not None:
                w.setEnabled(on)
        timer = getattr(getattr(self, "caption_motion_grid", None), "_timer", None)
        if timer is not None and not on:
            timer.stop()
        self._sync_caption_lock()

    def _spin_row(
        self, grid: QGridLayout, row: int, title: str, low: int, high: int, suffix: str, value
    ) -> ScrubSpinBox:
        lbl = QLabel(title)
        lbl.setObjectName("asr_field_label")
        spin = self._spin()
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

    def _sync_ollama(self, *_args, defer_refresh: bool = False):
        eid = self.combo_translator.currentData() or "auto"
        is_ollama = eid in {"auto", "movie", "ollama"}
        self.edit_ollama.setEnabled(is_ollama)
        if is_ollama and not defer_refresh and hasattr(self.edit_ollama, "check_and_refresh"):
            self.edit_ollama.check_and_refresh()

    def _sync_translate_style(self, *_args):
        eid = self.combo_translator.currentData() or "auto"
        from claynext.models.llm_providers import CHAT_PROVIDERS

        llm = eid in {"auto", "movie", "gemini", "ollama", *CHAT_PROVIDERS}
        for name in ("chk_translate_fit", "chk_translate_slang", "chk_translate_expression"):
            w = getattr(self, name, None)
            if w is not None:
                w.setEnabled(llm)

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
        # Picture FX kept from defaults (removed from dialog UI).
        return {
            "speed_preset": self._speed,
            "source_lang": self.combo_source.currentText(),
            "target_lang": self.combo_target.currentText(),
            "voice": self.combo_voice.currentData() or "",
            "secondary_voice": self.combo_voice_sec.currentData() or "",
            "asr_model": self.combo_model.currentText(),
            "translator": self.combo_translator.currentData() or "auto",
            "ollama_model": self.edit_ollama.text().strip() or "qwen3:8b",
            "sync_mode": self.combo_sync.currentData() or "stretch",
            "background": self.spin_duck.value(),
            "center_attenuation": self.spin_center.value(),
            "voiceover_boost": self.spin_vo.value(),
            "fade_ms": self.spin_fade.value(),
            "auto_chain": self.chk_auto_chain.isChecked(),
            "auto_captions": self.chk_auto_captions.isChecked(),
            "caption_look": self._caption_look_name(),
            "caption_lock": bool(
                getattr(self, "chk_caption_lock", None) and self.chk_caption_lock.isChecked()
            )
            if self._captions_built
            else bool(self._defaults.get("caption_lock", False)),
            "caption_anim": self._caption_anim_key(),
            "caption_fit": bool(
                getattr(self, "chk_caption_fit", None) and self.chk_caption_fit.isChecked()
            )
            if self._captions_built
            else bool(self._defaults.get("caption_fit", True)),
            "caption_y": int(self.spin_caption_y.value())
            if self._captions_built and hasattr(self, "spin_caption_y")
            else int(self._defaults.get("caption_y", 86) or 86),
            "picture_effect": str(self._defaults.get("picture_effect") or "none"),
            "picture_filter": str(self._defaults.get("picture_filter") or "clean"),
            "picture_transition": str(self._defaults.get("picture_transition") or "none"),
            "export_srt": bool(
                getattr(self, "chk_export_srt", None) and self.chk_export_srt.isChecked()
            )
            if self._captions_built
            else bool(self._defaults.get("export_srt", False)),
            "gender_detect": self.chk_gender_detect.isChecked(),
            "translate_fit_duration": self.chk_translate_fit.isChecked(),
            "translate_slang": self.chk_translate_slang.isChecked(),
            "translate_expression": self.chk_translate_expression.isChecked(),
            "auto_mix": self.chk_auto_mix.isChecked(),
            "vocal_master": self.chk_vocal_master.isChecked(),
            "clone_voices": bool(
                getattr(self, "chk_clone_voices", None) and self.chk_clone_voices.isChecked()
            ),
            "batch_mode": batch_mode,
        }

    def _refill_voices(self, lang: str):
        voices = TTSEngine.list_voices(lang)
        keep_prim = self.combo_voice.currentData() or self._voice_prim
        keep_sec = self.combo_voice_sec.currentData() or self._voice_sec
        self.combo_voice.blockSignals(True)
        self.combo_voice_sec.blockSignals(True)
        self.combo_voice.clear()
        self.combo_voice_sec.clear()
        pick_prim = 0
        pick_sec = min(1, len(voices) - 1) if len(voices) > 1 else 0
        for i, voice in enumerate(voices):
            label = voice["name"]
            self.combo_voice.addItem(label, voice["id"])
            self.combo_voice_sec.addItem(label, voice["id"])
            if voice["id"] == keep_prim:
                pick_prim = i
            if voice["id"] == keep_sec:
                pick_sec = i
        if lang == "Khmer":
            for i, voice in enumerate(voices):
                if voice["name"] == "Sreymom" and not keep_prim:
                    pick_prim = i
                elif voice["name"] == "Piseth" and not keep_sec:
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
