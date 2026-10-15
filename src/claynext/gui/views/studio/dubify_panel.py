"""
Dubify-style AI Studio Interface Components.
Streamlined, elegant, single-window layout matching Dubify AI PRO:
- Top Left: Video Preview with custom purple transport controls
- Top Right: Subtitle Data table with Add, Edit, Delete, Find, Scan Characters
- Middle: Timeline Editor with Translate, Generate Audio, Zoom, and tracks
- Bottom: Action & Status Footer (Export Video, Import/Export SRT, Load/Isolate BGM, Batch)
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from claynext.gui.components.field_controls import SelectField
from claynext.gui.icons import icon


class DubifyVideoPreviewPanel(QWidget):
    """Clean video preview container with transport bar and aspect ratio switcher."""

    fullscreen_clicked = Signal()
    aspect_changed = Signal(str)
    crop_clicked = Signal()
    loop_toggled = Signal(bool)
    fit_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dubify_preview_box")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Header Bar: [Video Preview icon] Video Preview <filename> ... tools
        header = QFrame()
        header.setObjectName("dubify_card_header")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(4, 2, 4, 4)
        h_lay.setSpacing(8)

        lbl_icon = QLabel()
        lbl_icon.setPixmap(icon("play", color="#8b5cf6", size=13).pixmap(13, 13))
        h_lay.addWidget(lbl_icon)

        self.lbl_title = QLabel("Video Preview")
        self.lbl_title.setStyleSheet("color: #818cf8; font-weight: 700; font-size: 13px;")
        h_lay.addWidget(self.lbl_title)

        self.lbl_filename = QLabel("No video loaded")
        self.lbl_filename.setStyleSheet("color: #94a3b8; font-size: 12px;")
        h_lay.addWidget(self.lbl_filename)

        h_lay.addStretch(1)

        # Mini Toolbar
        self.btn_fs = self._tool_btn("fullscreen", "Toggle Fullscreen")
        self.btn_fs.clicked.connect(self.fullscreen_clicked.emit)
        h_lay.addWidget(self.btn_fs)

        self.btn_aspect_toggle = self._tool_btn("ratio", "Aspect Ratio (9:16 / 16:9)")
        h_lay.addWidget(self.btn_aspect_toggle)

        self.btn_crop = self._tool_btn("crop", "Crop View")
        self.btn_crop.clicked.connect(self.crop_clicked.emit)
        h_lay.addWidget(self.btn_crop)

        self.btn_fit = self._tool_btn("fit", "Fit Window")
        self.btn_fit.clicked.connect(self.fit_clicked.emit)
        h_lay.addWidget(self.btn_fit)

        layout.addWidget(header)

        # Stage Host placeholder (will receive the preview stage host)
        self.stage_container = QWidget()
        self.stage_container.setObjectName("dubify_stage_container")
        self.stage_layout = QVBoxLayout(self.stage_container)
        self.stage_layout.setContentsMargins(0, 0, 0, 0)
        self.stage_layout.setSpacing(0)
        layout.addWidget(self.stage_container, 1)

        # Bottom Player Transport Controls Bar
        self.controls_box = QFrame()
        self.controls_box.setObjectName("dubify_player_controls")
        ctrl_lay = QVBoxLayout(self.controls_box)
        ctrl_lay.setContentsMargins(8, 6, 8, 4)
        ctrl_lay.setSpacing(4)

        # Time labels row
        time_row = QHBoxLayout()
        time_row.setContentsMargins(2, 0, 2, 0)
        self.lbl_pos = QLabel("00:00.00")
        self.lbl_pos.setStyleSheet("color: #e2e8f0; font-size: 12px; font-weight: 600; font-family: monospace;")
        time_row.addWidget(self.lbl_pos)
        time_row.addStretch(1)
        self.lbl_dur = QLabel("00:00.00")
        self.lbl_dur.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 500; font-family: monospace;")
        time_row.addWidget(self.lbl_dur)
        ctrl_lay.addLayout(time_row)

        # Seek Scrubber Slider
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setObjectName("dubify_seek_slider")
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.seek_slider.setStyleSheet("""
            QSlider#dubify_seek_slider::groove:horizontal {
                height: 4px;
                background: #2a2845;
                border-radius: 2px;
            }
            QSlider#dubify_seek_slider::sub-page:horizontal {
                background: #8b5cf6;
                border-radius: 2px;
            }
            QSlider#dubify_seek_slider::handle:horizontal {
                background: #c4b5fd;
                border: 2px solid #6d28d9;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider#dubify_seek_slider::handle:horizontal:hover {
                background: #ffffff;
                border-color: #8b5cf6;
            }
        """)
        ctrl_lay.addWidget(self.seek_slider)

        # Action buttons row: [Pause/Play (Purple)] [Stop] [Loop] [Volume] [9:16 Dropdown]
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 2, 0, 0)
        btn_row.setSpacing(8)

        self.btn_play = QPushButton("Play")
        self.btn_play.setObjectName("dubify_btn_play")
        self.btn_play.setIcon(icon("play", color="#ffffff", size=13))
        self.btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_play.setStyleSheet("""
            QPushButton#dubify_btn_play {
                background-color: #6d28d9;
                color: #ffffff;
                font-weight: 700;
                font-size: 12px;
                padding: 5px 14px;
                border-radius: 4px;
                border: none;
            }
            QPushButton#dubify_btn_play:hover {
                background-color: #7c3aed;
            }
            QPushButton#dubify_btn_play:pressed {
                background-color: #5b21b6;
            }
        """)
        btn_row.addWidget(self.btn_play)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setObjectName("dubify_btn_stop")
        self.btn_stop.setIcon(icon("stop", color="#e2e8f0", size=12))
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.setStyleSheet("""
            QPushButton#dubify_btn_stop {
                background-color: #24243a;
                color: #cbd5e1;
                font-size: 12px;
                font-weight: 500;
                padding: 5px 12px;
                border-radius: 4px;
                border: 1px solid #363556;
            }
            QPushButton#dubify_btn_stop:hover {
                background-color: #2f2e4c;
                border-color: #6366f1;
            }
        """)
        btn_row.addWidget(self.btn_stop)

        self.btn_loop = QToolButton()
        self.btn_loop.setObjectName("dubify_btn_loop")
        self.btn_loop.setIcon(icon("loop", color="#cbd5e1", size=13))
        self.btn_loop.setCheckable(True)
        self.btn_loop.setFixedSize(30, 28)
        self.btn_loop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_loop.setToolTip("Loop Playback")
        self.btn_loop.setStyleSheet("""
            QToolButton#dubify_btn_loop {
                background-color: #24243a;
                border: 1px solid #363556;
                border-radius: 4px;
            }
            QToolButton#dubify_btn_loop:checked {
                background-color: #5b21b6;
                border-color: #8b5cf6;
            }
        """)
        btn_row.addWidget(self.btn_loop)

        # Volume Scrubber
        self.btn_mute = QToolButton()
        self.btn_mute.setIcon(icon("volume", color="#cbd5e1", size=13))
        self.btn_mute.setFixedSize(26, 26)
        self.btn_mute.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mute.setStyleSheet("border: none; background: transparent;")
        btn_row.addWidget(self.btn_mute)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(70)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #2a2845; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #8b5cf6; border-radius: 2px; }
            QSlider::handle:horizontal { background: #e2e8f0; width: 10px; margin: -3px 0; border-radius: 5px; }
        """)
        btn_row.addWidget(self.volume_slider)

        btn_row.addStretch(1)

        # Aspect Ratio Selector
        self.combo_aspect = SelectField(size="sm", width=96)
        self.combo_aspect.addItems(["9:16", "16:9", "1:1", "4:3", "Original"])
        self.combo_aspect.setCurrentText("9:16")
        self.combo_aspect.currentTextChanged.connect(self.aspect_changed.emit)
        btn_row.addWidget(self.combo_aspect)

        ctrl_lay.addLayout(btn_row)
        layout.addWidget(self.controls_box)

    def _tool_btn(self, icon_name: str, tip: str) -> QToolButton:
        btn = QToolButton()
        btn.setIcon(icon(icon_name, color="#cbd5e1", size=13))
        btn.setFixedSize(26, 26)
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QToolButton {
                background-color: #232238;
                border: 1px solid #363556;
                border-radius: 4px;
            }
            QToolButton:hover {
                background-color: #2f2e4c;
                border-color: #8b5cf6;
            }
        """)
        return btn

    def set_media_title(self, path: str):
        import os
        name = os.path.basename(path) if path else "No video loaded"
        self.lbl_filename.setText(name)


class DubifySubtitleDataPanel(QWidget):
    """Subtitle Data table with action buttons and clear 5-column layout."""

    add_text_requested = Signal()
    edit_requested = Signal()
    delete_requested = Signal()
    find_replace_requested = Signal()
    scan_characters_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dubify_subtitle_box")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Top Bar: "Subtitle Data" + Actions Toolbar
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)

        lbl_title = QLabel("Subtitle Data")
        lbl_title.setStyleSheet("color: #c4b5fd; font-weight: 700; font-size: 13.5px;")
        top_bar.addWidget(lbl_title)
        top_bar.addSpacing(8)

        self.btn_add = self._action_btn("+ Add Text", "add")
        self.btn_add.clicked.connect(self.add_text_requested.emit)
        top_bar.addWidget(self.btn_add)

        self.btn_edit = self._action_btn("Edit", "edit")
        self.btn_edit.clicked.connect(self.edit_requested.emit)
        top_bar.addWidget(self.btn_edit)

        self.btn_delete = self._action_btn("Delete", "delete")
        self.btn_delete.clicked.connect(self.delete_requested.emit)
        top_bar.addWidget(self.btn_delete)

        self.btn_find = self._action_btn("Find & Replace", "search")
        self.btn_find.clicked.connect(self.find_replace_requested.emit)
        top_bar.addWidget(self.btn_find)

        top_bar.addStretch(1)

        # Scan Characters Button (Solid Purple with Sparkle)
        self.btn_scan = QPushButton("Scan Characters")
        self.btn_scan.setObjectName("dubify_btn_scan")
        self.btn_scan.setIcon(icon("sparkles", color="#ffffff", size=13))
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.setStyleSheet("""
            QPushButton#dubify_btn_scan {
                background-color: #6d28d9;
                color: #ffffff;
                font-weight: 700;
                font-size: 12px;
                padding: 5px 14px;
                border-radius: 4px;
                border: 1px solid #7c3aed;
            }
            QPushButton#dubify_btn_scan:hover {
                background-color: #7c3aed;
            }
            QPushButton#dubify_btn_scan:pressed {
                background-color: #5b21b6;
            }
        """)
        self.btn_scan.clicked.connect(self.scan_characters_requested.emit)
        top_bar.addWidget(self.btn_scan)

        layout.addLayout(top_bar)

        # 5-Column Table Widget
        self.table = QTableWidget()
        self.table.setObjectName("dubify_sub_table")
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "START",
            "END",
            "KHMER TEXT (EDITABLE)",
            "VOICE",
            "AUDIO STATUS",
        ])

        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 85)
        self.table.setColumnWidth(1, 85)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 120)

        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        self.table.setStyleSheet("""
            QTableWidget#dubify_sub_table {
                background-color: #121321;
                alternate-background-color: #17182a;
                border: 1px solid #282944;
                border-radius: 6px;
                color: #e2e8f0;
                gridline-color: transparent;
                selection-background-color: #5b21b6;
                selection-color: #ffffff;
            }
            QTableWidget#dubify_sub_table QHeaderView::section {
                background-color: #1a1a2e;
                color: #93c5fd;
                font-weight: 700;
                font-size: 11px;
                padding: 6px 8px;
                border: none;
                border-bottom: 2px solid #3730a3;
                letter-spacing: 0.5px;
            }
            QTableWidget#dubify_sub_table::item {
                padding: 4px 8px;
                border-bottom: 1px solid #1c1d32;
            }
            QTableWidget#dubify_sub_table::item:selected {
                background-color: #5b21b6;
                color: #ffffff;
                font-weight: 600;
            }
        """)

        layout.addWidget(self.table, 1)

        # Footer Instruction Label
        lbl_hint = QLabel(
            "Double-click START / END / KHMER TEXT to edit, click VOICE to choose Male/Female, AUDIO to play."
        )
        lbl_hint.setStyleSheet("color: #94a3b8; font-size: 11px; font-style: italic;")
        layout.addWidget(lbl_hint)

    def _action_btn(self, text: str, icon_name: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setIcon(icon(icon_name, color="#c4b5fd", size=12))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #232238;
                color: #e2e8f0;
                font-size: 11.5px;
                font-weight: 600;
                padding: 5px 11px;
                border: 1px solid #363556;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2e2d4a;
                border-color: #8b5cf6;
            }
        """)
        return btn


class DubifyTimelineContainer(QWidget):
    """Middle timeline container with language selector, translate/generate buttons, and canvas."""

    translate_requested = Signal()
    generate_audio_requested = Signal()
    language_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dubify_timeline_container")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)

        # Timeline Header Bar
        header = QFrame()
        header.setObjectName("dubify_timeline_header")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(4, 2, 4, 4)
        h_lay.setSpacing(10)

        # Left: Timeline Editor Title + Time Readout
        self.lbl_editor = QLabel("Timeline Editor")
        self.lbl_editor.setStyleSheet("color: #818cf8; font-weight: 700; font-size: 13px;")
        h_lay.addWidget(self.lbl_editor)

        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setStyleSheet("color: #cbd5e1; font-size: 12px; font-family: monospace; font-weight: 600;")
        h_lay.addWidget(self.lbl_time)

        # Target Language Combo
        self.combo_lang = SelectField(size="sm", width=120)
        self.combo_lang.addItems([
            "Khmer",
            "English",
            "Vietnamese",
            "Thai",
            "Chinese",
            "Japanese",
            "Korean",
            "Spanish",
            "French",
        ])
        self.combo_lang.setCurrentText("Khmer")
        self.combo_lang.currentTextChanged.connect(self.language_changed.emit)
        h_lay.addWidget(self.combo_lang)

        # Action Button: Translate (Purple)
        self.btn_translate = QPushButton("Translate")
        self.btn_translate.setObjectName("dubify_btn_translate")
        self.btn_translate.setIcon(icon("translate", color="#ffffff", size=13))
        self.btn_translate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_translate.setStyleSheet("""
            QPushButton#dubify_btn_translate {
                background-color: #6d28d9;
                color: #ffffff;
                font-weight: 700;
                font-size: 12px;
                padding: 5px 14px;
                border-radius: 4px;
                border: 1px solid #7c3aed;
            }
            QPushButton#dubify_btn_translate:hover {
                background-color: #7c3aed;
            }
        """)
        self.btn_translate.clicked.connect(self.translate_requested.emit)
        h_lay.addWidget(self.btn_translate)

        # Action Button: Generate Audio (Purple)
        self.btn_generate = QPushButton("Generate Audio")
        self.btn_generate.setObjectName("dubify_btn_generate")
        self.btn_generate.setIcon(icon("volume", color="#ffffff", size=13))
        self.btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_generate.setStyleSheet("""
            QPushButton#dubify_btn_generate {
                background-color: #6d28d9;
                color: #ffffff;
                font-weight: 700;
                font-size: 12px;
                padding: 5px 14px;
                border-radius: 4px;
                border: 1px solid #7c3aed;
            }
            QPushButton#dubify_btn_generate:hover {
                background-color: #7c3aed;
            }
        """)
        self.btn_generate.clicked.connect(self.generate_audio_requested.emit)
        h_lay.addWidget(self.btn_generate)

        h_lay.addStretch(1)

        # Zoom Controls
        lbl_zoom = QLabel("Zoom")
        lbl_zoom.setStyleSheet("color: #94a3b8; font-size: 11px;")
        h_lay.addWidget(lbl_zoom)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 200)
        self.zoom_slider.setValue(36)
        self.zoom_slider.setFixedWidth(80)
        self.zoom_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #2a2845; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #8b5cf6; border-radius: 2px; }
            QSlider::handle:horizontal { background: #e2e8f0; width: 10px; margin: -3px 0; border-radius: 5px; }
        """)
        h_lay.addWidget(self.zoom_slider)

        self.btn_fit = QPushButton("Fit")
        self.btn_fit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fit.setStyleSheet("""
            QPushButton {
                background-color: #232238;
                color: #cbd5e1;
                font-size: 11px;
                padding: 3px 8px;
                border-radius: 3px;
                border: 1px solid #363556;
            }
            QPushButton:hover {
                background-color: #2e2d4a;
                border-color: #8b5cf6;
            }
        """)
        h_lay.addWidget(self.btn_fit)

        layout.addWidget(header)

        # Host area for timeline widget
        self.timeline_host = QWidget()
        self.timeline_layout = QVBoxLayout(self.timeline_host)
        self.timeline_layout.setContentsMargins(0, 0, 0, 0)
        self.timeline_layout.setSpacing(0)
        layout.addWidget(self.timeline_host, 1)


class DubifyActionFooter(QWidget):
    """Bottom status and action bar."""

    add_to_batch_requested = Signal()
    batch_processing_requested = Signal()
    load_bgm_requested = Signal()
    isolate_bgm_requested = Signal()
    import_srt_requested = Signal()
    export_srt_requested = Signal()
    export_video_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dubify_footer_bar")
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        # Status & Progress on Left
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setFixedWidth(80)
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #232238;
                border-radius: 6px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #a855f7);
                border-radius: 6px;
            }
        """)
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("100% Done. Review the text, set voices, then Generate Audio.")
        self.lbl_status.setStyleSheet("color: #94a3b8; font-size: 11.5px; font-weight: 500;")
        layout.addWidget(self.lbl_status)

        layout.addStretch(1)

        # Action Buttons on Right
        self.btn_add_batch = self._footer_btn("+ Add to Batch", self.add_to_batch_requested)
        layout.addWidget(self.btn_add_batch)

        self.btn_batch = self._footer_btn("Batch Processing", self.batch_processing_requested)
        layout.addWidget(self.btn_batch)

        self.btn_load_bgm = self._footer_btn("Load BGM", self.load_bgm_requested)
        layout.addWidget(self.btn_load_bgm)

        self.btn_isolate_bgm = self._footer_btn("Isolate BGM", self.isolate_bgm_requested)
        layout.addWidget(self.btn_isolate_bgm)

        self.btn_import_srt = self._footer_btn("Import SRT", self.import_srt_requested)
        layout.addWidget(self.btn_import_srt)

        self.btn_export_srt = self._footer_btn("Export SRT", self.export_srt_requested)
        layout.addWidget(self.btn_export_srt)

        # Primary Action: Export Video (Solid Purple Accent)
        self.btn_export_video = QPushButton("Export Video")
        self.btn_export_video.setObjectName("dubify_btn_export_video")
        self.btn_export_video.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_video.setStyleSheet("""
            QPushButton#dubify_btn_export_video {
                background-color: #6d28d9;
                color: #ffffff;
                font-weight: 700;
                font-size: 12.5px;
                padding: 6px 18px;
                border-radius: 4px;
                border: 1px solid #7c3aed;
            }
            QPushButton#dubify_btn_export_video:hover {
                background-color: #7c3aed;
            }
            QPushButton#dubify_btn_export_video:pressed {
                background-color: #5b21b6;
            }
        """)
        self.btn_export_video.clicked.connect(self.export_video_requested.emit)
        layout.addWidget(self.btn_export_video)

    def _footer_btn(self, text: str, signal: Signal) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #202033;
                color: #cbd5e1;
                font-size: 11.5px;
                font-weight: 600;
                padding: 5px 12px;
                border: 1px solid #33334d;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2b2b45;
                border-color: #8b5cf6;
                color: #ffffff;
            }
        """)
        btn.clicked.connect(signal.emit)
        return btn
