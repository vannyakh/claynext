"""Compact dialog — add a single LLM API key (list lives in Settings → API Keys)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from claynext.controllers.store import get_store
from claynext.models.llm_keys import PROVIDERS, get_key_pool


def mask_secret(secret: str) -> str:
    raw = (secret or "").strip()
    if len(raw) <= 8:
        return "••••" + raw[-2:] if raw else ""
    return raw[:4] + "••••" + raw[-4:]


class ApiKeysDialog(QDialog):
    """Form-only dialog to add or edit one API key for a provider."""

    def __init__(self, parent=None, provider: str = "gemini", key_id: int | None = None):
        super().__init__(parent)
        self.setObjectName("apiKeysDialog")
        self.setFixedWidth(360)
        self.setModal(True)
        self._pool = get_key_pool()
        get_store().migrate_legacy_api_keys()
        self._key_id = int(key_id) if key_id else None
        self._record = None
        if self._key_id:
            self._record = next(
                (row for row in self._pool.list_keys() if int(row["id"]) == self._key_id),
                None,
            )
            if self._record:
                provider = str(self._record.get("provider") or provider)
        self._provider = provider if provider in {p[0] for p in PROVIDERS} else "gemini"
        self.setWindowTitle("Edit API key" if self._record else "Add API key")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        layout.addWidget(self._field_label("Provider"))
        self.combo_provider = QComboBox()
        self.combo_provider.setObjectName("api_keys_combo")
        self.combo_provider.setFixedHeight(28)
        for pid, name in PROVIDERS:
            self.combo_provider.addItem(name, pid)
        idx = self.combo_provider.findData(self._provider)
        if idx >= 0:
            self.combo_provider.setCurrentIndex(idx)
        layout.addWidget(self.combo_provider)

        layout.addWidget(self._field_label("Label"))
        self.edit_label = QLineEdit()
        self.edit_label.setObjectName("api_keys_input")
        self.edit_label.setPlaceholderText("Optional name")
        self.edit_label.setFixedHeight(28)
        layout.addWidget(self.edit_label)

        layout.addWidget(self._field_label("API key"))
        self.edit_secret = QLineEdit()
        self.edit_secret.setObjectName("api_keys_input")
        self.edit_secret.setPlaceholderText(
            "Leave blank to keep this key" if self._record else "Paste API key"
        )
        self.edit_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_secret.setFixedHeight(28)
        self.edit_secret.returnPressed.connect(self._accept_add)
        layout.addWidget(self.edit_secret)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        btn_cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        btn_ok.setText("Save" if self._record else "Add key")
        btn_ok.setObjectName("btn_primary")
        btn_cancel.setObjectName("btn_secondary")
        for btn in (btn_ok, btn_cancel):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(28)
        buttons.accepted.connect(self._accept_add)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if self._record:
            self.edit_label.setText(str(self._record.get("label") or ""))
            self.edit_label.setFocus()
        else:
            self.edit_secret.setFocus()

    @staticmethod
    def _field_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("settings_field_label")
        return lbl

    def provider_id(self) -> str:
        return str(self.combo_provider.currentData() or "gemini")

    def _accept_add(self):
        secret = self.edit_secret.text().strip()
        label = self.edit_label.text().strip()
        if self._record:
            self._pool.update_key(
                int(self._record["id"]),
                provider=self.provider_id(),
                label=label,
                secret=secret,
            )
            self.accept()
            return
        if not secret:
            QMessageBox.information(self, "API key", "Paste a key first.")
            self.edit_secret.setFocus()
            return
        self._pool.add_key(self.provider_id(), secret, label)
        self.accept()
