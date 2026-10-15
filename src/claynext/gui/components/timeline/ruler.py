"""Time ruler above the timeline sequence."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QWidget

from claynext.constants.timeline_constants import BG_TOOLS, PLAYHEAD, RULER_H
from claynext.gui.components.timeline.helpers import fmt_ms

if TYPE_CHECKING:
    from claynext.gui.components.timeline.canvas import TimelineCanvas


class TimelineRuler(QWidget):
    seek_requested = Signal(int)

    def __init__(self, canvas: TimelineCanvas, parent=None):
        super().__init__(parent)
        self.setObjectName("timeline_ruler")
        self.setFixedHeight(RULER_H)
        self.canvas = canvas
        self._offset = 0
        self._scrub = False
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    def set_offset(self, x: int):
        self._offset = max(0, int(x))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(BG_TOOLS))
        p.setPen(QColor("#3a3a3a"))
        p.drawLine(0, RULER_H - 1, self.width(), RULER_H - 1)
        c = self.canvas
        dur_s = max(c.duration_ms / 1000.0, (self.width() + self._offset) / max(c.pps, 1))
        step = 1
        if c.pps < 18:
            step = 30
        elif c.pps < 28:
            step = 10
        elif c.pps < 48:
            step = 5
        elif c.pps < 80:
            step = 2
        font = QFont()
        font.setPixelSize(10)
        p.setFont(font)
        t = 0.0
        while t <= dur_s + 0.05:
            x = int(t * c.pps) - self._offset
            nearest = int(round(t))
            major = nearest % (step * 3 if step < 10 else step) == 0
            p.setPen(QColor("#6b6b6b") if major else QColor("#3f3f3f"))
            p.drawLine(x, RULER_H - (11 if major else 5), x, RULER_H)
            if major and x > -48:
                p.setPen(QColor("#a3a3a3"))
                p.drawText(x + 4, 12, fmt_ms(int(t * 1000)))
            t += step
        hx = int(c.playhead_ms / 1000.0 * c.pps) - self._offset
        p.setPen(QPen(QColor(PLAYHEAD), 1))
        p.drawLine(hx, 0, hx, RULER_H)
        p.setBrush(QColor(PLAYHEAD))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon([QPoint(hx - 4, 0), QPoint(hx + 4, 0), QPoint(hx, 8)])
        p.end()

    def _seek_at(self, x: float):
        ms = max(0, int((x + self._offset) / max(self.canvas.pps, 1) * 1000))
        if self.canvas.duration_ms:
            ms = min(ms, self.canvas.duration_ms)
        self.canvas.set_playhead_ms(ms)
        self.seek_requested.emit(ms)
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._scrub = True
        self._seek_at(event.position().x())

    def mouseMoveEvent(self, event):
        if self._scrub:
            self._seek_at(event.position().x())

    def mouseReleaseEvent(self, event):
        self._scrub = False

