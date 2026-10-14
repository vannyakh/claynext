"""
Jela Studio Splash Screen.
Shown on application startup with animated progress bar and branding.
Auto-closes after loading and reveals the launcher window.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QPen, QFont, QFontDatabase

from jela.utils.config import APP_NAME, APP_VERSION
from jela.core.icons import image_pixmap


class SplashScreen(QWidget):
    """
    Frameless splash screen with animated gradient background,
    progress bar, and Jela branding. Emits finished() when done.
    """
    finished = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(500, 320)

        self._progress = 0
        self._phase_labels = [
            "Initializing core engine…",
            "Loading AI models…",
            "Preparing media tools…",
            "Starting Jela Studio…",
        ]
        self._phase_idx = 0

        self._center()
        self._build_ui()
        self._start_animation()

    def _center(self):
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            self.move(
                sg.center().x() - self.width() // 2,
                sg.center().y() - self.height() // 2,
            )

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 36, 40, 32)
        layout.setSpacing(0)

        layout.addStretch(1)

        # Centered 3D App Logo Box
        logo_lbl = QLabel()
        logo_lbl.setFixedSize(84, 84)
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        px = image_pixmap("splash_hero", 84)
        if px.isNull():
            px = image_pixmap("app", 84)
        if not px.isNull():
            logo_lbl.setPixmap(px)
        layout.addWidget(logo_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(16)

        # Centered App Title
        name_lbl = QLabel(APP_NAME)
        name_lbl.setObjectName("splash_title")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet(
            "color: #f0f6ff; font-size: 24px; font-weight: 800; "
            "letter-spacing: -0.5px; background: transparent;"
        )
        layout.addWidget(name_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addStretch(1)

        # Status label
        self.status_lbl = QLabel(self._phase_labels[0])
        self.status_lbl.setObjectName("splash_status")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setStyleSheet(
            "color: #64748b; font-size: 11px; font-weight: 500; background: transparent;"
        )
        layout.addWidget(self.status_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(8)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255,255,255,0.08);
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #38bdf8, stop:0.5 #818cf8, stop:1 #a855f7);
                border-radius: 2px;
            }
        """)
        layout.addWidget(self.progress_bar)

    def _start_animation(self):
        """Drive progress 0→100 over ~2.2 seconds then emit finished."""
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(22)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

    def _tick(self):
        self._progress += 1
        self.progress_bar.setValue(self._progress)

        # Update phase label at 25/50/75 marks
        phase_thresholds = [25, 55, 80]
        for i, threshold in enumerate(phase_thresholds):
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

        # Background card
        rect = self.rect().adjusted(1, 1, -1, -1)

        # Dark gradient background
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor("#0d1420"))
        grad.setColorAt(0.5, QColor("#0f1929"))
        grad.setColorAt(1.0, QColor("#0b1016"))
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 16, 16)

        # Subtle top accent glow
        glow_grad = QLinearGradient(0, 0, self.width(), 0)
        glow_grad.setColorAt(0.0, QColor(56, 189, 248, 0))
        glow_grad.setColorAt(0.3, QColor(56, 189, 248, 40))
        glow_grad.setColorAt(0.7, QColor(168, 85, 247, 40))
        glow_grad.setColorAt(1.0, QColor(168, 85, 247, 0))
        painter.setBrush(glow_grad)
        painter.drawRoundedRect(rect.adjusted(0, 0, 0, -rect.height() + 2), 16, 16)

        # Border
        pen = QPen(QColor(255, 255, 255, 18))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 16, 16)

        painter.end()
