from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox,
)
from PySide6.QtCore import Qt

from claynext.services.llm_keys import PROVIDERS, get_key_pool, _parse_iso, _now
from claynext.controllers.store import get_store


def mask_secret(secret: str) -> str:
    raw = (secret or "").strip()
    if len(raw) <= 8:
        return "••••" + raw[-2:] if raw else ""
    return raw[:4] + "••••" + raw[-4:]


class ApiKeysDialog(QDialog):
    """Manage rolling LLM API keys. Rate-limited keys cool down and rotate automatically."""

    def __init__(self, parent=None, provider: str = "gemini"):
        super().__init__(parent)
        self.setWindowTitle("LLM API Keys")
        self.setObjectName("apiKeysDialog")
        self.setMinimumSize(620, 420)
        self.resize(680, 460)
        self.setModal(True)
        self._pool = get_key_pool()
        get_store().migrate_legacy_api_keys()
        self._provider = provider if provider in {p[0] for p in PROVIDERS} else "gemini"
        self._init_ui()
        self._reload()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        hint = QLabel(
            "Free Gemini keys from aistudio.google.com (no credit card). "
            "Flash free tier is 15 RPM / 1,500 RPD — Claynext batches 15 lines and rotates keys on 429. "
            "Hugging Face token is optional for WhisperX. Local Ollama / NLLB need no keys."
        )
        hint.setWordWrap(True)
        hint.setObjectName("asr_field_label")
        layout.addWidget(hint)

        row = QHBoxLayout()
        lbl = QLabel("Provider")
        self.combo_provider = QComboBox()
        for pid, name in PROVIDERS:
            self.combo_provider.addItem(name, pid)
        idx = self.combo_provider.findData(self._provider)
        if idx >= 0:
            self.combo_provider.setCurrentIndex(idx)
        self.combo_provider.currentIndexChanged.connect(self._reload)
        row.addWidget(lbl)
        row.addWidget(self.combo_provider, 1)
        layout.addLayout(row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Label", "Key", "Status", "Fails", "Enabled"])
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        layout.addWidget(self.table, 1)

        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        self.edit_label = QLineEdit()
        self.edit_label.setPlaceholderText("Label")
        self.edit_label.setMaximumWidth(120)
        self.edit_secret = QLineEdit()
        self.edit_secret.setPlaceholderText("Paste API key")
        self.edit_secret.setEchoMode(QLineEdit.EchoMode.Password)
        btn_add = QPushButton("Add")
        btn_add.setObjectName("api_keys_btn_primary")
        btn_add.clicked.connect(self._add)
        add_row.addWidget(self.edit_label)
        add_row.addWidget(self.edit_secret, 1)
        add_row.addWidget(btn_add)
        layout.addLayout(add_row)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        btn_toggle = QPushButton("Enable")
        btn_toggle.setObjectName("api_keys_btn")
        btn_toggle.setToolTip("Enable or disable the selected key")
        btn_toggle.clicked.connect(self._toggle)
        btn_del = QPushButton("Remove")
        btn_del.setObjectName("api_keys_btn")
        btn_del.setToolTip("Remove the selected key")
        btn_del.clicked.connect(self._remove)
        btn_clear = QPushButton("Clear cooldown")
        btn_clear.setObjectName("api_keys_btn")
        btn_clear.setToolTip("Clear rate-limit cooldowns for this provider")
        btn_clear.clicked.connect(self._clear_cooldowns)
        actions.addWidget(btn_toggle)
        actions.addWidget(btn_del)
        actions.addWidget(btn_clear)
        actions.addStretch()
        btn_close = QPushButton("Done")
        btn_close.setObjectName("api_keys_btn_primary")
        btn_close.clicked.connect(self.accept)
        actions.addWidget(btn_close)
        layout.addLayout(actions)

    def _provider_id(self) -> str:
        return self.combo_provider.currentData() or "gemini"

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        return int(item.data(Qt.ItemDataRole.UserRole))

    def _reload(self):
        provider = self._provider_id()
        rows = self._pool.list_keys(provider)
        self.table.setRowCount(0)
        now = _now()
        for rec in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            label = QTableWidgetItem(rec.get("label") or f"Key {rec['id']}")
            label.setData(Qt.ItemDataRole.UserRole, int(rec["id"]))
            self.table.setItem(r, 0, label)
            self.table.setItem(r, 1, QTableWidgetItem(mask_secret(rec.get("secret") or "")))
            until = _parse_iso(rec.get("cooldown_until"))
            enabled = int(rec.get("enabled") or 0) == 1
            if not enabled:
                status = "Disabled"
            elif until and until > now:
                secs = int((until - now).total_seconds())
                status = f"Cooling {secs}s"
            else:
                status = "Ready"
            self.table.setItem(r, 2, QTableWidgetItem(status))
            self.table.setItem(r, 3, QTableWidgetItem(str(rec.get("fail_count") or 0)))
            self.table.setItem(r, 4, QTableWidgetItem("Yes" if enabled else "No"))

    def _add(self):
        secret = self.edit_secret.text().strip()
        if not secret:
            QMessageBox.information(self, "API key", "Paste a key first.")
            return
        self._pool.add_key(self._provider_id(), secret, self.edit_label.text().strip())
        self.edit_secret.clear()
        self.edit_label.clear()
        self._reload()

    def _toggle(self):
        key_id = self._selected_id()
        if key_id is None:
            return
        rec = next((r for r in self._pool.list_keys(self._provider_id()) if int(r["id"]) == key_id), None)
        if not rec:
            return
        self._pool.set_enabled(key_id, int(rec.get("enabled") or 0) != 1)
        self._reload()

    def _remove(self):
        key_id = self._selected_id()
        if key_id is None:
            return
        self._pool.remove_key(key_id)
        self._reload()

    def _clear_cooldowns(self):
        from claynext.controllers.store import get_store
        store = get_store()
        for rec in self._pool.list_keys(self._provider_id()):
            store.update_api_key_state(int(rec["id"]), fail_count=0, clear_cooldown=True)
        self._reload()
