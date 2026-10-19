"""Edit-line dialog and expression-tag chips."""
from __future__ import annotations

import hashlib
import os

from PySide6.QtCore import Qt, QUrl, QThreadPool
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDialog,
    QTextEdit, QComboBox, QDialogButtonBox, QSizePolicy, QToolButton, QGridLayout,
)

from claynext.gui.icons import icon
from claynext.models.tts_service import TTSEngine
from claynext.models.tts_expression import EXPRESSION_CHIPS
from claynext.gui.worker import Worker
from claynext.gui.components.spinner import Spinner
from claynext.utils.config import CACHE_DIR


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

