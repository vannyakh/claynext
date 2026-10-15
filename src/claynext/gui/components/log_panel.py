from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QToolButton, QLabel, QApplication
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QTextCharFormat, QColor, QTextCursor

from claynext.gui.icons import icon


class LogPanel(QWidget):
    """
    Timestamped activity log for tool pipelines.
    Slim top actions: copy / clear.
    """
    cleared = Signal()

    LEVEL_COLORS = {
        "info": "#9fb0c3",
        "success": "#34d399",
        "warn": "#fbbf24",
        "error": "#f87171",
        "debug": "#64748b",
    }

    def __init__(self, parent=None, show_title: bool = True):
        super().__init__(parent)
        self.setObjectName("log_panel")
        self._auto_scroll = True
        self._show_title = show_title
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QWidget()
        toolbar.setObjectName("log_toolbar")
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(10, 4, 8, 4)
        bar.setSpacing(4)

        if self._show_title:
            title = QLabel("Activity Log")
            title.setObjectName("log_toolbar_title")
            bar.addWidget(title)
        else:
            hint = QLabel("Activity")
            hint.setObjectName("log_toolbar_hint")
            bar.addWidget(hint)

        bar.addStretch(1)

        self.btn_copy = self._action_btn("copy", "Copy log")
        self.btn_copy.clicked.connect(self.copy_all)
        bar.addWidget(self.btn_copy)

        self.btn_clear = self._action_btn("stop", "Clear log")
        self.btn_clear.setObjectName("log_action_clear")
        self.btn_clear.clicked.connect(self.clear)
        bar.addWidget(self.btn_clear)

        layout.addWidget(toolbar)

        self.view = QPlainTextEdit()
        self.view.setObjectName("log_view")
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(2000)
        self.view.setPlaceholderText("Pipeline events will appear here…")
        layout.addWidget(self.view, 1)

    def _action_btn(self, name: str, tip: str) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("log_action_btn")
        btn.setIcon(icon(name, color="#94a3b8", size=12))
        btn.setIconSize(QSize(12, 12))
        btn.setFixedSize(24, 22)
        btn.setAutoRaise(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tip)
        return btn

    def log(self, message: str, level: str = "info"):
        level = (level or "info").lower()
        color = self.LEVEL_COLORS.get(level, self.LEVEL_COLORS["info"])
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] [{level.upper():7}] {message}"

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))

        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(line + "\n", fmt)
        if self._auto_scroll:
            self.view.setTextCursor(cursor)
            self.view.ensureCursorVisible()

    def info(self, message: str):
        self.log(message, "info")

    def success(self, message: str):
        self.log(message, "success")

    def warn(self, message: str):
        self.log(message, "warn")

    def error(self, message: str):
        self.log(message, "error")

    def debug(self, message: str):
        self.log(message, "debug")

    def copy_all(self):
        text = self.view.toPlainText().strip()
        if not text:
            return
        QApplication.clipboard().setText(text)

    def clear(self):
        self.view.clear()
        self.cleared.emit()
