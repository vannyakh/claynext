"""Dub script table and subtitle export."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime

from PySide6.QtCore import Qt, QSettings, QUrl, QThreadPool
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QFrame, QHeaderView, QAbstractItemView, QMenu,
    QStackedWidget, QMessageBox, QFileDialog, QDialog, QTextEdit, QComboBox,
    QDialogButtonBox, QApplication, QSizePolicy, QToolButton, QGridLayout,
)

from claynext.models.dubbing_service import timestamp_to_sec
from claynext.adapters.ffmpeg_service import concat_videos, mix_timeline_audio, render_timeline, run_ffmpeg
from claynext.gui.icons import icon
from claynext.models.thumbnails import VIDEO_EXTS
from claynext.models.translate_service import TranslateEngine
from claynext.models.tts_service import TTSEngine
from claynext.models.tts_expression import EXPRESSION_CHIPS
from claynext.models.canvas import is_neutral
from claynext.gui.worker import Worker
from claynext.gui.components.field_controls import SearchField, SelectField
from claynext.gui.components.shelf_header import make_shelf_header
from claynext.gui.components.spinner import Spinner
from claynext.gui.components.table_fit import fit_or_scroll
from claynext.gui.views.studio.helpers import export_segments, import_segments
from claynext.gui.views.studio.merge import MergeOrderDialog
from claynext.utils.config import CACHE_DIR, OUTPUTS_DIR


def _line_snapshot(seg: dict) -> dict:
    original = str(seg.get("original_text") or seg.get("text") or "")
    voice = str(seg.get("voice_id") or seg.get("tts_voice_hint") or "")
    return {
        "speaker": str(seg.get("speaker") or ""),
        "gender": str(seg.get("gender") or "Unknown"),
        "gender_manual": bool(seg.get("gender_manual")),
        "translated_text": str(seg.get("translated_text") or ""),
        "original_text": original,
        "text": str(seg.get("text") or original),
        "tts_voice_hint": str(seg.get("tts_voice_hint") or voice),
        "voice_id": voice,
    }


def _preview_cache_path(voice_id: str, text: str) -> str:
    folder = CACHE_DIR / "line_preview"
    folder.mkdir(parents=True, exist_ok=True)
    stem = "".join(ch if ch.isalnum() else "_" for ch in voice_id) or "voice"
    digest = hashlib.sha1(f"{voice_id}\n{text}".encode("utf-8")).hexdigest()[:10]
    return str(folder / f"{stem}_{digest}.mp3")


class _ChipGrid(QWidget):
    """Compact wrapping grid for expression tag chips."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QGridLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setHorizontalSpacing(4)
        self._lay.setVerticalSpacing(4)
        self._cols = 5
        self._count = 0

    def add_widget(self, widget: QWidget):
        row, col = divmod(self._count, self._cols)
        self._lay.addWidget(widget, row, col)
        self._count += 1


class LineEditDialog(QDialog):
    """Edit one dubbed line. Saving stores a version that can be accepted or reversed."""

    def __init__(
        self,
        seg: dict,
        cast_voices: list[dict],
        *,
        lang: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit line")
        self.setMinimumWidth(480)
        self._lang = lang or ""
        self._cast = list(cast_voices or [])
        self._preview_worker = None
        self._preview_mode = ""

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._audio.setVolume(0.9)
        self._player.setAudioOutput(self._audio)
        self._player.mediaStatusChanged.connect(self._on_preview_status)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        source_label = QLabel("Source dialogue")
        source_label.setObjectName("asr_field_label")
        self.source = QTextEdit()
        self.source.setObjectName("dub_setting_field")
        self.source.setPlainText(str(seg.get("original_text") or seg.get("text") or ""))
        self.source.setFixedHeight(72)

        dub_label = QLabel("Dubbed translation")
        dub_label.setObjectName("asr_field_label")
        self.dub = QTextEdit()
        self.dub.setObjectName("dub_setting_field")
        self.dub.setPlainText(str(seg.get("translated_text") or ""))
        self.dub.setFixedHeight(96)
        self.dub.setPlaceholderText(
            'Use tags for delivery, e.g. [laugh] I can\'t believe it! [sigh] What a mess.'
        )

        expr_hint = QLabel("Expression tags — insert at cursor")
        expr_hint.setObjectName("asr_field_label")
        chips = _ChipGrid()
        for label, token in EXPRESSION_CHIPS:
            btn = QPushButton(label)
            btn.setObjectName("dub_props_chip")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"Insert {token}")
            btn.clicked.connect(lambda _=False, t=token: self._insert_tag(t))
            chips.add_widget(btn)

        char_label = QLabel("Character · TTS voice")
        char_label.setObjectName("asr_field_label")
        char_row = QHBoxLayout()
        char_row.setSpacing(6)
        self.character = QComboBox()
        self.character.setObjectName("asr_option_combo")
        self.character.setEditable(False)
        self.character.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._fill_cast(seg)
        self.character.currentIndexChanged.connect(self._on_cast_changed)

        self.btn_preview_voice = QToolButton()
        self.btn_preview_voice.setObjectName("media_lib_icon_btn")
        self.btn_preview_voice.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_preview_voice.setIcon(icon("play", color="#e7ecf3", size=14))
        self.btn_preview_voice.setToolTip("Preview this TTS voice")
        self.btn_preview_voice.clicked.connect(self._preview_voice_sample)
        self.btn_preview_voice.setFixedSize(30, 30)

        self.btn_preview_line = QToolButton()
        self.btn_preview_line.setObjectName("media_lib_icon_btn")
        self.btn_preview_line.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_preview_line.setIcon(icon("volume", color="#e7ecf3", size=14))
        self.btn_preview_line.setToolTip("Preview this line (honours expression tags)")
        self.btn_preview_line.clicked.connect(self._preview_line)
        self.btn_preview_line.setFixedSize(30, 30)

        self.preview_spinner = Spinner(size=14)
        char_row.addWidget(self.character, 1)
        char_row.addWidget(self.btn_preview_voice)
        char_row.addWidget(self.btn_preview_line)
        char_row.addWidget(self.preview_spinner)

        gender_label = QLabel("Gender")
        gender_label.setObjectName("asr_field_label")
        self.gender = QComboBox()
        self.gender.setObjectName("asr_option_combo")
        self.gender.setEditable(False)
        self.gender.addItems(["Female", "Male", "Unknown"])
        g_idx = self.gender.findText(str(seg.get("gender") or "Unknown"))
        self.gender.setCurrentIndex(g_idx if g_idx >= 0 else 2)

        self.preview_status = QLabel("")
        self.preview_status.setObjectName("dub_switch_hint")
        self.preview_status.setWordWrap(True)

        lay.addWidget(source_label)
        lay.addWidget(self.source)
        lay.addWidget(dub_label)
        lay.addWidget(self.dub)
        lay.addWidget(expr_hint)
        lay.addWidget(chips)
        lay.addWidget(char_label)
        lay.addLayout(char_row)
        lay.addWidget(gender_label)
        lay.addWidget(self.gender)
        lay.addWidget(self.preview_status)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self._on_cast_changed()

    def _fill_cast(self, seg: dict):
        current_speaker = str(seg.get("speaker") or "")
        current_voice = str(seg.get("tts_voice_hint") or seg.get("voice_id") or "")
        generic = (
            not current_speaker
            or current_speaker.startswith("Character ")
            or current_speaker.startswith("SPEAKER_")
            or current_speaker in {"UNKNOWN_SPEAKER", "Unknown", "Speaker 1", "Speaker 2"}
        )
        seen: set[str] = set()
        voice_index: dict[str, int] = {}
        for voice in self._cast:
            label = str(voice.get("label") or "")
            vid = str(voice.get("id") or "")
            gender = str(voice.get("gender") or "")
            if not label or label in seen:
                continue
            seen.add(label)
            text = f"{label} · {gender}" if gender and gender != "Unknown" else label
            idx = self.character.count()
            self.character.addItem(text, {"label": label, "id": vid, "gender": gender})
            if vid and vid not in voice_index:
                voice_index[vid] = idx
        # Keep a custom (non-generic) speaker that is not already a TTS cast name.
        if current_speaker and current_speaker not in seen and not generic:
            self.character.insertItem(
                0,
                current_speaker,
                {
                    "label": current_speaker,
                    "id": current_voice,
                    "gender": str(seg.get("gender") or ""),
                },
            )
            # Shift cached voice indexes after insert at 0.
            voice_index = {vid: i + 1 for vid, i in voice_index.items()}
            if current_voice and current_voice not in voice_index:
                voice_index[current_voice] = 0
        # Prefer TTS cast matched by voice id (maps Character N → Sreymom/Piseth).
        picked = -1
        if current_voice and current_voice in voice_index:
            picked = voice_index[current_voice]
        if picked < 0 and current_speaker:
            for i in range(self.character.count()):
                data = self.character.itemData(i) or {}
                if str(data.get("label") or "") == current_speaker:
                    picked = i
                    break
        if picked >= 0:
            self.character.setCurrentIndex(picked)
        elif self.character.count():
            self.character.setCurrentIndex(0)

    def _cast_data(self) -> dict:
        data = self.character.currentData()
        return dict(data) if isinstance(data, dict) else {}

    def _on_cast_changed(self, _index: int = 0):
        data = self._cast_data()
        gender = str(data.get("gender") or "")
        if gender in {"Female", "Male", "Unknown"}:
            idx = self.gender.findText(gender)
            if idx >= 0:
                self.gender.setCurrentIndex(idx)

    def _insert_tag(self, token: str):
        cursor = self.dub.textCursor()
        # Space before/after when needed so tags don't glue to words.
        prefix = ""
        suffix = " "
        pos = cursor.position()
        text = self.dub.toPlainText()
        if pos > 0 and not text[pos - 1].isspace() and text[pos - 1] not in "([":
            prefix = " "
        if pos < len(text) and not text[pos].isspace():
            suffix = " "
        cursor.insertText(f"{prefix}{token}{suffix}")
        self.dub.setTextCursor(cursor)
        self.dub.setFocus()

    def _selected_voice_id(self) -> str:
        return str(self._cast_data().get("id") or "")

    def _stop_preview(self):
        self._preview_mode = ""
        self._player.stop()
        self.preview_spinner.stop()
        self.btn_preview_voice.setIcon(icon("play", color="#e7ecf3", size=14))
        self.btn_preview_line.setEnabled(True)
        self.btn_preview_voice.setEnabled(True)

    def _on_preview_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._stop_preview()
            self.preview_status.setText("")

    def _preview_voice_sample(self):
        from claynext.gui.views.studio.constants import VOICE_SAMPLE_FALLBACK, VOICE_SAMPLES

        voice_id = self._selected_voice_id()
        if not voice_id:
            self.preview_status.setText("Pick a TTS voice first.")
            return
        if self._preview_mode == "playing":
            self._stop_preview()
            return
        if self._preview_worker is not None:
            return
        key = "Chinese" if self._lang.startswith("Chinese") else self._lang
        text = VOICE_SAMPLES.get(key, VOICE_SAMPLE_FALLBACK)
        self._start_preview(voice_id, text, kind="voice")

    def _preview_line(self):
        voice_id = self._selected_voice_id()
        text = self.dub.toPlainText().strip()
        if not voice_id:
            self.preview_status.setText("Pick a TTS voice first.")
            return
        if not text:
            self.preview_status.setText("Dub text is empty.")
            return
        if self._preview_mode == "playing":
            self._stop_preview()
            return
        if self._preview_worker is not None:
            return
        self._start_preview(voice_id, text, kind="line")

    def _start_preview(self, voice_id: str, text: str, *, kind: str):
        path = _preview_cache_path(voice_id, text)
        self._preview_mode = "loading"
        self.preview_spinner.start()
        self.btn_preview_voice.setEnabled(False)
        self.btn_preview_line.setEnabled(False)
        self.preview_status.setText(
            "Generating line preview…" if kind == "line" else "Generating voice sample…"
        )
        if os.path.isfile(path) and os.path.getsize(path) > 800:
            self._play_preview(path)
            return

        def _job(vid=voice_id, body=text, out=path, progress_callback=None):
            return TTSEngine.synthesize(body, vid, out, progress_callback=progress_callback)

        worker = Worker(_job)
        worker.signals.result.connect(self._on_preview_ready)
        worker.signals.error.connect(self._on_preview_error)
        worker.signals.finished.connect(self._on_preview_finished)
        self._preview_worker = worker
        QThreadPool.globalInstance().start(worker)

    def _on_preview_ready(self, path: object):
        if isinstance(path, str) and os.path.isfile(path):
            self._play_preview(path)
        else:
            self._stop_preview()
            self.preview_status.setText("Preview failed.")

    def _on_preview_error(self, message: str, _stack: str):
        self._stop_preview()
        self.preview_status.setText(f"Preview failed · {message}")

    def _on_preview_finished(self):
        self._preview_worker = None

    def _play_preview(self, path: str):
        self._preview_mode = "playing"
        self.preview_spinner.stop()
        self.btn_preview_voice.setEnabled(True)
        self.btn_preview_line.setEnabled(True)
        self.btn_preview_voice.setIcon(icon("pause", color="#e7ecf3", size=14))
        self.preview_status.setText("Playing…")
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

    def reject(self):
        self._stop_preview()
        super().reject()

    def accept(self):
        self._stop_preview()
        super().accept()

    def values(self) -> dict:
        original = self.source.toPlainText().strip()
        data = self._cast_data()
        speaker = str(data.get("label") or self.character.currentText() or "").strip() or "Voice"
        voice_id = str(data.get("id") or "")
        return {
            "original_text": original,
            "text": original,
            "translated_text": self.dub.toPlainText().strip(),
            "speaker": speaker,
            "gender": self.gender.currentText() or "Unknown",
            "gender_manual": True,
            "tts_voice_hint": voice_id,
            "voice_id": voice_id,
        }


class ScriptTools:
    """Dialogue table and subtitle export."""

    def _focus_script_shelf(self):
        """Open the shelf Script tab (script lives in the icon shelf, not a dock)."""
        if hasattr(self, "workspace"):
            self.workspace.set_visible("shelf", True)
        if hasattr(self, "shelf"):
            self.shelf.show_key("script")

    def _on_timeline_transcript_action(self, action: str):
        """Handle Audio Transcripts extras from the timeline source context menu."""
        key = str(action or "").strip().lower()
        if key == "show":
            self._focus_script_shelf()
            return
        if key == "import":
            self._focus_script_shelf()
            self._import_script()
            return
        if key == "export":
            self._focus_script_shelf()
            self.open_export_dialog(script_only=True)
            return
        if key == "retry":
            self._focus_script_shelf()
            self._retry_script_transcript()
            return
        if key == "translate":
            self._focus_script_shelf()
            rows = list(range(len(getattr(self, "_segments", []) or [])))
            if not rows:
                self.log.warn("Retry translate · no script lines yet")
                return
            self._regenerate_rows(rows)
            return
        if key == "tts":
            self._focus_script_shelf()
            rows = list(range(len(getattr(self, "_segments", []) or [])))
            if not rows:
                self.log.warn("Retry TTS · no script lines yet")
                return
            self._resynthesize_rows(rows)
            return
        if key == "all":
            self._focus_script_shelf()
            self._retry_script_all()
            return

    def _build_script_header(self) -> QWidget:
        """Shelf title strip: line count, import/export menus, spinner."""
        self.lbl_script_count = QLabel("")
        self.lbl_script_count.setObjectName("transcript_count")
        self.lbl_script_count.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        )

        self.btn_script_import = QPushButton("Import ▾")
        self.btn_script_import.setObjectName("media_lib_menu_btn")
        self.btn_script_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_script_import.setFixedHeight(22)
        self.btn_script_import.setToolTip("Load script · SRT, VTT, or JSON")
        import_menu = QMenu(self.btn_script_import)
        import_menu.setObjectName("media_lib_menu")
        act_import = import_menu.addAction("Import script…")
        act_import.triggered.connect(lambda: self._import_script())
        import_menu.addSeparator()
        act_in_srt = import_menu.addAction("SRT…")
        act_in_srt.triggered.connect(lambda: self._import_script("srt"))
        act_in_vtt = import_menu.addAction("VTT…")
        act_in_vtt.triggered.connect(lambda: self._import_script("vtt"))
        act_in_json = import_menu.addAction("JSON…")
        act_in_json.triggered.connect(lambda: self._import_script("json"))
        self.btn_script_import.setMenu(import_menu)

        self.btn_script_export = QPushButton("Export ▾")
        self.btn_script_export.setObjectName("media_lib_menu_btn")
        self.btn_script_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_script_export.setEnabled(False)
        self.btn_script_export.setFixedHeight(22)
        self.btn_script_export.setToolTip("Export script text · SRT, VTT, or JSON")
        export_menu = QMenu(self.btn_script_export)
        export_menu.setObjectName("media_lib_menu")
        act_dialog = export_menu.addAction("Export script…")
        act_dialog.triggered.connect(lambda: self.open_export_dialog(script_only=True))
        export_menu.addSeparator()
        act_srt = export_menu.addAction("SRT…")
        act_srt.triggered.connect(lambda: self._export_subtitles("srt", "current"))
        act_vtt = export_menu.addAction("VTT…")
        act_vtt.triggered.connect(lambda: self._export_subtitles("vtt", "current"))
        act_json = export_menu.addAction("JSON…")
        act_json.triggered.connect(lambda: self._export_subtitles("json", "current"))
        export_menu.addSeparator()
        act_back_srt = export_menu.addAction("Previous version (SRT)…")
        act_back_srt.triggered.connect(lambda: self._export_subtitles("srt", "back"))
        act_back_vtt = export_menu.addAction("Previous version (VTT)…")
        act_back_vtt.triggered.connect(lambda: self._export_subtitles("vtt", "back"))
        self.btn_script_export.setMenu(export_menu)

        self.table_spinner = Spinner(size=16)
        self.script_header = make_shelf_header(
            "Script",
            self.lbl_script_count,
            self.btn_script_import,
            self.btn_script_export,
            self.table_spinner,
        )
        return self.script_header

    def _build_script_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("transcript_panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_script_header())

        tools = QFrame()
        tools.setObjectName("transcript_tools")
        filter_row = QHBoxLayout(tools)
        filter_row.setContentsMargins(12, 10, 12, 8)
        filter_row.setSpacing(8)

        # Left: search + character select · Right: action buttons
        left = QHBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(8)

        self.script_search = SearchField("Find in script…", size="md")
        self.script_search.setMinimumWidth(160)
        self.script_search.setMaximumWidth(260)
        self.script_search.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self.script_search.textChanged.connect(lambda _: self._apply_script_filters())
        left.addWidget(self.script_search, 0, Qt.AlignmentFlag.AlignVCenter)

        self.script_character_filter = SelectField(size="sm", width=148)
        self.script_character_filter.setObjectName("script_character_filter")
        self.script_character_filter.addItem("All characters", "all")
        self.script_character_filter.currentIndexChanged.connect(
            lambda _: self._apply_script_filters()
        )
        left.addWidget(self.script_character_filter, 0, Qt.AlignmentFlag.AlignVCenter)
        filter_row.addLayout(left, 0)

        filter_row.addStretch(1)

        self.btn_script_pending = QToolButton()
        self.btn_script_pending.setObjectName("media_lib_icon_btn")
        self.btn_script_pending.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_script_pending.setIcon(icon("sparkles", color="#e7ecf3", size=14))
        self.btn_script_pending.setFixedSize(28, 28)
        self.btn_script_pending.setToolTip("Next pending version")
        self.btn_script_pending.setEnabled(False)
        self.btn_script_pending.clicked.connect(lambda: self._jump_pending(1))
        filter_row.addWidget(self.btn_script_pending, 0, Qt.AlignmentFlag.AlignVCenter)

        self.btn_script_actions = QToolButton()
        self.btn_script_actions.setObjectName("media_lib_icon_btn")
        self.btn_script_actions.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_script_actions.setIcon(icon("more", color="#e7ecf3", size=14))
        self.btn_script_actions.setFixedSize(28, 28)
        self.btn_script_actions.setToolTip("Script actions")
        self.btn_script_actions.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_script_actions.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.btn_script_actions.setEnabled(False)
        actions_menu = QMenu(self.btn_script_actions)
        actions_menu.setObjectName("media_lib_menu")
        actions_menu.setToolTipsVisible(True)
        self._script_actions_menu = actions_menu
        self.btn_script_actions.setMenu(actions_menu)
        actions_menu.aboutToShow.connect(self._fill_script_actions_menu)
        filter_row.addWidget(self.btn_script_actions, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(tools)

        self.script_stack = QStackedWidget()
        empty = QWidget()
        empty.setObjectName("transcript_empty")
        empty_lay = QVBoxLayout(empty)
        empty_lay.addStretch(1)
        self.empty_title = QLabel("No dubbed script")
        self.empty_title.setObjectName("transcript_empty_title")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_lay.addWidget(self.empty_title)
        self.empty_hint = QLabel(
            "Select a movie and dub, or Import a script (SRT / VTT / JSON)"
        )
        self.empty_hint.setObjectName("transcript_empty_hint")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setWordWrap(True)
        empty_lay.addWidget(self.empty_hint)
        empty_lay.addStretch(2)
        self.script_stack.addWidget(empty)

        self.table = QTableWidget()
        self.table.setObjectName("transcript_table")
        # Timing + character + gender + source/dub lines.
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["#", "Time", "Character", "Gender", "Source", "Dub"])
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(36)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(1, 118)
        self.table.setColumnWidth(2, 112)
        self.table.setColumnWidth(3, 72)
        fit_or_scroll(self.table, (4, 5))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.verticalHeader().setMinimumSectionSize(36)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._script_menu)
        self.table.cellDoubleClicked.connect(self._play_row)
        self._script_worker = None
        self._regen_rows: list[int] = []
        self.script_stack.addWidget(self.table)
        layout.addWidget(self.script_stack, 1)

        QShortcut(QKeySequence("Return"), self.table).activated.connect(
            lambda: self._play_row(self.table.currentRow(), 0)
        )
        QShortcut(QKeySequence("Ctrl+F"), panel).activated.connect(self._focus_script_search)
        QShortcut(QKeySequence("Ctrl+C"), self.table).activated.connect(
            lambda: self._copy_script_lines("dub")
        )
        QShortcut(QKeySequence("Ctrl+Shift+C"), self.table).activated.connect(
            lambda: self._copy_script_lines("times")
        )
        self._update_script_meta()
        return panel

    def _lines_for_export(self, mode: str) -> list[dict]:
        rows = []
        for seg in self._segments:
            if mode == "current":
                rows.append(seg)
                continue
            if seg.get("pending") and isinstance(seg.get("committed"), dict):
                merged = dict(seg)
                merged.update(seg["committed"])
                rows.append(merged)
                continue
            merged = dict(seg)
            source = str(seg.get("original_text") or seg.get("text") or "")
            merged["translated_text"] = source
            rows.append(merged)
        return rows

    def _export_subtitles(self, fmt: str, mode: str = "current"):
        lines = self._lines_for_export(mode)
        if not lines:
            QMessageBox.information(self, "Export", "No dubbed script lines to export.")
            return
        label = "back" if mode == "back" else "current"
        default_name = f"dubbed_{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}"
        if self.selected_file:
            stem = os.path.splitext(os.path.basename(self.selected_file))[0]
            default_name = f"{stem}_{label}.{fmt}"
        path = str(OUTPUTS_DIR / default_name)
        filter_str = (
            "SubRip Subtitles (*.srt)"
            if fmt == "srt"
            else "WebVTT Subtitles (*.vtt)"
            if fmt == "vtt"
            else "JSON Files (*.json)"
        )
        file_path, _ = QFileDialog.getSaveFileName(self, f"Export {label} {fmt.upper()}", path, filter_str)
        if not file_path:
            return
        try:
            export_segments(file_path, fmt, lines)
            self.log.success(f"Exported {label} {fmt.upper()} → {os.path.basename(file_path)}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not export {fmt.upper()}: {e}")

    def _import_script(self, fmt: str | None = None):
        """Load script lines from SRT / VTT / JSON into the table."""
        if fmt == "srt":
            filter_str = "SubRip Subtitles (*.srt)"
        elif fmt == "vtt":
            filter_str = "WebVTT Subtitles (*.vtt)"
        elif fmt == "json":
            filter_str = "JSON Files (*.json)"
        else:
            filter_str = (
                "Script files (*.srt *.vtt *.json);;"
                "SubRip Subtitles (*.srt);;"
                "WebVTT Subtitles (*.vtt);;"
                "JSON Files (*.json)"
            )
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import script", str(OUTPUTS_DIR), filter_str,
        )
        if not file_path:
            return
        if self._segments:
            answer = QMessageBox.question(
                self,
                "Import script",
                f"Replace the current {len(self._segments)} line(s) with this file?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            kind = fmt or os.path.splitext(file_path)[1].lstrip(".").lower()
            lines = import_segments(file_path, kind)
        except Exception as exc:
            QMessageBox.critical(self, "Import Failed", f"Could not load script:\n{exc}")
            return
        if not lines:
            QMessageBox.information(self, "Import", "No script lines found in that file.")
            return
        self._fill_table(lines)
        self._update_script_meta()
        if hasattr(self, "_store_project_session"):
            self._store_project_session()
        self.log.success(
            f"Imported {len(lines)} line{'s' if len(lines) != 1 else ''} ← {os.path.basename(file_path)}"
        )

    def _episode_paths(self) -> list[str]:
        ordered: list[str] = []
        pool: list[str] = []
        if hasattr(self, "media_lib"):
            pool.extend(self.media_lib.selected_paths())
            pool.extend(self.media_lib.paths())
        if self.selected_file:
            pool.insert(0, self.selected_file)
        for path in pool:
            if not path or path in ordered or not os.path.isfile(path):
                continue
            if os.path.splitext(path)[1].lower() not in VIDEO_EXTS:
                continue
            ordered.append(path)
        return ordered

    def _render_copy(self, source: str, title: str, default_name: str):
        if not source or not os.path.isfile(source):
            QMessageBox.information(self, title, "That file is not ready to render.")
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, title, str(OUTPUTS_DIR / default_name), "Movie (*.mp4)",
        )
        if not dest:
            return
        if not dest.lower().endswith(".mp4"):
            dest += ".mp4"
        self.table_spinner.start()
        worker = Worker(lambda src, out, progress_callback=None: shutil.copy2(src, out), source, dest)
        worker.signals.result.connect(lambda _path, out=dest: self._on_render_ready(out, title))
        worker.signals.error.connect(self._on_render_error)
        worker.signals.finished.connect(self.table_spinner.stop)
        self.thread_pool.start(worker)

    def _on_render_ready(self, path: str, title: str):
        self.log.success(f"{title} → {os.path.basename(path)}")

    def _on_render_error(self, message: str, _stack: str):
        self.table_spinner.stop()
        self.log.error(f"Render failed · {message}")
        QMessageBox.warning(self, "Render", message)

    def _render_current(self):
        self.open_export_dialog("movie")

    def _export_summary(self) -> str:
        plan = self.timeline.render_plan()
        keys = sum(len(self.timeline.canvas.clip_keys(c)) for c in self.timeline.canvas.footage_clips())
        bed = "music and effects bed ready" if self.timeline.canvas.bed_path else "no music bed yet"
        frame = plan["canvas"]
        looks = []
        if any(c.extra.get("adjust") for c in self.timeline.canvas.footage_clips()):
            looks.append("colour grade")
        if not is_neutral(frame):
            looks.append(f"{frame['ratio']} canvas" if frame["ratio"] != "original" else "canvas framing")
        grade = f" · {' + '.join(looks)} applied (re-encodes video)" if looks else ""
        return (
            f"{len(plan['voice'])} voice clips · {keys} footage key points · "
            f"{len(self._segments)} script lines · {bed}{grade}"
        )

    def open_export_dialog(self, kind: str = "", *, script_only: bool = False):
        from claynext.gui.dialogs.export_dialog import ExportDialog

        source = self.timeline.canvas.media_path or self.selected_file
        stem = os.path.splitext(os.path.basename(source))[0] if source else "dub"
        saved = {}
        key = "dubbing/script_export_options" if script_only else "dubbing/export_options"
        raw = QSettings("Claynext", "ClaynextStudio").value(key, "")
        if raw:
            try:
                saved = json.loads(raw)
            except (TypeError, ValueError):
                saved = {}
        if kind:
            saved["kind"] = kind
        summary = (
            f"{len(self._segments)} script line{'s' if len(self._segments) != 1 else ''} · text export only"
            if script_only else self._export_summary()
        )
        dialog = ExportDialog(
            self, folder=str(OUTPUTS_DIR), stem=stem, summary=summary, saved=saved,
            script_only=script_only,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        opts = dialog.options()
        QSettings("Claynext", "ClaynextStudio").setValue(
            key, json.dumps({k: v for k, v in opts.items() if k != "path"}),
        )
        self._run_export(opts)

    def _run_export(self, opts: dict):
        kind = opts["kind"]
        dest = opts["path"]
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        if kind in {"srt", "vtt", "json"}:
            lines = self._lines_for_export(opts["version"])
            if not lines:
                QMessageBox.information(self, "Export", "No script lines to export yet.")
                return
            try:
                export_segments(dest, kind, lines)
                self.log.success(f"Exported {opts['version']} {kind.upper()} → {os.path.basename(dest)}")
            except Exception as exc:
                QMessageBox.critical(self, "Export failed", str(exc))
            return
        source = self.timeline.canvas.media_path or self.selected_file
        if not source or not os.path.isfile(source):
            QMessageBox.information(self, "Export", "Put footage on the timeline first.")
            return
        if kind == "source":
            self._export_source(source, dest, opts["video"] == "h264")
            return
        plan = self.timeline.render_plan()
        work_dir = str(OUTPUTS_DIR / ".render" / datetime.now().strftime("%Y%m%d_%H%M%S"))
        common = dict(
            footage_gain=plan["footage_gain"],
            bed_path=plan["bed_path"],
            bed_keys=plan["bed_keys"],
            work_dir=work_dir,
        )
        if kind == "movie":
            worker = Worker(
                render_timeline, source, dest, plan["voice"], plan["footage_keys"],
                overlays=self.timeline.export_overlays(aspect=self._stage_aspect()) if opts["overlays"] else None,
                segments=list(self._segments),
                audio_bitrate=opts["audio"],
                reencode=opts["video"] == "h264",
                video_filter=plan["video_filter"],
                **common,
            )
            title = "Render dub"
        else:
            worker = Worker(
                mix_timeline_audio, source, dest, plan["voice"], plan["footage_keys"],
                include_footage=kind == "mix_wav",
                **common,
            )
            title = "Export mix" if kind == "mix_wav" else "Export voice-over"
        self.table_spinner.start()
        worker.signals.progress.connect(lambda pct, msg: self.log.debug(f"{pct}% · {msg}"))
        worker.signals.result.connect(lambda path, d=work_dir, t=title, k=kind: self._on_timeline_rendered(path, d, t, k))
        worker.signals.error.connect(self._on_render_error)
        worker.signals.finished.connect(self.table_spinner.stop)
        self.thread_pool.start(worker)
        self.log.info(f"{title} · {len(plan['voice'])} voice clips · {len(plan['footage_keys'])} key points")

    def _export_source(self, source: str, dest: str, reencode: bool):
        def job(src: str, out: str, progress_callback=None) -> str:
            if not reencode:
                shutil.copy2(src, out)
                return out
            proc = run_ffmpeg([
                "-y", "-i", src, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", out,
            ], timeout=3600)
            if proc.returncode != 0 or not os.path.isfile(out):
                raise RuntimeError((proc.stderr or b"").decode("utf-8", errors="replace").strip() or "Encode failed.")
            return out

        self.table_spinner.start()
        worker = Worker(job, source, dest)
        worker.signals.result.connect(lambda path: self._on_render_ready(str(path), "Export source"))
        worker.signals.error.connect(self._on_render_error)
        worker.signals.finished.connect(self.table_spinner.stop)
        self.thread_pool.start(worker)

    def _on_timeline_rendered(self, path: str, work_dir: str, title: str = "Render dub", kind: str = "movie"):
        shutil.rmtree(work_dir, ignore_errors=True)
        if kind == "movie":
            self._output_path = str(path)
            if self.act_open_out:
                self.act_open_out.setEnabled(os.path.isfile(self._output_path))
        self._on_render_ready(str(path), title)

    def _render_source(self):
        source = self.selected_file
        stem = "source"
        if source:
            stem = os.path.splitext(os.path.basename(source))[0] + "_source"
        self._render_copy(source, "Render source", f"{stem}.mp4")

    def _hot_merge(self):
        paths = self._episode_paths()
        if len(paths) < 2:
            QMessageBox.information(self, "Hot merge", "Add at least two source episodes to merge.")
            return
        dialog = MergeOrderDialog(paths, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        ordered = dialog.ordered_paths()
        if len(ordered) < 2:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Hot merge", str(OUTPUTS_DIR / "full_movie.mp4"), "Movie (*.mp4)",
        )
        if not dest:
            return
        if not dest.lower().endswith(".mp4"):
            dest += ".mp4"
        self.table_spinner.start()
        worker = Worker(concat_videos, ordered, dest)
        worker.signals.result.connect(lambda path: self._on_render_ready(path, "Hot merge"))
        worker.signals.error.connect(self._on_render_error)
        worker.signals.finished.connect(self.table_spinner.stop)
        self.thread_pool.start(worker)
        self.log.info(f"Merging {len(ordered)} episodes")

    def _fill_table(self, segments: list):
        self._filling_table = True
        self._playing_row = -1
        self._segments = list(segments or [])
        self.table.setRowCount(0)

        is_5_col = self.table.columnCount() == 5

        for i, seg in enumerate(self._segments):
            row = self.table.rowCount()
            self.table.insertRow(row)

            start = str(seg.get("start", ""))
            end = str(seg.get("end", ""))
            orig = str(seg.get("original_text") or seg.get("text") or "")
            dub = str(seg.get("translated_text") or "")
            speaker = str(seg.get("speaker") or f"Character {i % 2 + 1}")
            gender = str(seg.get("gender") or "Male")
            voice = str(seg.get("tts_voice_hint") or seg.get("voice_id") or "")
            audio_path = str(seg.get("audio_path") or "")
            audio_status = "• Done" if audio_path or seg.get("audio_status") == "Done" else "• Pending"

            if is_5_col:
                # ── 5-Column Mode: START | END | KHMER TEXT | VOICE | AUDIO STATUS ──
                # Col 0: START
                start_val = self._format_timestamp(start)
                start_item = QTableWidgetItem(start_val)
                start_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                start_item.setForeground(QBrush(QColor("#cbd5e1")))
                start_item.setToolTip(f"Start: {start}")
                self.table.setItem(row, 0, start_item)

                # Col 1: END
                end_val = self._format_timestamp(end)
                end_item = QTableWidgetItem(end_val)
                end_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                end_item.setForeground(QBrush(QColor("#cbd5e1")))
                end_item.setToolTip(f"End: {end}")
                self.table.setItem(row, 1, end_item)

                # Col 2: KHMER TEXT (EDITABLE)
                display_text = dub if dub else orig
                text_item = QTableWidgetItem(display_text)
                text_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                text_item.setForeground(QBrush(QColor("#f8fafc")))
                font = text_item.font()
                font.setPointSize(10)
                text_item.setFont(font)
                text_item.setToolTip(f"Text:\n{display_text}")
                self.table.setItem(row, 2, text_item)

                # Col 3: VOICE
                voice_label = "♂ Male" if gender.lower() == "male" else "♀ Female"
                voice_item = QTableWidgetItem(voice_label)
                voice_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                voice_color = QColor("#38bdf8") if gender.lower() == "male" else QColor("#f472b6")
                voice_item.setForeground(QBrush(voice_color))
                voice_item.setToolTip(f"Speaker: {speaker}\nGender: {gender}\nClick to toggle gender")
                self.table.setItem(row, 3, voice_item)

                # Col 4: AUDIO STATUS
                status_item = QTableWidgetItem(audio_status)
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                status_color = QColor("#10b981") if "Done" in audio_status else QColor("#94a3b8")
                status_item.setForeground(QBrush(status_color))
                status_item.setToolTip("Click to preview speech audio" if audio_path else "Pending generation")
                self.table.setItem(row, 4, status_item)

            else:
                # ── Legacy 6-Column Mode ──
                id_item = QTableWidgetItem(str(seg.get("id", i + 1)))
                id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, 0, id_item)

                start_fmt = start[3:8] if len(start) >= 8 else start
                end_fmt = end[3:8] if len(end) >= 8 else end
                time_str = f"{start_fmt}-{end_fmt}" if end_fmt else start_fmt
                time_item = QTableWidgetItem(time_str)
                time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                time_item.setForeground(QBrush(QColor("#64748b")))
                time_item.setToolTip(f"{start} --> {end}")
                self.table.setItem(row, 1, time_item)

                mark = " ●" if seg.get("pending") else ""
                char_item = QTableWidgetItem(f"● {speaker}{mark}")
                char_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                char_item.setToolTip(f"{speaker}" + (f"\nVoice: {voice}" if voice else ""))
                char_color = QColor("#f472b6") if gender == "Female" else QColor("#38bdf8")
                char_item.setForeground(QBrush(char_color))
                self.table.setItem(row, 2, char_item)

                gender_item = QTableWidgetItem(gender)
                gender_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                gender_color = QColor("#f472b6") if gender == "Female" else QColor("#38bdf8")
                gender_item.setForeground(QBrush(gender_color))
                self.table.setItem(row, 3, gender_item)

                src_item = QTableWidgetItem(orig)
                src_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                src_item.setForeground(QBrush(QColor("#94a3b8")))
                self.table.setItem(row, 4, src_item)

                dub_item = QTableWidgetItem(dub)
                dub_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                dub_item.setForeground(QBrush(QColor("#f8fafc")))
                self.table.setItem(row, 5, dub_item)

        self._fit_script_columns()
        self.table.resizeRowsToContents()
        self._filling_table = False
        self._refresh_character_filter()
        self._apply_script_filters()
        if hasattr(self, "timeline"):
            self.timeline.set_dialogue(self._segments)

    def _format_timestamp(self, val: Any) -> str:
        if isinstance(val, (int, float)):
            sec = float(val)
            m = int(sec // 60)
            s = sec % 60
            return f"{m:02d}:{s:05.2f}"
        raw = str(val or "").strip()
        if not raw:
            return "00:00.00"
        if ":" in raw:
            parts = raw.split(":")
            if len(parts) == 3:
                try:
                    m = int(parts[1])
                    s = float(parts[2].replace(",", "."))
                    return f"{m:02d}:{s:05.2f}"
                except Exception:
                    pass
            elif len(parts) == 2:
                return raw[:8]
        try:
            sec = float(raw)
            m = int(sec // 60)
            s = sec % 60
            return f"{m:02d}:{s:05.2f}"
        except Exception:
            return raw[:8]

    def _update_script_meta(self):
        n = len(self._segments)
        visible = 0
        if hasattr(self, "table"):
            visible = sum(
                1 for r in range(self.table.rowCount()) if not self.table.isRowHidden(r)
            )
        if hasattr(self, "lbl_script_count"):
            if not n:
                self.lbl_script_count.setText("")
            elif visible < n:
                self.lbl_script_count.setText(f"{visible} of {n}")
            else:
                self.lbl_script_count.setText(f"{n} line{'s' if n != 1 else ''}")
        if hasattr(self, "btn_script_export"):
            self.btn_script_export.setEnabled(n > 0)
        if hasattr(self, "script_search"):
            self.script_search.setEnabled(n > 0)
            self.script_character_filter.setEnabled(n > 0)
        has_pending = any(seg.get("pending") for seg in self._segments)
        if hasattr(self, "btn_script_pending"):
            self.btn_script_pending.setEnabled(has_pending)
        if hasattr(self, "btn_script_actions"):
            self.btn_script_actions.setEnabled(n > 0)
        if hasattr(self, "script_stack"):
            self.script_stack.setCurrentIndex(1 if n else 0)
        spinning = self.table_spinner.is_spinning() if hasattr(self, "table_spinner") else False
        if n == 0 and not spinning and not getattr(self, "_error", "") and hasattr(self, "empty_title"):
            self.empty_title.setText("No dubbed script")
            if hasattr(self, "empty_hint"):
                self.empty_hint.setText(
                    "Select a movie and dub, or Import a script (SRT / VTT / JSON)"
                )

    def _fit_script_columns(self):
        """Keep meta columns compact; Source / Dub share the remaining width."""
        if not hasattr(self, "table"):
            return
        if self.table.columnCount() == 5:
            self.table.setColumnWidth(0, 85)
            self.table.setColumnWidth(1, 85)
            self.table.setColumnWidth(3, 100)
            self.table.setColumnWidth(4, 115)
            return
        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(1, 118)
        self.table.setColumnWidth(3, 72)
        # Character: fit longest visible name, then clamp so Source/Dub stay readable.
        header = self.table.horizontalHeader()
        mode = header.sectionResizeMode(2)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        width = self.table.columnWidth(2)
        header.setSectionResizeMode(2, mode)
        self.table.setColumnWidth(2, max(96, min(148, width + 8)))

    def _refresh_character_filter(self):
        if not hasattr(self, "script_character_filter"):
            return
        current = self.script_character_filter.currentData()
        self.script_character_filter.blockSignals(True)
        self.script_character_filter.clear()
        self.script_character_filter.addItem("All characters", "all")
        for name in self._character_names():
            self.script_character_filter.addItem(name, name)
        idx = self.script_character_filter.findData(current)
        self.script_character_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.script_character_filter.blockSignals(False)

    def _apply_script_filters(self, *_args):
        if not hasattr(self, "table"):
            return
        q = (self.script_search.text() or "").strip().lower() if hasattr(self, "script_search") else ""
        character = (
            self.script_character_filter.currentData()
            if hasattr(self, "script_character_filter")
            else "all"
        ) or "all"
        for row, seg in enumerate(self._segments):
            if row >= self.table.rowCount():
                break
            hide = False
            name = str(seg.get("speaker") or "").strip()
            if character not in (None, "all") and name != character:
                hide = True
            if q and not hide:
                blob = " ".join([
                    name,
                    str(seg.get("original_text") or seg.get("text") or ""),
                    str(seg.get("translated_text") or ""),
                    str(seg.get("start") or ""),
                ]).lower()
                if q not in blob:
                    hide = True
            self.table.setRowHidden(row, hide)
        self._update_script_meta()

    def _focus_script_search(self):
        if not hasattr(self, "script_search"):
            return
        self.script_search.setFocus()
        self.script_search.selectAll()

    def _script_menu_action(self, menu: QMenu, icon_name: str, text: str, slot, *, tip: str = ""):
        act = menu.addAction(icon(icon_name, size=14), text)
        act.setIconVisibleInMenu(True)
        if tip:
            act.setToolTip(tip)
        act.triggered.connect(slot)
        return act

    def _fill_script_actions_menu(self):
        menu = getattr(self, "_script_actions_menu", None)
        if menu is None:
            return
        menu.clear()
        n = len(self._segments)
        busy = self._script_worker is not None or bool(getattr(self, "_dub_busy", False))
        has_source = bool(str(getattr(self, "selected_file", "") or "") and os.path.isfile(str(self.selected_file)))
        all_rows = list(range(n))

        self._script_menu_action(
            menu, "check_on", "Accept all pending",
            lambda: self._accept_versions(all_rows),
            tip="Keep every pending edit",
        )
        self._script_menu_action(
            menu, "undo", "Reverse all pending",
            lambda: self._reverse_versions(all_rows),
            tip="Restore the last accepted version",
        )
        menu.addSeparator()

        act_asr = self._script_menu_action(
            menu, "mic", "Retry transcript",
            self._retry_script_transcript,
            tip="Re-run ASR on the movie (starts a new dub pass)",
        )
        act_asr.setEnabled(has_source and not busy)

        act_tr = self._script_menu_action(
            menu, "globe", "Retry translate",
            lambda: self._regenerate_rows(all_rows),
            tip="Re-translate every line from the source text",
        )
        act_tr.setEnabled(n > 0 and not busy)

        act_tts = self._script_menu_action(
            menu, "volume", "Retry TTS",
            lambda: self._resynthesize_rows(all_rows),
            tip="Re-synthesize voice audio for every line",
        )
        act_tts.setEnabled(n > 0 and not busy)

        act_all = self._script_menu_action(
            menu, "refresh", "Retry all",
            self._retry_script_all,
            tip="Full redub · transcript → translate → TTS → mix",
        )
        act_all.setEnabled(has_source and not busy)

        menu.addSeparator()
        self._script_menu_action(
            menu, "sparkles", "Auto-detect gender · best voices",
            lambda: self._autodetect_genders(None, all_lines=True),
        )
        menu.addSeparator()
        self._script_menu_action(
            menu, "folder", "Import script…",
            lambda: self._import_script(),
            tip="Load lines from SRT, VTT, or JSON",
        )
        self._script_menu_action(
            menu, "download", "Export script…",
            lambda: self.open_export_dialog(script_only=True),
        )

    def _current_script_task_id(self) -> int:
        viewing = int(getattr(self, "_viewing_task", -1) or -1)
        if viewing >= 0 and hasattr(self, "_task_by_id") and self._task_by_id(viewing):
            return viewing
        source = str(getattr(self, "selected_file", "") or "")
        if not source:
            return -1
        for task in getattr(self, "_tasks", []) or []:
            if str(task.get("source") or "") == source:
                return int(task.get("id") or -1)
        return -1

    def _retry_script_transcript(self):
        """Re-run ASR by restarting the dub job for the current movie."""
        self._retry_script_all()

    def _retry_script_all(self):
        """Full pipeline retry for the movie tied to this script."""
        if bool(getattr(self, "_dub_busy", False)):
            self.log.warn("Dub already running")
            return
        tid = self._current_script_task_id()
        if tid >= 0 and hasattr(self, "_retry_task"):
            self._retry_task(tid)
            self.log.info("Retry all · queued full dub pass")
            return
        source = str(getattr(self, "selected_file", "") or "")
        if source and os.path.isfile(source) and hasattr(self, "_begin_dub_jobs"):
            self._begin_dub_jobs([source])
            self.log.info("Retry all · starting dub")
            return
        self.log.warn("Retry all · no movie source for this script")

    def _resynthesize_rows(self, rows: list[int]):
        """Re-speak selected lines with their TTS voices and refresh the timeline."""
        rows = [row for row in rows if 0 <= row < len(self._segments)]
        if not rows or self._script_worker is not None:
            return
        lead, co_star = self._primary_voices()
        sync_mode = (
            self.combo_sync_mode.currentData()
            if hasattr(self, "combo_sync_mode")
            else "stretch"
        ) or "stretch"
        work = []
        for row in rows:
            seg = self._segments[row]
            text = str(seg.get("translated_text") or seg.get("text") or "").strip()
            voice = str(seg.get("tts_voice_hint") or seg.get("voice_id") or lead or co_star or "")
            if not text or not voice:
                continue
            work.append({
                "row": row,
                "text": text,
                "voice": voice,
                "start": seg.get("start", ""),
                "end": seg.get("end", ""),
                "start_sec": seg.get("start_sec"),
                "end_sec": seg.get("end_sec"),
            })
        if not work:
            self.log.warn("Retry TTS · no speakable lines")
            return

        self.table_spinner.start()
        self.log.info(f"Retry TTS · {len(work)} line(s)")

        def _job(items=work, mode=sync_mode, progress_callback=None):
            from claynext.adapters.ffmpeg_service import fit_duration

            folder = CACHE_DIR / "script_tts"
            folder.mkdir(parents=True, exist_ok=True)
            if mode == "natural":
                min_t, max_t = 1.0, 1.0
            elif mode == "subtle":
                min_t, max_t = 0.85, 1.25
            else:
                min_t, max_t = 0.65, 1.85
            out = []
            total = len(items)
            for i, item in enumerate(items):
                if progress_callback:
                    progress_callback(int((i / max(1, total)) * 100), f"TTS {i + 1}/{total}")
                digest = hashlib.sha1(
                    f"{item['voice']}\n{item['text']}".encode("utf-8")
                ).hexdigest()[:10]
                raw = str(folder / f"row_{item['row']}_{digest}.mp3")
                fitted = str(folder / f"row_{item['row']}_{digest}_fit.wav")
                TTSEngine.synthesize(item["text"], item["voice"], raw)
                start = float(item.get("start_sec") or timestamp_to_sec(item.get("start", "")))
                end = float(item.get("end_sec") or timestamp_to_sec(item.get("end", "")))
                slot = max(0.15, end - start) if end > start else 2.0
                fit_duration(raw, fitted, slot, min_tempo=min_t, max_tempo=max_t, pad_or_trim=True)
                out.append({
                    "row": item["row"],
                    "audio_path": fitted,
                    "start_ms": int(start * 1000),
                    "duration_sec": round(slot, 2),
                    "voice_id": item["voice"],
                })
            if progress_callback:
                progress_callback(100, "TTS ready")
            return out

        worker = Worker(_job)
        worker.signals.result.connect(self._on_resynth_ready)
        worker.signals.error.connect(self._on_resynth_error)
        worker.signals.finished.connect(self._on_resynth_finished)
        self._script_worker = worker
        self.thread_pool.start(worker)

    def _on_resynth_ready(self, result):
        rows_updated: list[int] = []
        for item in result if isinstance(result, list) else []:
            if not isinstance(item, dict):
                continue
            row = int(item.get("row", -1))
            if not (0 <= row < len(self._segments)):
                continue
            seg = self._segments[row]
            path = str(item.get("audio_path") or "")
            if path and os.path.isfile(path):
                seg["audio_path"] = path
            if item.get("start_ms") is not None:
                seg["start_ms"] = int(item["start_ms"])
            if item.get("duration_sec") is not None:
                seg["duration_sec"] = float(item["duration_sec"])
                seg["duration"] = f"{float(item['duration_sec']):.1f}s"
            voice = str(item.get("voice_id") or "")
            if voice:
                seg["voice_id"] = voice
                seg["tts_voice_hint"] = voice
            rows_updated.append(row)
        if rows_updated:
            self._refresh_row(rows_updated[0])
            self.log.success(f"Retry TTS · {len(rows_updated)} line(s) updated")
        else:
            self.log.warn("Retry TTS · no audio written")

    def _on_resynth_error(self, message: str, _stack: str):
        self.log.error(f"Retry TTS failed · {message}")
        QMessageBox.warning(self, "Retry TTS", message)

    def _on_resynth_finished(self):
        self._script_worker = None
        self.table_spinner.stop()

    def _visible_rows(self) -> list[int]:
        if not hasattr(self, "table"):
            return list(range(len(self._segments)))
        return [
            row for row in range(min(self.table.rowCount(), len(self._segments)))
            if not self.table.isRowHidden(row)
        ]

    def _selected_rows(self) -> list[int]:
        rows = sorted({item.row() for item in self.table.selectedIndexes()})
        return [row for row in rows if 0 <= row < len(self._segments)]

    def _pending_targets(self, rows: list[int] | None = None) -> list[int]:
        chosen = rows if rows is not None else (self._selected_rows() or self._visible_rows())
        return [row for row in chosen if self._segments[row].get("pending")]

    def _copy_script_lines(self, kind: str = "dub"):
        rows = self._selected_rows() or self._visible_rows()
        lines: list[str] = []
        for row in rows:
            if hasattr(self, "table") and self.table.isRowHidden(row):
                continue
            seg = self._segments[row]
            dub = str(seg.get("translated_text") or "").strip()
            source = str(seg.get("original_text") or seg.get("text") or "").strip()
            start = str(seg.get("start") or "")
            end = str(seg.get("end") or "")
            if kind == "source":
                if source:
                    lines.append(source)
            elif kind == "times":
                text = dub or source
                if text:
                    lines.append(f"{start} → {end}  {text}".strip())
            elif kind == "both":
                if source or dub:
                    lines.append(f"{source}\t{dub}".strip())
            else:
                if dub:
                    lines.append(dub)
                elif source:
                    lines.append(source)
        if not lines:
            self.log.warn("Nothing to copy")
            return
        QApplication.clipboard().setText("\n".join(lines))
        self.log.success(f"Copied {len(lines)} line(s)")

    def _jump_pending(self, direction: int = 1):
        if not self._segments:
            return
        current = self.table.currentRow()
        if current < 0:
            current = 0 if direction > 0 else len(self._segments) - 1
        count = len(self._segments)
        for step in range(1, count + 1):
            row = (current + direction * step) % count
            if self._segments[row].get("pending") and not self.table.isRowHidden(row):
                self.table.selectRow(row)
                item = self.table.item(row, 0)
                if item:
                    self.table.scrollToItem(item)
                return
        self.log.info("No pending versions in the filtered list")

    def _character_names(self) -> list[str]:
        names: list[str] = []
        for seg in self._segments:
            name = str(seg.get("speaker") or "").strip()
            if name and name not in names:
                names.append(name)
        return names

    def _cast_voice_choices(self) -> list[dict]:
        """TTS voices for the target language — used as character cast options."""
        from claynext.models.gender_voices import voices_for_lang

        return voices_for_lang(self._voice_lang())

    def _characters(self) -> list[str]:
        """Character labels: current cast, then TTS voice names for this language."""
        names = self._character_names()
        for voice in self._cast_voice_choices():
            label = str(voice.get("label") or "")
            if label and label not in names:
                names.append(label)
        if not names:
            lead, co = self._primary_voices()
            from claynext.models.gender_voices import voice_display_name
            for vid in (lead, co):
                if vid:
                    label = voice_display_name(vid)
                    if label not in names:
                        names.append(label)
        return names

    def _voice_id_for_label(self, label: str) -> str:
        for voice in self._cast_voice_choices():
            if voice.get("label") == label:
                return str(voice.get("id") or "")
        # Match existing segment by speaker name.
        for seg in self._segments:
            if str(seg.get("speaker") or "") == label:
                return str(seg.get("tts_voice_hint") or seg.get("voice_id") or "")
        from claynext.models.gender_voices import voice_display_name
        lead, co = self._primary_voices()
        for vid in (lead, co):
            if vid and voice_display_name(vid) == label:
                return vid
        return ""

    def _voice_lang(self) -> str:
        return str(getattr(self, "combo_lang", None) and self.combo_lang.currentText() or "")

    def _primary_voices(self) -> tuple[str, str]:
        lead = self.combo_voice.currentData() or ""
        co_star = self.combo_voice_sec.currentData() or lead
        return str(lead or ""), str(co_star or lead or "")

    def _voice_for_character(self, name: str, skip: int = -1, gender: str = "") -> str:
        from claynext.models.gender_voices import pick_voice_for_gender

        lead, co_star = self._primary_voices()
        for index, seg in enumerate(self._segments):
            if index == skip:
                continue
            if str(seg.get("speaker") or "") == name:
                voice = str(seg.get("tts_voice_hint") or seg.get("voice_id") or "")
                if voice:
                    return voice
        if gender:
            return pick_voice_for_gender(
                gender, primary=lead, secondary=co_star, lang=self._voice_lang(),
            ) or lead
        if name.strip().endswith("2"):
            return co_star
        return lead

    def _reassign_character_voices(self, *, force_redetect: bool = False):
        from claynext.models.gender_voices import assign_gender_and_voices

        lead, co_star = self._primary_voices()
        assign_gender_and_voices(
            self._segments,
            primary_voice=lead,
            secondary_voice=co_star,
            lang=self._voice_lang(),
            force_redetect=force_redetect,
        )

    def _propose_line(self, row: int, changes: dict):
        seg = self._segments[row]
        if not seg.get("pending"):
            seg["committed"] = _line_snapshot(seg)
        seg.update(changes)
        if "gender" in changes:
            seg["gender_manual"] = True
        # If speaker changed without an explicit voice, map TTS name → voice id.
        if changes.get("speaker") and not changes.get("tts_voice_hint") and not changes.get("voice_id"):
            mapped = self._voice_id_for_label(str(changes["speaker"]))
            if mapped:
                seg["tts_voice_hint"] = mapped
                seg["voice_id"] = mapped
        if (changes.get("speaker") or "gender" in changes) and not seg.get("tts_voice_hint"):
            gender = str(seg.get("gender") or "")
            voice = self._voice_for_character(
                str(seg.get("speaker") or ""), skip=row, gender=gender,
            )
            if voice:
                seg["tts_voice_hint"] = voice
                seg["voice_id"] = voice
        seg["pending"] = True

    def _refresh_row(self, row: int):
        self._fill_table(self._segments)
        if 0 <= row < self.table.rowCount():
            self.table.selectRow(row)

    def _script_menu(self, pos):
        row = self.table.indexAt(pos).row()
        if row < 0 or row >= len(self._segments):
            return
        if row not in self._selected_rows():
            self.table.selectRow(row)
        selected = self._selected_rows() or [row]
        pending = self._pending_targets(selected)
        all_pending = self._pending_targets(self._visible_rows())
        n = len(selected)
        menu = QMenu(self.table)
        menu.setObjectName("media_lib_menu")

        play = menu.addAction("Play from this line")
        play.triggered.connect(lambda: self._play_row(row, 0))
        edit = menu.addAction("Edit line…")
        edit.triggered.connect(lambda: self._edit_line(row))

        characters = menu.addMenu("Change character")
        characters.setObjectName("media_lib_menu")
        # Prefer TTS voice cast list (label + voice id).
        cast = self._cast_voice_choices()
        if cast:
            for voice in cast:
                label = str(voice.get("label") or "")
                vid = str(voice.get("id") or "")
                gender = str(voice.get("gender") or "")
                text = f"{label} · {gender}" if gender and gender != "Unknown" else label
                act = characters.addAction(text)
                act.triggered.connect(
                    lambda _checked=False, speaker=label, voice_id=vid, rows=list(selected):
                    self._change_characters(rows, speaker, voice_id=voice_id)
                )
        else:
            for name in self._characters():
                act = characters.addAction(name)
                act.triggered.connect(
                    lambda _checked=False, speaker=name, rows=list(selected):
                    self._change_characters(rows, speaker)
                )

        gender_menu = menu.addMenu("Set gender")
        gender_menu.setObjectName("media_lib_menu")
        for label in ("Female", "Male", "Unknown"):
            act = gender_menu.addAction(label)
            act.triggered.connect(
                lambda _checked=False, g=label, rows=list(selected):
                self._change_genders(rows, g)
            )
        gender_menu.addSeparator()
        act_auto = gender_menu.addAction("Auto-detect (selected)")
        act_auto.triggered.connect(lambda: self._autodetect_genders(selected))
        act_auto_all = gender_menu.addAction("Auto-detect all · best voices")
        act_auto_all.triggered.connect(lambda: self._autodetect_genders(None, all_lines=True))

        regen_label = "Regenerate translation" if n == 1 else f"Regenerate {n} lines"
        regen = menu.addAction(regen_label)
        regen.setEnabled(self._script_worker is None)
        regen.triggered.connect(lambda: self._regenerate_rows(selected))

        menu.addSeparator()
        accept = menu.addAction(
            "Accept version" if len(pending) <= 1 else f"Accept {len(pending)} versions"
        )
        accept.setEnabled(bool(pending))
        accept.triggered.connect(lambda: self._accept_versions(pending))
        reverse = menu.addAction(
            "Reverse version" if len(pending) <= 1 else f"Reverse {len(pending)} versions"
        )
        reverse.setEnabled(bool(pending))
        reverse.triggered.connect(lambda: self._reverse_versions(pending))
        if all_pending and set(all_pending) != set(pending):
            accept_all = menu.addAction(f"Accept all pending ({len(all_pending)})")
            accept_all.triggered.connect(lambda: self._accept_versions(all_pending))
            reverse_all = menu.addAction(f"Reverse all pending ({len(all_pending)})")
            reverse_all.triggered.connect(lambda: self._reverse_versions(all_pending))
        next_pending = menu.addAction("Next pending version")
        next_pending.setEnabled(bool(all_pending))
        next_pending.triggered.connect(lambda: self._jump_pending(1))

        menu.addSeparator()
        copy_menu = menu.addMenu("Copy")
        copy_menu.setObjectName("media_lib_menu")
        copy_menu.addAction("Dub text", lambda: self._copy_script_lines("dub"))
        copy_menu.addAction("Source text", lambda: self._copy_script_lines("source"))
        copy_menu.addAction("Source + dub", lambda: self._copy_script_lines("both"))
        copy_menu.addAction("With times", lambda: self._copy_script_lines("times"))

        menu.addSeparator()
        export_sel = menu.addAction("Export selected as SRT…")
        export_sel.setEnabled(bool(selected))
        export_sel.triggered.connect(lambda: self._export_selected_srt(selected))
        find = menu.addAction("Find in script…")
        find.triggered.connect(self._focus_script_search)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _change_characters(self, rows: list[int], speaker: str, voice_id: str = ""):
        changed = 0
        focus = -1
        vid = voice_id or self._voice_id_for_label(speaker)
        for row in rows:
            if not (0 <= row < len(self._segments)):
                continue
            changes: dict = {"speaker": speaker}
            if vid:
                changes["tts_voice_hint"] = vid
                changes["voice_id"] = vid
                from claynext.models.gender_voices import voice_entry_gender
                g = voice_entry_gender(vid)
                if g != "Unknown":
                    changes["gender"] = g
                    changes["gender_manual"] = True
            self._propose_line(row, changes)
            focus = row if focus < 0 else focus
            changed += 1
        if changed:
            self._refresh_row(focus)
            self.log.info(f"{changed} line(s) · {speaker}" + (f" · {vid}" if vid else "") + " · pending")

    def _change_genders(self, rows: list[int], gender: str):
        from claynext.models.gender_voices import apply_manual_gender

        lead, co_star = self._primary_voices()
        apply_manual_gender(
            self._segments,
            rows,
            gender,
            primary_voice=lead,
            secondary_voice=co_star,
            lang=self._voice_lang(),
            apply_to_character=True,
        )
        for row in rows:
            if 0 <= row < len(self._segments):
                seg = self._segments[row]
                if not seg.get("pending"):
                    seg["committed"] = _line_snapshot({**seg, "gender": gender, "gender_manual": False})
                seg["pending"] = True
        focus = rows[0] if rows else 0
        self._refresh_row(focus)
        self.log.info(f"{len(rows)} line(s) · gender {gender} · voices updated")

    def _autodetect_genders(self, rows: list[int] | None, *, all_lines: bool = False):
        targets = list(range(len(self._segments))) if all_lines else list(rows or [])
        for row in targets:
            if not (0 <= row < len(self._segments)):
                continue
            self._segments[row].pop("gender_manual", None)

        # Prefer Common-Voice wav2vec2 on source audio when torch is installed.
        audio = ""
        for key in ("selected_file", "_media_path"):
            candidate = getattr(self, key, None)
            if candidate and os.path.isfile(str(candidate)):
                audio = str(candidate)
                break
        comps = getattr(self, "_compositions", None) or []
        index = getattr(self, "_composition_index", -1)
        if not audio and 0 <= index < len(comps):
            source = str(comps[index].get("source") or "")
            if source and os.path.isfile(source):
                audio = source

        def _job(progress_callback=None):
            from claynext.models.gender_audio import enrich_segments_with_audio_gender, gender_model_available
            from claynext.models.gender_voices import assign_gender_and_voices

            segs = list(self._segments)
            used_audio = False
            if audio and gender_model_available():
                enrich_segments_with_audio_gender(
                    segs, audio, progress_callback=progress_callback,
                )
                used_audio = True
            lead, co_star = self._primary_voices()
            assign_gender_and_voices(
                segs,
                primary_voice=lead,
                secondary_voice=co_star,
                lang=self._voice_lang(),
                force_redetect=True,
            )
            return {"segments": segs, "audio": used_audio}

        if getattr(self, "_script_worker", None) is not None:
            return
        self.table_spinner.start()
        worker = Worker(_job)
        worker.signals.result.connect(
            lambda result, focus=(targets[0] if targets else 0): self._on_gender_detect_ready(result, focus)
        )
        worker.signals.error.connect(lambda err, _tb: self._on_gender_detect_error(err))
        worker.signals.finished.connect(self.table_spinner.stop)
        self._script_worker = worker
        self.thread_pool.start(worker)
        self.log.info("Detecting gender from dialogue audio…")

    def _on_gender_detect_ready(self, result, focus: int):
        self._script_worker = None
        if not isinstance(result, dict):
            return
        self._segments = list(result.get("segments") or self._segments)
        self._refresh_row(focus)
        if result.get("audio"):
            self.log.success("Common-Voice gender · TTS voices matched per character")
        else:
            self.log.success(
                "Gender auto-detect (text cues) · install uv sync --extra gender for audio model"
            )

    def _on_gender_detect_error(self, err):
        self._script_worker = None
        self.log.info(f"Gender detect fallback · {err}")
        self._reassign_character_voices(force_redetect=True)
        self._refresh_row(0)

    def _export_selected_srt(self, rows: list[int]):
        lines = []
        for row in rows:
            if 0 <= row < len(self._segments):
                lines.append(self._segments[row])
        if not lines:
            QMessageBox.information(self, "Export", "No lines selected.")
            return
        default_name = f"dubbed_selection_{datetime.now().strftime('%Y%m%d_%H%M%S')}.srt"
        if self.selected_file:
            stem = os.path.splitext(os.path.basename(self.selected_file))[0]
            default_name = f"{stem}_selection.srt"
        path = str(OUTPUTS_DIR / default_name)
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export selected SRT", path, "SubRip Subtitles (*.srt)"
        )
        if not file_path:
            return
        try:
            export_segments(file_path, "srt", lines)
            self.log.success(f"Exported {len(lines)} line(s) → {os.path.basename(file_path)}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not export SRT: {e}")

    def _edit_line(self, row: int):
        if not (0 <= row < len(self._segments)):
            return
        dialog = LineEditDialog(
            self._segments[row],
            self._cast_voice_choices(),
            lang=self._voice_lang(),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._propose_line(row, dialog.values())
        self._refresh_row(row)
        self.log.info(f"Line {row + 1} edited · pending version")

    def _regenerate_rows(self, rows: list[int]):
        rows = [row for row in rows if 0 <= row < len(self._segments)]
        if not rows or self._script_worker is not None:
            return
        lines = []
        for row in rows:
            seg = self._segments[row]
            lines.append({
                "id": seg.get("id", row + 1),
                "text": seg.get("original_text") or seg.get("text") or "",
                "start": seg.get("start", ""),
                "end": seg.get("end", ""),
                "speaker": seg.get("speaker") or "",
            })
        self._regen_rows = rows
        self.table_spinner.start()
        worker = Worker(
            TranslateEngine.translate_subtitles,
            lines,
            self.combo_lang.currentText(),
            source_lang=self.combo_source_lang.currentText(),
            translator=self.combo_translator.currentData() or "auto",
            ollama_model=self.edit_ollama.text().strip() or "qwen2.5:7b",
        )
        worker.signals.result.connect(self._on_regen_ready)
        worker.signals.error.connect(self._on_regen_error)
        worker.signals.finished.connect(self._on_regen_finished)
        self._script_worker = worker
        self.thread_pool.start(worker)
        self.log.info(f"Regenerating {len(rows)} line(s)")

    def _on_regen_ready(self, result):
        rows = list(self._regen_rows)
        lines = result if isinstance(result, list) else []
        changed = 0
        for row, line in zip(rows, lines):
            if not isinstance(line, dict) or not (0 <= row < len(self._segments)):
                continue
            text = str(line.get("translated_text") or "").strip()
            if not text or text == str(self._segments[row].get("translated_text") or "").strip():
                continue
            self._propose_line(row, {"translated_text": text})
            changed += 1
        focus = rows[0] if rows else -1
        self._refresh_row(focus)
        if changed:
            self.log.success(f"{changed} pending version(s) · right-click to Accept or Reverse")
        else:
            self.log.info("Regenerate kept the current line")

    def _on_regen_error(self, message: str, _stack: str):
        self.log.error(f"Regenerate failed · {message}")
        QMessageBox.warning(self, "Regenerate", message)

    def _on_regen_finished(self):
        self._script_worker = None
        self._regen_rows = []
        self.table_spinner.stop()

    def _accept_versions(self, rows: list[int] | None = None):
        targets = self._pending_targets(rows)
        for row in targets:
            seg = self._segments[row]
            seg["committed"] = _line_snapshot(seg)
            seg["pending"] = False
        if targets:
            self._refresh_row(targets[0])
            self.log.success(f"Accepted {len(targets)} version(s)")

    def _reverse_versions(self, rows: list[int] | None = None):
        targets = self._pending_targets(rows)
        for row in targets:
            seg = self._segments[row]
            previous = seg.get("committed")
            if isinstance(previous, dict):
                seg.update(previous)
            seg["pending"] = False
        if targets:
            self._refresh_row(targets[0])
            self.log.info(f"Reversed {len(targets)} version(s)")

    def _play_row(self, row: int, _col: int):
        if row < 0 or row >= len(self._segments):
            return
        sec = timestamp_to_sec(self._segments[row].get("start", ""))
        self.preview.seek_ms(int(sec * 1000))
        self.preview.player.play()

    def _set_error_style(self, error: bool):
        flag = "true" if error else "false"
        for w in (self.empty_title, self.empty_hint):
            w.setProperty("error", flag)
            w.style().unpolish(w)
            w.style().polish(w)

    def _show_error(self, title: str, hint: str):
        self._error = hint
        self._fill_table([])
        self.empty_title.setText(title)
        self.empty_hint.setText(hint)
        self._set_error_style(True)
        self.script_stack.setCurrentIndex(0)
        self._focus_script_shelf()

    def _clear_error(self):
        self._error = ""
        self._set_error_style(False)
        self.empty_title.setText("No dubbed script")
        self.empty_hint.setText(
            "Select a movie and dub, or Import a script (SRT / VTT / JSON)"
        )

