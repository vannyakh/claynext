from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QPushButton, QFileDialog, QTabWidget, QWidget, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QScrollArea, QFrame, QSizePolicy, QAbstractItemView,
    QStyledItemDelegate, QStyle, QStyleOptionViewItem,
)
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QColor
from claynext.constants.theme_constants import (
    COLOR_ACCENT_CYAN,
    COLOR_ACCENT_EMERALD,
    COLOR_ACCENT_ROSE,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
)
from claynext.utils.config import DEFAULT_CONFIG, MODELS_DIR, OUTPUTS_DIR
from claynext.gui.components.settings.panel import ModelsPanel
from claynext.gui.components.settings.toggle import SettingsToggle, bind_toggle_label
from claynext.gui.icons import icon
from claynext.gui.worker import Worker
from claynext.models.features import (
    DEMUCS_MODELS,
    FEATURE_SETTING_KEYS,
    get_feature_setting,
    install_uv_extra,
    list_features,
    set_feature_setting,
)
from claynext.controllers.store import get_store

_HEALTH_COLORS = {
    "Healthy": COLOR_ACCENT_EMERALD,
    "Busy": COLOR_ACCENT_CYAN,
    "Shaky": "#f59e0b",
    "Worn": COLOR_ACCENT_ROSE,
    "Limited": "#f59e0b",
    "Off": COLOR_TEXT_MUTED,
}


def _health_color(label: str) -> str:
    if str(label).startswith("Cooling"):
        return COLOR_ACCENT_CYAN
    return _HEALTH_COLORS.get(label, COLOR_TEXT_MAIN)


class _HealthDelegate(QStyledItemDelegate):
    """Paint health text in its status color. The table stylesheet forces item color."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
        if not text:
            return
        color = index.data(Qt.ItemDataRole.UserRole) or COLOR_TEXT_MAIN
        painter.save()
        painter.setPen(QColor(str(color)))
        painter.drawText(
            opt.rect.adjusted(8, 0, -8, 0),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            text,
        )
        painter.restore()


class SettingsDialog(QDialog):
    """Studio settings — Features, models, paths, and appearance."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings — Claynext Studio")
        self.setMinimumSize(760, 440)
        self.resize(860, 500)
        self.setModal(True)
        self.thread_pool = QThreadPool.globalInstance()
        self._feature_cards: list[QFrame] = []
        self._feature_controls: dict[str, dict] = {}
        self._feature_active: str | None = None
        self._feature_queue: list[tuple[str, str, str]] = []
        self._feature_pct: dict[str, int] = {}
        self.init_ui()
        self._load_from_store()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("settingsTabs")
        self.tabs.addTab(self._build_general_tab(), icon("settings", size=13), "General")
        self.tabs.addTab(self._build_features_tab(), icon("sparkles", size=13), "Features")
        self.tabs.addTab(self._build_api_keys_tab(), icon("lock", size=13), "API Keys")
        self.models_panel = ModelsPanel()
        self.models_panel.installed.connect(self._populate_features_cards)
        self.tabs.addTab(self.models_panel, icon("cpu", size=13), "Models")
        self.tabs.addTab(self._build_hardware_paths_tab(), icon("gpu", size=13), "Hardware")
        self.tabs.addTab(self._build_appearance_tab(), icon("shapes", size=13), "Appearance")
        layout.addWidget(self.tabs, 1)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)
        btn_reset = QPushButton("Defaults")
        btn_reset.setObjectName("btn_secondary")
        btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset.setFixedHeight(28)
        btn_reset.clicked.connect(self.restore_defaults)
        btn_box.addWidget(btn_reset)
        btn_box.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setFixedHeight(28)
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Save")
        btn_save.setObjectName("btn_primary")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setFixedHeight(28)
        btn_save.clicked.connect(self.save_config)
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _divider() -> QWidget:
        """Soft section rule with vertical breathing room."""
        wrap = QWidget()
        wrap.setObjectName("settings_divider_wrap")
        wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(0)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setObjectName("settings_divider")
        lay.addWidget(line)
        return wrap

    @staticmethod
    def _section(title: str, hint: str = "") -> tuple[QWidget, QVBoxLayout]:
        sec = QWidget()
        sec.setObjectName("settings_section")
        lay = QVBoxLayout(sec)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        hdr = QLabel(title)
        hdr.setObjectName("settings_section_title")
        lay.addWidget(hdr)
        if hint:
            note = QLabel(hint)
            note.setObjectName("settings_section_hint")
            note.setWordWrap(True)
            lay.addWidget(note)
        return sec, lay

    @staticmethod
    def _field_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("settings_field_label")
        return lbl

    @staticmethod
    def _setting_row(label: str, *fields: QWidget, grow: bool = False) -> QWidget:
        """One settings line: label on the left, control on the right."""
        row = QWidget()
        row.setObjectName("settings_row")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        text = QLabel(label)
        text.setObjectName("settings_row_label")
        lay.addWidget(text, 0, Qt.AlignmentFlag.AlignVCenter)
        if not grow:
            lay.addStretch(1)
        for index, field in enumerate(fields):
            stretch = 1 if grow and index == 0 else 0
            lay.addWidget(field, stretch, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _toggle_row(self, label: str, *, checked: bool = False) -> tuple[SettingsToggle, QWidget]:
        toggle = SettingsToggle()
        toggle.setChecked(checked)
        row = self._setting_row(label, toggle)
        text = row.findChild(QLabel, "settings_row_label")
        if text is not None:
            bind_toggle_label(text, toggle)
        return toggle, row

    @staticmethod
    def _scroll_page() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(14)
        scroll.setWidget(host)
        outer.addWidget(scroll)
        return page, lay

    # ─── General ─────────────────────────────────────────────────────

    def _build_general_tab(self) -> QWidget:
        page, lay = self._scroll_page()
        self.combo_lang = QComboBox()
        self.combo_lang.setFixedHeight(28)
        self.combo_lang.setFixedWidth(280)
        self.combo_lang.addItems([
            "English (US)", "Vietnamese (Tiếng Việt)", "Japanese (日本語)", "Chinese (中文)",
        ])
        lay.addWidget(self._setting_row("Language", self.combo_lang))

        lay.addWidget(self._divider())

        self.chk_updates, updates_row = self._toggle_row("Check for updates on startup", checked=True)
        self.chk_auto_open, open_row = self._toggle_row("Open export folder when complete", checked=True)
        self.chk_keep_awake, awake_row = self._toggle_row("Prevent sleep during processing", checked=True)
        self.chk_notify, notify_row = self._toggle_row("Show completion notifications", checked=True)
        for row in (updates_row, open_row, awake_row, notify_row):
            lay.addWidget(row)
        lay.addStretch(1)
        return page

    def _build_api_keys_tab(self) -> QWidget:
        from claynext.models.llm_keys import PROVIDERS, get_key_pool

        get_store().migrate_legacy_api_keys()
        self._api_key_pool = get_key_pool()

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(self._field_label("Provider"), 0, Qt.AlignmentFlag.AlignVCenter)
        self.combo_api_provider = QComboBox()
        self.combo_api_provider.setFixedHeight(28)
        for pid, name in PROVIDERS:
            self.combo_api_provider.addItem(name, pid)
        self.combo_api_provider.currentIndexChanged.connect(self._reload_api_keys)
        head.addWidget(self.combo_api_provider, 1)
        btn_import = self._api_key_button("Import", self._import_api_keys)
        btn_export = self._api_key_button("Export", self._export_api_keys)
        btn_add = self._api_key_button("Add key", self._open_add_api_key, primary=True)
        btn_add.setMinimumWidth(84)
        head.addWidget(btn_import, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(btn_export, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(btn_add, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(head)

        self.api_keys_table = QTableWidget(0, 6)
        self.api_keys_table.setObjectName("settings_api_keys_table")
        self.api_keys_table.setHorizontalHeaderLabels(
            ["Label", "Key", "Health", "Tokens", "Limit", "Speed"]
        )
        hdr = self.api_keys_table.horizontalHeader()
        hdr.setHighlightSections(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        for col, width in ((3, 64), (4, 58), (5, 72)):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.api_keys_table.setColumnWidth(col, width)
        self.api_keys_table.setItemDelegateForColumn(2, _HealthDelegate(self.api_keys_table))
        self.api_keys_table.verticalHeader().setVisible(False)
        self.api_keys_table.verticalHeader().setDefaultSectionSize(32)
        self.api_keys_table.setShowGrid(False)
        self.api_keys_table.setAlternatingRowColors(True)
        self.api_keys_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.api_keys_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.api_keys_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.api_keys_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.api_keys_table.customContextMenuRequested.connect(self._api_keys_context_menu)
        self.api_keys_table.itemDoubleClicked.connect(lambda *_args: self._open_edit_api_key())
        lay.addWidget(self.api_keys_table, 1)

        self._reload_api_keys()
        return page

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "api_keys_table"):
            self._reload_api_keys()

    def _api_provider_id(self) -> str:
        if not hasattr(self, "combo_api_provider"):
            return "gemini"
        return str(self.combo_api_provider.currentData() or "gemini")

    def _selected_api_key_id(self) -> int | None:
        row = self.api_keys_table.currentRow()
        if row < 0:
            return None
        item = self.api_keys_table.item(row, 0)
        if not item:
            return None
        return int(item.data(Qt.ItemDataRole.UserRole))

    def _api_keys_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu

        row = self.api_keys_table.indexAt(pos).row()
        if row >= 0:
            self.api_keys_table.selectRow(row)
        menu = QMenu(self.api_keys_table)
        menu.setObjectName("media_lib_menu")
        key_id = self._selected_api_key_id()
        if key_id is not None:
            rec = next(
                (r for r in self._api_key_pool.list_keys(self._api_provider_id()) if int(r["id"]) == key_id),
                None,
            )
            enabled = bool(rec and int(rec.get("enabled") or 0) == 1)
            act_edit = menu.addAction("Edit")
            act_edit.triggered.connect(self._open_edit_api_key)
            menu.addSeparator()
            act_toggle = menu.addAction("Disable" if enabled else "Enable")
            act_toggle.triggered.connect(self._toggle_api_key)
            act_remove = menu.addAction("Remove")
            act_remove.triggered.connect(self._remove_api_key)
            menu.addSeparator()
        act_clear = menu.addAction("Clear cooldown")
        act_clear.triggered.connect(self._clear_api_cooldowns)
        menu.addSeparator()
        menu.addAction("Import keys…").triggered.connect(self._import_api_keys)
        menu.addAction("Export keys…").triggered.connect(self._export_api_keys)
        menu.exec(self.api_keys_table.viewport().mapToGlobal(pos))

    def _reload_api_keys(self, *_args):
        if not hasattr(self, "api_keys_table"):
            return
        from claynext.controllers.store import get_store
        from claynext.gui.dialogs.api_keys_dialog import mask_secret
        from claynext.models.llm_keys import describe_key

        provider = self._api_provider_id()
        rows = self._api_key_pool.list_keys(provider)
        usage = get_store().llm_usage(provider)
        self.api_keys_table.setRowCount(0)
        for rec in rows:
            r = self.api_keys_table.rowCount()
            self.api_keys_table.insertRow(r)
            label = QTableWidgetItem(rec.get("label") or f"Key {rec['id']}")
            label.setData(Qt.ItemDataRole.UserRole, int(rec["id"]))
            view = describe_key(rec, usage.get(int(rec["id"])))
            fails = int(rec.get("fail_count") or 0)
            self.api_keys_table.setItem(r, 0, label)
            self.api_keys_table.setItem(r, 1, QTableWidgetItem(mask_secret(rec.get("secret") or "")))
            health = QTableWidgetItem(view["health"])
            health.setData(Qt.ItemDataRole.UserRole, _health_color(view["health"]))
            health.setForeground(QColor(_health_color(view["health"])))
            if fails:
                health.setToolTip(f"{fails} rate-limit hits. Rotation prefers a healthier key.")
            self.api_keys_table.setItem(r, 2, health)
            for col, text in ((3, view["tokens"]), (4, view["limit"]), (5, view["speed"])):
                cell = QTableWidgetItem(text)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.api_keys_table.setItem(r, col, cell)

    def _open_add_api_key(self):
        self._open_api_key_dialog()

    def _open_edit_api_key(self):
        key_id = self._selected_api_key_id()
        if key_id is None:
            return
        self._open_api_key_dialog(key_id)

    def _open_api_key_dialog(self, key_id: int | None = None):
        from claynext.gui.dialogs.api_keys_dialog import ApiKeysDialog

        dlg = ApiKeysDialog(self, provider=self._api_provider_id(), key_id=key_id)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            pid = dlg.provider_id()
            idx = self.combo_api_provider.findData(pid)
            if idx >= 0:
                self.combo_api_provider.blockSignals(True)
                self.combo_api_provider.setCurrentIndex(idx)
                self.combo_api_provider.blockSignals(False)
            self._reload_api_keys()

    def _toggle_api_key(self):
        key_id = self._selected_api_key_id()
        if key_id is None:
            return
        rec = next(
            (r for r in self._api_key_pool.list_keys(self._api_provider_id()) if int(r["id"]) == key_id),
            None,
        )
        if not rec:
            return
        self._api_key_pool.set_enabled(key_id, int(rec.get("enabled") or 0) != 1)
        self._reload_api_keys()

    def _remove_api_key(self):
        key_id = self._selected_api_key_id()
        if key_id is None:
            return
        self._api_key_pool.remove_key(key_id)
        self._reload_api_keys()

    def _api_key_button(self, text: str, slot, *, primary: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("btn_primary" if primary else "btn_secondary")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedHeight(28)
        button.clicked.connect(slot)
        return button

    def _export_api_keys(self):
        import json
        import os
        from pathlib import Path

        from claynext.gui.dialogs.api_keys_dialog import ExportKeysDialog
        from claynext.models.llm_keys import export_api_keys_payload

        dialog = ExportKeysDialog(self, provider=self._api_provider_id())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        choice = dialog.chosen()
        rows = self._api_key_pool.list_keys(choice["provider"] or None)
        if choice["status"] != "all":
            rows = [row for row in rows if int(row.get("enabled") or 0) == 1]
        payload = export_api_keys_payload(rows)
        count = len(payload["keys"])
        if count == 0:
            QMessageBox.information(self, "Export keys", "There are no keys for that choice.")
            return
        dest = Path(choice["path"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            os.chmod(dest, 0o600)
        except OSError:
            pass
        QMessageBox.information(self, "Export keys", f"Saved {count} key(s) to {dest.name}.")

    def _import_api_keys(self):
        import json
        from pathlib import Path

        from claynext.models.llm_keys import parse_api_keys_payload

        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Import API keys",
            str(Path.home()),
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            incoming = parse_api_keys_payload(json.loads(Path(path).read_text(encoding="utf-8")))
        except Exception as exc:
            QMessageBox.warning(self, "Import keys", str(exc) or "Could not read that file.")
            return
        existing = {
            (str(row.get("provider") or ""), str(row.get("secret") or "").strip())
            for row in self._api_key_pool.list_keys()
        }
        added = 0
        for row in incoming:
            identity = (row["provider"], row["secret"])
            if identity in existing:
                continue
            key_id = self._api_key_pool.add_key(row["provider"], row["secret"], row["label"])
            if not row["enabled"]:
                self._api_key_pool.set_enabled(key_id, False)
            existing.add(identity)
            added += 1
        if added:
            current = self._api_provider_id()
            providers = [row["provider"] for row in incoming]
            show = current if current in providers else providers[0]
            idx = self.combo_api_provider.findData(show)
            if idx >= 0 and idx != self.combo_api_provider.currentIndex():
                self.combo_api_provider.setCurrentIndex(idx)
        self._reload_api_keys()
        skipped = len(incoming) - added
        if skipped:
            message = f"Added {added} key(s). {skipped} already saved."
        else:
            message = f"Added {added} key(s)."
        QMessageBox.information(self, "Import keys", message)

    def _clear_api_cooldowns(self):
        store = get_store()
        for rec in self._api_key_pool.list_keys(self._api_provider_id()):
            store.update_api_key_state(int(rec["id"]), fail_count=0, clear_cooldown=True)
        self._reload_api_keys()

    # ─── Features ────────────────────────────────────────────────────

    def _build_features_tab(self) -> QWidget:
        page, lay = self._scroll_page()

        lay.addWidget(self._field_label("Tool backends"))

        cards_host = QWidget()
        cards_host.setObjectName("settings_feature_list")
        self._features_lay = QVBoxLayout(cards_host)
        self._features_lay.setContentsMargins(0, 2, 0, 2)
        self._features_lay.setSpacing(0)
        lay.addWidget(cards_host)

        lay.addWidget(self._divider())

        self.lbl_stem_status = QLabel()
        self.lbl_stem_status.setObjectName("settings_section_hint")
        self.lbl_stem_status.setWordWrap(True)
        self.lbl_stem_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._setting_row("Stem separation", self.lbl_stem_status, grow=True))

        self.combo_stem_mode = QComboBox()
        self.combo_stem_mode.setFixedHeight(28)
        self.combo_stem_mode.setFixedWidth(280)
        self.combo_stem_mode.addItem("Auto — Demucs when installed", "auto")
        self.combo_stem_mode.addItem("Force Demucs", "demucs")
        self.combo_stem_mode.addItem("FFmpeg mid-side only", "ffmpeg")
        self.combo_stem_mode.currentIndexChanged.connect(self._refresh_stem_status_label)
        lay.addWidget(self._setting_row("Mode", self.combo_stem_mode))

        self.combo_demucs_model = QComboBox()
        self.combo_demucs_model.setFixedHeight(28)
        self.combo_demucs_model.setFixedWidth(280)
        for name in DEMUCS_MODELS:
            self.combo_demucs_model.addItem(name, name)
        self.combo_demucs_model.currentIndexChanged.connect(self._refresh_stem_status_label)
        lay.addWidget(self._setting_row("Demucs model", self.combo_demucs_model))

        self.chk_prefer_whisperx, whisper_row = self._toggle_row("Prefer WhisperX for dubbing ASR")
        self.chk_prefer_voxcpm, vox_row = self._toggle_row("Prefer VoxCPM voices in TTS Studio")
        self.chk_transcript_ocr, ocr_row = self._toggle_row(
            "Check burned-in captions before transcription"
        )
        lay.addWidget(whisper_row)
        lay.addWidget(vox_row)
        lay.addWidget(ocr_row)

        self.txt_sglang_url = QLineEdit()
        self.txt_sglang_url.setFixedHeight(28)
        self.txt_sglang_url.setPlaceholderText("http://127.0.0.1:8000")
        lay.addWidget(self._setting_row("SGLang-Omni", self.txt_sglang_url, grow=True))

        self._populate_features_cards()
        lay.addStretch(1)
        return page

    def _populate_features_cards(self):
        while self._features_lay.count():
            item = self._features_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._feature_cards.clear()
        self._feature_controls.clear()

        rows = list_features()
        for i, item in enumerate(rows):
            card = self._make_feature_card(item, last=(i == len(rows) - 1))
            self._features_lay.addWidget(card)

        if self._feature_active:
            self._set_feature_row_progress(
                self._feature_active, self._feature_pct.get(self._feature_active), busy=True,
            )
        for feature_id, _extra, _label in self._feature_queue:
            self._set_feature_row_progress(feature_id, None, busy=True, queued=True)

    def _make_feature_card(self, item: dict, *, last: bool = False) -> QFrame:
        row = QFrame()
        row.setObjectName("settings_feature_row")
        if last:
            row.setProperty("last", "true")
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.setFixedHeight(36)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 0, 10, 0)
        lay.setSpacing(10)

        fid = str(item.get("id") or "")
        title = QLabel(item["label"])
        title.setObjectName("settings_feature_title")
        tip = (item.get("hint") or "").split(". uv sync")[0].strip()
        if tip:
            title.setToolTip(tip)
            row.setToolTip(tip)
        lay.addWidget(title, 0, Qt.AlignmentFlag.AlignVCenter)

        cat = QLabel(str(item.get("category", "")).upper())
        cat.setObjectName("settings_cat_pill")
        lay.addWidget(cat, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addStretch(1)

        pct = QLabel("")
        pct.setObjectName("settings_feature_pct")
        pct.setFixedWidth(40)
        pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        pct.hide()
        lay.addWidget(pct, 0, Qt.AlignmentFlag.AlignVCenter)

        status = str(item.get("status") or "Not installed")
        pill = QLabel(status)
        pill.setObjectName("settings_status_pill")
        if status == "Ready":
            pill.setProperty("tone", "ready")
        elif status == "Unsupported":
            pill.setProperty("tone", "unsupported")
        else:
            pill.setProperty("tone", "missing")
        pill.style().unpolish(pill)
        pill.style().polish(pill)
        if tip:
            pill.setToolTip(tip)
        lay.addWidget(pill, 0, Qt.AlignmentFlag.AlignVCenter)

        action: QWidget | None = None
        extra = str(item.get("extra") or "")
        if extra and status != "Ready" and status != "Unsupported":
            btn = QPushButton("Install")
            btn.setObjectName("settings_copy_btn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip("Installs once and keeps the tools already on this machine.")
            btn.clicked.connect(
                lambda _=False, i=fid, e=extra, n=item["label"]: self._install_feature(i, e, n)
            )
            lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
            action = btn
        elif status == "Ready":
            ok = QLabel("Active")
            ok.setObjectName("settings_feature_active")
            lay.addWidget(ok, 0, Qt.AlignmentFlag.AlignVCenter)
            action = ok

        row.style().unpolish(row)
        row.style().polish(row)
        self._feature_cards.append(row)
        self._feature_controls[fid] = {
            "pct": pct,
            "pill": pill,
            "action": action,
            "label": item["label"],
            "extra": extra,
        }
        return row

    def _install_feature(self, feature_id: str, extra: str, label: str):
        if feature_id == self._feature_active or any(fid == feature_id for fid, _e, _n in self._feature_queue):
            return
        from claynext.models.features import feature_status

        current = feature_status(feature_id)
        if not current.get("supported"):
            QMessageBox.information(self, "Unsupported", current.get("hint") or f"{label} cannot be installed on this Mac.")
            return
        if self._feature_active:
            self._feature_queue.append((feature_id, extra, label))
            self._set_feature_row_progress(feature_id, None, busy=True, queued=True)
            return
        self._start_feature_install(feature_id, extra, label)

    def _start_feature_install(self, feature_id: str, extra: str, label: str):
        self._feature_active = feature_id
        self._feature_pct[feature_id] = 0
        self._set_feature_row_progress(feature_id, 0, busy=True)

        def _task(progress_callback=None):
            return install_uv_extra(extra, progress_callback=progress_callback)

        worker = Worker(_task)
        worker.signals.progress.connect(
            lambda v, _m, fid=feature_id: self._on_feature_progress(fid, v)
        )
        worker.signals.result.connect(
            lambda _r, fid=feature_id, n=label: self._on_feature_install_done(fid, n)
        )
        worker.signals.error.connect(
            lambda err, _tb, fid=feature_id: self._on_feature_install_error(fid, err)
        )
        self.thread_pool.start(worker)

    def _pump_feature_queue(self):
        if self._feature_active or not self._feature_queue:
            return
        feature_id, extra, label = self._feature_queue.pop(0)
        self._start_feature_install(feature_id, extra, label)

    def _on_feature_progress(self, feature_id: str, percent: int):
        self._feature_pct[feature_id] = max(0, min(100, int(percent)))
        self._set_feature_row_progress(feature_id, self._feature_pct[feature_id], busy=True)

    def _set_feature_row_progress(
        self, feature_id: str, percent: int | None, *, busy: bool, queued: bool = False,
    ):
        ctrl = self._feature_controls.get(feature_id)
        if not ctrl:
            return
        pct_lbl: QLabel = ctrl["pct"]
        pill: QLabel = ctrl["pill"]
        action = ctrl.get("action")
        if busy:
            if queued:
                pct_lbl.setText("")
                pct_lbl.hide()
                pill.setText("Queued")
            else:
                val = 0 if percent is None else max(0, min(100, int(percent)))
                pct_lbl.setText(f"{val}%")
                pct_lbl.show()
                pill.setText("Installing")
            pill.setProperty("tone", "missing")
            pill.style().unpolish(pill)
            pill.style().polish(pill)
            if isinstance(action, QPushButton):
                action.setEnabled(False)
                action.setText("…")
        else:
            pct_lbl.hide()
            pct_lbl.setText("")

    def _on_feature_install_done(self, feature_id: str, label: str):
        self._feature_pct.pop(feature_id, None)
        if self._feature_active == feature_id:
            self._feature_active = None
        self._pump_feature_queue()
        self._populate_features_cards()
        self._refresh_stem_status_label()
        QMessageBox.information(self, "Installed", f"{label} is ready.")

    def _on_feature_install_error(self, feature_id: str, err_msg: str):
        self._feature_pct.pop(feature_id, None)
        if self._feature_active == feature_id:
            self._feature_active = None
        self._pump_feature_queue()
        self._populate_features_cards()
        QMessageBox.critical(self, "Install failed", str(err_msg or "uv sync failed."))

    def _refresh_stem_status_label(self, *_args):
        mode = self.combo_stem_mode.currentData() or "auto"
        model = self.combo_demucs_model.currentData() or "htdemucs"
        from claynext.models.features import stem_backend
        backend = stem_backend()
        if mode == "ffmpeg":
            text = "Active bed · FFmpeg mid-side (forced)"
        elif backend == "mlx":
            text = f"Active bed · Demucs MLX · {model}"
        elif backend == "torch":
            text = f"Active bed · Demucs · {model}"
        elif mode == "demucs":
            text = "Demucs required · uv sync --extra demucs-mlx or demucs"
        else:
            text = "Fallback bed · FFmpeg · install Demucs for AI isolation"
        self.lbl_stem_status.setText(text)

    # ─── Hardware ────────────────────────────────────────────────────

    def _build_hardware_paths_tab(self) -> QWidget:
        page, lay = self._scroll_page()

        from claynext.adapters.resources import available_devices, resource_plan

        self.combo_device = QComboBox()
        self.combo_device.setFixedHeight(28)
        self.combo_device.setFixedWidth(280)
        for row in available_devices():
            self.combo_device.addItem(row["label"], row["id"])
        lay.addWidget(self._setting_row("Preferred device", self.combo_device))

        cores = max(1, int(resource_plan()["logical_cores"]))
        self.spin_threads = QSpinBox()
        self.spin_threads.setFixedHeight(28)
        self.spin_threads.setFixedWidth(88)
        self.spin_threads.setRange(0, cores)
        self.spin_threads.setSpecialValueText("Auto")
        self.spin_threads.setValue(0)
        lay.addWidget(self._setting_row("Worker threads", self.spin_threads))

        self.lbl_hardware = QLabel("")
        self.lbl_hardware.setObjectName("settings_section_hint")
        self.lbl_hardware.setWordWrap(True)
        lay.addWidget(self.lbl_hardware)
        self.combo_device.currentIndexChanged.connect(self._refresh_hardware_label)
        self.spin_threads.valueChanged.connect(self._refresh_hardware_label)

        lay.addWidget(self._divider())

        self.txt_models_dir = QLineEdit(str(MODELS_DIR))
        self.txt_models_dir.setFixedHeight(28)
        btn_b_models = QPushButton("Browse")
        btn_b_models.setObjectName("btn_secondary")
        btn_b_models.setFixedHeight(28)
        btn_b_models.setFixedWidth(74)
        btn_b_models.clicked.connect(lambda: self.browse_folder(self.txt_models_dir))
        lay.addWidget(self._setting_row("Models cache", self.txt_models_dir, btn_b_models, grow=True))

        self.txt_outputs_dir = QLineEdit(str(OUTPUTS_DIR))
        self.txt_outputs_dir.setFixedHeight(28)
        btn_b_outputs = QPushButton("Browse")
        btn_b_outputs.setObjectName("btn_secondary")
        btn_b_outputs.setFixedHeight(28)
        btn_b_outputs.setFixedWidth(74)
        btn_b_outputs.clicked.connect(lambda: self.browse_folder(self.txt_outputs_dir))
        lay.addWidget(self._setting_row("Default exports", self.txt_outputs_dir, btn_b_outputs, grow=True))

        lay.addStretch(1)
        return page

    # ─── Appearance ──────────────────────────────────────────────────

    def _build_appearance_tab(self) -> QWidget:
        page, lay = self._scroll_page()

        self.combo_theme = QComboBox()
        self.combo_theme.setFixedHeight(28)
        self.combo_theme.setFixedWidth(280)
        self.combo_theme.addItems(["CamDot Dark Obsidian (Default)", "System Light Mode"])
        lay.addWidget(self._setting_row("Theme", self.combo_theme))

        self.combo_accent = QComboBox()
        self.combo_accent.setFixedHeight(28)
        self.combo_accent.setFixedWidth(280)
        self.combo_accent.addItems([
            "Indigo / Purple (#6366f1)",
            "Emerald Green (#10b981)",
            "Cyan Blue (#06b6d4)",
            "Rose Pink (#f43f5e)",
        ])
        lay.addWidget(self._setting_row("Accent", self.combo_accent))

        lay.addWidget(self._divider())

        self.chk_anim, anim_row = self._toggle_row("Enable UI micro-animations", checked=True)
        lay.addWidget(anim_row)

        lay.addStretch(1)
        return page

    def _refresh_hardware_label(self, *_args) -> None:
        if not hasattr(self, "lbl_hardware"):
            return
        from claynext.adapters.resources import describe_plan, resource_plan

        plan = resource_plan(
            device=str(self.combo_device.currentData() or "best"),
            threads=int(self.spin_threads.value()),
        )
        self.lbl_hardware.setText(describe_plan(plan))

    def browse_folder(self, target_line_edit: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, "Select Directory", target_line_edit.text())
        if folder:
            target_line_edit.setText(folder)

    def _set_combo_data(self, combo: QComboBox, data: str):
        idx = combo.findData(data)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _set_combo_text(self, combo: QComboBox, text: str):
        idx = combo.findText(text)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _load_from_store(self):
        store = get_store()
        self._set_combo_text(
            self.combo_lang,
            store.get_setting("studio", "ui_language", DEFAULT_CONFIG["ui_language"]),
        )
        self.chk_updates.setChecked(store.get_setting("studio", "check_updates", "1") == "1")
        self.chk_auto_open.setChecked(store.get_setting("studio", "auto_open_exports", "1") == "1")
        self.chk_keep_awake.setChecked(store.get_setting("studio", "keep_awake", "1") == "1")
        self.chk_notify.setChecked(store.get_setting("studio", "notify_on_complete", "1") == "1")

        self._set_combo_data(
            self.combo_stem_mode,
            get_feature_setting("stem_separation", DEFAULT_CONFIG["stem_separation"]),
        )
        self._set_combo_data(
            self.combo_demucs_model,
            get_feature_setting("demucs_model", DEFAULT_CONFIG["demucs_model"]),
        )
        self.chk_prefer_whisperx.setChecked(
            get_feature_setting("prefer_whisperx", DEFAULT_CONFIG["prefer_whisperx"]) == "1"
        )
        self.chk_prefer_voxcpm.setChecked(
            get_feature_setting("prefer_voxcpm", DEFAULT_CONFIG["prefer_voxcpm"]) == "1"
        )
        self.chk_transcript_ocr.setChecked(
            get_feature_setting("transcript_ocr", DEFAULT_CONFIG["transcript_ocr"]) == "1"
        )
        self.txt_sglang_url.setText(
            get_feature_setting("sglang_omni_url", DEFAULT_CONFIG["sglang_omni_url"])
            or DEFAULT_CONFIG["sglang_omni_url"]
        )
        self._refresh_stem_status_label()
        self._populate_features_cards()

        from claynext.adapters.resources import stored_choice

        device, threads = stored_choice()
        self._set_combo_data(self.combo_device, device)
        self.spin_threads.setValue(max(0, min(self.spin_threads.maximum(), threads)))
        self._refresh_hardware_label()
        self.txt_models_dir.setText(
            store.get_setting("studio", "models_directory", str(MODELS_DIR)) or str(MODELS_DIR)
        )
        self.txt_outputs_dir.setText(
            store.get_setting("studio", "save_directory", str(OUTPUTS_DIR)) or str(OUTPUTS_DIR)
        )

        theme = store.get_setting("studio", "theme", DEFAULT_CONFIG["theme"])
        self.combo_theme.setCurrentIndex(1 if "Light" in theme else 0)
        accent = store.get_setting("studio", "accent", DEFAULT_CONFIG["accent"])
        self._set_combo_text(self.combo_accent, accent)
        self.chk_anim.setChecked(store.get_setting("studio", "ui_animations", "1") == "1")

    def restore_defaults(self):
        self.combo_lang.setCurrentIndex(0)
        self.chk_updates.setChecked(True)
        self.chk_auto_open.setChecked(True)
        self.chk_keep_awake.setChecked(True)
        self.chk_notify.setChecked(True)
        self._set_combo_data(self.combo_stem_mode, DEFAULT_CONFIG["stem_separation"])
        self._set_combo_data(self.combo_demucs_model, DEFAULT_CONFIG["demucs_model"])
        self.chk_prefer_whisperx.setChecked(DEFAULT_CONFIG["prefer_whisperx"] == "1")
        self.chk_prefer_voxcpm.setChecked(DEFAULT_CONFIG["prefer_voxcpm"] == "1")
        self.chk_transcript_ocr.setChecked(DEFAULT_CONFIG["transcript_ocr"] == "1")
        self.txt_sglang_url.setText(DEFAULT_CONFIG["sglang_omni_url"])
        self._refresh_stem_status_label()
        self._populate_features_cards()
        self._set_combo_data(self.combo_device, DEFAULT_CONFIG["device"])
        self.spin_threads.setValue(int(DEFAULT_CONFIG["worker_threads"]))
        self._refresh_hardware_label()
        self.txt_models_dir.setText(str(MODELS_DIR))
        self.txt_outputs_dir.setText(str(OUTPUTS_DIR))
        self.combo_theme.setCurrentIndex(0)
        self._set_combo_text(self.combo_accent, DEFAULT_CONFIG["accent"])
        self.chk_anim.setChecked(True)

    def save_config(self):
        store = get_store()
        store.set_setting("studio", "ui_language", self.combo_lang.currentText())
        store.set_setting("studio", "check_updates", "1" if self.chk_updates.isChecked() else "0")
        store.set_setting("studio", "auto_open_exports", "1" if self.chk_auto_open.isChecked() else "0")
        store.set_setting("studio", "keep_awake", "1" if self.chk_keep_awake.isChecked() else "0")
        store.set_setting("studio", "notify_on_complete", "1" if self.chk_notify.isChecked() else "0")

        set_feature_setting("stem_separation", self.combo_stem_mode.currentData() or "auto")
        set_feature_setting("demucs_model", self.combo_demucs_model.currentData() or "htdemucs")
        set_feature_setting("prefer_whisperx", "1" if self.chk_prefer_whisperx.isChecked() else "0")
        set_feature_setting("prefer_voxcpm", "1" if self.chk_prefer_voxcpm.isChecked() else "0")
        set_feature_setting("transcript_ocr", "1" if self.chk_transcript_ocr.isChecked() else "0")
        set_feature_setting(
            "sglang_omni_url",
            self.txt_sglang_url.text().strip() or DEFAULT_CONFIG["sglang_omni_url"],
        )

        store.set_setting("studio", "device", str(self.combo_device.currentData() or "best"))
        store.set_setting("studio", "worker_threads", str(self.spin_threads.value()))
        try:
            from claynext.adapters.resources import apply_process_threads

            apply_process_threads()
        except Exception:
            pass
        store.set_setting("studio", "models_directory", self.txt_models_dir.text().strip() or str(MODELS_DIR))
        store.set_setting("studio", "save_directory", self.txt_outputs_dir.text().strip() or str(OUTPUTS_DIR))

        theme = "System Light Mode" if self.combo_theme.currentIndex() == 1 else DEFAULT_CONFIG["theme"]
        store.set_setting("studio", "theme", theme)
        store.set_setting("studio", "accent", self.combo_accent.currentText())
        store.set_setting("studio", "ui_animations", "1" if self.chk_anim.isChecked() else "0")

        for key in FEATURE_SETTING_KEYS:
            if not store.get_setting("studio", key, ""):
                set_feature_setting(key, str(DEFAULT_CONFIG.get(key, "")))

        self.accept()

