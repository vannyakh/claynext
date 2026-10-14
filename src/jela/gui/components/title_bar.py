from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QToolButton, QMenuBar, QPushButton
)
from PySide6.QtCore import Signal, Qt, QPoint

from jela.constants import TITLEBAR_HEIGHT
from jela.core.icons import icon, image_pixmap, ICON_ON_DARK


class CustomTitleBar(QWidget):
    """
    Custom window chrome:
    [Logo] [MenuBar] …… [Tool title · badge] [Settings] [— □ ×]
    Tool header identity lives here so the workspace stays clean.
    """
    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("custom_title_bar")
        self.setFixedHeight(TITLEBAR_HEIGHT)
        self._drag_pos = QPoint()
        self.is_maximized = False
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(8)

        # Logo
        self.logo_label = QLabel()
        self.logo_label.setObjectName("title_logo_icon")
        self.logo_label.setToolTip("Jela Studio")
        pixmap = image_pixmap("splash_hero", height=20)
        if pixmap.isNull():
            pixmap = image_pixmap("app", height=18)
        if not pixmap.isNull():
            self.logo_label.setPixmap(pixmap)
        else:
            self.logo_label.setText("M")
            self.logo_label.setFixedSize(20, 20)
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.logo_label.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6366f1, stop:1 #8b5cf6);
                color: #ffffff;
                font-weight: 900;
                font-size: 10px;
                border-radius: 5px;
            """)
        layout.addWidget(self.logo_label)

        # In-window menu bar
        self.menu_bar = QMenuBar(self)
        self.menu_bar.setObjectName("titleMenuBar")
        self.menu_bar.setNativeMenuBar(False)
        layout.addWidget(self.menu_bar)

        layout.addStretch(1)

        # Tool identity (replaces separate header bar)
        self.tool_icon = QLabel()
        self.tool_icon.setObjectName("title_tool_icon")
        self.tool_icon.setFixedSize(22, 22)
        self.tool_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tool_icon.hide()
        layout.addWidget(self.tool_icon)

        self.tool_title = QLabel()
        self.tool_title.setObjectName("title_tool_name")
        self.tool_title.hide()
        layout.addWidget(self.tool_title)

        self.tool_badge = QLabel()
        self.tool_badge.setObjectName("title_tool_badge")
        self.tool_badge.hide()
        layout.addWidget(self.tool_badge)

        # Settings
        self.btn_settings = QToolButton()
        self.btn_settings.setObjectName("title_settings_btn")
        self.btn_settings.setIcon(icon("settings", color="#94a3b8", size=14))
        self.btn_settings.setFixedSize(32, 28)
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setToolTip("Settings (Ctrl+,)")
        self.btn_settings.clicked.connect(self.settings_requested.emit)
        layout.addWidget(self.btn_settings)

        # Window controls
        win_box = QWidget()
        win_box.setObjectName("winControls")
        btn_layout = QHBoxLayout(win_box)
        btn_layout.setContentsMargins(4, 0, 0, 0)
        btn_layout.setSpacing(0)

        self.btn_min = self._win_btn("win-minimize", "Minimize")
        self.btn_min.clicked.connect(self.minimize_requested.emit)

        self.btn_max = self._win_btn("win-maximize", "Maximize")
        self.btn_max.clicked.connect(self.on_toggle_maximize)

        self.btn_close = self._win_btn("win-close", "Close", is_close=True)
        self.btn_close.setObjectName("winClose")
        self.btn_close.clicked.connect(self.close_requested.emit)

        btn_layout.addWidget(self.btn_min)
        btn_layout.addWidget(self.btn_max)
        btn_layout.addWidget(self.btn_close)
        layout.addWidget(win_box)

    def set_tool_info(self, tool_data: dict | None):
        """Show tool name / badge in the title bar (replaces page header)."""
        if not tool_data:
            self.tool_icon.hide()
            self.tool_title.hide()
            self.tool_badge.hide()
            return

        accent = tool_data.get("color", "#6366f1")
        label = tool_data.get("label", "")
        badge = tool_data.get("badge", "")
        icon_name = tool_data.get("icon", "")

        self.tool_title.setText(label)
        self.tool_title.show()

        self.tool_badge.hide()

        if icon_name:
            self.tool_icon.setPixmap(icon(icon_name, color=accent, size=12).pixmap(12, 12))
            self.tool_icon.setStyleSheet(f"""
                QLabel#title_tool_icon {{
                    background-color: {accent}20;
                    border: 1px solid {accent}40;
                    border-radius: 6px;
                }}
            """)
            self.tool_icon.show()
        else:
            self.tool_icon.hide()

    def _win_btn(self, icon_name: str, tooltip: str, is_close: bool = False) -> QToolButton:
        btn = QToolButton()
        btn.setIcon(icon(icon_name, color=ICON_ON_DARK, size=14))
        btn.setToolTip(tooltip)
        btn.setFixedSize(42, TITLEBAR_HEIGHT)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hover_bg = "#e81123" if is_close else "#243044"
        btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: 0;
                border-radius: 0;
            }}
            QToolButton:hover {{ background: {hover_bg}; }}
        """)
        return btn

    def set_maximized(self, is_maximized: bool):
        self.is_maximized = is_maximized
        icon_name = "win-restore" if is_maximized else "win-maximize"
        self.btn_max.setIcon(icon(icon_name, color=ICON_ON_DARK, size=14))
        self.btn_max.setToolTip("Restore" if is_maximized else "Maximize")

    def on_toggle_maximize(self):
        self.maximize_requested.emit()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_toggle_maximize()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Don't start drag from interactive controls
            child = self.childAt(event.pos())
            if isinstance(child, (QMenuBar, QToolButton, QPushButton)):
                super().mousePressEvent(event)
                return
            win = self.window()
            handle = win.windowHandle() if win else None
            if handle and hasattr(handle, "startSystemMove") and not win.isMaximized():
                if handle.startSystemMove():
                    event.accept()
                    return
            if win and not win.isMaximized():
                self._drag_pos = event.globalPosition().toPoint() - win.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
            win = self.window()
            if win and not win.isMaximized():
                win.move(event.globalPosition().toPoint() - self._drag_pos)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = QPoint()
        super().mouseReleaseEvent(event)
