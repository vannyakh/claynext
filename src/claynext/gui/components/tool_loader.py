"""
Claynext Studio Tool Loader Screen.
Shown at startup (and when opening the studio) with smooth progress animation
and tool branding.
"""
from typing import Callable, Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QApplication
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QPen, QPixmap

from claynext.utils.config import APP_NAME
from claynext.gui.icons import image_pixmap, icon


def _hex_to_color(hex_str: str, default: str = "#38bdf8") -> QColor:
    try:
        return QColor(hex_str)
    except Exception:
        return QColor(default)


class ToolLoaderScreen(QWidget):
    """
    Frameless, elegant loading dialog displayed when launching any Claynext tool.
    Drives a smooth progress bar using the tool's signature color scheme,
    then executes the completion callback to reveal the tool window.
    """
    finished = Signal()

    def __init__(self, tool_data: dict, parent: Optional[QWidget] = None, on_complete: Optional[Callable] = None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(480, 300)

        self.tool_data = tool_data
        self.on_complete = on_complete
        self._accent = tool_data.get("color", "#38bdf8")
        self._accent_color = _hex_to_color(self._accent)

        self._progress = 0
        self._phase_labels = [
            f"Initializing {tool_data.get('label', 'Tool')} engine…",
            "Loading AI models & media processors…",
            "Preparing studio workspace…",
            "Ready!",
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

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 32, 40, 28)
        layout.setSpacing(0)

        layout.addStretch(1)

        # Centered 3D Tool Icon Box
        logo_lbl = QLabel()
        logo_lbl.setFixedSize(72, 72)
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo_img_name = self.tool_data.get("logo_img", "")
        pix = image_pixmap(logo_img_name, 72) if logo_img_name else QPixmap()

        if not pix.isNull():
            logo_lbl.setPixmap(pix)
        else:
            icon_name = self.tool_data.get("icon", "")
            if icon_name:
                logo_lbl.setPixmap(icon(icon_name, color=self._accent, size=48).pixmap(48, 48))

        layout.addWidget(logo_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(14)

        # Tool Title
        title_lbl = QLabel(self.tool_data.get("label", "Claynext Tool"))
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            "color: #f0f6ff; font-size: 20px; font-weight: 800; "
            "letter-spacing: -0.4px; background: transparent;"
        )
        layout.addWidget(title_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        # Badge subtitle
        badge_text = self.tool_data.get("badge", "")
        if badge_text:
            layout.addSpacing(4)
            badge_lbl = QLabel(badge_text)
            badge_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge_lbl.setStyleSheet(
                f"color: {self._accent}; font-size: 11px; font-weight: 600; background: transparent;"
            )
            layout.addWidget(badge_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addStretch(1)

        # Status Label
        self.status_lbl = QLabel(self._phase_labels[0])
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setStyleSheet(
            "color: #64748b; font-size: 11px; font-weight: 500; background: transparent;"
        )
        layout.addWidget(self.status_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(8)

        # Progress bar with dynamic tool accent styling
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)

        r, g, b, _ = self._accent_color.getRgb()
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba(255,255,255,0.08);
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba({r},{g},{b},0.7), stop:1 rgba({r},{g},{b},1.0));
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self.progress_bar)

    def _start_animation(self):
        """Smooth ~550ms loader progress sequence."""
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        self._progress += 3
        if self._progress > 100:
            self._progress = 100

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

        # Dark gradient background
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor("#0d1420"))
        grad.setColorAt(0.5, QColor("#0f1929"))
        grad.setColorAt(1.0, QColor("#0b1016"))
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 16, 16)

        # Top subtle accent glow matching tool color
        r, g, b, _ = self._accent_color.getRgb()
        glow_grad = QLinearGradient(0, 0, self.width(), 0)
        glow_grad.setColorAt(0.0, QColor(r, g, b, 0))
        glow_grad.setColorAt(0.5, QColor(r, g, b, 45))
        glow_grad.setColorAt(1.0, QColor(r, g, b, 0))
        painter.setBrush(glow_grad)
        painter.drawRoundedRect(rect.adjusted(0, 0, 0, -rect.height() + 2), 16, 16)

        # Card border
        pen = QPen(QColor(255, 255, 255, 20))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 16, 16)

        painter.end()

