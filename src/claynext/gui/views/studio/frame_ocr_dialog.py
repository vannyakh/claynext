"""
Frame OCR Subtitle Scanner Dialog:
Interactive subtitle capture zone tracking, live crop preview, and frame-by-frame script extraction.
"""
from __future__ import annotations

import io
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QProgressBar, QPushButton, QSlider, QSpinBox, QSplitter,
    QToolButton, QVBoxLayout, QWidget,
)

from claynext.constants.theme_constants import (
    COLOR_ACCENT_CYAN, COLOR_BG_CARD, COLOR_BG_CARD_HOVER, COLOR_BG_DARK,
    COLOR_BORDER, COLOR_PRIMARY, COLOR_TEXT_MAIN, COLOR_TEXT_MUTED,
)
from claynext.gui.icons import icon
from claynext.models.ocr_service import OCREngine, sec_to_timestamp, timestamp_to_sec
from claynext.gui.worker import Worker


class FrameOcrDialog(QDialog):
    """Interactive subtitle capture zone tracker and frame-by-frame OCR dialog."""

    subtitles_extracted = Signal(list)

    def __init__(self, studio_view, parent=None):
        super().__init__(parent or studio_view)
        self.studio = studio_view
        self.setWindowTitle("Subtitle Frame OCR & Auto Zone Capture")
        self.setMinimumSize(680, 520)
        self.resize(760, 560)
        self.setModal(False)  # Allow user to scrub video preview while dialog is open

        self._video_path = str(getattr(self.studio, "selected_file", "") or "")
        self._worker = None
        self._current_crop_pixmap = None

        # Retrieve current capture zone from overlay if active
        overlay = getattr(self.studio, "overlay", None)
        if overlay and hasattr(overlay, "get_capture_zone"):
            self._roi = overlay.get_capture_zone()
        else:
            self._roi = {"x": 0.05, "y": 0.72, "w": 0.90, "h": 0.20}

        self._build_ui()
        self._sync_to_overlay(active=True)
        self._update_crop_preview()

        # Listen to overlay drag changes
        if overlay and hasattr(overlay, "capture_zone_changed"):
            overlay.capture_zone_changed.connect(self._on_overlay_zone_changed)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        # Header Strip
        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        ico = QLabel()
        ico.setPixmap(icon("video", color="#38bdf8", size=24).pixmap(24, 24))
        hdr.addWidget(ico)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        title_lbl = QLabel("Subtitle Frame OCR & Auto Zone Capture")
        title_lbl.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {COLOR_TEXT_MAIN};")
        sub_lbl = QLabel("Automatically detects burned-in subtitles frame-by-frame. Adjust the tracker box over the captions.")
        sub_lbl.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_MUTED};")
        titles.addWidget(title_lbl)
        titles.addWidget(sub_lbl)
        hdr.addLayout(titles, 1)

        self.btn_toggle_preview = QPushButton("Hide Overlay")
        self.btn_toggle_preview.setCheckable(True)
        self.btn_toggle_preview.setChecked(True)
        self.btn_toggle_preview.setObjectName("dub_props_chip")
        self.btn_toggle_preview.clicked.connect(self._toggle_overlay_visibility)
        hdr.addWidget(self.btn_toggle_preview)
        root.addLayout(hdr)

        # Content Splitter: Left = Zone Tracker & Live Preview; Right = Detection Settings
        content = QHBoxLayout()
        content.setSpacing(14)

        # --- LEFT: TRACKER & LIVE CROP ---
        left_box = QFrame()
        left_box.setObjectName("asr_setting_group")
        left_lay = QVBoxLayout(left_box)
        left_lay.setContentsMargins(12, 10, 12, 12)
        left_lay.setSpacing(10)

        left_title = QLabel("🎯 Key Point Tracker (Capture Zone)")
        left_title.setObjectName("asr_field_label")
        left_lay.addWidget(left_title)

        # Live crop thumbnail
        self.crop_display = QLabel("No video frame loaded")
        self.crop_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crop_display.setFixedHeight(95)
        self.crop_display.setStyleSheet(
            f"background-color: {COLOR_BG_DARK}; border: 1px dashed #38bdf8; "
            f"border-radius: 6px; color: {COLOR_TEXT_MUTED}; font-size: 11px;"
        )
        left_lay.addWidget(self.crop_display)

        # Presets row
        preset_lbl = QLabel("Quick Presets")
        preset_lbl.setObjectName("asr_field_label")
        left_lay.addWidget(preset_lbl)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        btn_movie = QPushButton("🎬 Lower (72%–92%)")
        btn_movie.setObjectName("dub_props_chip")
        btn_movie.setToolTip("Standard movie & vertical drama subtitle placement")
        btn_movie.clicked.connect(lambda: self._apply_preset(0.05, 0.72, 0.90, 0.20))
        preset_row.addWidget(btn_movie)

        btn_third = QPushButton("📺 Lower 1/3 (65%–95%)")
        btn_third.setObjectName("dub_props_chip")
        btn_third.clicked.connect(lambda: self._apply_preset(0.04, 0.65, 0.92, 0.30))
        preset_row.addWidget(btn_third)

        btn_top = QPushButton("📱 Top (6%–24%)")
        btn_top.setObjectName("dub_props_chip")
        btn_top.clicked.connect(lambda: self._apply_preset(0.05, 0.06, 0.90, 0.18))
        preset_row.addWidget(btn_top)

        btn_full = QPushButton("📐 Full Frame")
        btn_full.setObjectName("dub_props_chip")
        btn_full.clicked.connect(lambda: self._apply_preset(0.0, 0.0, 1.0, 1.0))
        preset_row.addWidget(btn_full)
        left_lay.addLayout(preset_row)

        # Sliders grid
        grid = QGridLayout()
        grid.setSpacing(6)

        # Y Position
        grid.addWidget(QLabel("Y Position (%):"), 0, 0)
        self.slider_y = QSlider(Qt.Orientation.Horizontal)
        self.slider_y.setRange(0, 95)
        self.slider_y.setValue(int(self._roi.get("y", 0.72) * 100))
        self.slider_y.valueChanged.connect(self._on_sliders_changed)
        grid.addWidget(self.slider_y, 0, 1)
        self.lbl_y_val = QLabel(f"{self.slider_y.value()}%")
        self.lbl_y_val.setFixedWidth(36)
        grid.addWidget(self.lbl_y_val, 0, 2)

        # Height
        grid.addWidget(QLabel("Height (%):"), 1, 0)
        self.slider_h = QSlider(Qt.Orientation.Horizontal)
        self.slider_h.setRange(4, 50)
        self.slider_h.setValue(int(self._roi.get("h", 0.20) * 100))
        self.slider_h.valueChanged.connect(self._on_sliders_changed)
        grid.addWidget(self.slider_h, 1, 1)
        self.lbl_h_val = QLabel(f"{self.slider_h.value()}%")
        self.lbl_h_val.setFixedWidth(36)
        grid.addWidget(self.lbl_h_val, 1, 2)

        # X Position
        grid.addWidget(QLabel("X Position (%):"), 2, 0)
        self.slider_x = QSlider(Qt.Orientation.Horizontal)
        self.slider_x.setRange(0, 90)
        self.slider_x.setValue(int(self._roi.get("x", 0.05) * 100))
        self.slider_x.valueChanged.connect(self._on_sliders_changed)
        grid.addWidget(self.slider_x, 2, 1)
        self.lbl_x_val = QLabel(f"{self.slider_x.value()}%")
        self.lbl_x_val.setFixedWidth(36)
        grid.addWidget(self.lbl_x_val, 2, 2)

        # Width
        grid.addWidget(QLabel("Width (%):"), 3, 0)
        self.slider_w = QSlider(Qt.Orientation.Horizontal)
        self.slider_w.setRange(10, 100)
        self.slider_w.setValue(int(self._roi.get("w", 0.90) * 100))
        self.slider_w.valueChanged.connect(self._on_sliders_changed)
        grid.addWidget(self.slider_w, 3, 1)
        self.lbl_w_val = QLabel(f"{self.slider_w.value()}%")
        self.lbl_w_val.setFixedWidth(36)
        grid.addWidget(self.lbl_w_val, 3, 2)

        left_lay.addLayout(grid)
        left_lay.addStretch(1)
        content.addWidget(left_box, 1)

        # --- RIGHT: DETECTION & PIPELINE SETTINGS ---
        right_box = QFrame()
        right_box.setObjectName("asr_setting_group")
        right_lay = QVBoxLayout(right_box)
        right_lay.setContentsMargins(12, 10, 12, 12)
        right_lay.setSpacing(10)

        right_title = QLabel("⚙ Detection & Scan Settings")
        right_title.setObjectName("asr_field_label")
        right_lay.addWidget(right_title)

        # Sample Interval
        rate_lbl = QLabel("Sample Frequency")
        rate_lbl.setObjectName("asr_field_label")
        self.combo_interval = QComboBox()
        self.combo_interval.setObjectName("asr_option_combo")
        self.combo_interval.addItem("Balanced · 0.40s interval (Recommended)", 0.40)
        self.combo_interval.addItem("High Precision · 0.25s interval", 0.25)
        self.combo_interval.addItem("Fast Scan · 0.80s interval", 0.80)
        right_lay.addWidget(rate_lbl)
        right_lay.addWidget(self.combo_interval)

        # OCR Engine
        eng_lbl = QLabel("OCR Recognition Engine")
        eng_lbl.setObjectName("asr_field_label")
        self.combo_engine = QComboBox()
        self.combo_engine.setObjectName("asr_option_combo")
        self.combo_engine.addItem("Auto (Gemini Flash Vision → Local Neural)", "auto")
        self.combo_engine.addItem("Gemini Flash Vision (Cloud Free Tier)", "gemini")
        self.combo_engine.addItem("Local Neural OCR (RapidOCR / EasyOCR)", "local")
        right_lay.addWidget(eng_lbl)
        right_lay.addWidget(self.combo_engine)

        # Language
        lang_lbl = QLabel("Language / Script")
        lang_lbl.setObjectName("asr_field_label")
        self.combo_lang = QComboBox()
        self.combo_lang.setObjectName("asr_option_combo")
        self.combo_lang.addItems(["Auto Detect", "Chinese (Simplified / Traditional)", "English / Latin", "Khmer", "Vietnamese", "Japanese", "Korean"])
        right_lay.addWidget(lang_lbl)
        right_lay.addWidget(self.combo_lang)

        # Confidence
        conf_lbl = QLabel("Min Confidence: 50%")
        self.conf_lbl = conf_lbl
        conf_lbl.setObjectName("asr_field_label")
        self.slider_conf = QSlider(Qt.Orientation.Horizontal)
        self.slider_conf.setRange(20, 90)
        self.slider_conf.setValue(50)
        self.slider_conf.valueChanged.connect(lambda v: self.conf_lbl.setText(f"Min Confidence: {v}%"))
        right_lay.addWidget(conf_lbl)
        right_lay.addWidget(self.slider_conf)

        right_lay.addStretch(1)
        content.addWidget(right_box, 1)

        root.addLayout(content, 1)

        # Progress bar (hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)

        self.status_lbl = QLabel("Ready to scan. Adjust the tracker over the video captions.")
        self.status_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 11px;")
        root.addWidget(self.status_lbl)

        # Bottom Buttons
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_refresh_preview = QPushButton("Refresh Crop")
        self.btn_refresh_preview.setObjectName("dub_props_chip")
        self.btn_refresh_preview.clicked.connect(self._update_crop_preview)
        btn_bar.addWidget(self.btn_refresh_preview)
        btn_bar.addStretch(1)

        self.btn_close = QPushButton("Cancel")
        self.btn_close.setObjectName("dub_props_chip")
        self.btn_close.clicked.connect(self.close)
        btn_bar.addWidget(self.btn_close)

        self.btn_scan = QPushButton("▶ Scan & Extract Subtitles from Video Frames")
        self.btn_scan.setObjectName("asr_run_button")
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.setFixedHeight(34)
        self.btn_scan.clicked.connect(self._start_scan)
        btn_bar.addWidget(self.btn_scan)

        root.addLayout(btn_bar)

    def _sync_to_overlay(self, active: bool = True):
        overlay = getattr(self.studio, "overlay", None)
        if overlay and hasattr(overlay, "set_capture_zone"):
            overlay.set_capture_zone(self._roi, active=active)

    def _toggle_overlay_visibility(self):
        show = self.btn_toggle_preview.isChecked()
        self.btn_toggle_preview.setText("Hide Overlay" if show else "Show Overlay")
        self._sync_to_overlay(active=show)

    def _on_overlay_zone_changed(self, roi: dict):
        if not roi:
            return
        self._roi = dict(roi)
        # Block signals temporarily to prevent loop
        self.slider_x.blockSignals(True)
        self.slider_y.blockSignals(True)
        self.slider_w.blockSignals(True)
        self.slider_h.blockSignals(True)
        self.slider_x.setValue(int(self._roi.get("x", 0.05) * 100))
        self.slider_y.setValue(int(self._roi.get("y", 0.72) * 100))
        self.slider_w.setValue(int(self._roi.get("w", 0.90) * 100))
        self.slider_h.setValue(int(self._roi.get("h", 0.20) * 100))
        self.lbl_x_val.setText(f"{self.slider_x.value()}%")
        self.lbl_y_val.setText(f"{self.slider_y.value()}%")
        self.lbl_w_val.setText(f"{self.slider_w.value()}%")
        self.lbl_h_val.setText(f"{self.slider_h.value()}%")
        self.slider_x.blockSignals(False)
        self.slider_y.blockSignals(False)
        self.slider_w.blockSignals(False)
        self.slider_h.blockSignals(False)
        self._update_crop_preview()

    def _on_sliders_changed(self):
        self._roi = {
            "x": self.slider_x.value() / 100.0,
            "y": self.slider_y.value() / 100.0,
            "w": self.slider_w.value() / 100.0,
            "h": self.slider_h.value() / 100.0,
        }
        self.lbl_x_val.setText(f"{self.slider_x.value()}%")
        self.lbl_y_val.setText(f"{self.slider_y.value()}%")
        self.lbl_w_val.setText(f"{self.slider_w.value()}%")
        self.lbl_h_val.setText(f"{self.slider_h.value()}%")
        self._sync_to_overlay(active=True)
        self._update_crop_preview()

    def _apply_preset(self, x: float, y: float, w: float, h: float):
        self.slider_x.setValue(int(x * 100))
        self.slider_y.setValue(int(y * 100))
        self.slider_w.setValue(int(w * 100))
        self.slider_h.setValue(int(h * 100))
        self._on_sliders_changed()

    def _update_crop_preview(self):
        """Extract a single frame crop at the player position and display it in the dialog."""
        video_path = self._video_path or str(getattr(self.studio, "selected_file", "") or "")
        if not video_path:
            return
        preview = getattr(self.studio, "preview", None)
        pos_sec = 0.0
        if preview and hasattr(preview, "position"):
            pos_sec = preview.position() / 1000.0

        try:
            pil_crop = OCREngine.extract_frame_image(video_path, pos_sec, roi=self._roi)
            if pil_crop is not None:
                buf = io.BytesIO()
                pil_crop.save(buf, format="PNG")
                qimg = QImage.fromData(buf.getvalue())
                pix = QPixmap.fromImage(qimg)
                scaled = pix.scaled(
                    self.crop_display.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.crop_display.setPixmap(scaled)
        except Exception:
            pass

    def _start_scan(self):
        video_path = self._video_path or str(getattr(self.studio, "selected_file", "") or "")
        if not video_path:
            self.status_lbl.setText("No video file open in Claynext Studio.")
            return

        interval = float(self.combo_interval.currentData() or 0.40)
        min_conf = self.slider_conf.value() / 100.0
        lang = self.combo_lang.currentText()

        self.btn_scan.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status_lbl.setText("Scanning video frames with custom capture zone…")

        def _job(progress_callback=None):
            return OCREngine.extract_subtitles_from_video(
                video_path,
                self._roi,
                sample_interval=interval,
                min_confidence=min_conf,
                lang=lang,
                progress_callback=progress_callback,
            )

        worker = Worker(_job)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.result.connect(self._on_success)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self._worker = worker
        self.studio.thread_pool.start(worker)

    def _on_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.status_lbl.setText(msg)

    def _on_success(self, segments: list[dict]):
        self.progress_bar.setValue(100)
        count = len(segments)
        self.status_lbl.setText(f"Done! Found {count} subtitle lines.")
        if count > 0:
            self.subtitles_extracted.emit(segments)
            # Add to script table
            if hasattr(self.studio, "_segments"):
                self.studio._segments = list(segments)
                if hasattr(self.studio, "_fill_table"):
                    self.studio._fill_table(self.studio._segments)
                if hasattr(self.studio, "_refresh_character_list"):
                    self.studio._refresh_character_list()
                if hasattr(self.studio, "log"):
                    self.studio.log.success(f"Frame OCR Extracted: {count} subtitle lines added to script!")
        else:
            if hasattr(self.studio, "log"):
                self.studio.log.warn("No subtitles detected in the selected capture zone.")

    def _on_error(self, err: Exception, _stack: str = ""):
        self.status_lbl.setText(f"Error during scan: {err}")
        if hasattr(self.studio, "log"):
            self.studio.log.warn(f"Frame OCR scan error · {err}")

    def _on_finished(self):
        self.btn_scan.setEnabled(True)
        self._worker = None

    def closeEvent(self, event):
        # Keep capture zone state or hide it when dialog closes
        self._sync_to_overlay(active=False)
        super().closeEvent(event)
