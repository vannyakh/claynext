"""Hidden dub settings (config UI lives in StartLocalizeDialog)."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox,
    QFrame, QLineEdit, QCheckBox,
)

from claynext.models.asr_service import ASREngine
from claynext.models.thumbnails import VIDEO_EXTS
from claynext.models.translate_service import TranslateEngine
from claynext.models.tts_service import TTSEngine
from claynext.gui.components.scrub_spin import ScrubSpinBox
from claynext.gui.views.studio.constants import SOURCE_LANGS


class ConfigTools:
    """Persisted dub settings (hidden widgets for pipeline / project / start dialog)."""

    def _init_dub_settings(self):
        """Create store-backed widgets used by pipeline / project / start dialog."""
        if getattr(self, "_dub_settings_ready", False):
            return
        self._dub_settings_host = QWidget(self)
        self._dub_settings_host.hide()
        host = self._dub_settings_host

        self.combo_source_lang = QComboBox(host)
        self.combo_source_lang.addItems(list(SOURCE_LANGS))
        saved_src = self.store.get_setting("dub", "source_language", "Chinese")
        if saved_src in SOURCE_LANGS:
            self.combo_source_lang.setCurrentText(saved_src)
        self.combo_source_lang.currentTextChanged.connect(
            lambda val: self.store.set_setting("dub", "source_language", val)
        )

        self.combo_lang = QComboBox(host)
        self.combo_lang.addItems(list(TranslateEngine.TARGET_LANGUAGES))
        saved_lang = self.store.get_setting("dub", "language", "Khmer")
        if saved_lang in TranslateEngine.TARGET_LANGUAGES:
            self.combo_lang.setCurrentText(saved_lang)
        self.combo_lang.currentTextChanged.connect(self._on_lang_changed)

        self.combo_voice = QComboBox(host)
        self.combo_voice_sec = QComboBox(host)
        self.combo_voice.currentIndexChanged.connect(self._save_voice)
        self.combo_voice_sec.currentIndexChanged.connect(self._save_voice_sec)

        self.chk_auto_chain = self._hidden_switch(host, "auto_chain", True)
        self.chk_auto_captions = self._hidden_switch(host, "auto_captions", True)
        self.chk_auto_mix = self._hidden_switch(host, "auto_mix", True)
        self.chk_vocal_master = self._hidden_switch(host, "vocal_master", True)

        self.slider_duck = ScrubSpinBox(host)
        self.slider_duck.setRange(5, 50)
        self.slider_duck.setSuffix("%")
        try:
            self.slider_duck.setValue(int(self.store.get_setting("dub", "background", "20")))
        except ValueError:
            self.slider_duck.setValue(20)
        self.slider_duck.valueChanged.connect(self._on_duck_changed)

        self.combo_sync_mode = QComboBox(host)
        self.combo_sync_mode.addItem("Smart tempo · 0.65×–1.85×", "stretch")
        self.combo_sync_mode.addItem("Subtle tempo · 0.85×–1.25×", "subtle")
        self.combo_sync_mode.addItem("Natural speed · 1.0×", "natural")
        idx_sm = self.combo_sync_mode.findData(self.store.get_setting("dub", "sync_mode", "stretch"))
        if idx_sm >= 0:
            self.combo_sync_mode.setCurrentIndex(idx_sm)
        self.combo_sync_mode.currentIndexChanged.connect(
            lambda: self.store.set_setting(
                "dub", "sync_mode", self.combo_sync_mode.currentData() or "stretch"
            )
        )

        self.slider_center_att = self._hidden_spin(host, "center_attenuation", 70, 0, 100)
        self.slider_vo_boost = self._hidden_spin(host, "voiceover_boost", 115, 80, 160)
        self.slider_fade_ms = self._hidden_spin(host, "fade_ms", 150, 50, 350)

        self.combo_model = QComboBox(host)
        self.combo_model.addItems(list(ASREngine.MODELS))
        saved_model = self.store.get_setting("dub", "asr_model", "whisper-small")
        if saved_model in ASREngine.MODELS:
            self.combo_model.setCurrentText(saved_model)
        self.combo_model.currentTextChanged.connect(
            lambda val: self.store.set_setting("dub", "asr_model", val)
        )

        self.combo_translator = QComboBox(host)
        for eid, label in TranslateEngine.ENGINES:
            self.combo_translator.addItem(label, eid)
        idx_tr = self.combo_translator.findData(self.store.get_setting("dub", "translator", "auto"))
        if idx_tr >= 0:
            self.combo_translator.setCurrentIndex(idx_tr)
        self.combo_translator.currentIndexChanged.connect(self._on_translator_changed)

        self.edit_ollama = QLineEdit(host)
        self.edit_ollama.setText(self.store.get_setting("dub", "ollama_model", "qwen2.5:7b") or "qwen2.5:7b")
        self.edit_ollama.editingFinished.connect(
            lambda: self.store.set_setting(
                "dub", "ollama_model", self.edit_ollama.text().strip() or "qwen2.5:7b"
            )
        )
        self._sync_translator_fields()
        self._fill_voices(self.combo_lang.currentText())
        self._dub_settings_ready = True

    def _hidden_switch(self, host: QWidget, setting: str, default: bool) -> QCheckBox:
        chk = QCheckBox(host)
        chk.setChecked(self.store.get_setting("dub", setting, "1" if default else "0") == "1")
        chk.toggled.connect(
            lambda checked, key=setting: self.store.set_setting("dub", key, "1" if checked else "0")
        )
        return chk

    def _hidden_spin(self, host: QWidget, setting: str, default: int, low: int, high: int) -> ScrubSpinBox:
        spin = ScrubSpinBox(host)
        spin.setRange(low, high)
        try:
            spin.setValue(int(self.store.get_setting("dub", setting, str(default))))
        except ValueError:
            spin.setValue(default)
        spin.valueChanged.connect(lambda val, key=setting: self.store.set_setting("dub", key, str(val)))
        return spin

    def _dub_sources(self) -> list[str]:
        if not hasattr(self, "media_lib"):
            return []
        return [
            path for path in self.media_lib.selected_paths()
            if os.path.splitext(path)[1].lower() in VIDEO_EXTS and os.path.isfile(path)
        ]

    def _show_setup_page(self, index: int):
        return

    def _section(self, layout: QVBoxLayout, title: str) -> QVBoxLayout:
        """Purple section title — shared by Captions and other shelf panels."""
        box = QFrame()
        box.setObjectName("dub_config_section")
        box_lay = QVBoxLayout(box)
        box_lay.setContentsMargins(2, 6, 2, 4)
        box_lay.setSpacing(6)
        head = QLabel(title.upper())
        head.setObjectName("dub_config_header")
        box_lay.addWidget(head)
        layout.addWidget(box)
        return box_lay

    def _fill_voices(self, lang: str):
        saved_prim = self.store.get_setting("dub", "voice", "")
        saved_sec = self.store.get_setting("dub", "secondary_voice", "")
        voice_lang = "Chinese" if lang.startswith("Chinese") else lang

        self.combo_voice.blockSignals(True)
        self.combo_voice_sec.blockSignals(True)
        self.combo_voice.clear()
        self.combo_voice_sec.clear()

        voices = [v for v in TTSEngine.VOICE_PRESETS if v.get("lang") == voice_lang]
        if not voices:
            voices = TTSEngine.VOICE_PRESETS

        pick_prim = 0
        pick_sec = min(1, len(voices) - 1) if len(voices) > 1 else 0

        for i, v in enumerate(voices):
            self.combo_voice.addItem(v["name"], v["id"])
            self.combo_voice_sec.addItem(v["name"], v["id"])
            if v["id"] == saved_prim:
                pick_prim = i
            if v["id"] == saved_sec:
                pick_sec = i

        if lang == "Khmer":
            for i, v in enumerate(voices):
                if "Sreymom" in v["name"] and not saved_prim:
                    pick_prim = i
                elif "Piseth" in v["name"] and not saved_sec:
                    pick_sec = i

        self.combo_voice.setCurrentIndex(pick_prim)
        self.combo_voice_sec.setCurrentIndex(pick_sec)
        self.combo_voice.blockSignals(False)
        self.combo_voice_sec.blockSignals(False)

        if self.combo_voice.currentData():
            self.store.set_setting("dub", "voice", self.combo_voice.currentData())
        if self.combo_voice_sec.currentData():
            self.store.set_setting("dub", "secondary_voice", self.combo_voice_sec.currentData())

    def _save_voice(self, *_):
        vid = self.combo_voice.currentData()
        if vid:
            self.store.set_setting("dub", "voice", vid)

    def _save_voice_sec(self, *_):
        vid = self.combo_voice_sec.currentData()
        if vid:
            self.store.set_setting("dub", "secondary_voice", vid)

    def _on_lang_changed(self, lang: str):
        self.store.set_setting("dub", "language", lang)
        self._fill_voices(lang)
        if hasattr(self, "_refresh_voice_browser"):
            self._refresh_voice_browser()

    def _on_duck_changed(self, val: int):
        self.store.set_setting("dub", "background", str(val))
        if hasattr(self, "timeline"):
            self.timeline.duck_level = val / 100.0

    def _on_translator_changed(self):
        eid = self.combo_translator.currentData() or "auto"
        self.store.set_setting("dub", "translator", eid)
        self._sync_translator_fields()

    def _sync_translator_fields(self):
        eid = self.combo_translator.currentData() or "auto"
        self.edit_ollama.setEnabled(eid in {"auto", "ollama"})

