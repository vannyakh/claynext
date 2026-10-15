from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QToolButton, QMenuBar, QPushButton
)
from PySide6.QtCore import Signal, Qt, QPoint

from claynext.constants import TITLEBAR_HEIGHT
from claynext.gui.icons import icon, image_pixmap, ICON_ON_DARK


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
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(10)

        # Logo
        self.logo_label = QLabel()
        self.logo_label.setObjectName("title_logo_icon")
        self.logo_label.setToolTip("Dubify AI PRO")
        pixmap = image_pixmap("splash_hero", height=22)
        if pixmap.isNull():
            pixmap = image_pixmap("app", height=20)
        if not pixmap.isNull():
            self.logo_label.setPixmap(pixmap)
        else:
            self.logo_label.setText("D")
            self.logo_label.setFixedSize(22, 22)
            self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.logo_label.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7c3aed, stop:1 #4f46e5);
                color: #ffffff;
                font-weight: 900;
                font-size: 11px;
                border-radius: 6px;
            """)
        layout.addWidget(self.logo_label)

        # Brand Identity (Dubify AI + PRO badge + Subtitle)
        brand_box = QWidget()
        brand_box.setObjectName("title_brand_box")
        brand_layout = QVBoxLayout(brand_box)
        brand_layout.setContentsMargins(0, 3, 0, 3)
        brand_layout.setSpacing(1)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)

        self.lbl_brand_name = QLabel("Dubify AI")
        self.lbl_brand_name.setStyleSheet("""
            color: #ffffff;
            font-size: 13px;
            font-weight: 800;
            letter-spacing: 0.3px;
        """)
        title_row.addWidget(self.lbl_brand_name)

        self.lbl_pro_badge = QLabel("PRO")
        self.lbl_pro_badge.setStyleSheet("""
            background-color: #6d28d9;
            color: #ffffff;
            font-size: 9px;
            font-weight: 800;
            padding: 1px 5px;
            border-radius: 3px;
        """)
        title_row.addWidget(self.lbl_pro_badge)
        title_row.addStretch(1)
        brand_layout.addLayout(title_row)

        self.lbl_brand_sub = QLabel("AI Video Translation & Dubbing Studio")
        self.lbl_brand_sub.setStyleSheet("""
            color: #818cf8;
            font-size: 9.5px;
            font-weight: 500;
        """)
        brand_layout.addWidget(self.lbl_brand_sub)
        layout.addWidget(brand_box)

        # In-window menu bar
        self.menu_bar = QMenuBar(self)
        self.menu_bar.setObjectName("titleMenuBar")
        self.menu_bar.setNativeMenuBar(False)
        layout.addWidget(self.menu_bar)

        layout.addStretch(1)

        # PRO Activated status badge
        self.pro_status_badge = QLabel("☑ PRO Activated")
        self.pro_status_badge.setObjectName("title_pro_badge")
        self.pro_status_badge.setStyleSheet("""
            color: #c4b5fd;
            font-size: 11px;
            font-weight: 600;
            padding: 3px 8px;
            background-color: rgba(109, 40, 217, 0.15);
            border: 1px solid rgba(139, 92, 246, 0.3);
            border-radius: 4px;
        """)
        layout.addWidget(self.pro_status_badge)

        # Settings Button
        self.btn_settings = QPushButton("Settings")
        self.btn_settings.setObjectName("title_settings_btn")
        self.btn_settings.setIcon(icon("settings", color="#c4b5fd", size=13))
        self.btn_settings.setFixedHeight(24)
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setToolTip("Settings (Ctrl+,)")
        self.btn_settings.setStyleSheet("""
            QPushButton#title_settings_btn {
                background-color: #232238;
                color: #e2e8f0;
                font-size: 11px;
                font-weight: 500;
                border: 1px solid #3b3a58;
                border-radius: 4px;
                padding: 0 10px;
            }
            QPushButton#title_settings_btn:hover {
                background-color: #2f2e4b;
                border-color: #6366f1;
            }
        """)
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
        """Show tool name / badge in the title bar."""
        if not tool_data:
            return
        desc = tool_data.get("description", "")
        if desc:
            self.lbl_brand_sub.setText(desc)

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

