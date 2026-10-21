from __future__ import annotations

from PySide6.QtCore import Qt, QElapsedTimer, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QWidget

from claynext.constants import STATUSBAR_HEIGHT
from claynext.constants.theme_constants import (
    COLOR_ACCENT_PURPLE,
    COLOR_PRIMARY,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_SUB,
)
from claynext.gui.components.controls.spinner import Spinner
from claynext.utils.config import APP_VERSION


class CustomStatusBar(QWidget):
    """Lightweight footer for tool status and active feature — no system meters."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("custom_status_bar")
        self.setFixedHeight(STATUSBAR_HEIGHT)
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        # Spinner and track scale to the status-bar height so they stay inside the chrome.
        spin_size = max(12, STATUSBAR_HEIGHT - 12)
        track_h = max(4, min(8, STATUSBAR_HEIGHT // 4))
        track_w = max(120, STATUSBAR_HEIGHT * 6)

        self._spinner = Spinner(self, size=spin_size, color=COLOR_ACCENT_PURPLE)
        layout.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignVCenter)

        self._elapsed = QElapsedTimer()
        self._elapsed_tick = QTimer(self)
        self._elapsed_tick.setInterval(1000)
        self._elapsed_tick.timeout.connect(self._paint_elapsed)
        self.lbl_elapsed = QLabel("")
        self.lbl_elapsed.setObjectName("status_elapsed")
        self.lbl_elapsed.hide()
        layout.addWidget(self.lbl_elapsed, 0, Qt.AlignmentFlag.AlignVCenter)

        self.lbl_msg = QLabel("Ready")
        self.lbl_msg.setObjectName("status_message")
        layout.addWidget(self.lbl_msg, 1)

        self.progress = QProgressBar()
        self.progress.setObjectName("status_progress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedSize(track_w, track_h)
        self.progress.hide()
        layout.addWidget(self.progress, 0, Qt.AlignmentFlag.AlignVCenter)

        self.lbl_active_tool = QLabel("")
        self.lbl_active_tool.setObjectName("status_tool")
        layout.addWidget(self.lbl_active_tool)

        self.lbl_ver = QLabel(f"v{APP_VERSION}")
        self.lbl_ver.setObjectName("status_version")
        layout.addWidget(self.lbl_ver)

    def set_status_message(self, msg: str, progress: int | None = None):
        text = msg or "Ready"
        if self.lbl_msg.text() != text:
            self.lbl_msg.setText(text)
        if progress is None:
            self._stop_elapsed()
            self._spinner.stop()
            self.progress.hide()
            return
        self._start_elapsed()
        pct = max(0, min(100, int(progress)))
        if self.progress.value() != pct:
            self.progress.setValue(pct)
        if not self.progress.isVisible():
            self.progress.show()
        if not self._spinner.is_spinning():
            self._spinner.start()

    def set_active_tool_name(self, name: str):
        self.lbl_active_tool.setText(name or "")

    def _start_elapsed(self) -> None:
        """Count from the moment this process became busy. Later progress ticks keep the same clock."""
        if self._elapsed_tick.isActive():
            return
        self._elapsed.start()
        self._elapsed_tick.start()
        self.lbl_elapsed.show()
        self._paint_elapsed()

    def _stop_elapsed(self) -> None:
        self._elapsed_tick.stop()
        self.lbl_elapsed.clear()
        self.lbl_elapsed.hide()

    def _paint_elapsed(self) -> None:
        total = max(0, int(self._elapsed.elapsed() // 1000))
        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)
        text = f"{hours:d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"
        if self.lbl_elapsed.text() != text:
            self.lbl_elapsed.setText(text)
