from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
    QLineEdit, QPushButton, QFileDialog, QTabWidget, QWidget, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar, QMessageBox,
    QScrollArea, QFrame, QSizePolicy, QAbstractItemView,
)
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QColor
from claynext.utils.config import DEFAULT_CONFIG, MODELS_DIR, OUTPUTS_DIR
from claynext.gui.icons import icon
from claynext.gui.worker import Worker
from claynext.models.hf_hub import get_model_registry, pull_model, is_model_downloaded
from claynext.models.features import (
    DEMUCS_MODELS,
    FEATURE_SETTING_KEYS,
    get_feature_setting,
    install_uv_extra,
    list_features,
    set_feature_setting,
)
from claynext.controllers.store import get_store


class SettingsDialog(QDialog):
    """Studio settings — Features, models, paths, and appearance."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings — Claynext Studio")
        self.setMinimumSize(660, 440)
        self.resize(720, 480)
        self.setModal(True)
        self.thread_pool = QThreadPool.globalInstance()
        self._feature_cards: list[QFrame] = []
        self._feature_controls: dict[str, dict] = {}
        self._feature_installing: str | None = None
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
        self.tabs.addTab(self._build_models_tab(), icon("cpu", size=13), "Models")
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
        lay.addWidget(self._field_label("Language"))
        self.combo_lang = QComboBox()
        self.combo_lang.setFixedHeight(28)
        self.combo_lang.addItems([
            "English (US)", "Vietnamese (Tiếng Việt)", "Japanese (日本語)", "Chinese (中文)",
        ])
        lay.addWidget(self.combo_lang)

        lay.addWidget(self._divider())

        self.chk_updates = QCheckBox("Check for updates on startup")
        self.chk_auto_open = QCheckBox("Open export folder when complete")
        self.chk_keep_awake = QCheckBox("Prevent sleep during processing")
        self.chk_notify = QCheckBox("Show completion notifications")
        for chk in (self.chk_updates, self.chk_auto_open, self.chk_keep_awake, self.chk_notify):
            chk.setChecked(True)
            lay.addWidget(chk)
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
        btn_add = QPushButton("Add key")
        btn_add.setObjectName("btn_primary")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setFixedHeight(28)
        btn_add.setMinimumWidth(84)
        btn_add.clicked.connect(self._open_add_api_key)
        head.addWidget(btn_add, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(head)

        self.api_keys_table = QTableWidget(0, 5)
        self.api_keys_table.setObjectName("settings_api_keys_table")
        self.api_keys_table.setHorizontalHeaderLabels(
            ["Label", "Key", "Status", "Fails", "Enabled"]
        )
        hdr = self.api_keys_table.horizontalHeader()
        hdr.setHighlightSections(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.api_keys_table.setColumnWidth(3, 52)
        self.api_keys_table.setColumnWidth(4, 64)
        self.api_keys_table.verticalHeader().setVisible(False)
        self.api_keys_table.verticalHeader().setDefaultSectionSize(32)
        self.api_keys_table.setShowGrid(False)
        self.api_keys_table.setAlternatingRowColors(True)
        self.api_keys_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.api_keys_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.api_keys_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.api_keys_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.api_keys_table.customContextMenuRequested.connect(self._api_keys_context_menu)
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
            act_toggle = menu.addAction("Disable" if enabled else "Enable")
            act_toggle.triggered.connect(self._toggle_api_key)
            act_remove = menu.addAction("Remove")
            act_remove.triggered.connect(self._remove_api_key)
            menu.addSeparator()
        act_clear = menu.addAction("Clear cooldown")
        act_clear.triggered.connect(self._clear_api_cooldowns)
        menu.exec(self.api_keys_table.viewport().mapToGlobal(pos))

    def _reload_api_keys(self, *_args):
        if not hasattr(self, "api_keys_table"):
            return
        from claynext.gui.dialogs.api_keys_dialog import mask_secret
        from claynext.models.llm_keys import _now, _parse_iso

        provider = self._api_provider_id()
        rows = self._api_key_pool.list_keys(provider)
        self.api_keys_table.setRowCount(0)
        now = _now()
        for rec in rows:
            r = self.api_keys_table.rowCount()
            self.api_keys_table.insertRow(r)
            label = QTableWidgetItem(rec.get("label") or f"Key {rec['id']}")
            label.setData(Qt.ItemDataRole.UserRole, int(rec["id"]))
            self.api_keys_table.setItem(r, 0, label)
            self.api_keys_table.setItem(r, 1, QTableWidgetItem(mask_secret(rec.get("secret") or "")))
            until = _parse_iso(rec.get("cooldown_until"))
            enabled = int(rec.get("enabled") or 0) == 1
            if not enabled:
                status = "Disabled"
            elif until and until > now:
                secs = int((until - now).total_seconds())
                status = f"Cooling {secs}s"
            else:
                status = "Ready"
            fails = QTableWidgetItem(str(rec.get("fail_count") or 0))
            fails.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            enabled_item = QTableWidgetItem("Yes" if enabled else "No")
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.api_keys_table.setItem(r, 2, QTableWidgetItem(status))
            self.api_keys_table.setItem(r, 3, fails)
            self.api_keys_table.setItem(r, 4, enabled_item)

    def _open_add_api_key(self):
        from claynext.gui.dialogs.api_keys_dialog import ApiKeysDialog

        dlg = ApiKeysDialog(self, provider=self._api_provider_id())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Keep provider filter on the key that was added
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

        lay.addWidget(self._field_label("Stem separation"))
        self.lbl_stem_status = QLabel()
        self.lbl_stem_status.setObjectName("settings_section_hint")
        self.lbl_stem_status.setWordWrap(True)
        lay.addWidget(self.lbl_stem_status)

        row = QHBoxLayout()
        row.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(5)
        left.addWidget(self._field_label("Mode"))
        self.combo_stem_mode = QComboBox()
        self.combo_stem_mode.setFixedHeight(28)
        self.combo_stem_mode.addItem("Auto — Demucs when installed", "auto")
        self.combo_stem_mode.addItem("Force Demucs", "demucs")
        self.combo_stem_mode.addItem("FFmpeg mid-side only", "ffmpeg")
        self.combo_stem_mode.currentIndexChanged.connect(self._refresh_stem_status_label)
        left.addWidget(self.combo_stem_mode)
        row.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(5)
        right.addWidget(self._field_label("Demucs model"))
        self.combo_demucs_model = QComboBox()
        self.combo_demucs_model.setFixedHeight(28)
        for name in DEMUCS_MODELS:
            self.combo_demucs_model.addItem(name, name)
        self.combo_demucs_model.currentIndexChanged.connect(self._refresh_stem_status_label)
        right.addWidget(self.combo_demucs_model)
        row.addLayout(right, 1)
        lay.addLayout(row)

        lay.addSpacing(4)
        self.chk_prefer_whisperx = QCheckBox("Prefer WhisperX for dubbing ASR")
        self.chk_prefer_voxcpm = QCheckBox("Prefer VoxCPM voices in TTS Studio")
        lay.addWidget(self.chk_prefer_whisperx)
        lay.addWidget(self.chk_prefer_voxcpm)

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

        # Restore in-progress install chrome after a rebuild
        if self._feature_installing:
            self._set_feature_row_progress(self._feature_installing, None, busy=True)

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
        lay.addWidget(pill, 0, Qt.AlignmentFlag.AlignVCenter)

        action: QWidget | None = None
        extra = str(item.get("extra") or "")
        if extra and status != "Ready" and status != "Unsupported":
            btn = QPushButton("Install")
            btn.setObjectName("settings_copy_btn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"uv sync --extra {extra}")
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
        if self._feature_installing:
            return
        self._feature_installing = feature_id
        self._set_feature_row_progress(feature_id, 0, busy=True)

        def _task(progress_callback=None):
            return install_uv_extra(extra, progress_callback=progress_callback)

        worker = Worker(_task)
        worker.signals.progress.connect(
            lambda v, _m, fid=feature_id: self._set_feature_row_progress(fid, v, busy=True)
        )
        worker.signals.result.connect(
            lambda _r, fid=feature_id, n=label: self._on_feature_install_done(fid, n)
        )
        worker.signals.error.connect(
            lambda err, _tb, fid=feature_id: self._on_feature_install_error(fid, err)
        )
        self.thread_pool.start(worker)

    def _set_feature_row_progress(self, feature_id: str, percent: int | None, *, busy: bool):
        ctrl = self._feature_controls.get(feature_id)
        if not ctrl:
            return
        pct_lbl: QLabel = ctrl["pct"]
        pill: QLabel = ctrl["pill"]
        action = ctrl.get("action")
        if busy:
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
            # Disable other Install buttons while one job runs
            for fid, other in self._feature_controls.items():
                if fid == feature_id:
                    continue
                btn = other.get("action")
                if isinstance(btn, QPushButton):
                    btn.setEnabled(False)
        else:
            pct_lbl.hide()
            pct_lbl.setText("")

    def _on_feature_install_done(self, feature_id: str, label: str):
        self._feature_installing = None
        self._populate_features_cards()
        self._refresh_stem_status_label()
        QMessageBox.information(self, "Installed", f"{label} is ready.")

    def _on_feature_install_error(self, feature_id: str, err_msg: str):
        self._feature_installing = None
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

    # ─── Models ──────────────────────────────────────────────────────

    def _build_models_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self._field_label("Models"), 0, Qt.AlignmentFlag.AlignVCenter)
        top.addStretch(1)

        self.combo_model_filter = QComboBox()
        self.combo_model_filter.setObjectName("settings_filter_combo")
        self.combo_model_filter.setFixedHeight(26)
        self.combo_model_filter.addItem("All types", "")
        self.combo_model_filter.addItem("Translate", "translate")
        self.combo_model_filter.addItem("TTS", "tts")
        self.combo_model_filter.addItem("ASR", "asr")
        self.combo_model_filter.addItem("Audio", "audio")
        self.combo_model_filter.currentIndexChanged.connect(self._populate_models_table)
        top.addWidget(self.combo_model_filter, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(top)

        pull_row = QHBoxLayout()
        pull_row.setSpacing(6)
        self.edit_custom_repo = QLineEdit()
        self.edit_custom_repo.setFixedHeight(26)
        self.edit_custom_repo.setPlaceholderText("owner/repo — e.g. prithivMLmods/Common-Voice-Gender-Detection")
        btn_pull_custom = QPushButton("Pull")
        btn_pull_custom.setObjectName("btn_primary")
        btn_pull_custom.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_pull_custom.setFixedSize(70, 26)
        btn_pull_custom.clicked.connect(self._pull_custom_repo)
        pull_row.addWidget(self.edit_custom_repo, 1)
        pull_row.addWidget(btn_pull_custom)
        lay.addLayout(pull_row)

        self.models_table = QTableWidget()
        self.models_table.setObjectName("settings_models_table")
        self.models_table.setColumnCount(5)
        self.models_table.setHorizontalHeaderLabels(["Model", "Type", "Size", "Status", ""])
        hdr_view = self.models_table.horizontalHeader()
        hdr_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr_view.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.models_table.setColumnWidth(4, 86)
        self.models_table.verticalHeader().setVisible(False)
        self.models_table.verticalHeader().setDefaultSectionSize(34)
        self.models_table.setShowGrid(False)
        self.models_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.models_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.models_table, 1)

        self.model_prog_box = QWidget()
        self.model_prog_box.hide()
        p_lay = QVBoxLayout(self.model_prog_box)
        p_lay.setContentsMargins(0, 0, 0, 0)
        p_lay.setSpacing(4)
        self.lbl_model_prog = QLabel("Pulling model…")
        self.lbl_model_prog.setObjectName("settings_section_hint")
        self.lbl_model_prog.setStyleSheet("color: #6366f1; font-weight: 600;")
        self.bar_model_prog = QProgressBar()
        self.bar_model_prog.setFixedHeight(5)
        p_lay.addWidget(self.lbl_model_prog)
        p_lay.addWidget(self.bar_model_prog)
        lay.addWidget(self.model_prog_box)

        self._populate_models_table()
        return page

    def _populate_models_table(self, *_args):
        filt = ""
        if hasattr(self, "combo_model_filter"):
            filt = self.combo_model_filter.currentData() or ""
        models = get_model_registry()
        if filt:
            models = [m for m in models if str(m.get("category", "")).lower() == filt]

        self.models_table.setRowCount(0)
        for row, item in enumerate(models):
            self.models_table.insertRow(row)
            name = QTableWidgetItem(item["name"])
            name.setToolTip(item["id"])
            self.models_table.setItem(row, 0, name)

            cat_item = QTableWidgetItem(str(item.get("category", "")).upper())
            cat_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.models_table.setItem(row, 1, cat_item)

            size_item = QTableWidgetItem(item.get("size_label", ""))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.models_table.setItem(row, 2, size_item)

            is_down = is_model_downloaded(item["id"])
            status_item = QTableWidgetItem("Downloaded" if is_down else "Available")
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setForeground(QColor("#10b981") if is_down else QColor("#64748b"))
            self.models_table.setItem(row, 3, status_item)

            btn = QPushButton("Ready" if is_down else "Pull HF")
            btn.setObjectName("btn_secondary" if is_down else "btn_primary")
            btn.setEnabled(not is_down)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(70, 22)
            btn.setStyleSheet("font-size: 11px; padding: 0;")
            repo_id = item["id"]
            btn.clicked.connect(lambda _=False, rid=repo_id: self._pull_repo(rid))
            wrap = QWidget()
            wrap_l = QHBoxLayout(wrap)
            wrap_l.setContentsMargins(4, 2, 6, 2)
            wrap_l.addStretch(1)
            wrap_l.addWidget(btn)
            self.models_table.setCellWidget(row, 4, wrap)

    def _pull_custom_repo(self):
        repo_id = self.edit_custom_repo.text().strip()
        if not repo_id:
            QMessageBox.warning(self, "Missing Repo", "Enter a valid Hugging Face repository ID.")
            return
        self._pull_repo(repo_id)

    def _pull_repo(self, repo_id: str):
        self.model_prog_box.show()
        self.lbl_model_prog.setText(f"Pulling {repo_id}…")
        self.bar_model_prog.setValue(10)

        def _task(progress_callback=None):
            return pull_model(repo_id, progress_callback=progress_callback)

        worker = Worker(_task)
        worker.signals.progress.connect(self._on_model_pull_progress)
        worker.signals.result.connect(self._on_model_pull_complete)
        worker.signals.error.connect(self._on_model_pull_error)
        self.thread_pool.start(worker)

    def _on_model_pull_progress(self, val: int, msg: str):
        self.bar_model_prog.setValue(val)
        self.lbl_model_prog.setText(msg)

    def _on_model_pull_complete(self, _path):
        self.model_prog_box.hide()
        self._populate_models_table()
        self._populate_features_cards()
        QMessageBox.information(self, "Download Complete", "Model pulled into the local cache.")

    def _on_model_pull_error(self, err_msg, stack):
        self.model_prog_box.hide()
        QMessageBox.critical(self, "Download Failed", f"Could not pull model:\n{err_msg}")

    # ─── Hardware ────────────────────────────────────────────────────

    def _build_hardware_paths_tab(self) -> QWidget:
        page, lay = self._scroll_page()

        lay.addWidget(self._field_label("Preferred device"))
        self.combo_device = QComboBox()
        self.combo_device.setFixedHeight(28)
        self.combo_device.addItems([
            "CUDA (NVIDIA GPU)", "DirectML (AMD / Intel GPU)", "CPU Threadpool (Fallback)",
        ])
        lay.addWidget(self.combo_device)

        lay.addWidget(self._field_label("Worker threads"))
        self.spin_threads = QSpinBox()
        self.spin_threads.setFixedHeight(28)
        self.spin_threads.setRange(1, 16)
        self.spin_threads.setValue(4)
        lay.addWidget(self.spin_threads)

        lay.addWidget(self._divider())

        lay.addWidget(self._field_label("Models cache"))
        models_box = QHBoxLayout()
        models_box.setSpacing(6)
        self.txt_models_dir = QLineEdit(str(MODELS_DIR))
        self.txt_models_dir.setFixedHeight(28)
        btn_b_models = QPushButton("Browse")
        btn_b_models.setObjectName("btn_secondary")
        btn_b_models.setFixedWidth(74)
        btn_b_models.clicked.connect(lambda: self.browse_folder(self.txt_models_dir))
        models_box.addWidget(self.txt_models_dir, 1)
        models_box.addWidget(btn_b_models)
        lay.addLayout(models_box)

        lay.addWidget(self._field_label("Default exports"))
        outputs_box = QHBoxLayout()
        outputs_box.setSpacing(6)
        self.txt_outputs_dir = QLineEdit(str(OUTPUTS_DIR))
        self.txt_outputs_dir.setFixedHeight(28)
        btn_b_outputs = QPushButton("Browse")
        btn_b_outputs.setObjectName("btn_secondary")
        btn_b_outputs.setFixedWidth(74)
        btn_b_outputs.clicked.connect(lambda: self.browse_folder(self.txt_outputs_dir))
        outputs_box.addWidget(self.txt_outputs_dir, 1)
        outputs_box.addWidget(btn_b_outputs)
        lay.addLayout(outputs_box)

        lay.addStretch(1)
        return page

    # ─── Appearance ──────────────────────────────────────────────────

    def _build_appearance_tab(self) -> QWidget:
        page, lay = self._scroll_page()

        lay.addWidget(self._field_label("Theme"))
        self.combo_theme = QComboBox()
        self.combo_theme.setFixedHeight(28)
        self.combo_theme.addItems(["CamDot Dark Obsidian (Default)", "System Light Mode"])
        lay.addWidget(self.combo_theme)

        lay.addWidget(self._field_label("Accent"))
        self.combo_accent = QComboBox()
        self.combo_accent.setFixedHeight(28)
        self.combo_accent.addItems([
            "Indigo / Purple (#6366f1)",
            "Emerald Green (#10b981)",
            "Cyan Blue (#06b6d4)",
            "Rose Pink (#f43f5e)",
        ])
        lay.addWidget(self.combo_accent)

        lay.addWidget(self._divider())

        self.chk_anim = QCheckBox("Enable UI micro-animations")
        self.chk_anim.setChecked(True)
        lay.addWidget(self.chk_anim)

        lay.addStretch(1)
        return page

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
        self._refresh_stem_status_label()
        self._populate_features_cards()

        device = store.get_setting("studio", "device", DEFAULT_CONFIG["device"])
        self._set_combo_text(self.combo_device, device)
        try:
            threads = int(store.get_setting("studio", "worker_threads", DEFAULT_CONFIG["worker_threads"]))
        except ValueError:
            threads = 4
        self.spin_threads.setValue(max(1, min(16, threads)))
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
        self._refresh_stem_status_label()
        self._populate_features_cards()
        self._set_combo_text(self.combo_device, DEFAULT_CONFIG["device"])
        self.spin_threads.setValue(int(DEFAULT_CONFIG["worker_threads"]))
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

        store.set_setting("studio", "device", self.combo_device.currentText())
        store.set_setting("studio", "worker_threads", str(self.spin_threads.value()))
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

