from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
    QLineEdit, QPushButton, QFileDialog, QTabWidget, QWidget, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar, QMessageBox,
    QScrollArea, QFrame, QSizePolicy, QApplication, QAbstractItemView,
)
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QColor
from claynext.utils.config import DEFAULT_CONFIG, MODELS_DIR, OUTPUTS_DIR
from claynext.gui.icons import icon
from claynext.gui.worker import Worker
from claynext.services.hf_hub import get_model_registry, pull_model, is_model_downloaded
from claynext.services.features import (
    DEMUCS_MODELS,
    FEATURE_SETTING_KEYS,
    get_feature_setting,
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
        self.init_ui()
        self._load_from_store()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel("Settings")
        title.setObjectName("settings_section_title")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #f1f5f9;")
        sub = QLabel("Studio preferences & AI backends")
        sub.setObjectName("settings_section_hint")
        sub.setStyleSheet("font-size: 11px; color: #64748b; margin-top: 2px;")
        head.addWidget(title)
        head.addWidget(sub)
        head.addStretch(1)
        layout.addLayout(head)

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
    def _divider() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setObjectName("settings_divider")
        return line

    @staticmethod
    def _section(title: str, hint: str = "") -> tuple[QWidget, QVBoxLayout]:
        sec = QWidget()
        sec.setObjectName("settings_section")
        lay = QVBoxLayout(sec)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
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
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)
        scroll.setWidget(host)
        outer.addWidget(scroll)
        return page, lay

    # ─── General ─────────────────────────────────────────────────────

    def _build_general_tab(self) -> QWidget:
        page, lay = self._scroll_page()
        sec_lang, p = self._section("Interface Language", "Display language for menus and studio tools.")
        self.combo_lang = QComboBox()
        self.combo_lang.setFixedHeight(26)
        self.combo_lang.addItems([
            "English (US)", "Vietnamese (Tiếng Việt)", "Japanese (日本語)", "Chinese (中文)",
        ])
        p.addWidget(self.combo_lang)
        lay.addWidget(sec_lang)

        lay.addWidget(self._divider())

        sec_ops, ops = self._section("Automation & Behavior", "Background execution and completion preferences.")
        self.chk_updates = QCheckBox("Check for updates on startup")
        self.chk_auto_open = QCheckBox("Open export folder when complete")
        self.chk_keep_awake = QCheckBox("Prevent sleep during processing")
        self.chk_notify = QCheckBox("Show completion notifications")
        for chk in (self.chk_updates, self.chk_auto_open, self.chk_keep_awake, self.chk_notify):
            chk.setChecked(True)
            ops.addWidget(chk)
        lay.addWidget(sec_ops)
        lay.addStretch(1)
        return page

    def _build_api_keys_tab(self) -> QWidget:
        page, lay = self._scroll_page()
        panel, p = self._section(
            "Cloud & AI Keys",
            "Gemini Flash, Hugging Face, and local inference keys.",
        )
        btn = QPushButton("Manage Keys…")
        btn.setObjectName("btn_primary")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(26)
        btn.clicked.connect(self._open_api_keys)
        p.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(panel)
        lay.addStretch(1)
        return page

    def _open_api_keys(self):
        from claynext.gui.dialogs.api_keys_dialog import ApiKeysDialog
        ApiKeysDialog(self).exec()

    # ─── Features ────────────────────────────────────────────────────

    def _build_features_tab(self) -> QWidget:
        page, lay = self._scroll_page()

        tools, t = self._section(
            "Tool Backends",
            "Optional AI models and neural voice engines.",
        )
        summary = QLabel()
        summary.setObjectName("settings_section_hint")
        self.lbl_feature_summary = summary
        t.addWidget(summary)

        cards_host = QWidget()
        self._features_lay = QVBoxLayout(cards_host)
        self._features_lay.setContentsMargins(0, 4, 0, 0)
        self._features_lay.setSpacing(2)
        t.addWidget(cards_host)
        lay.addWidget(tools)

        lay.addWidget(self._divider())

        mix, m = self._section(
            "Dubbing & Separation",
            "Stem isolation and default engine preferences.",
        )
        self.lbl_stem_status = QLabel()
        self.lbl_stem_status.setObjectName("settings_section_hint")
        self.lbl_stem_status.setWordWrap(True)
        m.addWidget(self.lbl_stem_status)

        row = QHBoxLayout()
        row.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(self._field_label("Stem separation"))
        self.combo_stem_mode = QComboBox()
        self.combo_stem_mode.setFixedHeight(26)
        self.combo_stem_mode.addItem("Auto — Demucs when installed", "auto")
        self.combo_stem_mode.addItem("Force Demucs", "demucs")
        self.combo_stem_mode.addItem("FFmpeg mid-side only", "ffmpeg")
        self.combo_stem_mode.currentIndexChanged.connect(self._refresh_stem_status_label)
        left.addWidget(self.combo_stem_mode)
        row.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(self._field_label("Demucs model"))
        self.combo_demucs_model = QComboBox()
        self.combo_demucs_model.setFixedHeight(26)
        for name in DEMUCS_MODELS:
            self.combo_demucs_model.addItem(name, name)
        self.combo_demucs_model.currentIndexChanged.connect(self._refresh_stem_status_label)
        right.addWidget(self.combo_demucs_model)
        row.addLayout(right, 1)
        m.addLayout(row)

        self.chk_prefer_whisperx = QCheckBox("Prefer WhisperX for dubbing ASR")
        self.chk_prefer_voxcpm = QCheckBox("Prefer VoxCPM voices in TTS Studio")
        m.addWidget(self.chk_prefer_whisperx)
        m.addWidget(self.chk_prefer_voxcpm)
        lay.addWidget(mix)

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

        rows = list_features()
        ready = sum(1 for r in rows if r["status"] == "Ready")
        self.lbl_feature_summary.setText(
            f"{ready} of {len(rows)} ready · copy an install command if a backend is missing"
        )
        for item in rows:
            self._features_lay.addWidget(self._make_feature_card(item))

    def _make_feature_card(self, item: dict) -> QFrame:
        row = QFrame()
        row.setObjectName("settings_feature_row")
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.setFixedHeight(30)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(2, 0, 2, 0)
        lay.setSpacing(8)

        title = QLabel(item["label"])
        title.setObjectName("settings_feature_title")
        lay.addWidget(title)

        cat = QLabel(str(item.get("category", "")).upper())
        cat.setObjectName("settings_cat_pill")
        lay.addWidget(cat)

        raw_hint = item.get("hint") or ""
        short_hint = raw_hint.split(". uv sync")[0].strip()
        meta = QLabel(short_hint)
        meta.setObjectName("settings_feature_meta")
        lay.addWidget(meta, 1)

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

        cmd = f"uv sync --extra {item['extra']}" if item.get("extra") else ""
        if cmd and status != "Ready":
            copy = QPushButton("Install")
            copy.setObjectName("settings_copy_btn")
            copy.setCursor(Qt.CursorShape.PointingHandCursor)
            copy.setToolTip(cmd)
            copy.clicked.connect(lambda _=False, c=cmd: self._copy_install(c))
            lay.addWidget(copy, 0, Qt.AlignmentFlag.AlignVCenter)
        elif status == "Ready":
            ok = QLabel("Active")
            ok.setObjectName("settings_feature_meta")
            ok.setStyleSheet("color: #10b981; font-weight: 600; font-size: 10.5px;")
            lay.addWidget(ok, 0, Qt.AlignmentFlag.AlignVCenter)

        self._feature_cards.append(row)
        return row

    def _copy_install(self, cmd: str):
        QApplication.clipboard().setText(cmd)
        self.lbl_feature_summary.setText(f"Copied · {cmd}")

    def _refresh_stem_status_label(self, *_args):
        mode = self.combo_stem_mode.currentData() or "auto"
        model = self.combo_demucs_model.currentData() or "htdemucs"
        from claynext.services.features import stem_backend
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
        hdr_col = QVBoxLayout()
        hdr_col.setSpacing(1)
        hdr = QLabel("Model Registry")
        hdr.setObjectName("settings_section_title")
        hdr.setStyleSheet("font-size: 13px; font-weight: 700; color: #f1f5f9;")
        hint = QLabel("Hugging Face & local models")
        hint.setObjectName("settings_section_hint")
        hdr_col.addWidget(hdr)
        hdr_col.addWidget(hint)
        top.addLayout(hdr_col, 1)

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
        sec_dev, d = self._section("Compute & Hardware", "Execution device and worker pool threads.")

        d.addWidget(self._field_label("Preferred device"))
        self.combo_device = QComboBox()
        self.combo_device.setFixedHeight(26)
        self.combo_device.addItems([
            "CUDA (NVIDIA GPU)", "DirectML (AMD / Intel GPU)", "CPU Threadpool (Fallback)",
        ])
        d.addWidget(self.combo_device)

        d.addWidget(self._field_label("Worker threads"))
        self.spin_threads = QSpinBox()
        self.spin_threads.setFixedHeight(26)
        self.spin_threads.setRange(1, 16)
        self.spin_threads.setValue(4)
        d.addWidget(self.spin_threads)
        lay.addWidget(sec_dev)

        lay.addWidget(self._divider())

        sec_paths, p = self._section("Storage & Paths", "Model cache and default export directories.")

        p.addWidget(self._field_label("Models cache"))
        models_box = QHBoxLayout()
        models_box.setSpacing(6)
        self.txt_models_dir = QLineEdit(str(MODELS_DIR))
        self.txt_models_dir.setFixedHeight(26)
        btn_b_models = QPushButton("Browse")
        btn_b_models.setObjectName("btn_secondary")
        btn_b_models.setFixedWidth(74)
        btn_b_models.clicked.connect(lambda: self.browse_folder(self.txt_models_dir))
        models_box.addWidget(self.txt_models_dir, 1)
        models_box.addWidget(btn_b_models)
        p.addLayout(models_box)

        p.addWidget(self._field_label("Default exports"))
        outputs_box = QHBoxLayout()
        outputs_box.setSpacing(6)
        self.txt_outputs_dir = QLineEdit(str(OUTPUTS_DIR))
        self.txt_outputs_dir.setFixedHeight(26)
        btn_b_outputs = QPushButton("Browse")
        btn_b_outputs.setObjectName("btn_secondary")
        btn_b_outputs.setFixedWidth(74)
        btn_b_outputs.clicked.connect(lambda: self.browse_folder(self.txt_outputs_dir))
        outputs_box.addWidget(self.txt_outputs_dir, 1)
        outputs_box.addWidget(btn_b_outputs)
        p.addLayout(outputs_box)
        lay.addWidget(sec_paths)

        lay.addStretch(1)
        return page

    # ─── Appearance ──────────────────────────────────────────────────

    def _build_appearance_tab(self) -> QWidget:
        page, lay = self._scroll_page()
        sec_theme, t = self._section("Interface Theme", "Studio color scheme and accent palette.")

        t.addWidget(self._field_label("Theme"))
        self.combo_theme = QComboBox()
        self.combo_theme.setFixedHeight(26)
        self.combo_theme.addItems(["CamDot Dark Obsidian (Default)", "System Light Mode"])
        t.addWidget(self.combo_theme)

        t.addWidget(self._field_label("Accent"))
        self.combo_accent = QComboBox()
        self.combo_accent.setFixedHeight(26)
        self.combo_accent.addItems([
            "Indigo / Purple (#6366f1)",
            "Emerald Green (#10b981)",
            "Cyan Blue (#06b6d4)",
            "Rose Pink (#f43f5e)",
        ])
        t.addWidget(self.combo_accent)
        lay.addWidget(sec_theme)

        lay.addWidget(self._divider())

        sec_motion, m = self._section("Visual Effects", "Motion transitions and animations.")
        self.chk_anim = QCheckBox("Enable UI micro-animations")
        self.chk_anim.setChecked(True)
        m.addWidget(self.chk_anim)
        lay.addWidget(sec_motion)

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
