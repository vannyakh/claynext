"""
Claynext Studio Splash Screen (legacy entry).
Bordeered progress track matches the app export / QProgressBar style.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

from claynext.constants.theme_constants import (
    COLOR_BG_CARD,
    COLOR_BG_DARK,
    COLOR_BG_INPUT,
    COLOR_BORDER,
    COLOR_PRIMARY,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
)
from claynext.gui.icons import image_pixmap


class SplashScreen(QWidget):
    """Frameless splash with branded progress; emits finished() when done."""

    finished = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(420, 260)
        self.setObjectName("splashScreen")

        self._progress = 0
        self._phase_labels = [
            "Initializing…",
            "Loading media engines…",
            "Preparing workspace…",
            "Ready",
        ]
        self._phase_idx = 0
        self._logo_size = 120

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

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(0)
        layout.addStretch(1)

        size = self._logo_size
        logo_lbl = QLabel()
        logo_lbl.setFixedSize(size, size)
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_lbl.setScaledContents(False)
        px = image_pixmap("splash_hero", size)
        if px.isNull():
            px = image_pixmap("app", size)
        if not px.isNull():
            logo_lbl.setPixmap(
                px.scaled(
                    size,
                    size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        layout.addWidget(logo_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addStretch(1)

        self.status_lbl = QLabel(self._phase_labels[0])
        self.status_lbl.setObjectName("splash_status")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: 11px; font-weight: 500; background: transparent;"
        )
        layout.addWidget(self.status_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("splash_progress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setStyleSheet(f"""
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
                background-color: {COLOR_PRIMARY};
                border-radius: 3px;
                margin: 1px;
            }}
        """)
        layout.addWidget(self.progress_bar)

    def _start_animation(self):
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(22)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

    def _tick(self):
        self._progress += 1
        self.progress_bar.setValue(self._progress)

        for i, threshold in enumerate((25, 55, 80)):
            if self._progress == threshold and i + 1 < len(self._phase_labels):
                self._phase_idx = i + 1
                self.status_lbl.setText(self._phase_labels[self._phase_idx])

        if self._progress >= 100:
            self._tick_timer.stop()
            QTimer.singleShot(250, self.finished.emit)
            QTimer.singleShot(450, self.close)

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

        glow = QLinearGradient(0, 0, self.width(), 0)
        c0 = QColor(COLOR_PRIMARY)
        c0.setAlpha(0)
        c1 = QColor(COLOR_PRIMARY)
        c1.setAlpha(36)
        c2 = QColor(COLOR_ACCENT_PURPLE)
        c2.setAlpha(36)
        c3 = QColor(COLOR_ACCENT_PURPLE)
        c3.setAlpha(0)
        glow.setColorAt(0.0, c0)
        glow.setColorAt(0.35, c1)
        glow.setColorAt(0.65, c2)
        glow.setColorAt(1.0, c3)
        painter.setBrush(glow)
        painter.drawRoundedRect(rect.adjusted(0, 0, 0, -rect.height() + 2), 12, 12)

        pen = QPen(QColor(COLOR_BORDER))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 12, 12)
        painter.end()
