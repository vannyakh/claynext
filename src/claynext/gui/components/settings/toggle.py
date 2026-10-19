"""Pill switch for a settings row."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QCheckBox, QLabel

from claynext.constants.theme_constants import COLOR_PRIMARY


class SettingsToggle(QCheckBox):
    """Compact on/off switch. Keeps the QCheckBox checked API."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settings_toggle")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(36, 20)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        track = QColor(COLOR_PRIMARY if on else "#162033")
        if self.underMouse() and not on:
            track = QColor("#1e2d40")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 9, 9)
        knob = 14
        margin = 3
        x = self.width() - margin - knob if on else margin
        y = (self.height() - knob) // 2
        painter.setBrush(QColor("#f4f7fb"))
        painter.drawEllipse(x, y, knob, knob)
        painter.end()


def bind_toggle_label(label: QLabel, toggle: SettingsToggle) -> None:
    """Clicking the row label flips the switch."""
    label.setCursor(Qt.CursorShape.PointingHandCursor)

    def _press(event, box=toggle, text=label):
        QLabel.mousePressEvent(text, event)
        if event.button() == Qt.MouseButton.LeftButton:
            box.toggle()

    label.mousePressEvent = _press
