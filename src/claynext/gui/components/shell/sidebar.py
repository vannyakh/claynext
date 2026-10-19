from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QButtonGroup
from PySide6.QtCore import Signal, Qt, QSize
from claynext.constants import NAV_ITEMS, SIDEBAR_MIN_WIDTH, SIDEBAR_MAX_WIDTH
from claynext.gui.icons import icon
from claynext.constants.theme_constants import COLOR_PRIMARY


class SidebarWidget(QWidget):
    """
    Sidebar Navigation with SVG icons and text labels.
    Emits nav_changed(int index) when user selects a menu item,
    and launcher_requested() when user wants to return to the launcher window.
    """
    nav_changed = Signal(int)
    launcher_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("sidebar")
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(2)

        # Back to Launcher Hub Button
        self.btn_launcher = QPushButton("  ← Launcher")
        self.btn_launcher.setObjectName("btn_back_launcher")
        self.btn_launcher.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_launcher.setIcon(icon("folder", color="#94a3b8", size=14))
        self.btn_launcher.setToolTip("Back to Startup & Launcher Hub (Ctrl+0 / ⌘0)")
        self.btn_launcher.clicked.connect(self.launcher_requested.emit)
        layout.addWidget(self.btn_launcher)

        layout.addSpacing(10)

        # Section Label
        section_lbl = QLabel("STUDIO TABS")
        section_lbl.setStyleSheet(
            "color: #4b5563; font-size: 10px; font-weight: 800; "
            "padding: 4px 10px 6px 10px; letter-spacing: 1px;"
        )
        layout.addWidget(section_lbl)

        # Navigation Buttons with SVG Icons
        for item in NAV_ITEMS:
            btn = QPushButton(f"  {item['label']}")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIconSize(QSize(16, 16))

            icon_name = item.get("icon", "")
            if icon_name:
                btn.setIcon(icon(icon_name, color="#9fb0c3", size=16))

            if item["index"] == 0:
                btn.setChecked(True)
                if icon_name:
                    btn.setIcon(icon(icon_name, color=COLOR_PRIMARY, size=16))

            self.button_group.addButton(btn, item["index"])
            layout.addWidget(btn)

        self.button_group.idClicked.connect(self.on_btn_clicked)
        layout.addStretch()

    def on_btn_clicked(self, index: int):
        self.nav_changed.emit(index)

        # Update icon colors: active gets accent, others get muted
        for item in NAV_ITEMS:
            btn = self.button_group.button(item["index"])
            icon_name = item.get("icon", "")
            if icon_name and btn:
                if item["index"] == index:
                    btn.setIcon(icon(icon_name, color=COLOR_PRIMARY, size=16))
                else:
                    btn.setIcon(icon(icon_name, color="#9fb0c3", size=16))

