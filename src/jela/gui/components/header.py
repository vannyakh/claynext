from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal
from jela.constants import NAV_ITEMS
from jela.core.icons import icon


class HeaderWidget(QWidget):
    """
    Tool workspace header — back navigation, tool identity, badge, and settings.
    Designed as a single clear toolbar: navigate left, identify center-left, actions right.
    """
    launcher_requested = Signal()
    settings_requested = Signal()

    def __init__(self, tool_index: int = 0, show_back: bool = True, show_settings: bool = True):
        super().__init__()
        self.setObjectName("header_bar")
        self._tool_index = tool_index
        self._show_back = show_back
        self._show_settings = show_settings
        self.init_ui()
        self.set_page(tool_index)

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(12)

        if self._show_back:
            self.btn_back = QPushButton("Launcher")
            self.btn_back.setObjectName("header_back_btn")
            self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_back.setIcon(icon("folder", color="#cbd5e1", size=14))
            self.btn_back.setToolTip("Back to Launcher Hub (Ctrl+0 / ⌘0)")
            self.btn_back.clicked.connect(self.launcher_requested.emit)
            layout.addWidget(self.btn_back)

            divider = QLabel()
            divider.setObjectName("header_divider")
            divider.setFixedWidth(1)
            divider.setFixedHeight(28)
            layout.addWidget(divider)
        else:
            self.btn_back = None

        self.icon_box = QLabel()
        self.icon_box.setObjectName("header_tool_icon")
        self.icon_box.setFixedSize(34, 34)
        self.icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_box)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title_box.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel()
        self.title_lbl.setObjectName("page_title")

        self.desc_lbl = QLabel()
        self.desc_lbl.setObjectName("page_desc")
        self.desc_lbl.setWordWrap(False)

        title_box.addWidget(self.title_lbl)
        title_box.addWidget(self.desc_lbl)
        layout.addLayout(title_box, 1)

        layout.addStretch(0)

        self.badge_lbl = QLabel()
        self.badge_lbl.setObjectName("page_badge")
        layout.addWidget(self.badge_lbl)

        if self._show_settings:
            self.btn_settings = QPushButton()
            self.btn_settings.setObjectName("header_settings_btn")
            self.btn_settings.setIcon(icon("settings", color="#94a3b8", size=14))
            self.btn_settings.setFixedSize(34, 34)
            self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_settings.setToolTip("Settings & Hardware Models (Ctrl+, / ⌘,)")
            self.btn_settings.clicked.connect(self.settings_requested.emit)
            layout.addWidget(self.btn_settings)
        else:
            self.btn_settings = None

    def set_page(self, index: int):
        if not (0 <= index < len(NAV_ITEMS)):
            return

        item = NAV_ITEMS[index]
        self._tool_index = index
        accent = item.get("color", "#6366f1")

        self.title_lbl.setText(item["label"])
        self.desc_lbl.setText(item.get("desc", ""))

        icon_name = item.get("icon", "")
        if icon_name:
            self.icon_box.setPixmap(icon(icon_name, color=accent, size=16).pixmap(16, 16))

        self.icon_box.setStyleSheet(f"""
            QLabel#header_tool_icon {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {accent}28, stop:1 {accent}10);
                border: 1px solid {accent}55;
                border-radius: 8px;
            }}
        """)

        self.badge_lbl.setText(item.get("badge", "AI Engine"))
        self.badge_lbl.setStyleSheet(f"""
            QLabel#page_badge {{
                background-color: {accent}18;
                color: {accent};
                border: 1px solid {accent}44;
                border-radius: 999px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.3px;
            }}
        """)
