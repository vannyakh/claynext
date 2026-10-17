"""CapCut-style timeline hover / context scrub tip (name · time)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from claynext.gui.components.timeline.helpers import fmt_ms
from claynext.gui.icons import icon


class TimelineScrubTip(QFrame):
    """
    Compact floating card: thumb + truncated title, time below.
    Hover scrub preview and context-menu anchor.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(
            parent,
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setObjectName("timeline_scrub_tip")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(108)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(3)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.setContentsMargins(0, 0, 0, 0)

        self.thumb = QLabel()
        self.thumb.setObjectName("timeline_scrub_tip_thumb")
        self.thumb.setFixedSize(18, 18)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.thumb)

        self.title = QLabel("—")
        self.title.setObjectName("timeline_scrub_tip_title")
        self.title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        row.addWidget(self.title, 1)
        root.addLayout(row)

        self.time = QLabel("00:00")
        self.time.setObjectName("timeline_scrub_tip_time")
        self.time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.time)

        self.hide()

    def set_content(
        self,
        *,
        name: str,
        ms: int,
        icon_name: str = "video",
        accent: str = "#94a3b8",
        thumb: QPixmap | None = None,
    ):
        text = (name or "Clip").strip()
        if len(text) > 10:
            text = text[:9] + "…"
        self.title.setText(text)
        self.title.setToolTip(name or "")
        self.time.setText(fmt_ms(ms))
        if thumb is not None and not thumb.isNull():
            self.thumb.setPixmap(
                thumb.scaled(
                    18,
                    18,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.thumb.setPixmap(icon(icon_name, color=accent, size=14).pixmap(14, 14))

    def show_at(self, global_anchor: QPoint):
        """Place tip centered above the anchor point (cursor / scrub x)."""
        self.adjustSize()
        tip_w = max(self.width(), 108)
        tip_h = self.sizeHint().height()
        self.resize(tip_w, tip_h)
        pos = QPoint(global_anchor.x() - tip_w // 2, global_anchor.y() - tip_h - 8)
        self.move(pos)
        self.show()
        self.raise_()
