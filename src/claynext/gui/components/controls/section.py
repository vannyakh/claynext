"""Click-to-expand property sections with a short height animation."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from claynext.gui.icons import icon


class CollapsibleSection(QWidget):
    """Header click toggles the body; optional feature checkbox is independent."""

    toggled = Signal(bool)

    def __init__(
        self,
        title: str,
        *,
        open: bool = True,
        divider: bool = False,
        feature: bool = False,
        collapsible: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("dub_config_section")
        self._collapsible = bool(collapsible)
        self._open = True if not self._collapsible else bool(open)
        self._anim: QPropertyAnimation | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 0)
        root.setSpacing(0)

        if divider:
            line = QFrame()
            line.setObjectName("dub_config_divider")
            line.setFixedHeight(1)
            root.addWidget(line)

        self._head = QWidget()
        self._head.setObjectName("dub_config_head")
        self._head.setCursor(
            Qt.CursorShape.PointingHandCursor if self._collapsible else Qt.CursorShape.ArrowCursor
        )
        self._head.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        head_l = QHBoxLayout(self._head)
        head_l.setContentsMargins(2, 6, 2, 6)
        head_l.setSpacing(6)

        self._chevron = QToolButton()
        self._chevron.setObjectName("dub_config_chevron_btn")
        self._chevron.setAutoRaise(True)
        self._chevron.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._chevron.setFixedSize(16, 16)
        self._chevron.setIconSize(QSize(10, 10))
        if self._collapsible:
            self._chevron.setCursor(Qt.CursorShape.PointingHandCursor)
            self._chevron.clicked.connect(self.toggle)
            self._paint_chevron()
            head_l.addWidget(self._chevron)
        else:
            self._chevron.hide()

        self._title = QLabel(title.upper())
        self._title.setObjectName("dub_config_header")
        head_l.addWidget(self._title, 1)

        self.feature_check: QCheckBox | None = None
        if feature:
            self.feature_check = QCheckBox()
            self.feature_check.setObjectName("dub_switch")
            self.feature_check.setCursor(Qt.CursorShape.PointingHandCursor)
            self.feature_check.setToolTip(f"Enable {title.lower()}")
            head_l.addWidget(self.feature_check)

        if self._collapsible:
            self._head.mousePressEvent = self._on_head_press  # type: ignore[method-assign]
        root.addWidget(self._head)

        self._body = QWidget()
        self._body.setObjectName("dub_config_body")
        self._body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.body_layout = QVBoxLayout(self._body)
        self.body_layout.setContentsMargins(2, 0, 6, 12)
        self.body_layout.setSpacing(8)
        root.addWidget(self._body)

        if self._open:
            self._body.setMaximumHeight(16777215)
            self._body.setVisible(True)
        else:
            self._body.setMaximumHeight(0)
            self._body.setVisible(False)

    def _paint_chevron(self):
        name = "chevron-down" if self._open else "chevron-right"
        self._chevron.setIcon(icon(name, color="#9fb0c3", size=10))
        self._chevron.setToolTip("Collapse" if self._open else "Expand")

    def set_title(self, title: str):
        self._title.setText(str(title).upper())

    def setText(self, title: str):
        self.set_title(title)

    def is_expanded(self) -> bool:
        return self._open

    def set_expanded(self, open: bool, *, animate: bool = True):
        if not self._collapsible:
            return
        open = bool(open)
        if open == self._open and (self._anim is None or self._anim.state() == QPropertyAnimation.State.Stopped):
            return
        self._open = open
        self._paint_chevron()
        self.toggled.emit(open)

        if self._anim is not None:
            self._anim.stop()

        if not animate:
            if open:
                self._body.setVisible(True)
                self._body.setMaximumHeight(16777215)
            else:
                self._body.setMaximumHeight(0)
                self._body.setVisible(False)
            return

        if open:
            self._body.setVisible(True)
            self._body.setMaximumHeight(0)
            hint = max(1, self._body.sizeHint().height())
            start, end = 0, hint
        else:
            start = max(0, self._body.height())
            end = 0
            if start <= 0:
                start = max(1, self._body.sizeHint().height())

        anim = QPropertyAnimation(self._body, b"maximumHeight", self)
        anim.setDuration(160)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(self._on_anim_finished)
        self._anim = anim
        anim.start()

    def toggle(self):
        if not self._collapsible:
            return
        self.set_expanded(not self._open)

    def _on_head_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Chevron button handles its own click
            if self._chevron.geometry().contains(event.position().toPoint()):
                return
            self.toggle()
            event.accept()
            return
        QWidget.mousePressEvent(self._head, event)

    def _on_anim_finished(self):
        if self._open:
            self._body.setMaximumHeight(16777215)
        else:
            self._body.setVisible(False)
            self._body.setMaximumHeight(0)

