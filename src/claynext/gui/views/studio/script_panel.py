"""Script shelf, dialogue table, filters, and empty states."""
from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QFrame, QHeaderView, QAbstractItemView, QMenu,
    QStackedWidget, QSizePolicy, QToolButton,
)

from claynext.gui.icons import icon
from claynext.gui.components.controls.fields import SearchField, SelectField
from claynext.gui.components.shell.shelf_header import make_shelf_button, make_shelf_header
from claynext.gui.components.controls.spinner import Spinner
from claynext.gui.components.controls.table_fit import fit_or_scroll
from claynext.utils.job_control import JobControl


_SCRIPT_VIEW_FILTERS = (
    ("all", "All lines"),
    ("pending", "Pending edits"),
    ("dubbed", "Has dub text"),
    ("source", "Source only"),
)


def _format_script_error(hint: str) -> str:
    """Turn raw engine errors into short, actionable empty-state copy."""
    text = str(hint or "").strip()
    low = text.lower()
    if "voxcpm is not installed" in low or "extra voxcpm" in low:
        return (
            "VoxCPM optional pack is missing.\n"
            "Run: uv sync --extra voxcpm\n"
            "Or pick Edge / Kitten voices in Settings and retry."
        )
    if "choose an edge" in low or "no voice" in low:
        return "Pick a TTS voice in the Voices shelf, then retry dub."
    return text


class _ScriptLoadBridge:
    """Compatibility shim — table_spinner.start/stop drive the centered loader.

    The loader covers the script panel only while there is no transcript list yet.
    Translate, TTS, and other later steps leave the table in place.
    """

    def __init__(self, host):
        self._host = host

    def start(self):
        self._host._set_script_loading(True, "Transcribing…", "Reading dialogue from the movie")

    def stop(self):
        self._host._set_script_loading(False)

    def is_spinning(self) -> bool:
        return bool(getattr(self._host, "_script_loading", False))


class ScriptPanelTools:
    """Script shelf, dialogue table, filters, and empty states."""

    def _focus_script_shelf(self):
        """Open the shelf Script tab (script lives in the icon shelf, not a dock)."""
        if hasattr(self, "workspace"):
            self.workspace.set_visible("shelf", True)
        if hasattr(self, "shelf"):
            self.shelf.show_key("script")

    def _on_timeline_transcript_action(self, action: str):
        """Handle Audio Transcripts extras from the timeline source context menu."""
        key = str(action or "").strip().lower()
        if key == "show":
            self._focus_script_shelf()
            return
        if key == "import":
            self._focus_script_shelf()
            self._import_script()
            return
        if key == "export":
            self._focus_script_shelf()
            self.open_export_dialog(script_only=True)
            return
        if key == "retry":
            self._focus_script_shelf()
            self._retry_script_transcript()
            return
        if key == "translate":
            self._focus_script_shelf()
            rows = list(range(len(getattr(self, "_segments", []) or [])))
            if not rows:
                self.log.warn("Retry translate · no script lines yet")
                return
            self._regenerate_rows(rows)
            return
        if key == "tts":
            self._focus_script_shelf()
            rows = list(range(len(getattr(self, "_segments", []) or [])))
            if not rows:
                self.log.warn("Retry TTS · no script lines yet")
                return
            self._resynthesize_rows(rows)
            return
        if key == "all":
            self._focus_script_shelf()
            self._retry_script_all()
            return

    def _build_script_header(self) -> QWidget:
        """Shelf title strip: count, import/export, regenerate, more."""
        self.lbl_script_count = QLabel("")
        self.lbl_script_count.setObjectName("transcript_count")
        self.lbl_script_count.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        )

        self.btn_script_import = make_shelf_button(
            "Import", tip="Load script · SRT, VTT, or JSON", icon_name="folder", menu=True,
        )
        import_menu = QMenu(self.btn_script_import)
        import_menu.setObjectName("media_lib_menu")
        import_menu.addAction(icon("folder", size=14), "Import script…").triggered.connect(
            lambda: self._import_script()
        )
        import_menu.addSeparator()
        import_menu.addAction("SRT…").triggered.connect(lambda: self._import_script("srt"))
        import_menu.addAction("VTT…").triggered.connect(lambda: self._import_script("vtt"))
        import_menu.addAction("JSON…").triggered.connect(lambda: self._import_script("json"))
        self.btn_script_import.setMenu(import_menu)

        self.btn_script_export = make_shelf_button(
            "Export", tip="Export script · SRT, VTT, or JSON", icon_name="download", menu=True,
        )
        self.btn_script_export.setEnabled(False)
        export_menu = QMenu(self.btn_script_export)
        export_menu.setObjectName("media_lib_menu")
        export_menu.addAction(icon("download", size=14), "Export script…").triggered.connect(
            lambda: self.open_export_dialog(script_only=True)
        )
        export_menu.addSeparator()
        export_menu.addAction("SRT…").triggered.connect(
            lambda: self._export_subtitles("srt", "current")
        )
        export_menu.addAction("VTT…").triggered.connect(
            lambda: self._export_subtitles("vtt", "current")
        )
        export_menu.addAction("JSON…").triggered.connect(
            lambda: self._export_subtitles("json", "current")
        )
        export_menu.addSeparator()
        export_menu.addAction("Previous version (SRT)…").triggered.connect(
            lambda: self._export_subtitles("srt", "back")
        )
        export_menu.addAction("Previous version (VTT)…").triggered.connect(
            lambda: self._export_subtitles("vtt", "back")
        )
        self.btn_script_export.setMenu(export_menu)

        self.btn_script_regen = make_shelf_button(
            tip="Regenerate · transcript, translate, TTS", icon_name="sparkles", menu=True,
        )
        self.btn_script_regen.setEnabled(False)
        regen_menu = QMenu(self.btn_script_regen)
        regen_menu.setObjectName("media_lib_menu")
        regen_menu.setToolTipsVisible(True)
        self._script_regen_menu = regen_menu
        self.btn_script_regen.setMenu(regen_menu)
        regen_menu.aboutToShow.connect(self._fill_script_regen_menu)

        self.btn_script_actions = make_shelf_button(
            tip="More script actions", icon_name="more", menu=True,
        )
        self.btn_script_actions.setEnabled(False)
        actions_menu = QMenu(self.btn_script_actions)
        actions_menu.setObjectName("media_lib_menu")
        actions_menu.setToolTipsVisible(True)
        self._script_actions_menu = actions_menu
        self.btn_script_actions.setMenu(actions_menu)
        actions_menu.aboutToShow.connect(self._fill_script_actions_menu)

        self.script_header = make_shelf_header(
            "Script",
            self.lbl_script_count,
            self.btn_script_import,
            self.btn_script_export,
            self.btn_script_regen,
            self.btn_script_actions,
        )
        return self.script_header

    def _build_script_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("transcript_panel")
        self.script_panel = panel
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_script_header())

        tools = QFrame()
        tools.setObjectName("transcript_tools")
        self.script_tools = tools
        filter_row = QHBoxLayout(tools)
        filter_row.setContentsMargins(10, 6, 10, 6)
        filter_row.setSpacing(6)

        self.script_search = SearchField("Find in script…", size="sm")
        self.script_search.setMinimumWidth(96)
        self.script_search.setMaximumWidth(16777215)
        self.script_search.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.script_search.textChanged.connect(lambda _: self._apply_script_filters())
        filter_row.addWidget(self.script_search, 1, Qt.AlignmentFlag.AlignVCenter)

        self.script_character_filter = SelectField(size="sm", width=120)
        self.script_character_filter.setObjectName("script_character_filter")
        self.script_character_filter.setToolTip("Filter by character")
        self.script_character_filter.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self.script_character_filter.addItem("All characters", "all")
        self.script_character_filter.currentIndexChanged.connect(
            lambda _: self._apply_script_filters()
        )
        filter_row.addWidget(self.script_character_filter, 0, Qt.AlignmentFlag.AlignVCenter)

        self.script_view_filter = SelectField(size="sm", width=112)
        self.script_view_filter.setObjectName("script_view_filter")
        self.script_view_filter.setToolTip("Filter by line status")
        self.script_view_filter.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        for key, label in _SCRIPT_VIEW_FILTERS:
            self.script_view_filter.addItem(label, key)
        self.script_view_filter.currentIndexChanged.connect(
            lambda _: self._apply_script_filters()
        )
        filter_row.addWidget(self.script_view_filter, 0, Qt.AlignmentFlag.AlignVCenter)

        self.btn_script_pending = make_shelf_button(
            tip="Jump to next pending edit", icon_name="chevron-right",
        )
        self.btn_script_pending.setEnabled(False)
        self.btn_script_pending.clicked.connect(lambda: self._jump_pending(1))
        filter_row.addWidget(self.btn_script_pending, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(tools)

        self.script_stack = QStackedWidget()
        empty = QWidget()
        empty.setObjectName("transcript_empty")
        empty_lay = QVBoxLayout(empty)
        empty_lay.setContentsMargins(16, 12, 16, 16)
        empty_lay.setSpacing(6)
        empty_lay.addStretch(1)
        self.empty_title = QLabel("No dubbed script")
        self.empty_title.setObjectName("transcript_empty_title")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_lay.addWidget(self.empty_title)
        self.empty_hint = QLabel("Dub a movie from Tasks, or")
        self.empty_hint.setObjectName("transcript_empty_hint")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.empty_hint.setWordWrap(True)
        empty_lay.addWidget(self.empty_hint, 0, Qt.AlignmentFlag.AlignHCenter)

        empty_actions = QHBoxLayout()
        empty_actions.setContentsMargins(0, 6, 0, 0)
        empty_actions.setSpacing(6)
        empty_actions.addStretch(1)
        self.btn_empty_import = QPushButton("Import script")
        self.btn_empty_import.setObjectName("transcript_empty_btn")
        self.btn_empty_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_empty_import.setFixedHeight(24)
        self.btn_empty_import.setIcon(icon("folder", color="#e7ecf3", size=13))
        self.btn_empty_import.setIconSize(QSize(13, 13))
        self.btn_empty_import.clicked.connect(lambda: self._import_script())
        empty_actions.addWidget(self.btn_empty_import)
        self.btn_empty_retry = QPushButton("Retry dub")
        self.btn_empty_retry.setObjectName("transcript_empty_btn_primary")
        self.btn_empty_retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_empty_retry.setFixedHeight(24)
        self.btn_empty_retry.setIcon(icon("refresh", color="#e7ecf3", size=13))
        self.btn_empty_retry.setIconSize(QSize(13, 13))
        self.btn_empty_retry.setVisible(False)
        self.btn_empty_retry.clicked.connect(self._retry_script_all)
        empty_actions.addWidget(self.btn_empty_retry)
        empty_actions.addStretch(1)
        empty_lay.addLayout(empty_actions)
        empty_lay.addStretch(2)
        self.script_empty_page = empty
        self.script_stack.addWidget(empty)

        # Centered loading page (large spinner — replaces header spinner)
        loading = QWidget()
        loading.setObjectName("transcript_loading")
        load_lay = QVBoxLayout(loading)
        load_lay.setContentsMargins(24, 24, 24, 24)
        load_lay.setSpacing(12)
        load_lay.addStretch(1)
        self.script_load_spinner = Spinner(size=44, color="#a855f7")
        load_lay.addWidget(self.script_load_spinner, 0, Qt.AlignmentFlag.AlignHCenter)
        self.load_title = QLabel("Dubbing…")
        self.load_title.setObjectName("transcript_empty_title")
        self.load_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        load_lay.addWidget(self.load_title)
        self.load_hint = QLabel("Please wait")
        self.load_hint.setObjectName("transcript_empty_hint")
        self.load_hint.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.load_hint.setWordWrap(True)
        load_lay.addWidget(self.load_hint, 0, Qt.AlignmentFlag.AlignHCenter)
        load_lay.addStretch(2)
        self.script_loading_page = loading
        self.script_stack.addWidget(loading)
        self._script_loading = False
        # Bridge so existing table_spinner.start/stop calls drive the center loader
        self.table_spinner = _ScriptLoadBridge(self)

        self._script_compact = None
        panel.installEventFilter(self)

        self.table = QTableWidget()
        self.table.setObjectName("transcript_table")
        # Timing + character + gender + source/dub lines.
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["#", "Time", "Character", "Gender", "Source", "Dub"])
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(36)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(1, 118)
        self.table.setColumnWidth(2, 112)
        self.table.setColumnWidth(3, 72)
        fit_or_scroll(self.table, (4, 5))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.verticalHeader().setMinimumSectionSize(36)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._script_menu)
        self.table.cellDoubleClicked.connect(self._play_row)
        self._script_worker = None
        self._script_control: JobControl | None = None
        self._regen_rows: list[int] = []
        self.script_stack.addWidget(self.table)
        layout.addWidget(self.script_stack, 1)

        QShortcut(QKeySequence("Return"), self.table).activated.connect(
            lambda: self._play_row(self.table.currentRow(), 0)
        )
        QShortcut(QKeySequence("Escape"), panel).activated.connect(self._cancel_script_job)
        QShortcut(QKeySequence("Ctrl+F"), panel).activated.connect(self._focus_script_search)
        QShortcut(QKeySequence("Ctrl+C"), self.table).activated.connect(
            lambda: self._copy_script_lines("dub")
        )
        QShortcut(QKeySequence("Ctrl+Shift+C"), self.table).activated.connect(
            lambda: self._copy_script_lines("times")
        )
        self._update_script_meta()
        self._sync_script_panel_layout(panel.width() or 420)
        return panel

    def eventFilter(self, obj, event):
        if obj is getattr(self, "script_panel", None) and event.type() == QEvent.Type.Resize:
            self._sync_script_panel_layout(event.size().width())
        return super().eventFilter(obj, event)

    def _sync_script_panel_layout(self, width: int):
        """Compact header / filters / columns when the script shelf is narrow."""
        w = max(0, int(width or 0))
        compact = w < 420
        tight = w < 340
        if self._script_compact == (compact, tight, w // 40):
            return
        self._script_compact = (compact, tight, w // 40)

        for btn, label in (
            (getattr(self, "btn_script_import", None), "Import"),
            (getattr(self, "btn_script_export", None), "Export"),
        ):
            if isinstance(btn, QToolButton):
                if compact:
                    btn.setText("")
                    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                    btn.setProperty("icon_only", "true")
                    btn.setFixedSize(24, 24)
                else:
                    btn.setText(label)
                    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                    btn.setProperty("icon_only", "false")
                    btn.setFixedHeight(24)
                    btn.setMinimumWidth(0)
                    btn.setMaximumWidth(16777215)
                    btn.setMinimumWidth(max(56, btn.sizeHint().width()))
                btn.style().unpolish(btn)
                btn.style().polish(btn)

        if hasattr(self, "script_search"):
            self.script_search.setMinimumWidth(72 if tight else 96)
            self.script_search.setMaximumWidth(16777215)

        if hasattr(self, "script_character_filter"):
            cw = 96 if tight else (108 if compact else 120)
            self.script_character_filter.setFixedWidth(cw)
            self.script_character_filter.setVisible(not tight or w >= 280)

        if hasattr(self, "script_view_filter"):
            vw = 88 if tight else (100 if compact else 112)
            self.script_view_filter.setFixedWidth(vw)

        if hasattr(self, "empty_hint"):
            self.empty_hint.setMaximumWidth(max(160, w - 32))

        self._fit_script_columns()

    def _script_row_key(self, seg: dict, index: int) -> tuple:
        return (
            str(seg.get("id", index + 1)),
            str(seg.get("start", "")),
            str(seg.get("end", "")),
            str(seg.get("speaker") or ""),
            str(seg.get("gender") or ""),
            bool(seg.get("pending")),
            bool(seg.get("gender_manual")),
            str(seg.get("tts_voice_hint") or seg.get("voice_id") or ""),
            str(seg.get("original_text") or seg.get("text") or ""),
            str(seg.get("translated_text") or ""),
            str(seg.get("audio_path") or ""),
        )

    def _apply_script_row(self, row: int, seg: dict, index: int) -> None:
        id_item = QTableWidgetItem(str(seg.get("id", index + 1)))
        id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 0, id_item)

        start = str(seg.get("start", ""))
        end = str(seg.get("end", ""))
        start_fmt = start[3:8] if len(start) >= 8 else start
        end_fmt = end[3:8] if len(end) >= 8 else end
        time_str = f"{start_fmt}-{end_fmt}" if end_fmt else start_fmt
        time_item = QTableWidgetItem(time_str)
        time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        time_item.setForeground(QBrush(QColor("#64748b")))
        time_item.setToolTip(f"{start} --> {end}")
        self.table.setItem(row, 1, time_item)

        speaker = str(seg.get("speaker") or f"Character {index % 2 + 1}")
        mark = " ●" if seg.get("pending") else ""
        char_item = QTableWidgetItem(f"● {speaker}{mark}")
        char_item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        voice = str(seg.get("tts_voice_hint") or seg.get("voice_id") or "")
        char_item.setToolTip(f"{speaker}" + (f"\nVoice: {voice}" if voice else ""))
        gender = str(seg.get("gender") or "Unknown")
        if gender == "Female":
            char_color = QColor("#f472b6")
        elif gender == "Male":
            char_color = QColor("#38bdf8")
        else:
            hue = (sum(ord(c) for c in speaker) * 47) % 360
            char_color = QColor.fromHsv(hue, 120, 220)
        char_item.setForeground(QBrush(char_color))
        self.table.setItem(row, 2, char_item)

        gender_item = QTableWidgetItem(gender)
        gender_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if gender == "Female":
            gender_item.setForeground(QBrush(QColor("#f472b6")))
        elif gender == "Male":
            gender_item.setForeground(QBrush(QColor("#38bdf8")))
        else:
            gender_item.setForeground(QBrush(QColor("#64748b")))
        tip = "Manual gender" if seg.get("gender_manual") else "Auto-detected gender"
        if voice:
            tip += f"\nTTS: {voice}"
        gender_item.setToolTip(tip)
        self.table.setItem(row, 3, gender_item)

        orig = str(seg.get("original_text") or seg.get("text") or "")
        src_item = QTableWidgetItem(orig)
        src_item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        src_item.setForeground(QBrush(QColor("#94a3b8")))
        src_item.setToolTip(f"Original speech:\n{orig}")
        self.table.setItem(row, 4, src_item)

        dub = str(seg.get("translated_text") or "")
        dub_item = QTableWidgetItem(dub)
        dub_item.setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        dub_item.setForeground(QBrush(QColor("#f8fafc")))
        font = dub_item.font()
        font.setBold(True)
        dub_item.setFont(font)
        if seg.get("pending"):
            dub_item.setBackground(QBrush(QColor(168, 85, 247, 48)))
            dub_item.setToolTip("Pending version. Accept to keep it, or Reverse to restore the previous line.")
        else:
            dub_item.setToolTip(f"Dubbed translation:\n{dub}")
        self.table.setItem(row, 5, dub_item)

    def _patch_script_rows(self, segments: list) -> bool:
        """Update changed script lines. A full rebuild is required when the count changes."""
        segs = [seg for seg in (segments or []) if isinstance(seg, dict)]
        if len(segs) != len(self._segments) or len(segs) != self.table.rowCount():
            return False
        changed: list[int] = []
        speakers_changed = False
        filters_changed = False
        for index, seg in enumerate(segs):
            old = self._segments[index]
            if self._script_row_key(old, index) == self._script_row_key(seg, index):
                continue
            changed.append(index)
            if str(old.get("speaker") or "") != str(seg.get("speaker") or ""):
                speakers_changed = True
            if (
                bool(old.get("pending")) != bool(seg.get("pending"))
                or bool(str(old.get("translated_text") or "").strip()) != bool(str(seg.get("translated_text") or "").strip())
                or bool(str(old.get("original_text") or old.get("text") or "").strip())
                != bool(str(seg.get("original_text") or seg.get("text") or "").strip())
            ):
                filters_changed = True
        if not changed:
            self._segments = segs
            return True
        self._filling_table = True
        self.table.setUpdatesEnabled(False)
        try:
            for index in changed:
                self._apply_script_row(index, segs[index], index)
                self.table.resizeRowToContents(index)
            playing = int(getattr(self, "_playing_row", -1))
            if playing in changed and 0 <= playing < self.table.rowCount():
                brush = QBrush(QColor(99, 102, 241, 38))
                for col in range(self.table.columnCount()):
                    item = self.table.item(playing, col)
                    if item is not None:
                        item.setBackground(brush)
        finally:
            self.table.setUpdatesEnabled(True)
            self._filling_table = False
        self._segments = segs
        if speakers_changed:
            self._refresh_character_filter()
        if speakers_changed or filters_changed:
            self._apply_script_filters()
        else:
            self._update_script_meta()
        return True

    def _fill_table(self, segments: list):
        self._filling_table = True
        self._playing_row = -1
        self._segments = list(segments or [])
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(0)
            for index, seg in enumerate(self._segments):
                self.table.insertRow(index)
                if isinstance(seg, dict):
                    self._apply_script_row(index, seg, index)
        finally:
            self.table.setUpdatesEnabled(True)
        self._filling_table = False
        if getattr(self, "_sequence_switching", False):
            QTimer.singleShot(0, self._fit_script_rows)
        else:
            self._fit_script_rows()
        self._refresh_character_filter()
        self._apply_script_filters()
        if hasattr(self, "timeline"):
            self.timeline.set_dialogue(self._segments)

    def _fit_script_rows(self):
        if not hasattr(self, "table"):
            return
        self._fit_script_columns()
        self.table.resizeRowsToContents()

    def _update_script_meta(self):
        n = len(self._segments)
        visible = 0
        if hasattr(self, "table"):
            visible = sum(
                1 for r in range(self.table.rowCount()) if not self.table.isRowHidden(r)
            )
        pending_n = sum(1 for seg in self._segments if seg.get("pending"))
        if hasattr(self, "lbl_script_count"):
            if not n:
                self.lbl_script_count.setText("")
            elif pending_n and visible == n:
                self.lbl_script_count.setText(
                    f"{n} line{'s' if n != 1 else ''} · {pending_n} pending"
                )
            elif visible < n:
                self.lbl_script_count.setText(f"{visible} of {n}")
            else:
                self.lbl_script_count.setText(f"{n} line{'s' if n != 1 else ''}")
        if self._script_loading and n:
            # Transcript lines are in — drop the overlay and keep the table.
            self._script_loading = False
            spinner = getattr(self, "script_load_spinner", None)
            if spinner is not None:
                spinner.stop()
        if self._script_loading:
            self.script_stack.setCurrentWidget(self.script_loading_page)
            self._set_script_actions_enabled(False)
            return
        dub_busy = bool(getattr(self, "_dub_busy", False))
        if dub_busy:
            self._set_script_actions_enabled(False)
            if hasattr(self, "script_search"):
                self.script_search.setEnabled(n > 0)
                self.script_character_filter.setEnabled(n > 0)
                if hasattr(self, "script_view_filter"):
                    self.script_view_filter.setEnabled(n > 0)
            if n > 0:
                self.script_stack.setCurrentWidget(self.table)
            else:
                self.script_stack.setCurrentWidget(self.script_empty_page)
            return
        if hasattr(self, "btn_script_import"):
            self.btn_script_import.setEnabled(True)
        if hasattr(self, "btn_empty_import"):
            self.btn_empty_import.setEnabled(True)
        if hasattr(self, "btn_script_export"):
            self.btn_script_export.setEnabled(n > 0)
        has_source = bool(
            str(getattr(self, "selected_file", "") or "")
            and os.path.isfile(str(self.selected_file))
        )
        can_retry = has_source or self._current_script_task_id() >= 0
        if hasattr(self, "script_search"):
            self.script_search.setEnabled(n > 0)
            self.script_character_filter.setEnabled(n > 0)
            if hasattr(self, "script_view_filter"):
                self.script_view_filter.setEnabled(n > 0)
        has_pending = pending_n > 0
        if hasattr(self, "btn_script_pending"):
            self.btn_script_pending.setEnabled(has_pending)
            self.btn_script_pending.setToolTip(
                f"Next pending edit ({pending_n})" if has_pending else "No pending edits"
            )
        if hasattr(self, "btn_script_actions"):
            self.btn_script_actions.setEnabled(n > 0 or can_retry)
        if hasattr(self, "btn_script_regen"):
            self.btn_script_regen.setEnabled(n > 0 or can_retry)
        err = bool(getattr(self, "_error", ""))
        if hasattr(self, "btn_empty_retry"):
            self.btn_empty_retry.setVisible(err and can_retry)
            self.btn_empty_retry.setEnabled(err and can_retry)
        if n > 0:
            self.script_stack.setCurrentWidget(self.table)
        else:
            self.script_stack.setCurrentWidget(self.script_empty_page)
            if not err:
                self.empty_title.setText("No dubbed script")
                self.empty_hint.setText("Dub a movie from Tasks, or")
                if hasattr(self, "btn_empty_retry"):
                    self.btn_empty_retry.setVisible(False)

    def _set_script_loading(self, on: bool, title: str = "Transcribing…", hint: str = ""):
        """Cover the script panel only while transcription has not produced lines yet."""
        if on and getattr(self, "_segments", None):
            return
        self._script_loading = bool(on)
        if on:
            if hasattr(self, "load_title"):
                self.load_title.setText(title or "Transcribing…")
            if hasattr(self, "load_hint"):
                self.load_hint.setText(hint or "Please wait")
            if hasattr(self, "script_load_spinner"):
                self.script_load_spinner.start()
            if hasattr(self, "script_loading_page"):
                self.script_stack.setCurrentWidget(self.script_loading_page)
            self._set_script_actions_enabled(False)
            if hasattr(self, "workspace"):
                self._focus_script_shelf()
            return
        if hasattr(self, "script_load_spinner"):
            self.script_load_spinner.stop()
        self._update_script_meta()

    def _set_script_loading_hint(self, hint: str):
        if hasattr(self, "load_hint") and self._script_loading:
            self.load_hint.setText(str(hint or "Please wait"))

    def _set_script_actions_enabled(self, enabled: bool):
        for name in (
            "btn_script_import",
            "btn_script_export",
            "btn_script_regen",
            "btn_script_actions",
            "btn_script_pending",
            "btn_empty_import",
            "btn_empty_retry",
            "script_search",
            "script_character_filter",
            "script_view_filter",
        ):
            w = getattr(self, name, None)
            if w is not None:
                w.setEnabled(bool(enabled))

    def _fit_script_columns(self):
        """Keep meta columns compact; Source / Dub share the remaining width."""
        if not hasattr(self, "table"):
            return
        panel_w = 0
        if hasattr(self, "script_panel") and self.script_panel is not None:
            panel_w = self.script_panel.width()
        narrow = panel_w > 0 and panel_w < 420
        tight = panel_w > 0 and panel_w < 340

        self.table.setColumnHidden(3, tight)  # Gender
        self.table.setColumnWidth(0, 32 if tight else 36)
        self.table.setColumnWidth(1, 88 if tight else (104 if narrow else 118))
        if not tight:
            self.table.setColumnWidth(3, 64 if narrow else 72)
        # Character: fit longest visible name, then clamp so Source/Dub stay readable.
        header = self.table.horizontalHeader()
        mode = header.sectionResizeMode(2)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        width = self.table.columnWidth(2)
        header.setSectionResizeMode(2, mode)
        lo, hi = (72, 110) if tight else ((84, 128) if narrow else (96, 148))
        self.table.setColumnWidth(2, max(lo, min(hi, width + 8)))

    def _refresh_character_filter(self):
        if not hasattr(self, "script_character_filter"):
            return
        current = self.script_character_filter.currentData()
        self.script_character_filter.blockSignals(True)
        self.script_character_filter.clear()
        self.script_character_filter.addItem("All characters", "all")
        for name in self._character_names():
            self.script_character_filter.addItem(name, name)
        idx = self.script_character_filter.findData(current)
        self.script_character_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.script_character_filter.blockSignals(False)

    def _apply_script_filters(self, *_args):
        if not hasattr(self, "table"):
            return
        q = (self.script_search.text() or "").strip().lower() if hasattr(self, "script_search") else ""
        character = (
            self.script_character_filter.currentData()
            if hasattr(self, "script_character_filter")
            else "all"
        ) or "all"
        view = (
            self.script_view_filter.currentData()
            if hasattr(self, "script_view_filter")
            else "all"
        ) or "all"
        for row, seg in enumerate(self._segments):
            if row >= self.table.rowCount():
                break
            hide = False
            name = str(seg.get("speaker") or "").strip()
            dub = str(seg.get("translated_text") or "").strip()
            if character not in (None, "all") and name != character:
                hide = True
            if not hide and view == "pending" and not seg.get("pending"):
                hide = True
            elif not hide and view == "dubbed" and not dub:
                hide = True
            elif not hide and view == "source" and dub:
                hide = True
            if q and not hide:
                blob = " ".join([
                    name,
                    str(seg.get("original_text") or seg.get("text") or ""),
                    dub,
                    str(seg.get("start") or ""),
                    str(seg.get("gender") or ""),
                ]).lower()
                if q not in blob:
                    hide = True
            self.table.setRowHidden(row, hide)
        self._update_script_meta()

    def _focus_script_search(self):
        if not hasattr(self, "script_search"):
            return
        self.script_search.setFocus()
        self.script_search.selectAll()

    def _set_error_style(self, error: bool):
        flag = "true" if error else "false"
        for w in (self.empty_title, self.empty_hint):
            w.setProperty("error", flag)
            w.style().unpolish(w)
            w.style().polish(w)

    def _show_error(self, title: str, hint: str):
        self._error = hint
        self._script_loading = False
        if hasattr(self, "script_load_spinner"):
            self.script_load_spinner.stop()
        self._fill_table([])
        self.empty_title.setText(title or "Dubbing failed")
        self.empty_hint.setText(_format_script_error(hint))
        self._set_error_style(True)
        self.script_stack.setCurrentWidget(self.script_empty_page)
        self._update_script_meta()
        self._focus_script_shelf()

    def _clear_error(self):
        self._error = ""
        self._set_error_style(False)
        self.empty_title.setText("No dubbed script")
        self.empty_hint.setText("Dub a movie from Tasks, or")
        if hasattr(self, "btn_empty_retry"):
            self.btn_empty_retry.setVisible(False)

