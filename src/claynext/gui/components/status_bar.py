from __future__ import annotations

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

from claynext.constants import STATUSBAR_HEIGHT
from claynext.constants.theme_constants import COLOR_TEXT_SUB, COLOR_TEXT_MUTED, COLOR_PRIMARY
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
        layout.setSpacing(10)

        self.lbl_msg = QLabel("Ready")
        self.lbl_msg.setStyleSheet(
            f"color: {COLOR_TEXT_SUB}; font-size: 11px;"
        )
        layout.addWidget(self.lbl_msg, 1)

        self.lbl_active_tool = QLabel("")
        self.lbl_active_tool.setStyleSheet(
            f"color: {COLOR_PRIMARY}; font-weight: 700; font-size: 11px;"
        )
        layout.addWidget(self.lbl_active_tool)

        self.lbl_ver = QLabel(f"v{APP_VERSION}")
        self.lbl_ver.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: 11px; font-weight: 600; "
            f"padding: 2px 6px; border-radius: 3px; background: rgba(255,255,255,0.04);"
        )
        layout.addWidget(self.lbl_ver)

    def set_status_message(self, msg: str):
        self.lbl_msg.setText(msg or "Ready")

    def set_active_tool_name(self, name: str):
        self.lbl_active_tool.setText(name or "")
