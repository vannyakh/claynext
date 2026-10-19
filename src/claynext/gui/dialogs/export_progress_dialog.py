"""Export progress window: movie thumbnail and a bordered encode bar."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QSize, QThreadPool, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QFrame,
)

from claynext.gui.dialogs.export_dialog import (
    ExportTitleBar, frameless_shell, place_export_dialog, rounded_still,
)
from claynext.gui.worker import Worker

_THUMB_MAX = QSize(132, 176)
_THUMB_RADIUS = 8


class ExportProgressDialog(QDialog):
    """Shows the movie being exported and live encode progress."""

    def __init__(self, parent=None, *, title: str, source: str, dest: str):
        super().__init__(parent)
        self.setObjectName("exportProgressDialog")
        self.setWindowTitle(title or "Export")
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(520)
        self._placed = False
        self._closed = False
        self._target = 0.0
        self._shown = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)

        root, rule = frameless_shell(self)
        root.addWidget(ExportTitleBar(self, title or "Export"))
        root.addWidget(rule)

        content = QHBoxLayout()
        content.setContentsMargins(16, 4, 16, 8)
        content.setSpacing(16)
        details = QVBoxLayout()
        details.setSpacing(10)

        self.name = QLabel(os.path.basename(dest) if dest else "")
        self.name.setObjectName("export_filename")
        self.name.setWordWrap(True)
        if dest:
            self.name.setToolTip(dest)
        details.addWidget(self.name)

        self.status = QLabel("Preparing export…")
        self.status.setObjectName("export_status")
        self.status.setWordWrap(True)
        details.addWidget(self.status)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.bar = QProgressBar()
        self.bar.setObjectName("export_progress")
        self.bar.setRange(0, 10_000)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(18)
        row.addWidget(self.bar, 1)
        self.percent = QLabel("0%")
        self.percent.setObjectName("export_percent")
        self.percent.setMinimumWidth(54)
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.percent)
        details.addLayout(row)
        details.addStretch(1)
        content.addLayout(details, 1)

        card = QFrame()
        card.setObjectName("export_preview_card")
        card.setFixedWidth(156)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(10, 10, 10, 10)
        self.thumb = QLabel("Preview")
        self.thumb.setObjectName("export_thumb")
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setMinimumSize(120, 80)
        card_lay.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignCenter)
        content.addWidget(card, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(content)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(16, 0, 16, 0)
        buttons.addStretch(1)
        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("api_keys_btn_primary")
        self.btn_close.setVisible(False)
        self.btn_close.clicked.connect(self.accept)
        buttons.addWidget(self.btn_close)
        root.addLayout(buttons)

        self._load_thumb(source)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._placed:
            self._placed = True
            place_export_dialog(self)

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
        rounded = rounded_still(pix, _THUMB_MAX, _THUMB_RADIUS, self.devicePixelRatioF())
        self.thumb.setPixmap(rounded)
        self.thumb.setText("")
        ratio = rounded.devicePixelRatio() or 1.0
        self.thumb.setFixedSize(int(rounded.width() / ratio), int(rounded.height() / ratio))

    def set_progress(self, pct: float, msg: str = "") -> None:
        if self._closed:
            return
        try:
            value = float(pct)
        except (TypeError, ValueError):
            value = 0.0
        self._target = max(0.0, min(100.0, value))
        if msg:
            self.status.setText(msg)
        if not self._timer.isActive():
            self._timer.start()

    def _tick(self) -> None:
        if self._closed:
            self._timer.stop()
            return
        delta = self._target - self._shown
        if abs(delta) <= 0.45:
            self._shown = self._target
        else:
            self._shown += delta * 0.2
        self._paint_bar()
        if abs(self._target - self._shown) <= 0.01:
            self._timer.stop()

    def _paint_bar(self) -> None:
        self.bar.setValue(int(round(self._shown * 100.0)))
        if self._shown >= 99.95:
            label = "100%"
        else:
            label = f"{self._shown:.1f}%"
        if self.percent.text() != label:
            self.percent.setText(label)

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
        self._timer.stop()
        super().closeEvent(event)
