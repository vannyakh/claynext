"""Edit-line dialog, speech pacing HUD, and expression-tag chips."""
from __future__ import annotations

import hashlib
import os
import re

from PySide6.QtCore import Qt, QUrl, QThreadPool, QTimer
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDialog,
    QTextEdit, QComboBox, QDialogButtonBox, QSizePolicy, QToolButton, QGridLayout,
    QFrame, QSlider,
)

from claynext.constants.theme_constants import COLOR_TEXT_MUTED, COLOR_TEXT_SUB
from claynext.gui.icons import icon
from claynext.models.character_intel import STYLES, set_line_style
from claynext.models.tts_service import TTSEngine
from claynext.models.tts_expression import EXPRESSION_CHIPS
from claynext.models.dubbing_service import timestamp_to_sec
from claynext.models.translate_service import TranslateEngine
from claynext.adapters.ffmpeg_service import fit_duration, master_voiceover_track
from claynext.gui.worker import Worker
from claynext.gui.components.controls.spinner import Spinner
from claynext.utils.config import CACHE_DIR


class _TagHighlighter(QSyntaxHighlighter):
    """Expression tags in the line editor stay gray. The spoken words stay bright."""

    _TAG = re.compile(r"\[[^\[\]]+\]|\{[^{}]+\}")

    def __init__(self, document):
        super().__init__(document)
        self._fmt = QTextCharFormat()
        self._fmt.setForeground(QColor("#64748b"))

    def highlightBlock(self, text: str):
        for match in self._TAG.finditer(text or ""):
            self.setFormat(match.start(), match.end() - match.start(), self._fmt)


def _preview_cache_path(voice_id: str, text: str, delivery: str = "") -> str:
    folder = CACHE_DIR / "line_preview"
    folder.mkdir(parents=True, exist_ok=True)
    stem = "".join(ch if ch.isalnum() else "_" for ch in voice_id) or "voice"
    digest = hashlib.sha1(f"{voice_id}\n{text}\n{delivery}".encode("utf-8")).hexdigest()[:10]
    return str(folder / f"{stem}_{digest}.mp3")


def _fitted_preview_cache_path(voice_id: str, text: str, slot_dur: float, delivery: str = "") -> str:
    folder = CACHE_DIR / "line_preview"
    folder.mkdir(parents=True, exist_ok=True)
    stem = "".join(ch if ch.isalnum() else "_" for ch in voice_id) or "voice"
    digest = hashlib.sha1(f"{voice_id}\n{text}\n{slot_dur:.2f}\n{delivery}".encode("utf-8")).hexdigest()[:10]
    return str(folder / f"{stem}_{digest}_fit.wav")


def performance_summary(perf: dict | None) -> str:
    """One-line delivery read-out for tooltips: style · intensity · confidence."""
    if not isinstance(perf, dict) or not perf.get("style"):
        return ""
    style = str(perf.get("style") or "neutral")
    intensity = int(round(float(perf.get("intensity") or 0) * 100))
    conf = perf.get("confidence") or {}
    if perf.get("manual"):
        tail = "set by editor"
    else:
        tail = f"{int(round(float(conf.get('overall') or conf.get('emotion') or 0) * 100))}% confidence"
    return f"{style} · {intensity}% · {tail}"


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
    """Edit one dubbed line with real-time speech pacing and audio preview."""

    def __init__(
        self,
        seg: dict,
        cast_voices: list[dict],
        *,
        lang: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Edit line · Studio Speech Sync")
        self.setMinimumWidth(520)
        self._seg = dict(seg or {})
        self._lang = lang or ""
        self._cast = list(cast_voices or [])
        self._preview_worker = None
        self._fit_ai_worker = None
        self._preview_mode = ""

        start = float(seg.get("start_sec") or timestamp_to_sec(str(seg.get("start", ""))))
        end = float(seg.get("end_sec") or timestamp_to_sec(str(seg.get("end", ""))))
        self._slot_dur = max(0.15, end - start) if end > start else float(seg.get("duration_sec") or 2.0)
        self._quota = TranslateEngine.estimate_speech_quota(self._slot_dur, self._lang)

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._audio.setVolume(0.95)
        self._player.setAudioOutput(self._audio)
        self._player.mediaStatusChanged.connect(self._on_preview_status)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        source_label = QLabel("Source dialogue")
        source_label.setObjectName("asr_field_label")
        self.source = QTextEdit()
        self.source.setObjectName("dub_setting_field")
        self.source.setPlainText(str(seg.get("original_text") or seg.get("text") or ""))
        self.source.setFixedHeight(68)

        dub_hdr = QHBoxLayout()
        dub_hdr.setSpacing(6)
        dub_label = QLabel("Dubbed translation")
        dub_label.setObjectName("asr_field_label")
        dub_hdr.addWidget(dub_label)
        dub_hdr.addStretch(1)

        self.btn_fit_ai = QPushButton("✨ Fit to Slot (AI)")
        self.btn_fit_ai.setObjectName("dub_props_chip")
        self.btn_fit_ai.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fit_ai.setToolTip("Re-phrase with AI to fit the natural speaking slot duration")
        self.btn_fit_ai.clicked.connect(self._fit_line_with_ai)
        dub_hdr.addWidget(self.btn_fit_ai)

        self.dub = QTextEdit()
        self.dub.setObjectName("dub_setting_field")
        self.dub.setPlainText(str(seg.get("translated_text") or ""))
        self.dub.setFixedHeight(92)
        self._tag_highlighter = _TagHighlighter(self.dub.document())
        self.dub.setPlaceholderText(
            'Use tags for delivery, e.g. [laugh] I can\'t believe it! [sigh] What a mess.'
        )

        # Real-time Speech Pacing HUD Card
        self.pacing_hud = QFrame()
        self.pacing_hud.setObjectName("script_pacing_hud")
        self.pacing_hud.setStyleSheet("""
            QFrame#script_pacing_hud {
                background: #0d1522;
                border: 1px solid #1e2c3f;
                border-radius: 6px;
            }
        """)
        hud_lay = QHBoxLayout(self.pacing_hud)
        hud_lay.setContentsMargins(8, 5, 8, 5)
        hud_lay.setSpacing(10)

        self.lbl_slot_dur = QLabel(f"⏱ {self._slot_dur:.2f}s slot")
        self.lbl_slot_dur.setStyleSheet("color: #94a3b8; font-weight: 600; font-size: 11px;")
        hud_lay.addWidget(self.lbl_slot_dur)

        self.lbl_beats_count = QLabel(f"Beats: 0 / {self._quota['target']}")
        self.lbl_beats_count.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        hud_lay.addWidget(self.lbl_beats_count)

        hud_lay.addStretch(1)

        self.lbl_pacing_badge = QLabel("Optimal")
        self.lbl_pacing_badge.setStyleSheet("""
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
            background: rgba(16, 185, 129, 0.15);
            color: #10b981;
            border: 1px solid rgba(16, 185, 129, 0.3);
        """)
        hud_lay.addWidget(self.lbl_pacing_badge)

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
        self.btn_preview_voice.setToolTip("Preview raw TTS voice sample")
        self.btn_preview_voice.clicked.connect(self._preview_voice_sample)
        self.btn_preview_voice.setFixedSize(30, 30)

        self.btn_preview_line = QToolButton()
        self.btn_preview_line.setObjectName("media_lib_icon_btn")
        self.btn_preview_line.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_preview_line.setIcon(icon("volume", color="#e7ecf3", size=14))
        self.btn_preview_line.setToolTip("Preview line (natural speech pace)")
        self.btn_preview_line.clicked.connect(lambda: self._preview_line(fitted=False))
        self.btn_preview_line.setFixedSize(30, 30)

        self.btn_preview_fitted = QToolButton()
        self.btn_preview_fitted.setObjectName("media_lib_icon_btn")
        self.btn_preview_fitted.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_preview_fitted.setIcon(icon("sparkles", color="#38bdf8", size=14))
        self.btn_preview_fitted.setToolTip("Preview line fitted to slot duration (exact movie timing + studio mastering)")
        self.btn_preview_fitted.clicked.connect(lambda: self._preview_line(fitted=True))
        self.btn_preview_fitted.setFixedSize(30, 30)

        self.preview_spinner = Spinner(size=14)
        char_row.addWidget(self.character, 1)
        char_row.addWidget(self.btn_preview_voice)
        char_row.addWidget(self.btn_preview_line)
        char_row.addWidget(self.btn_preview_fitted)
        char_row.addWidget(self.preview_spinner)

        gender_label = QLabel("Gender")
        gender_label.setObjectName("asr_field_label")
        self.gender = QComboBox()
        self.gender.setObjectName("asr_option_combo")
        self.gender.setEditable(False)
        self.gender.addItems(["Female", "Male", "Unknown"])
        g_idx = self.gender.findText(str(seg.get("gender") or "Unknown"))
        self.gender.setCurrentIndex(g_idx if g_idx >= 0 else 2)

        perf = seg.get("performance") if isinstance(seg.get("performance"), dict) else {}
        self._perf_initial = (
            str(perf.get("style") or "neutral"),
            int(round(float(perf.get("intensity", 0.5) or 0) * 100)),
        )
        perf_label = QLabel("Performance · delivery & intensity")
        perf_label.setObjectName("asr_field_label")
        perf_row = QHBoxLayout()
        perf_row.setSpacing(8)
        self.perf_style = QComboBox()
        self.perf_style.setObjectName("asr_option_combo")
        for style in STYLES:
            self.perf_style.addItem(style.capitalize(), style)
        s_idx = self.perf_style.findData(self._perf_initial[0])
        self.perf_style.setCurrentIndex(s_idx if s_idx >= 0 else 0)
        self.perf_intensity = QSlider(Qt.Orientation.Horizontal)
        self.perf_intensity.setRange(0, 100)
        self.perf_intensity.setValue(self._perf_initial[1])
        self.perf_intensity.setToolTip("Intensity of the delivery (0–100%)")
        self.perf_intensity_label = QLabel(f"{self._perf_initial[1]}%")
        self.perf_intensity_label.setMinimumWidth(34)
        self.perf_intensity_label.setStyleSheet(f"color: {COLOR_TEXT_SUB}; font-size: 11px;")
        self.perf_intensity.valueChanged.connect(lambda v: self.perf_intensity_label.setText(f"{v}%"))
        perf_row.addWidget(self.perf_style, 1)
        perf_row.addWidget(self.perf_intensity, 2)
        perf_row.addWidget(self.perf_intensity_label)
        self.perf_info = QLabel(self._perf_info_text(perf))
        self.perf_info.setWordWrap(True)
        self.perf_info.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")

        self.preview_status = QLabel("")
        self.preview_status.setObjectName("dub_switch_hint")
        self.preview_status.setWordWrap(True)

        lay.addWidget(source_label)
        lay.addWidget(self.source)
        lay.addLayout(dub_hdr)
        lay.addWidget(self.dub)
        lay.addWidget(self.pacing_hud)
        lay.addWidget(expr_hint)
        lay.addWidget(chips)
        lay.addWidget(char_label)
        lay.addLayout(char_row)
        lay.addWidget(gender_label)
        lay.addWidget(self.gender)
        lay.addWidget(perf_label)
        lay.addLayout(perf_row)
        lay.addWidget(self.perf_info)
        lay.addWidget(self.preview_status)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        # Debounced pacing calculation
        self._hud_timer = QTimer(self)
        self._hud_timer.setSingleShot(True)
        self._hud_timer.setInterval(120)
        self._hud_timer.timeout.connect(self._update_pacing_hud)
        self.dub.textChanged.connect(self._hud_timer.start)

        self._on_cast_changed()
        self._update_pacing_hud()

    @staticmethod
    def _perf_info_text(perf: dict) -> str:
        if not perf:
            return "No performance plan yet · the planner runs during the dub."
        parts = [performance_summary(perf)]
        target = perf.get("target_duration_sec")
        if target:
            pauses = float(perf.get("pause_before_sec") or 0), float(perf.get("pause_after_sec") or 0)
            parts.append(f"target {float(target):.2f}s · pauses {pauses[0]:.2f}s / {pauses[1]:.2f}s")
        hints = [str(h.get("text") or "") for h in perf.get("pronunciation") or [] if isinstance(h, dict)]
        if hints:
            parts.append("pronounce: " + ", ".join(hints[:4]))
        evidence = [str(e) for e in perf.get("evidence") or []][:2]
        if evidence:
            parts.append("why: " + "; ".join(evidence))
        return "\n".join(p for p in parts if p)

    def _performance_values(self) -> dict | None:
        """The line's performance, marked manual only when the editor changed it."""
        style = str(self.perf_style.currentData() or "neutral")
        level = int(self.perf_intensity.value())
        current = self._seg.get("performance") if isinstance(self._seg.get("performance"), dict) else None
        if (style, level) == self._perf_initial and current is not None:
            return dict(current)
        if (style, level) == self._perf_initial and current is None:
            return None
        probe = {"performance": dict(current or {})}
        return set_line_style(probe, style, level / 100.0)

    def _preview_performance(self) -> tuple[dict | None, str]:
        perf = self._performance_values()
        if not perf:
            return None, ""
        return perf, f"{perf.get('style')}:{float(perf.get('intensity') or 0):.2f}"

    def _update_pacing_hud(self):
        text = self.dub.toPlainText().strip()
        units = TranslateEngine.spoken_units_fast(text, self._lang) if text else 0
        tgt = self._quota.get("target", 1)
        mx = self._quota.get("max", tgt)
        mn = self._quota.get("min", max(1, int(round(tgt * 0.7))))

        self.lbl_beats_count.setText(f"Beats: {units} / {tgt} (target {tgt}, max {mx})")

        if not text or units == 0:
            self.lbl_pacing_badge.setText("Empty")
            self.lbl_pacing_badge.setStyleSheet("""
                padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;
                background: rgba(100, 116, 139, 0.15); color: #94a3b8; border: 1px solid rgba(100, 116, 139, 0.3);
            """)
        elif mn <= units <= mx:
            self.lbl_pacing_badge.setText("✓ Cinema Fit")
            self.lbl_pacing_badge.setStyleSheet("""
                padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;
                background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.35);
            """)
        elif units < mn:
            self.lbl_pacing_badge.setText("~ Relaxed Pace")
            self.lbl_pacing_badge.setStyleSheet("""
                padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;
                background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.35);
            """)
        elif units <= int(round(mx * 1.25)):
            est = units / max(1, tgt)
            self.lbl_pacing_badge.setText(f"~ Slight Stretch ({est:.2f}x)")
            self.lbl_pacing_badge.setStyleSheet("""
                padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;
                background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.35);
            """)
        else:
            est = units / max(1, tgt)
            self.lbl_pacing_badge.setText(f"⚠ Fast ({est:.2f}x · will rush)")
            self.lbl_pacing_badge.setStyleSheet("""
                padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;
                background: rgba(248, 113, 113, 0.15); color: #f87171; border: 1px solid rgba(248, 113, 113, 0.35);
            """)

    def _fit_line_with_ai(self):
        orig = self.source.toPlainText().strip()
        if not orig:
            self.preview_status.setText("Source dialogue is empty.")
            return
        if self._fit_ai_worker is not None:
            return

        self.btn_fit_ai.setEnabled(False)
        self.preview_spinner.start()
        self.preview_status.setText("Fitting line to timing slot with AI…")

        def _job():
            lines = [{
                "id": self._seg.get("id", 1),
                "text": orig,
                "original_text": orig,
                "duration_sec": self._slot_dur,
                "recommended_syllables": self._quota,
                "speaker": self._cast_data().get("label") or "",
                "gender": self.gender.currentText() or "",
            }]
            return TranslateEngine.translate_subtitles(
                lines,
                target_lang=self._lang,
                fit_duration=True,
                use_slang=True,
                use_expression=True,
            )

        worker = Worker(_job)
        worker.signals.result.connect(self._on_fit_ai_ready)
        worker.signals.error.connect(self._on_fit_ai_error)
        worker.signals.finished.connect(self._on_fit_ai_finished)
        self._fit_ai_worker = worker
        QThreadPool.globalInstance().start(worker)

    def _on_fit_ai_ready(self, result):
        if isinstance(result, list) and result:
            text = str(result[0].get("translated_text") or "").strip()
            if text:
                self.dub.setPlainText(text)
                self._update_pacing_hud()
                self.preview_status.setText("Line fitted to timing slot.")
                return
        self.preview_status.setText("AI fit completed with current text.")

    def _on_fit_ai_error(self, message: str, _stack: str):
        self.preview_status.setText(f"AI fit failed · {message}")

    def _on_fit_ai_finished(self):
        self._fit_ai_worker = None
        self.btn_fit_ai.setEnabled(True)
        self.preview_spinner.stop()

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
        self._update_pacing_hud()

    def _selected_voice_id(self) -> str:
        return str(self._cast_data().get("id") or "")

    def _stop_preview(self):
        self._preview_mode = ""
        self._player.stop()
        self.preview_spinner.stop()
        self.btn_preview_voice.setIcon(icon("play", color="#e7ecf3", size=14))
        self.btn_preview_line.setIcon(icon("volume", color="#e7ecf3", size=14))
        self.btn_preview_fitted.setIcon(icon("sparkles", color="#38bdf8", size=14))
        self.btn_preview_voice.setEnabled(True)
        self.btn_preview_line.setEnabled(True)
        self.btn_preview_fitted.setEnabled(True)

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
        if self._preview_mode == "voice":
            self._stop_preview()
            return
        if self._preview_worker is not None:
            return
        key = "Chinese" if self._lang.startswith("Chinese") else self._lang
        text = VOICE_SAMPLES.get(key, VOICE_SAMPLE_FALLBACK)
        self._start_preview(voice_id, text, kind="voice")

    def _preview_line(self, *, fitted: bool = False):
        voice_id = self._selected_voice_id()
        text = self.dub.toPlainText().strip()
        if not voice_id:
            self.preview_status.setText("Pick a TTS voice first.")
            return
        if not text:
            self.preview_status.setText("Dub text is empty.")
            return
        mode_key = "fitted" if fitted else "line"
        if self._preview_mode == mode_key:
            self._stop_preview()
            return
        if self._preview_worker is not None:
            return
        self._start_preview(voice_id, text, kind=mode_key)

    def _start_preview(self, voice_id: str, text: str, *, kind: str):
        self._preview_mode = kind
        self.preview_spinner.start()
        self.btn_preview_voice.setEnabled(False)
        self.btn_preview_line.setEnabled(False)
        self.btn_preview_fitted.setEnabled(False)

        perf, perf_key = self._preview_performance() if kind != "voice" else (None, "")
        if kind == "fitted":
            path = _fitted_preview_cache_path(voice_id, text, self._slot_dur, perf_key)
            self.preview_status.setText("Generating slot-fitted studio preview…")
        elif kind == "line":
            path = _preview_cache_path(voice_id, text, perf_key)
            self.preview_status.setText("Generating line preview…")
        else:
            path = _preview_cache_path(voice_id, text)
            self.preview_status.setText("Generating voice sample…")

        if os.path.isfile(path) and os.path.getsize(path) > 800:
            self._play_preview(path, kind=kind)
            return

        slot_dur = self._slot_dur

        def _job(vid=voice_id, body=text, out=path, k=kind, dur=slot_dur, plan=perf, key=perf_key,
                 progress_callback=None):
            if k == "fitted":
                raw_mp3 = _preview_cache_path(vid, body, key)
                TTSEngine.synthesize(body, vid, raw_mp3, progress_callback=progress_callback, performance=plan)
                fit_wav = out.replace(".wav", "_rawfit.wav")
                fit_duration(raw_mp3, fit_wav, dur, pad_or_trim=False, never_trim=True)
                return master_voiceover_track(fit_wav, out, volume_boost=1.15)
            return TTSEngine.synthesize(body, vid, out, progress_callback=progress_callback, performance=plan)

        worker = Worker(_job)
        worker.signals.result.connect(lambda p: self._on_preview_ready(p, kind=kind))
        worker.signals.error.connect(self._on_preview_error)
        worker.signals.finished.connect(self._on_preview_finished)
        self._preview_worker = worker
        QThreadPool.globalInstance().start(worker)

    def _on_preview_ready(self, path: object, *, kind: str = ""):
        if isinstance(path, str) and os.path.isfile(path):
            self._play_preview(path, kind=kind)
        else:
            self._stop_preview()
            self.preview_status.setText("Preview failed.")

    def _on_preview_error(self, message: str, _stack: str):
        self._stop_preview()
        self.preview_status.setText(f"Preview failed · {message}")

    def _on_preview_finished(self):
        self._preview_worker = None

    def _play_preview(self, path: str, *, kind: str = ""):
        self._preview_mode = kind or "playing"
        self.preview_spinner.stop()
        self.btn_preview_voice.setEnabled(True)
        self.btn_preview_line.setEnabled(True)
        self.btn_preview_fitted.setEnabled(True)

        if kind == "voice":
            self.btn_preview_voice.setIcon(icon("pause", color="#e7ecf3", size=14))
        elif kind == "fitted":
            self.btn_preview_fitted.setIcon(icon("pause", color="#38bdf8", size=14))
        else:
            self.btn_preview_line.setIcon(icon("pause", color="#e7ecf3", size=14))

        self.preview_status.setText(
            "Playing slot-fitted preview…" if kind == "fitted" else "Playing…"
        )
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
        out = {
            "original_text": original,
            "text": original,
            "translated_text": self.dub.toPlainText().strip(),
            "speaker": speaker,
            "gender": self.gender.currentText() or "Unknown",
            "gender_manual": True,
            "tts_voice_hint": voice_id,
            "voice_id": voice_id,
        }
        perf = self._performance_values()
        if perf is not None:
            out["performance"] = perf
        return out
