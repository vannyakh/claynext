"""Widgets for the New Project dialog."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from claynext.constants.project_constants import (
    ASPECT_RATIOS,
    NEW_PROJECT_FIELD_H,
    ProjectTemplate,
)
from claynext.constants.theme_constants import (
    COLOR_BG_DARK,
    COLOR_BORDER,
    primary_color,
)


def labeled_field(label: str, widget: QWidget) -> QWidget:
    wrap = QWidget()
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(3)
    lbl = QLabel(label)
    lbl.setObjectName("new_project_field_lbl")
    lay.addWidget(lbl)
    lay.addWidget(widget)
    return wrap


class TemplateCard(QToolButton):
    """Flat chip: aspect ratio only, so the row never truncates."""

    def __init__(self, template: ProjectTemplate, parent=None):
        super().__init__(parent)
        self.template = template
        self.setObjectName("new_project_template")
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setText(template.label)
        self.setToolTip(template.hint)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(NEW_PROJECT_FIELD_H)


class CanvasPreviewWidget(QWidget):
    """Aspect-ratio frame only — labels live outside so nothing overlaps."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._aspect = "16:9"
        self.setMinimumHeight(88)
        self.setMaximumHeight(96)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def update_canvas(self, aspect: str):
        self._aspect = aspect
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QColor(COLOR_BG_DARK))
        painter.setPen(QPen(QColor(COLOR_BORDER), 1))
        painter.drawRoundedRect(rect, 8, 8)

        grid = QPen(QColor(255, 255, 255, 10), 1, Qt.PenStyle.DotLine)
        painter.setPen(grid)
        for x in range(rect.left() + 16, rect.right(), 16):
            painter.drawLine(x, rect.top() + 6, x, rect.bottom() - 6)
        for y in range(rect.top() + 16, rect.bottom(), 16):
            painter.drawLine(rect.left() + 6, y, rect.right() - 6, y)

        ratio = ASPECT_RATIOS.get(self._aspect, 16 / 9)
        avail_w = max(10.0, float(rect.width()) - 40)
        avail_h = max(10.0, float(rect.height()) - 28)
        if avail_w / avail_h > ratio:
            h = avail_h
            w = h * ratio
        else:
            w = avail_w
            h = w / ratio

        cx = rect.center().x()
        cy = rect.center().y()
        frame = QRectF(cx - w / 2, cy - h / 2, w, h)

        accent = QColor(primary_color())
        grad = QLinearGradient(frame.topLeft(), frame.bottomRight())
        grad.setColorAt(0.0, QColor(24, 34, 52, 220))
        grad.setColorAt(1.0, QColor(12, 18, 28, 240))
        painter.setBrush(grad)
        painter.setPen(QPen(accent, 1.5))
        painter.drawRoundedRect(frame, 3, 3)

        painter.setPen(QPen(accent, 1))
        painter.drawLine(QPointF(cx - 4, cy), QPointF(cx + 4, cy))
        painter.drawLine(QPointF(cx, cy - 4), QPointF(cx, cy + 4))
