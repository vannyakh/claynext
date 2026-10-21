"""Models settings panel: filter, custom repo, and the catalog table."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from claynext.gui.components.settings.install import ModelInstall
from claynext.gui.components.settings.table import ModelsTable, paint_progress
from claynext.models.hf_hub import get_model_registry


class ModelsPanel(QWidget):
    """Settings tab for the model catalog."""

    installed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._job = ModelInstall(self)
        self._job.progress.connect(self._on_progress)
        self._job.finished.connect(self._on_done)
        self._job.failed.connect(self._on_error)
        self._build()
        self.reload()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 22, 12)
        lay.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(8)
        title = QLabel("Models")
        title.setObjectName("settings_field_label")
        top.addWidget(title, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addStretch(1)

        self.filter = QComboBox()
        self.filter.setObjectName("settings_filter_combo")
        self.filter.setFixedHeight(26)
        self.filter.addItem("All types", "")
        self.filter.addItem("Translate", "translate")
        self.filter.addItem("TTS", "tts")
        self.filter.addItem("ASR", "asr")
        self.filter.addItem("Audio", "audio")
        self.filter.addItem("LLM", "llm")
        self.filter.currentIndexChanged.connect(self.reload)
        top.addWidget(self.filter, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(top)

        pull = QHBoxLayout()
        pull.setSpacing(6)
        self.custom = QLineEdit()
        self.custom.setFixedHeight(26)
        self.custom.setPlaceholderText("owner/repo — e.g. Systran/faster-whisper-base")
        self.custom_btn = QPushButton("Install")
        self.custom_btn.setObjectName("btn_primary")
        self.custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.custom_btn.setFixedHeight(26)
        self.custom_btn.setMinimumWidth(92)
        self.custom_btn.clicked.connect(self._install_custom)
        pull.addWidget(self.custom, 1)
        pull.addWidget(self.custom_btn)
        lay.addLayout(pull)

        self.table = ModelsTable()
        self.table.install_requested.connect(self.install)
        lay.addWidget(self.table, 1)

    def reload(self, *_args) -> None:
        kind = self.filter.currentData() or ""
        models = get_model_registry()
        if kind:
            models = [row for row in models if str(row.get("category", "")).lower() == kind]
        self.table.fill(models, self._job.jobs)

    def _install_custom(self) -> None:
        repo_id = self.custom.text().strip()
        if not repo_id:
            QMessageBox.warning(self, "Missing Repo", "Enter a valid Hugging Face repository ID.")
            return
        self.install(repo_id)

    def install(self, repo_id: str) -> None:
        if not self._job.start(repo_id):
            return
        if self.custom.text().strip() == repo_id:
            self.custom_btn.setEnabled(False)
        self.reload()

    def _on_progress(self, repo_id: str, val: int, msg: str) -> None:
        btn = self.table.button(repo_id)
        if btn is None and self.custom.text().strip() == repo_id:
            btn = self.custom_btn
        if btn is None:
            return
        paint_progress(btn, val)
        if msg:
            btn.setToolTip(msg)

    def _reset_custom(self, repo_id: str) -> None:
        if self.custom.text().strip() != repo_id:
            return
        if repo_id in self._job.jobs:
            return
        self.custom_btn.setEnabled(True)
        self.custom_btn.setText("Install")
        self.custom_btn.setStyleSheet("")

    def _on_done(self, repo_id: str, _path: str) -> None:
        self._reset_custom(repo_id)
        self.reload()
        self.installed.emit()
        QMessageBox.information(self, "Installed", f"{repo_id} is in the local cache.")

    def _on_error(self, repo_id: str, err_msg: str) -> None:
        self._reset_custom(repo_id)
        self.reload()
        QMessageBox.critical(self, "Install failed", f"Could not install {repo_id}:\n{err_msg}")
