from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QToolButton, QMenuBar, QPushButton, QSizePolicy,
)
from PySide6.QtCore import Signal, Qt, QPoint

from claynext.constants import TITLEBAR_HEIGHT
from claynext.gui.icons import icon, image_pixmap, ICON_ON_DARK


class CustomTitleBar(QWidget):
    """
    Custom window chrome:
    [Logo] [MenuBar] …… [— □ ×]
    Compact left cluster so the menu sits close to the logo.
    """
    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()
    settings_requested = Signal()  # kept for menu/shortcut wiring; no title-bar button

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("custom_title_bar")
        self.setFixedHeight(TITLEBAR_HEIGHT)
        self._drag_pos = QPoint()
        self.is_maximized = False
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(4)

        # Small icon logo only
        self.logo_label = QLabel()
        self.logo_label.setObjectName("title_logo_icon")
        self.logo_label.setToolTip("Claynext Studio")
        self.logo_label.setFixedSize(20, 20)
        self.logo_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = image_pixmap("app", height=18)
        if pixmap.isNull():
            pixmap = image_pixmap("splash_hero", height=18)
        if not pixmap.isNull():
            self.logo_label.setPixmap(pixmap)
        else:
            self.logo_label.setText("C")
        layout.addWidget(self.logo_label, 0, Qt.AlignmentFlag.AlignVCenter)

        # Menu bar directly after logo
        self.menu_bar = QMenuBar(self)
        self.menu_bar.setObjectName("titleMenuBar")
        self.menu_bar.setNativeMenuBar(False)
        self.menu_bar.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.menu_bar, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch(1)

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
        """Keep brand logo only; tool description is not shown in the title bar."""
        return

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

    def _is_interactive_child(self, child) -> bool:
        """True when press is on menu bar / buttons (including nested menu items)."""
        w = child
        while w is not None and w is not self:
            if isinstance(w, (QMenuBar, QToolButton, QPushButton)):
                return True
            w = w.parentWidget()
        return False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Don't start window-drag from File/Tools/Help or chrome buttons
            if self._is_interactive_child(self.childAt(event.pos())):
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
