"""
Claynext Studio startup loader.
Frameless splash with bordered progress track matching the app export / QProgressBar style.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

from claynext.constants.theme_constants import (
    COLOR_BG_CARD,
    COLOR_BG_DARK,
    COLOR_BG_INPUT,
    COLOR_BORDER,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_SUB,
)
from claynext.gui.icons import icon, image_pixmap
from claynext.utils.config import APP_NAME


def _hex_to_color(hex_str: str, default: str = "#6366f1") -> QColor:
    try:
        return QColor(hex_str)
    except Exception:
        return QColor(default)


class ToolLoaderScreen(QWidget):
    """Frameless loader shown at startup, then opens Studio."""

    finished = Signal()

    def __init__(
        self,
        tool_data: dict,
        parent: Optional[QWidget] = None,
        on_complete: Optional[Callable] = None,
    ):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(460, 280)
        self.setObjectName("toolLoaderScreen")

        self.tool_data = tool_data or {}
        self.on_complete = on_complete
        self._accent = self.tool_data.get("color", "#a855f7")
        self._accent_color = _hex_to_color(self._accent)

        self._progress = 0
        label = self.tool_data.get("label") or APP_NAME
        self._phase_labels = [
            f"Initializing {label}…",
            "Loading media engines…",
            "Preparing workspace…",
            "Ready",
        ]
        self._phase_idx = 0

        self._center()
        self._build_ui()
        self._start_animation()

    def _center(self):
        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            self.move(
                sg.center().x() - self.width() // 2,
                sg.center().y() - self.height() // 2,
            )

    def _progress_qss(self) -> str:
        """Match global export / widgets QProgressBar: bordered track + accent fill."""
        r, g, b, _ = self._accent_color.getRgb()
        return f"""
            QProgressBar {{
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                background-color: {COLOR_BG_INPUT};
                text-align: center;
                color: {COLOR_TEXT_MAIN};
                font-weight: 600;
                font-size: 10px;
            }}
            QProgressBar::chunk {{
                background-color: rgb({r}, {g}, {b});
                border-radius: 3px;
                margin: 1px;
            }}
        """

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 24)
        layout.setSpacing(0)
        layout.addStretch(1)

        logo_lbl = QLabel()
        logo_lbl.setFixedSize(64, 64)
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_img_name = self.tool_data.get("logo_img", "")
        pix = image_pixmap(logo_img_name, 64) if logo_img_name else QPixmap()
        if pix.isNull():
            pix = image_pixmap("splash_hero", 64)
        if pix.isNull():
            pix = image_pixmap("app", 64)
        if not pix.isNull():
            logo_lbl.setPixmap(pix)
        else:
            icon_name = self.tool_data.get("icon", "volume")
            logo_lbl.setPixmap(icon(icon_name, color=self._accent, size=40).pixmap(40, 40))
        layout.addWidget(logo_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(12)

        title_lbl = QLabel(self.tool_data.get("label") or APP_NAME)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MAIN}; font-size: 18px; font-weight: 800; "
            "letter-spacing: -0.3px; background: transparent;"
        )
        layout.addWidget(title_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        badge = str(self.tool_data.get("badge") or "").strip()
        if badge:
            layout.addSpacing(4)
            badge_lbl = QLabel(badge)
            badge_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge_lbl.setStyleSheet(
                f"color: {self._accent}; font-size: 11px; font-weight: 600; background: transparent;"
            )
            layout.addWidget(badge_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addStretch(1)

        self.status_lbl = QLabel(self._phase_labels[0])
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: 11px; font-weight: 500; background: transparent;"
        )
        layout.addWidget(self.status_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("tool_loader_progress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setStyleSheet(self._progress_qss())
        layout.addWidget(self.progress_bar)

        layout.addSpacing(8)
        foot = QLabel(APP_NAME)
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        foot.setStyleSheet(
            f"color: {COLOR_TEXT_SUB}; font-size: 10px; font-weight: 600; background: transparent;"
        )
        layout.addWidget(foot, 0, Qt.AlignmentFlag.AlignCenter)

    def _start_animation(self):
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        self._progress = min(100, self._progress + 3)
        self.progress_bar.setValue(self._progress)

        if self._progress > 70 and self._phase_idx < 2:
            self._phase_idx = 2
            self.status_lbl.setText(self._phase_labels[2])
        elif self._progress > 30 and self._phase_idx < 1:
            self._phase_idx = 1
            self.status_lbl.setText(self._phase_labels[1])

        if self._progress >= 100:
            self._timer.stop()
            self.status_lbl.setText(self._phase_labels[3])
            if self.on_complete:
                QTimer.singleShot(100, self.on_complete)
            QTimer.singleShot(150, self.finished.emit)
            QTimer.singleShot(250, self.close)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)

        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor(COLOR_BG_CARD))
        grad.setColorAt(1.0, QColor(COLOR_BG_DARK))
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 12, 12)

        r, g, b, _ = self._accent_color.getRgb()
        glow = QLinearGradient(0, 0, self.width(), 0)
        glow.setColorAt(0.0, QColor(r, g, b, 0))
        glow.setColorAt(0.5, QColor(r, g, b, 36))
        glow.setColorAt(1.0, QColor(r, g, b, 0))
        painter.setBrush(glow)
        painter.drawRoundedRect(rect.adjusted(0, 0, 0, -rect.height() + 2), 12, 12)

        # Export-style card border (theme border, not soft white)
        pen = QPen(QColor(COLOR_BORDER))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 12, 12)
        painter.end()
