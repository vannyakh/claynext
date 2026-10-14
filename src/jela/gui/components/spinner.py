from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QConicalGradient, QBrush


class Spinner(QWidget):
    """Compact indeterminate loader — no progress bar."""

    def __init__(self, parent=None, size: int = 16, color: str = "#818cf8"):
        super().__init__(parent)
        self.setObjectName("ui_spinner")
        self._angle = 0
        self._color = QColor(color)
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def start(self):
        if not self._timer.isActive():
            self._timer.start(16)
        self.show()

    def stop(self):
        self._timer.stop()
        self.hide()

    def is_spinning(self) -> bool:
        return self._timer.isActive()

    def _tick(self):
        self._angle = (self._angle + 12) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        pad = 1.5
        rect = QRectF(pad, pad, side - pad * 2, side - pad * 2)
        grad = QConicalGradient(rect.center(), -self._angle)
        c = self._color
        grad.setColorAt(0.0, c)
        grad.setColorAt(0.7, QColor(c.red(), c.green(), c.blue(), 0))
        pen = QPen()
        pen.setWidthF(2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setBrush(QBrush(grad))
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)
        painter.end()
