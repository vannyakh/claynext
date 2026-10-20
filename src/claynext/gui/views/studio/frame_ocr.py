"""Subtitle capture zone for the right-side Inspector."""
from __future__ import annotations

import io

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from claynext.gui.components.controls.scrub_spin import ScrubSpinBox
from claynext.gui.worker import Worker
from claynext.models.ocr_service import OCREngine


class FrameOcrPanel(QWidget):
    """Subtitle capture zone and frame scan, laid out for the Inspector dock."""

    def __init__(self, studio, parent=None):
        super().__init__(parent or studio)
        self.studio = studio
        self._worker = None
        self._page_open = False
        self._bound = False
        self._roi = {"x": 0.05, "y": 0.72, "w": 0.90, "h": 0.20}
        self._crop_timer = QTimer(self)
        self._crop_timer.setSingleShot(True)
        self._crop_timer.timeout.connect(self._update_crop_preview)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        self.crop_display = QLabel("No frame yet")
        self.crop_display.setObjectName("ocr_crop")
        self.crop_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crop_display.setMinimumHeight(56)
        self.crop_display.setMaximumHeight(84)
        root.addWidget(self.crop_display)

        self.spin_x = self._zone_spin("X ", 0, 90, self._roi["x"])
        self.spin_y = self._zone_spin("Y ", 0, 95, self._roi["y"])
        xy = QHBoxLayout()
        xy.setContentsMargins(0, 3, 0, 3)
        xy.setSpacing(8)
        xy.addWidget(self.spin_x, 1)
        xy.addWidget(self.spin_y, 1)
        root.addLayout(xy)

        self.spin_h = self._spin_row(root, "Height", 4, 50, self._roi["h"])
        self.spin_w = self._spin_row(root, "Width", 10, 100, self._roi["w"])

        presets = QHBoxLayout()
        presets.setSpacing(4)
        presets.setContentsMargins(0, 4, 0, 2)
        for label, tip, box in (
            ("Lower", "72%–92%", (0.05, 0.72, 0.90, 0.20)),
            ("1/3", "65%–95%", (0.04, 0.65, 0.92, 0.30)),
            ("Top", "6%–24%", (0.05, 0.06, 0.90, 0.18)),
            ("Full", "Whole frame", (0.0, 0.0, 1.0, 1.0)),
        ):
            btn = QPushButton(label)
            btn.setObjectName("dub_props_chip")
            btn.setToolTip(tip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, b=box: self._apply_preset(*b))
            presets.addWidget(btn)
        root.addLayout(presets)

        line = QFrame()
        line.setObjectName("prop_divider")
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        self.combo_interval = QComboBox()
        self.combo_interval.setObjectName("prop_combo")
        self.combo_interval.addItem("0.40s", 0.40)
        self.combo_interval.addItem("0.25s", 0.25)
        self.combo_interval.addItem("0.80s", 0.80)
        root.addWidget(self._field_row("Sample", self.combo_interval))

        self.combo_lang = QComboBox()
        self.combo_lang.setObjectName("prop_combo")
        self.combo_lang.addItems([
            "Auto",
            "Chinese",
            "English",
            "Khmer",
            "Vietnamese",
            "Japanese",
            "Korean",
        ])
        root.addWidget(self._field_row("Language", self.combo_lang))

        self.spin_conf = self._spin_row(root, "Confidence", 20, 90, 0.50, live=False)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)

        self.status_lbl = QLabel("Ready")
        self.status_lbl.setObjectName("ocr_status")
        self.status_lbl.setWordWrap(True)
        root.addWidget(self.status_lbl)

        foot = QHBoxLayout()
        foot.setContentsMargins(0, 8, 0, 0)
        self.btn_refresh_preview = QPushButton("Refresh")
        self.btn_refresh_preview.setObjectName("prop_modify_btn")
        self.btn_refresh_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh_preview.setToolTip("Grab the crop at the playhead")
        self.btn_refresh_preview.clicked.connect(self._update_crop_preview)
        foot.addWidget(self.btn_refresh_preview)
        foot.addStretch(1)
        self.btn_scan = QPushButton("Scan")
        self.btn_scan.setObjectName("prop_modify_btn")
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.clicked.connect(self._start_scan)
        foot.addWidget(self.btn_scan)
        root.addLayout(foot)
        root.addStretch(1)

    def _field_row(self, title: str, widget: QWidget, *, stretch: bool = True) -> QWidget:
        row = QWidget()
        row.setObjectName("prop_row")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 3, 0, 3)
        lay.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("prop_key")
        lay.addWidget(label, 1 if not stretch else 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(widget, 1 if stretch else 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        return row

    def _zone_spin(self, prefix: str, low: int, high: int, value: float) -> ScrubSpinBox:
        spin = ScrubSpinBox()
        spin.setRange(low, high)
        spin.setPrefix(prefix)
        spin.setSuffix("%")
        spin.setMinimumWidth(88)
        spin.setMaximumWidth(16777215)
        spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        spin.setValue(int(round(value * 100)))
        spin.setToolTip("Drag up/down to scrub · click to type · ▲▼ to step")
        spin.valueChanged.connect(self._on_zone_changed)
        return spin

    def _spin_row(
        self, layout: QVBoxLayout, title: str, low: int, high: int, value: float, *, live: bool = True,
    ) -> ScrubSpinBox:
        spin = ScrubSpinBox()
        spin.setRange(low, high)
        spin.setSuffix("%")
        spin.setFixedWidth(78)
        spin.setValue(int(round(value * 100)))
        spin.setToolTip("Drag up/down to scrub · click to type · ▲▼ to step")
        if live:
            spin.valueChanged.connect(self._on_zone_changed)
        layout.addWidget(self._field_row(title, spin, stretch=False))
        return spin

    def set_active(self, active: bool):
        """Show or hide the capture box when this Inspector page opens or closes."""
        self._page_open = active
        if active:
            overlay = getattr(self.studio, "overlay", None)
            if overlay and hasattr(overlay, "get_capture_zone"):
                zone = overlay.get_capture_zone()
                if isinstance(zone, dict) and zone:
                    self._roi = dict(zone)
                    self._write_zone()
            self._bind_overlay()
        self._sync_to_overlay(active=active)
        if active:
            self._schedule_crop()

    def _bind_overlay(self):
        if self._bound:
            return
        overlay = getattr(self.studio, "overlay", None)
        if overlay and hasattr(overlay, "capture_zone_changed"):
            overlay.capture_zone_changed.connect(self._on_overlay_zone_changed)
            self._bound = True

    def _sync_to_overlay(self, active: bool = True):
        overlay = getattr(self.studio, "overlay", None)
        if overlay and hasattr(overlay, "set_capture_zone"):
            overlay.set_capture_zone(self._roi, active=active)

    def _write_zone(self):
        pairs = (
            (self.spin_x, "x", 0.05),
            (self.spin_y, "y", 0.72),
            (self.spin_w, "w", 0.90),
            (self.spin_h, "h", 0.20),
        )
        for spin, key, default in pairs:
            spin.blockSignals(True)
            spin.setValue(int(round(float(self._roi.get(key, default)) * 100)))
            spin.blockSignals(False)

    def _on_overlay_zone_changed(self, roi: dict):
        if not roi or not self._page_open:
            return
        self._roi = dict(roi)
        self._write_zone()
        self._schedule_crop()

    def _on_zone_changed(self, _value: int = 0):
        self._roi = {
            "x": self.spin_x.value() / 100.0,
            "y": self.spin_y.value() / 100.0,
            "w": self.spin_w.value() / 100.0,
            "h": self.spin_h.value() / 100.0,
        }
        if self._page_open:
            self._sync_to_overlay(active=True)
            self._schedule_crop()

    def _apply_preset(self, x: float, y: float, w: float, h: float):
        self.spin_x.setValue(int(x * 100))
        self.spin_y.setValue(int(y * 100))
        self.spin_w.setValue(int(w * 100))
        self.spin_h.setValue(int(h * 100))

    def _schedule_crop(self):
        self._crop_timer.start(160)

    def _update_crop_preview(self):
        video_path = str(getattr(self.studio, "selected_file", "") or "")
        if not video_path:
            return
        preview = getattr(self.studio, "preview", None)
        pos_sec = 0.0
        if preview and hasattr(preview, "position"):
            pos_sec = preview.position() / 1000.0
        try:
            pil_crop = OCREngine.extract_frame_image(video_path, pos_sec, roi=self._roi)
            if pil_crop is None:
                return
            buf = io.BytesIO()
            pil_crop.save(buf, format="PNG")
            pix = QPixmap.fromImage(QImage.fromData(buf.getvalue()))
            self.crop_display.setPixmap(pix.scaled(
                self.crop_display.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            ))
        except Exception:
            pass

    def _start_scan(self):
        video_path = str(getattr(self.studio, "selected_file", "") or "")
        if not video_path:
            self.status_lbl.setText("Open a video first.")
            return
        interval = float(self.combo_interval.currentData() or 0.40)
        min_conf = self.spin_conf.value() / 100.0
        lang = self.combo_lang.currentText()
        self.btn_scan.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status_lbl.setText("Scanning frames in the capture zone…")

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

    def _on_success(self, segments: list):
        self.progress_bar.setValue(100)
        count = len(segments or [])
        if count == 0:
            self.status_lbl.setText("No subtitle text in this capture zone.")
        else:
            self.status_lbl.setText(f"Found {count} subtitle line{'s' if count != 1 else ''}.")
        if count > 0 and hasattr(self.studio, "_segments"):
            self.studio._segments = list(segments)
            if hasattr(self.studio, "_fill_table"):
                self.studio._fill_table(self.studio._segments)
            if hasattr(self.studio, "log"):
                self.studio.log.success(f"Frame OCR · {count} line{'s' if count != 1 else ''} added to the script")
        elif hasattr(self.studio, "log"):
            self.studio.log.warn("No subtitles in the capture zone.")

    def _on_error(self, err, _stack: str = ""):
        self.status_lbl.setText(f"Scan failed · {err}")
        if hasattr(self.studio, "log"):
            self.studio.log.warn(f"Frame OCR · {err}")

    def _on_finished(self):
        self.btn_scan.setEnabled(True)
        self._worker = None
