"""Left project-actions rail for Project Home."""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from claynext.constants.theme_constants import COLOR_TEXT_SUB
from claynext.gui.icons import icon, image_pixmap
from claynext.utils.config import APP_NAME, APP_VERSION


class HomeRail(QFrame):
    """Brand + New / Open project actions."""

    new_requested = Signal()
    open_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("home_rail")
        self.setFixedWidth(248)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 24, 20, 20)
        lay.setSpacing(10)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        logo = QLabel()
        logo.setFixedSize(36, 36)
        px = image_pixmap("splash_hero", 36)
        if px.isNull():
            px = image_pixmap("app", 36)
        if not px.isNull():
            logo.setPixmap(px)
        brand_row.addWidget(logo)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(1)
        brand = QLabel(APP_NAME)
        brand.setObjectName("home_brand")
        brand_col.addWidget(brand)
        ver = QLabel(f"v{APP_VERSION}")
        ver.setObjectName("home_hint")
        brand_col.addWidget(ver)
        brand_row.addLayout(brand_col, 1)
        lay.addLayout(brand_row)
        lay.addSpacing(14)

        kicker = QLabel("PROJECT")
        kicker.setObjectName("home_kicker")
        lay.addWidget(kicker)

        self.btn_new = QPushButton("  New Project")
        self.btn_new.setObjectName("home_primary")
        self.btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.setIcon(icon("plus", color="#ffffff", size=15))
        self.btn_new.setIconSize(QSize(15, 15))
        self.btn_new.setFixedHeight(42)
        self.btn_new.clicked.connect(self.new_requested.emit)
        lay.addWidget(self.btn_new)

        self.btn_open = QPushButton("  Open Project…")
        self.btn_open.setObjectName("home_action")
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.setIcon(icon("folder", color=COLOR_TEXT_SUB, size=15))
        self.btn_open.setIconSize(QSize(15, 15))
        self.btn_open.setFixedHeight(42)
        self.btn_open.clicked.connect(self.open_requested.emit)
        lay.addWidget(self.btn_open)

        lay.addStretch(1)

        tip = QLabel("Projects save as .claynext.json\nin the projects folder.")
        tip.setObjectName("home_hint")
        tip.setWordWrap(True)
        lay.addWidget(tip)

