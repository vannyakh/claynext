"""Export progress window: movie thumbnail and a bordered encode bar."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QSize, QThreadPool
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QFrame,
)

from claynext.gui.worker import Worker


class ExportProgressDialog(QDialog):
    """Shows the movie being exported and live encode progress."""

    def __init__(self, parent=None, *, title: str, source: str, dest: str):
        super().__init__(parent)
        self.setObjectName("exportProgressDialog")
        self.setWindowTitle(title or "Export")
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(420)
        self._closed = False

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 16)
        root.setSpacing(12)

        self.thumb_frame = QFrame()
        self.thumb_frame.setObjectName("export_thumb_frame")
        self.thumb_frame.setFixedSize(384, 216)
        frame_layout = QVBoxLayout(self.thumb_frame)
        frame_layout.setContentsMargins(1, 1, 1, 1)
        self.thumb = QLabel("Loading preview…")
        self.thumb.setObjectName("export_thumb")
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self.thumb)
        root.addWidget(self.thumb_frame, alignment=Qt.AlignmentFlag.AlignHCenter)

        heading = QLabel(title or "Export")
        heading.setObjectName("dub_panel_title")
        root.addWidget(heading)

        self.name = QLabel(os.path.basename(dest) if dest else "")
        self.name.setObjectName("export_filename")
        self.name.setWordWrap(True)
        if dest:
            self.name.setToolTip(dest)
        root.addWidget(self.name)

        self.status = QLabel("Preparing export…")
        self.status.setObjectName("export_status")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.bar = QProgressBar()
        self.bar.setObjectName("export_progress")
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(18)
        row.addWidget(self.bar, 1)
        self.percent = QLabel("0%")
        self.percent.setObjectName("export_percent")
        self.percent.setMinimumWidth(42)
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.percent)
        root.addLayout(row)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("btn_primary")
        self.btn_close.setVisible(False)
        self.btn_close.clicked.connect(self.accept)
        buttons.addWidget(self.btn_close)
        root.addLayout(buttons)

        self._load_thumb(source)

    def _load_thumb(self, source: str) -> None:
        if not source or not os.path.isfile(source):
            self.thumb.setText("No preview")
            return
        from claynext.models.thumbnails import thumb_path_for

        for width in (480, 160):
            cached = thumb_path_for(source, width)
            if cached.is_file():
                self._apply_pix(QPixmap(str(cached)))
                if width >= 480:
                    return
        worker = Worker(self._extract, source)
        self._thumb_worker = worker
        worker.signals.result.connect(self._on_thumb)
        worker.signals.finished.connect(self._clear_thumb_worker)
        QThreadPool.globalInstance().start(worker)

    def _clear_thumb_worker(self) -> None:
        self._thumb_worker = None

    @staticmethod
    def _extract(source: str, progress_callback=None) -> str | None:
        from claynext.models.thumbnails import ensure_thumbnail

        return ensure_thumbnail(source, 480)

    def _on_thumb(self, path) -> None:
        if self._closed or not path:
            return
        self._apply_pix(QPixmap(str(path)))

    def _apply_pix(self, pix: QPixmap) -> None:
        if pix.isNull():
            self.thumb.setText("No preview")
            return
        scaled = pix.scaled(
            QSize(382, 214),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.thumb.setPixmap(scaled)
        self.thumb.setText("")

    def set_progress(self, pct: int, msg: str) -> None:
        if self._closed:
            return
        value = max(0, min(100, int(pct)))
        self.bar.setValue(value)
        self.percent.setText(f"{value}%")
        if msg:
            self.status.setText(msg)

    def succeed(self, name: str) -> None:
        self.set_progress(100, "Export complete")
        if name:
            self.status.setText(f"Saved {name}")
        self.btn_close.setVisible(True)

    def fail(self, message: str) -> None:
        if self._closed:
            return
        self.status.setText(message or "Export failed.")
        self.status.setProperty("error", True)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.btn_close.setVisible(True)

    def closeEvent(self, event) -> None:
        self._closed = True
        super().closeEvent(event)
