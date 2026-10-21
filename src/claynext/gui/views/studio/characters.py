"""Characters shelf: AI cast analysis, role profiling, voice audition, and character management."""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget,
)

from claynext.gui.icons import icon
from claynext.gui.components.shell.shelf_header import make_shelf_button, make_shelf_header

# Vibrant accent palette for character avatars
_AVATAR_PALETTE = [
    "#8b5cf6",  # Purple
    "#06b6d4",  # Cyan
    "#10b981",  # Emerald
    "#f59e0b",  # Amber
    "#ec4899",  # Pink
    "#3b82f6",  # Blue
    "#14b8a6",  # Teal
    "#e11d48",  # Rose
]

_ROLE_COLORS = {
    "Lead": ("#a855f7", "rgba(168, 85, 247, 0.18)"),
    "Co-Star": ("#38bdf8", "rgba(56, 189, 248, 0.18)"),
    "Supporting": ("#34d399", "rgba(52, 211, 153, 0.18)"),
    "Minor": ("#94a3b8", "rgba(148, 163, 184, 0.12)"),
    "Narrator": ("#fbbf24", "rgba(251, 191, 36, 0.18)"),
}


class _CharacterDialog(QDialog):
    """Name, gender, role, and TTS voice for one character with live audition."""

    def __init__(self, voices: list[dict], current: dict | None = None, parent=None):
        super().__init__(parent)
        self._parent_ref = parent
        current = current or {}
        self.setWindowTitle("Edit character" if current.get("name") else "New character")
        self.setModal(True)
        self.setMinimumWidth(360)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        name_label = QLabel("Name")
        name_label.setObjectName("asr_field_label")
        self.name = QLineEdit()
        self.name.setObjectName("dub_setting_field")
        self.name.setPlaceholderText("Character name")
        self.name.setText(str(current.get("name") or ""))

        role_label = QLabel("Role")
        role_label.setObjectName("asr_field_label")
        self.role = QComboBox()
        self.role.setObjectName("asr_option_combo")
        self.role.addItems(["Lead", "Co-Star", "Supporting", "Minor", "Narrator"])
        current_role = str(current.get("role") or "Supporting")
        r_idx = self.role.findText(current_role)
        self.role.setCurrentIndex(r_idx if r_idx >= 0 else 2)

        gender_label = QLabel("Gender")
        gender_label.setObjectName("asr_field_label")
        self.gender = QComboBox()
        self.gender.setObjectName("asr_option_combo")
        self.gender.addItems(["Female", "Male", "Unknown"])
        idx = self.gender.findText(str(current.get("gender") or "Unknown"))
        self.gender.setCurrentIndex(idx if idx >= 0 else 2)

        voice_label = QLabel("TTS voice")
        voice_label.setObjectName("asr_field_label")
        voice_box = QHBoxLayout()
        voice_box.setSpacing(6)
        self.voice = QComboBox()
        self.voice.setObjectName("asr_option_combo")
        self.voice.addItem("Match gender", "")
        pick = 0
        want = str(current.get("voice_id") or "")
        for v in voices:
            label = str(v.get("label") or v.get("name") or "")
            vid = str(v.get("id") or "")
            if not label or not vid:
                continue
            gender = str(v.get("gender") or "")
            text = f"{label} · {gender}" if gender and gender != "Unknown" else label
            self.voice.addItem(text, vid)
            if vid == want:
                pick = self.voice.count() - 1
        self.voice.setCurrentIndex(pick)
        voice_box.addWidget(self.voice, 1)

        self.btn_audition = QToolButton()
        self.btn_audition.setObjectName("media_lib_icon_btn")
        self.btn_audition.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_audition.setIcon(icon("play", color="#38bdf8", size=14))
        self.btn_audition.setToolTip("Audition selected voice")
        self.btn_audition.setFixedSize(30, 30)
        self.btn_audition.clicked.connect(self._audition_selected_voice)
        voice_box.addWidget(self.btn_audition)

        lay.addWidget(name_label)
        lay.addWidget(self.name)
        lay.addWidget(role_label)
        lay.addWidget(self.role)
        lay.addWidget(gender_label)
        lay.addWidget(self.gender)
        lay.addWidget(voice_label)
        lay.addLayout(voice_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _audition_selected_voice(self):
        vid = str(self.voice.currentData() or "")
        if not vid:
            return
        if hasattr(self._parent_ref, "_preview_voice"):
            self._parent_ref._preview_voice(vid)

    def values(self) -> dict:
        return {
            "name": self.name.text().strip(),
            "role": self.role.currentText() or "Supporting",
            "gender": self.gender.currentText() or "Unknown",
            "voice_id": str(self.voice.currentData() or ""),
        }


class CharacterTools:
    """Shelf tab for the cast used by the script, translate, and TTS."""

    def _build_character_panel(self) -> QWidget:
        self._cast_extra = list(getattr(self, "_cast_extra", []) or [])
        self._cast_signature = None
        self._ai_cast_worker = None
        panel = QWidget()
        panel.setObjectName("character_panel")
        root = QVBoxLayout(panel)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.btn_ai_cast = make_shelf_button(
            "AI Cast", tip="✨ AI Cast: Auto-detect character names, roles, gender & best voices", icon_name="sparkles", icon_color="#a855f7"
        )
        self.btn_ai_cast.clicked.connect(self._run_ai_cast_analysis)

        self.btn_character_add = make_shelf_button(
            "", tip="Create a character", icon_name="plus",
        )
        self.btn_character_add.clicked.connect(self._create_character)
        root.addWidget(make_shelf_header("Characters", self.btn_ai_cast, self.btn_character_add))

        self.character_hint = QLabel("AI detects names, dialogue roles & matches neural voices for each character.")
        self.character_hint.setObjectName("dub_panel_hint")
        self.character_hint.setWordWrap(True)
        root.addWidget(self.character_hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        self.character_list = QVBoxLayout(host)
        self.character_list.setContentsMargins(10, 4, 10, 10)
        self.character_list.setSpacing(6)
        self.character_list.addStretch(1)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        self.character_empty = QLabel("No characters yet · Click '✨ AI Cast' or '+' to add")
        self.character_empty.setObjectName("transcript_empty_title")
        self.character_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.character_list.insertWidget(0, self.character_empty)
        return panel

    def _run_ai_cast_analysis(self) -> None:
        """Run AI Character Cast Analysis across all dialogue segments."""
        segs = getattr(self, "_segments", []) or []
        if not segs:
            if hasattr(self, "log"):
                self.log.warn("Load media or script first to run AI Cast Analysis")
            return
        if getattr(self, "_ai_cast_worker", None) is not None:
            return

        lang = self._voice_lang() if hasattr(self, "_voice_lang") else ""
        lead, co_star = "", ""
        if hasattr(self, "_primary_voices"):
            lead, co_star = self._primary_voices()
        else:
            lead = getattr(self, "combo_voice", None) and self.combo_voice.currentData() or ""
            co_star = getattr(self, "combo_voice_sec", None) and self.combo_voice_sec.currentData() or lead

        if hasattr(self, "table_spinner"):
            self.table_spinner.start()
        if hasattr(self, "log"):
            self.log.info("✨ AI Cast Analysis starting · analyzing dialogue turns & roles…")

        from claynext.models.gender_voices import ai_analyze_movie_cast
        from claynext.gui.worker import Worker

        def _job(progress_callback=None):
            return ai_analyze_movie_cast(
                list(segs),
                lang=lang,
                primary_voice=str(lead or ""),
                secondary_voice=str(co_star or lead or ""),
                progress_callback=progress_callback,
            )

        worker = Worker(_job)
        worker.signals.result.connect(self._on_ai_cast_ready)
        worker.signals.error.connect(self._on_ai_cast_error)
        worker.signals.finished.connect(self._on_ai_cast_finished)
        self._ai_cast_worker = worker
        self.thread_pool.start(worker)

    def _on_ai_cast_ready(self, result: dict) -> None:
        if not isinstance(result, dict):
            return
        self._segments = list(result.get("segments") or self._segments)
        self._cast_signature = None
        if hasattr(self, "_fill_table"):
            self._fill_table(self._segments)
        self._refresh_character_list()
        count = int(result.get("count") or 0)
        if hasattr(self, "log"):
            self.log.success(f"✨ AI Cast complete: {count} characters profiled with distinct neural voices")

    def _on_ai_cast_error(self, err: Exception, _stack: str = "") -> None:
        if hasattr(self, "log"):
            self.log.warn(f"AI Cast error · {err}")

    def _on_ai_cast_finished(self) -> None:
        self._ai_cast_worker = None
        if hasattr(self, "table_spinner"):
            self.table_spinner.stop()

    def _character_rows(self) -> list[dict]:
        rows: dict[str, dict] = {}
        for seg in getattr(self, "_segments", []) or []:
            if not isinstance(seg, dict):
                continue
            name = str(seg.get("speaker") or "").strip()
            if not name:
                continue
            row = rows.get(name)
            if row is None:
                row = {
                    "name": name,
                    "gender": "Unknown",
                    "role": str(seg.get("character_role") or "Supporting"),
                    "voice_id": "",
                    "lines": 0,
                    "expression": "",
                    "in_script": True,
                }
                rows[name] = row
            row["lines"] += 1
            if seg.get("character_role"):
                row["role"] = str(seg.get("character_role"))
            gender = str(seg.get("gender") or "")
            if gender and gender != "Unknown":
                row["gender"] = gender
            voice = str(seg.get("tts_voice_hint") or seg.get("voice_id") or "")
            if voice:
                row["voice_id"] = voice
            perf = seg.get("performance") if isinstance(seg.get("performance"), dict) else None
            style = str((perf or {}).get("style") or "")
            if style and style != "neutral":
                row.setdefault("_styles", {})
                row["_styles"][style] = row["_styles"].get(style, 0) + 1
            expr = str(seg.get("expression") or "")
            if expr and not row["expression"]:
                row["expression"] = expr
        for row in rows.values():
            styles = row.pop("_styles", None)
            if styles:
                top = sorted(styles.items(), key=lambda kv: -kv[1])[:2]
                row["expression"] = ", ".join(name for name, _ in top)
        for extra in getattr(self, "_cast_extra", []) or []:
            name = str(extra.get("name") or "").strip()
            if not name or name in rows:
                continue
            rows[name] = {
                "name": name,
                "gender": str(extra.get("gender") or "Unknown"),
                "role": str(extra.get("role") or "Supporting"),
                "voice_id": str(extra.get("voice_id") or ""),
                "lines": 0,
                "expression": "",
                "in_script": False,
            }
        return list(rows.values())

    def _refresh_character_list(self) -> None:
        if not hasattr(self, "character_list"):
            return
        rows = self._character_rows()
        signature = tuple(
            (row["name"], row["gender"], row.get("role", ""), row["voice_id"], row["lines"], row["expression"])
            for row in rows
        )
        if signature == getattr(self, "_cast_signature", None):
            return
        self._cast_signature = signature
        index = 0
        while index < self.character_list.count():
            item = self.character_list.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is None or widget is self.character_empty:
                index += 1
                continue
            self.character_list.takeAt(index)
            widget.deleteLater()
        self.character_empty.setVisible(not rows)
        from claynext.models.gender_voices import voice_display_name

        for row in rows:
            self.character_list.insertWidget(
                self.character_list.count() - 1,
                self._character_card(row, voice_display_name(row["voice_id"]) if row["voice_id"] else ""),
            )

    def _character_card(self, row: dict, voice_label: str) -> QFrame:
        card = QFrame()
        card.setObjectName("character_row")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(10)

        # Avatar initial circle
        avatar_color = _AVATAR_PALETTE[abs(hash(row["name"])) % len(_AVATAR_PALETTE)]
        initial = (row["name"][:1] if row["name"] else "C").upper()
        avatar = QLabel(initial)
        avatar.setFixedSize(28, 28)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background-color: {avatar_color}; color: #ffffff; "
            f"border-radius: 14px; font-size: 13px; font-weight: bold;"
        )
        lay.addWidget(avatar)

        # Middle info column
        text = QVBoxLayout()
        text.setSpacing(2)

        # Top line: Name + Role Badge
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        title = QLabel(row["name"])
        title.setObjectName("character_name")
        top_row.addWidget(title)

        role = str(row.get("role") or "Supporting")
        fg, bg = _ROLE_COLORS.get(role, ("#94a3b8", "rgba(148, 163, 184, 0.12)"))
        role_badge = QLabel(role.upper())
        role_badge.setStyleSheet(
            f"color: {fg}; background-color: {bg}; border-radius: 3px; "
            f"padding: 1px 5px; font-size: 9px; font-weight: 700; letter-spacing: 0.5px;"
        )
        top_row.addWidget(role_badge)
        top_row.addStretch(1)
        text.addLayout(top_row)

        # Subtitle: Gender · Voice · Lines · Expression
        gender = row["gender"] or "Unknown"
        bits = [gender]
        if voice_label:
            bits.append(voice_label)
        count = int(row["lines"])
        bits.append(f"{count} line" if count == 1 else f"{count} lines")
        if row.get("expression"):
            bits.append(f"🎭 {row['expression']}")
        meta = QLabel(" · ".join(bits))
        meta.setObjectName("character_meta")
        text.addWidget(meta)
        lay.addLayout(text, 1)

        # Audition button
        play = QToolButton()
        play.setObjectName("media_lib_icon_btn")
        play.setCursor(Qt.CursorShape.PointingHandCursor)
        play.setIcon(icon("play", color="#38bdf8", size=14))
        play.setToolTip(f"Audition voice for {row['name']}")
        play.setFixedSize(28, 28)
        if row["voice_id"]:
            play.clicked.connect(lambda _=False, vid=row["voice_id"]: self._preview_voice(vid) if hasattr(self, "_preview_voice") else None)
        else:
            play.setEnabled(False)
        lay.addWidget(play)

        # Edit button
        edit = QToolButton()
        edit.setObjectName("media_lib_icon_btn")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.setIcon(icon("settings", color="#e7ecf3", size=14))
        edit.setToolTip("Edit name, gender, role, and voice")
        edit.setFixedSize(28, 28)
        edit.clicked.connect(lambda _=False, name=row["name"]: self._edit_character(name))
        lay.addWidget(edit)

        # Remove button (if not part of active script)
        if not row["in_script"]:
            remove = QToolButton()
            remove.setObjectName("media_lib_icon_btn")
            remove.setCursor(Qt.CursorShape.PointingHandCursor)
            remove.setIcon(icon("trash", color="#f87171", size=14))
            remove.setToolTip("Remove this character")
            remove.setFixedSize(28, 28)
            remove.clicked.connect(lambda _=False, name=row["name"]: self._remove_character(name))
            lay.addWidget(remove)
        return card

    def _voice_choices(self) -> list[dict]:
        from claynext.models.gender_voices import voices_for_lang

        lang = ""
        combo = getattr(self, "combo_lang", None)
        if combo is not None:
            lang = str(combo.currentText() or "")
        return voices_for_lang(lang)

    def _create_character(self) -> None:
        dialog = _CharacterDialog(self._voice_choices(), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        name = values["name"]
        if not name:
            return
        if any(row["name"].casefold() == name.casefold() for row in self._character_rows()):
            if hasattr(self, "log"):
                self.log.warn(f"{name} is already in the cast")
            return
        self._cast_extra.append(values)
        self._cast_signature = None
        self._refresh_character_list()
        if hasattr(self, "log"):
            self.log.info(f"Character · {name}")

    def _edit_character(self, name: str) -> None:
        current = next((row for row in self._character_rows() if row["name"] == name), None)
        if current is None:
            return
        dialog = _CharacterDialog(self._voice_choices(), current, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        new_name = values["name"]
        if not new_name:
            return
        if new_name.casefold() != name.casefold() and any(
            row["name"].casefold() == new_name.casefold() for row in self._character_rows()
        ):
            if hasattr(self, "log"):
                self.log.warn(f"{new_name} is already in the cast")
            return
        for extra in self._cast_extra:
            if str(extra.get("name") or "") == name:
                extra.update(values)
        changed = False
        for seg in getattr(self, "_segments", []) or []:
            if not isinstance(seg, dict) or str(seg.get("speaker") or "") != name:
                continue
            seg["speaker"] = new_name
            seg["character"] = new_name
            seg["gender"] = values["gender"]
            seg["character_role"] = values.get("role", "Supporting")
            seg["gender_manual"] = True
            if values["voice_id"]:
                seg["tts_voice_hint"] = values["voice_id"]
                seg["voice_id"] = values["voice_id"]
            changed = True
        self._cast_signature = None
        if changed and hasattr(self, "_fill_table"):
            self._fill_table(self._segments)
        else:
            self._refresh_character_list()
        self._save_character_override(name, values)
        if hasattr(self, "log"):
            self.log.info(f"Character · {new_name}")

    def _save_character_override(self, label: str, values: dict) -> None:
        """Editor choices become registry overrides so the next dub keeps them."""
        media = str(getattr(self, "selected_file", "") or "")
        if not media:
            return
        from claynext.gui.worker import Worker
        from claynext.models.character_intel import CharacterRegistry
        from claynext.models.character_intel.voice_casting import presentation_from_gender

        gender = str(values.get("gender") or "Unknown")
        fields = {
            "name": str(values.get("name") or "") or None,
            "voice_id": str(values.get("voice_id") or "") or None,
            "presentation": presentation_from_gender(gender) if gender != "Unknown" else None,
            "role": str(values.get("role") or "") or None,
        }

        def _job(progress_callback=None):
            registry = CharacterRegistry.for_media(media)
            registry.override_by_label(label, **fields)
            return registry.save()

        worker = Worker(_job)
        if hasattr(self, "log"):
            worker.signals.error.connect(lambda msg, _stack="": self.log.warn(f"Character registry · {msg}"))
        self.thread_pool.start(worker)

    def _remove_character(self, name: str) -> None:
        self._cast_extra = [
            extra for extra in self._cast_extra
            if str(extra.get("name") or "") != name
        ]
        self._cast_signature = None
        self._refresh_character_list()
