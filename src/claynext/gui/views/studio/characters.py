"""Characters shelf: create a cast and keep names found in the script."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QScrollArea, QToolButton, QVBoxLayout, QWidget,
)

from claynext.gui.icons import icon
from claynext.gui.components.shell.shelf_header import make_shelf_button, make_shelf_header


class _CharacterDialog(QDialog):
    """Name, gender, and TTS voice for one character."""

    def __init__(self, voices: list[dict], current: dict | None = None, parent=None):
        super().__init__(parent)
        current = current or {}
        self.setWindowTitle("Edit character" if current.get("name") else "New character")
        self.setModal(True)
        self.setMinimumWidth(320)
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        name_label = QLabel("Name")
        name_label.setObjectName("asr_field_label")
        self.name = QLineEdit()
        self.name.setObjectName("dub_setting_field")
        self.name.setPlaceholderText("Character name")
        self.name.setText(str(current.get("name") or ""))

        gender_label = QLabel("Gender")
        gender_label.setObjectName("asr_field_label")
        self.gender = QComboBox()
        self.gender.setObjectName("asr_option_combo")
        self.gender.addItems(["Female", "Male", "Unknown"])
        idx = self.gender.findText(str(current.get("gender") or "Unknown"))
        self.gender.setCurrentIndex(idx if idx >= 0 else 2)

        voice_label = QLabel("TTS voice")
        voice_label.setObjectName("asr_field_label")
        self.voice = QComboBox()
        self.voice.setObjectName("asr_option_combo")
        self.voice.addItem("Match gender", "")
        pick = 0
        want = str(current.get("voice_id") or "")
        for voice in voices:
            label = str(voice.get("label") or voice.get("name") or "")
            vid = str(voice.get("id") or "")
            if not label or not vid:
                continue
            gender = str(voice.get("gender") or "")
            text = f"{label} · {gender}" if gender and gender != "Unknown" else label
            self.voice.addItem(text, vid)
            if vid == want:
                pick = self.voice.count() - 1
        self.voice.setCurrentIndex(pick)

        lay.addWidget(name_label)
        lay.addWidget(self.name)
        lay.addWidget(gender_label)
        lay.addWidget(self.gender)
        lay.addWidget(voice_label)
        lay.addWidget(self.voice)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def values(self) -> dict:
        return {
            "name": self.name.text().strip(),
            "gender": self.gender.currentText() or "Unknown",
            "voice_id": str(self.voice.currentData() or ""),
        }


class CharacterTools:
    """Shelf tab for the cast used by the script, translate, and TTS."""

    def _build_character_panel(self) -> QWidget:
        self._cast_extra = list(getattr(self, "_cast_extra", []) or [])
        self._cast_signature = None
        panel = QWidget()
        panel.setObjectName("character_panel")
        root = QVBoxLayout(panel)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.btn_character_add = make_shelf_button(
            "", tip="Create a character", icon_name="plus",
        )
        self.btn_character_add.clicked.connect(self._create_character)
        root.addWidget(make_shelf_header("Characters", self.btn_character_add))

        self.character_hint = QLabel("Create the cast, or run a dub and names from the transcript appear here.")
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

        self.character_empty = QLabel("No characters yet")
        self.character_empty.setObjectName("transcript_empty_title")
        self.character_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.character_list.insertWidget(0, self.character_empty)
        return panel

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
                    "voice_id": "",
                    "lines": 0,
                    "expression": "",
                    "in_script": True,
                }
                rows[name] = row
            row["lines"] += 1
            gender = str(seg.get("gender") or "")
            if gender and gender != "Unknown":
                row["gender"] = gender
            voice = str(seg.get("tts_voice_hint") or seg.get("voice_id") or "")
            if voice:
                row["voice_id"] = voice
            expr = str(seg.get("expression") or "")
            if expr and not row["expression"]:
                row["expression"] = expr
        for extra in getattr(self, "_cast_extra", []) or []:
            name = str(extra.get("name") or "").strip()
            if not name or name in rows:
                continue
            rows[name] = {
                "name": name,
                "gender": str(extra.get("gender") or "Unknown"),
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
            (row["name"], row["gender"], row["voice_id"], row["lines"], row["expression"])
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
        lay.setContentsMargins(10, 8, 8, 8)
        lay.setSpacing(8)
        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(row["name"])
        title.setObjectName("character_name")
        gender = row["gender"] or "Unknown"
        bits = [gender]
        if voice_label:
            bits.append(voice_label)
        count = int(row["lines"])
        bits.append(f"{count} line" if count == 1 else f"{count} lines")
        if row.get("expression"):
            bits.append(str(row["expression"]))
        meta = QLabel(" · ".join(bits))
        meta.setObjectName("character_meta")
        text.addWidget(title)
        text.addWidget(meta)
        lay.addLayout(text, 1)

        edit = QToolButton()
        edit.setObjectName("media_lib_icon_btn")
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.setIcon(icon("settings", color="#e7ecf3", size=14))
        edit.setToolTip("Edit name, gender, and voice")
        edit.setFixedSize(28, 28)
        edit.clicked.connect(lambda _=False, name=row["name"]: self._edit_character(name))
        lay.addWidget(edit)

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
        if hasattr(self, "log"):
            self.log.info(f"Character · {new_name}")

    def _remove_character(self, name: str) -> None:
        self._cast_extra = [
            extra for extra in self._cast_extra
            if str(extra.get("name") or "") != name
        ]
        self._cast_signature = None
        self._refresh_character_list()
