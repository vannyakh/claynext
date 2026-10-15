"""Export settings window for the dubbing timeline."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox, QLineEdit,
    QPushButton, QCheckBox, QFileDialog, QFrame,
)

EXPORT_KINDS = (
    ("movie", "Dubbed movie (timeline mix)", "mp4"),
    ("mix_wav", "Full mix audio", "wav"),
    ("voice_wav", "Voice-over track only", "wav"),
    ("source", "Source movie", "mp4"),
    ("srt", "Subtitles (SRT)", "srt"),
    ("vtt", "Subtitles (WebVTT)", "vtt"),
    ("json", "Script (JSON)", "json"),
)
_EXT = {kind: ext for kind, _label, ext in EXPORT_KINDS}
_MOVIE = {"movie", "source"}
_SCRIPT = {"srt", "vtt", "json"}


class ExportDialog(QDialog):
    """Pick what to export, where it goes, and how the movie is encoded."""

    def __init__(
        self, parent=None, *, folder: str, stem: str, summary: str,
        saved: dict | None = None, script_only: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle("Export script" if script_only else "Export")
        self.setObjectName("exportDialog")
        self.setMinimumWidth(480 if script_only else 520)
        self.setModal(True)
        self._stem = stem or "export"
        self._script_only = bool(script_only)
        saved = saved or {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 16)
        root.setSpacing(12)

        title = QLabel("Export script" if script_only else "Export")
        title.setObjectName("dub_panel_title")
        root.addWidget(title)
        self.summary = QLabel(summary)
        self.summary.setObjectName("dub_switch_hint")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        line = QFrame()
        line.setObjectName("dub_config_divider")
        line.setFixedHeight(1)
        root.addWidget(line)
        box = QFrame()
        box.setObjectName("dub_config_section")
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 4, 0, 4)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self.combo_kind = QComboBox()
        kinds = [row for row in EXPORT_KINDS if row[0] in _SCRIPT] if script_only else list(EXPORT_KINDS)
        for kind, label, _ext in kinds:
            self.combo_kind.addItem(label, kind)
        default_kind = saved.get("kind", "srt" if script_only else "movie")
        if script_only and default_kind not in _SCRIPT:
            default_kind = "srt"
        self._select(self.combo_kind, default_kind)
        self.combo_kind.currentIndexChanged.connect(self._sync)
        grid.addWidget(self._label("Format"), 0, 0)
        grid.addWidget(self.combo_kind, 0, 1, 1, 2)

        self.combo_version = QComboBox()
        self.combo_version.addItem("Current version", "current")
        self.combo_version.addItem("Back version (last accepted / source)", "back")
        self._select(self.combo_version, saved.get("version", "current"))
        self.lbl_version = self._label("Script")
        grid.addWidget(self.lbl_version, 1, 0)
        grid.addWidget(self.combo_version, 1, 1, 1, 2)

        self.edit_name = QLineEdit()
        self.edit_name.setObjectName("dub_setting_field")
        grid.addWidget(self._label("File name"), 2, 0)
        grid.addWidget(self.edit_name, 2, 1, 1, 2)

        self.edit_folder = QLineEdit(saved.get("folder") or folder)
        self.edit_folder.setObjectName("dub_setting_field")
        browse = QPushButton("Browse…")
        browse.setObjectName("api_keys_btn")
        browse.clicked.connect(self._browse)
        grid.addWidget(self._label("Folder"), 3, 0)
        grid.addWidget(self.edit_folder, 3, 1)
        grid.addWidget(browse, 3, 2)

        self.combo_video = QComboBox()
        self.combo_video.addItem("Keep original picture (fast)", "copy")
        self.combo_video.addItem("Re-encode H.264 high quality", "h264")
        self._select(self.combo_video, saved.get("video", "copy"))
        self.lbl_video = self._label("Video")
        grid.addWidget(self.lbl_video, 4, 0)
        grid.addWidget(self.combo_video, 4, 1, 1, 2)

        self.combo_audio = QComboBox()
        for rate in ("128k", "192k", "256k", "320k"):
            self.combo_audio.addItem(f"AAC {rate.replace('k', '')} kbps", rate)
        self._select(self.combo_audio, saved.get("audio", "256k"))
        self.lbl_audio = self._label("Audio")
        grid.addWidget(self.lbl_audio, 5, 0)
        grid.addWidget(self.combo_audio, 5, 1, 1, 2)

        self.chk_overlays = QCheckBox("Burn on-screen text and captions")
        self.chk_overlays.setChecked(saved.get("overlays", True) is not False)
        grid.addWidget(self.chk_overlays, 6, 1, 1, 2)
        grid.setColumnStretch(1, 1)
        root.addWidget(box)

        self.lbl_target = QLabel("")
        self.lbl_target.setObjectName("dub_switch_hint")
        self.lbl_target.setWordWrap(True)
        root.addWidget(self.lbl_target)
        self.edit_name.textChanged.connect(self._sync_target)
        self.edit_folder.textChanged.connect(self._sync_target)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("api_keys_btn")
        cancel.clicked.connect(self.reject)
        self.btn_export = QPushButton("Export")
        self.btn_export.setObjectName("api_keys_btn_primary")
        self.btn_export.setDefault(True)
        self.btn_export.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(self.btn_export)
        root.addLayout(actions)
        self._sync()

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("asr_field_label")
        return label

    @staticmethod
    def _select(combo: QComboBox, value):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _kind(self) -> str:
        return self.combo_kind.currentData() or "movie"

    def _default_name(self) -> str:
        kind = self._kind()
        suffix = {
            "movie": "_dub", "mix_wav": "_mix", "voice_wav": "_voice", "source": "_source",
        }.get(kind, "_" + str(self.combo_version.currentData() or "current"))
        return f"{self._stem}{suffix}.{_EXT[kind]}"

    def _sync(self):
        kind = self._kind()
        self.lbl_version.setVisible(kind in _SCRIPT)
        self.combo_version.setVisible(kind in _SCRIPT)
        movie = kind in _MOVIE
        for widget in (self.lbl_video, self.combo_video):
            widget.setVisible(movie)
        for widget in (self.lbl_audio, self.combo_audio):
            widget.setVisible(kind in {"movie"})
        self.chk_overlays.setVisible(kind == "movie")
        self.edit_name.setText(self._default_name())
        self._sync_target()

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Export folder", self.edit_folder.text())
        if folder:
            self.edit_folder.setText(folder)

    def _sync_target(self):
        path = self.target_path()
        self.lbl_target.setText(f"Saves to {path}" if path else "Choose a folder and a file name.")
        self.btn_export.setEnabled(bool(path))

    def target_path(self) -> str:
        folder = self.edit_folder.text().strip()
        name = self.edit_name.text().strip()
        if not folder or not name:
            return ""
        ext = "." + _EXT[self._kind()]
        if not name.lower().endswith(ext):
            name += ext
        return os.path.join(folder, name)

    def options(self) -> dict:
        return {
            "kind": self._kind(),
            "version": self.combo_version.currentData() or "current",
            "path": self.target_path(),
            "folder": self.edit_folder.text().strip(),
            "video": self.combo_video.currentData() or "copy",
            "audio": self.combo_audio.currentData() or "256k",
            "overlays": self.chk_overlays.isChecked(),
        }

