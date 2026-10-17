"""Voice browser: preview a sample and keep favorite voices."""
from __future__ import annotations

import hashlib
import json
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QScrollArea, QFrame, QToolButton, QSizePolicy, QStackedWidget,
)

from claynext.gui.components.spinner import Spinner

from claynext.gui.icons import icon
from claynext.models.tts_service import TTSEngine
from claynext.gui.worker import Worker
from claynext.gui.views.studio.constants import VOICE_SAMPLE_FALLBACK, VOICE_SAMPLES
from claynext.utils.config import CACHE_DIR


_VOICE_ORDERS = (
    ("favorite", "Favorites"),
    ("name", "Name"),
    ("gender", "Gender"),
    ("language", "Language"),
    ("engine", "Engine"),
)


def _voice_gender(voice: dict) -> str:
    gender = str(voice.get("gender") or "").strip()
    if gender:
        return gender
    name = voice.get("name") or ""
    if "Female" in name:
        return "Female"
    if "Male" in name:
        return "Male"
    return ""


def _sample_for(lang: str) -> str:
    key = "Chinese" if (lang or "").startswith("Chinese") else (lang or "")
    return VOICE_SAMPLES.get(key, VOICE_SAMPLE_FALLBACK)


def _safe_voice_file(voice_id: str, text: str) -> str:
    folder = CACHE_DIR / "voice_preview"
    folder.mkdir(parents=True, exist_ok=True)
    stem = "".join(ch if ch.isalnum() else "_" for ch in voice_id) or "voice"
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return str(folder / f"{stem}_{digest}.mp3")


def _speak_sample(voice_id: str, text: str, output_path: str, progress_callback=None) -> str:
    return TTSEngine.synthesize(text, voice_id, output_path, progress_callback=progress_callback)


class VoiceTools:
    """Shelf tab for hearing a voice and starring favorites."""

    def _build_voice_panel(self) -> QWidget:
        from claynext.gui.components.shelf_header import make_shelf_header

        panel = QWidget()
        panel.setObjectName("voice_browser")
        root = QVBoxLayout(panel)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(make_shelf_header("Voices"))

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(10, 8, 10, 8)
        body_lay.setSpacing(6)

        target = self.combo_lang.currentText()
        self._voice_lang_filter = "Chinese" if target.startswith("Chinese") else target
        self._voice_order = "favorite"

        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self.voice_search = QLineEdit()
        self.voice_search.setObjectName("media_lib_search")
        self.voice_search.setPlaceholderText("Search voices…")
        self.voice_search.setClearButtonEnabled(True)
        self.voice_search.textChanged.connect(lambda _text: self._refresh_voice_browser())
        search_row.addWidget(self.voice_search, 1)

        self.voice_filter_btn = QToolButton()
        self.voice_filter_btn.setObjectName("voice_filter_btn")
        self.voice_filter_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.voice_filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.voice_filter_btn.setToolTip("Filter language and sort order")
        self._voice_menu = QMenu(self.voice_filter_btn)
        self._voice_menu.setObjectName("media_lib_menu")
        self._voice_menu.aboutToShow.connect(self._fill_voice_menu)
        self.voice_filter_btn.setMenu(self._voice_menu)
        self._sync_voice_filter_caption()
        search_row.addWidget(self.voice_filter_btn)
        body_lay.addLayout(search_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._voice_host = QWidget()
        self._voice_lay = QVBoxLayout(self._voice_host)
        self._voice_lay.setContentsMargins(0, 0, 0, 0)
        self._voice_lay.setSpacing(4)
        self._voice_lay.addStretch(1)
        scroll.setWidget(self._voice_host)
        body_lay.addWidget(scroll, 1)

        self.voice_status = QLabel("")
        self.voice_status.setObjectName("dub_panel_hint")
        self.voice_status.setWordWrap(True)
        body_lay.addWidget(self.voice_status)
        root.addWidget(body, 1)

        self._voice_player = QMediaPlayer(self)
        self._voice_audio = QAudioOutput(self)
        self._voice_audio.setVolume(0.9)
        self._voice_player.setAudioOutput(self._voice_audio)
        self._voice_player.mediaStatusChanged.connect(self._on_voice_media_status)
        self._voice_worker = None
        self._voice_active_id = ""
        self._voice_mode = ""
        self._voice_play_btns = {}
        self._voice_slots = {}
        self._voice_spinners = {}

        self._refresh_voice_browser()
        return panel

    def _favorite_voice_ids(self) -> list[str]:
        raw = self.store.get_setting("dub", "favorite_voices", "") or ""
        if not raw.strip():
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return [part for part in raw.split(",") if part]
        if isinstance(data, list):
            return [str(item) for item in data if item]
        return []

    def _save_favorite_voice_ids(self, ids: list[str]):
        seen: list[str] = []
        for voice_id in ids:
            if voice_id and voice_id not in seen:
                seen.append(voice_id)
        self.store.set_setting("dub", "favorite_voices", json.dumps(seen))

    def _toggle_favorite_voice(self, voice_id: str):
        ids = self._favorite_voice_ids()
        if voice_id in ids:
            ids = [item for item in ids if item != voice_id]
            self.voice_status.setText("Removed from favorites")
        else:
            ids.append(voice_id)
            self.voice_status.setText("Saved to favorites")
        self._save_favorite_voice_ids(ids)
        self._refresh_voice_browser()

    def _sync_voice_filter_caption(self):
        if not hasattr(self, "voice_filter_btn"):
            return
        lang = self._voice_lang_filter or "All"
        order = dict(_VOICE_ORDERS).get(self._voice_order, "Favorites")
        self.voice_filter_btn.setText(f"{lang} · {order}")

    def _set_voice_lang_filter(self, lang: str):
        self._voice_lang_filter = lang
        self._sync_voice_filter_caption()
        self._refresh_voice_browser()

    def _set_voice_order(self, order: str):
        self._voice_order = order
        self._sync_voice_filter_caption()
        self._refresh_voice_browser()

    def _fill_voice_menu(self):
        menu = self._voice_menu
        menu.clear()
        lang_menu = menu.addMenu("Language")
        lang_menu.setObjectName("media_lib_menu")
        lang_group = QActionGroup(menu)
        lang_group.setExclusive(True)
        languages = sorted({str(voice.get("lang") or "") for voice in TTSEngine.list_voices() if voice.get("lang")})
        for key, label in [("", "All languages"), *[(name, name) for name in languages]]:
            act = QAction(label, menu)
            act.setCheckable(True)
            act.setChecked(key == self._voice_lang_filter)
            act.triggered.connect(lambda _checked=False, value=key: self._set_voice_lang_filter(value))
            lang_group.addAction(act)
            lang_menu.addAction(act)

        order_menu = menu.addMenu("Order")
        order_menu.setObjectName("media_lib_menu")
        order_group = QActionGroup(menu)
        order_group.setExclusive(True)
        for key, label in _VOICE_ORDERS:
            act = QAction(label, menu)
            act.setCheckable(True)
            act.setChecked(key == self._voice_order)
            act.triggered.connect(lambda _checked=False, value=key: self._set_voice_order(value))
            order_group.addAction(act)
            order_menu.addAction(act)

    def _voice_rows(self) -> list[dict]:
        query = self.voice_search.text().strip().lower() if hasattr(self, "voice_search") else ""
        favorites = set(self._favorite_voice_ids())
        chosen_lang = getattr(self, "_voice_lang_filter", "")
        rows = []
        for voice in TTSEngine.list_voices(chosen_lang or None):
            blob = " ".join(
                str(voice.get(key) or "")
                for key in ("name", "lang", "tag", "id")
            ).lower()
            gender = _voice_gender(voice).lower()
            if query and query not in blob and query not in gender:
                continue
            rows.append(voice)

        def sort_key(voice: dict):
            name = (voice.get("name") or "").lower()
            gender = _voice_gender(voice).lower()
            language = (voice.get("lang") or "").lower()
            engine = (voice.get("tag") or "").lower()
            order = getattr(self, "_voice_order", "favorite")
            if order == "name":
                return (name,)
            if order == "gender":
                return (gender or "z", name)
            if order == "language":
                return (language, name)
            if order == "engine":
                return (engine, name)
            return (voice["id"] not in favorites, name)

        rows.sort(key=sort_key)
        return rows

    def _refresh_voice_browser(self):
        if not hasattr(self, "_voice_lay"):
            return
        for spinner in getattr(self, "_voice_spinners", {}).values():
            spinner.stop()
        self._voice_play_btns = {}
        self._voice_slots = {}
        self._voice_spinners = {}
        while self._voice_lay.count():
            item = self._voice_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        favorites = set(self._favorite_voice_ids())
        rows = self._voice_rows()
        if not rows:
            empty = QLabel("No voices match this search.")
            empty.setObjectName("dub_panel_hint")
            empty.setWordWrap(True)
            self._voice_lay.addWidget(empty)
        for voice in rows:
            self._voice_lay.addWidget(self._voice_row(voice, voice["id"] in favorites))
        self._voice_lay.addStretch(1)
        self._apply_voice_controls()

    def _voice_row(self, voice: dict, favorite: bool) -> QFrame:
        row = QFrame()
        row.setObjectName("voice_row")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(8, 4, 6, 4)
        lay.setSpacing(4)

        text = QVBoxLayout()
        text.setSpacing(0)
        name = QLabel(TTSEngine.voice_label(voice))
        name.setObjectName("voice_name")
        gender = _voice_gender(voice)
        # Engine/model stays in meta only — title is the character name
        detail = " · ".join(part for part in (voice.get("lang", ""), gender, voice.get("tag", "")) if part)
        meta = QLabel(detail)
        meta.setObjectName("voice_meta")
        text.addWidget(name)
        text.addWidget(meta)
        lay.addLayout(text, 1)

        play = QToolButton()
        play.setObjectName("media_ctrl_btn")
        play.setIcon(icon("play", color="#e7ecf3", size=14))
        play.setFixedSize(28, 28)
        play.setAutoRaise(True)
        play.setCursor(Qt.CursorShape.PointingHandCursor)
        play.setToolTip("Preview this voice")
        play.clicked.connect(lambda _checked=False, vid=voice["id"]: self._preview_voice(vid))

        spinner = Spinner(size=18, color="#c084fc")
        spin_page = QWidget()
        spin_lay = QHBoxLayout(spin_page)
        spin_lay.setContentsMargins(5, 5, 5, 5)
        spin_lay.addWidget(spinner, 0, Qt.AlignmentFlag.AlignCenter)

        slot = QStackedWidget()
        slot.setFixedSize(28, 28)
        slot.addWidget(play)
        slot.addWidget(spin_page)
        self._voice_play_btns[voice["id"]] = play
        self._voice_slots[voice["id"]] = slot
        self._voice_spinners[voice["id"]] = spinner
        lay.addWidget(slot)

        star = QToolButton()
        star.setObjectName("voice_star")
        star.setText("★" if favorite else "☆")
        star.setFixedSize(28, 28)
        star.setAutoRaise(True)
        star.setCursor(Qt.CursorShape.PointingHandCursor)
        star.setToolTip("Remove favorite" if favorite else "Save favorite")
        star.clicked.connect(lambda _checked=False, vid=voice["id"]: self._toggle_favorite_voice(vid))
        lay.addWidget(star)
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return row

    def _apply_voice_controls(self):
        for voice_id, button in self._voice_play_btns.items():
            slot = self._voice_slots.get(voice_id)
            spinner = self._voice_spinners.get(voice_id)
            loading = voice_id == self._voice_active_id and self._voice_mode == "loading"
            playing = voice_id == self._voice_active_id and self._voice_mode == "playing"
            if loading and slot is not None and spinner is not None:
                slot.setCurrentIndex(1)
                spinner.start()
                continue
            if spinner is not None:
                spinner.stop()
            if slot is not None:
                slot.setCurrentIndex(0)
            button.setIcon(icon("pause" if playing else "play", color="#e7ecf3", size=14))
            button.setToolTip("Pause preview" if playing else "Preview this voice")

    def _preview_voice(self, voice_id: str):
        if voice_id == self._voice_active_id and self._voice_mode == "playing":
            self.stop_voice_preview()
            return
        if voice_id == self._voice_active_id and self._voice_mode == "loading":
            return
        if self._voice_worker is not None:
            return
        if self._voice_mode == "playing":
            self._voice_player.stop()
        text = _sample_for(self.combo_lang.currentText())
        path = _safe_voice_file(voice_id, text)
        self._voice_active_id = voice_id
        if os.path.isfile(path) and os.path.getsize(path) > 800:
            self._play_voice_file(path, voice_id)
            return
        self._voice_mode = "loading"
        self._apply_voice_controls()
        worker = Worker(_speak_sample, voice_id, text, path)
        worker.signals.result.connect(lambda out, vid=voice_id: self._on_voice_ready(vid, out))
        worker.signals.error.connect(self._on_voice_error)
        worker.signals.finished.connect(self._on_voice_finished)
        self._voice_worker = worker
        self.thread_pool.start(worker)

    def _on_voice_ready(self, voice_id: str, path: object):
        if voice_id != self._voice_active_id:
            return
        if isinstance(path, str) and os.path.isfile(path):
            self._play_voice_file(path, voice_id)

    def _on_voice_error(self, message: str, _stack: str):
        self._voice_mode = ""
        self._voice_active_id = ""
        self._apply_voice_controls()
        self.voice_status.setText("Preview failed")
        if hasattr(self, "log"):
            self.log.warn(f"Voice preview · {message}")

    def _on_voice_finished(self):
        self._voice_worker = None

    def _on_voice_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self._voice_mode == "playing":
            self._voice_mode = ""
            self._voice_active_id = ""
            self._apply_voice_controls()

    def _play_voice_file(self, path: str, voice_id: str):
        self._voice_active_id = voice_id
        self._voice_mode = "playing"
        self._apply_voice_controls()
        self._voice_player.stop()
        self._voice_player.setSource(QUrl.fromLocalFile(path))
        self._voice_player.play()

    def stop_voice_preview(self):
        self._voice_mode = ""
        self._voice_active_id = ""
        if hasattr(self, "_voice_player"):
            self._voice_player.stop()
        if hasattr(self, "_voice_play_btns"):
            self._apply_voice_controls()

