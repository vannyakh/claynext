import random
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QPen, QBrush


class WaveVisualizerWidget(QWidget):
    """
    Custom audio waveform visualization widget painted using PySide6 QPainter.
    """
    def __init__(self, peaks=None):
        super().__init__()
        self.setFixedHeight(90)
        self.peaks = peaks or [random.uniform(0.1, 0.95) for _ in range(70)]

    def set_peaks(self, peaks):
        self.peaks = peaks
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        width = rect.width()
        height = rect.height()
        cy = height / 2.0

        # Draw dark background card
        painter.fillRect(rect, QColor(7, 10, 18))
        
        # Border
        painter.setPen(QPen(QColor(30, 41, 59), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)

        if not self.peaks:
            return

        bar_count = len(self.peaks)
        gap = 2.0
        bar_width = max(2.0, (width - 30.0 - (bar_count * gap)) / bar_count)

        gradient = QLinearGradient(0, 0, width, 0)
        gradient.setColorAt(0.0, QColor(99, 102, 241))   # Indigo
        gradient.setColorAt(0.5, QColor(168, 85, 247))   # Purple
        gradient.setColorAt(1.0, QColor(236, 72, 153))   # Pink

        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)

        x = 15.0
        for amp in self.peaks:
            bar_h = max(4.0, (height - 24.0) * amp)
            top = cy - (bar_h / 2.0)
            painter.drawRoundedRect(QRectF(x, top, bar_width, bar_h), 2, 2)
            x += bar_width + gap

        # Center timeline indicator line
        painter.setPen(QPen(QColor(52, 211, 153, 180), 2, Qt.PenStyle.DashLine))
        painter.drawLine(int(width / 2), 10, int(width / 2), height - 10)
