"""Sequence list. A wide dock shows one row; a right dock shows a column."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QSize, Qt, Signal
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class SequenceBar(QFrame):
    """Dub sequences. Drag the Sequences title to dock this panel on the right."""

    picked = Signal(int)
    presence_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sequence_bar")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("sequence_scroll")
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.viewport().installEventFilter(self)

        self._host = QWidget()
        self._host.setObjectName("sequence_host")
        self._host.installEventFilter(self)
        self._row = QHBoxLayout(self._host)
        self._row.setContentsMargins(8, 4, 8, 4)
        self._row.setSpacing(6)
        self._scroll.setWidget(self._host)
        lay.addWidget(self._scroll)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self._on_picked)
        self._chips: list[QPushButton] = []
        self._names: list[str] = []
        self._index = -1
        self._vertical = False
        self._follow_size = False
        self._drag_pos = 0
        self._drag_scroll = 0
        self._sliding = False
        self._shown = False
        self._rebuilding = False
        self._fitting = False

    def set_follow_size(self, follow: bool) -> None:
        """While floating, the panel shape picks the row or the column."""
        self._follow_size = bool(follow)

    def set_vertical(self, vertical: bool) -> None:
        vertical = bool(vertical)
        if vertical == self._vertical:
            self._fit_host()
            return
        self._vertical = vertical
        self.setProperty("flow", "column" if vertical else "row")
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self._rebuild()

    def set_names(self, names: list[str], index: int = 0) -> None:
        self._names = [str(name or "") for name in names]
        self._index = index if 0 <= index < len(self._names) else -1
        self._rebuild()
        show = bool(self._names)
        if show != self._shown:
            self._shown = show
            self.presence_changed.emit(show)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._follow_size:
            self._fit_host()
            return
        vertical = self.height() > max(80, self.width())
        if vertical != self._vertical:
            self.set_vertical(vertical)
        else:
            self._fit_host()

    def sizeHint(self) -> QSize:
        if self._vertical:
            return QSize(220, max(96, 34 * max(1, len(self._chips)) + 12))
        return QSize(max(240, self._host.sizeHint().width()), 34)

    def minimumSizeHint(self) -> QSize:
        if self._vertical:
            return QSize(160, 72)
        return QSize(80, 34)

    def eventFilter(self, watched: QObject, event) -> bool:
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = int(event.globalPosition().y() if self._vertical else event.globalPosition().x())
            bar = self._bar()
            self._drag_scroll = bar.value()
            self._sliding = False
            return False
        if kind == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton:
            pos = int(event.globalPosition().y() if self._vertical else event.globalPosition().x())
            delta = pos - self._drag_pos
            if abs(delta) > 4:
                self._sliding = True
                self._bar().setValue(self._drag_scroll - delta)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return True
            return False
        if kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            self.unsetCursor()
            if self._sliding:
                self._sliding = False
                if isinstance(watched, QPushButton):
                    watched.setDown(False)
                return True
            return False
        if kind == QEvent.Type.Wheel and isinstance(event, QWheelEvent):
            step = event.pixelDelta().y() or event.pixelDelta().x() or event.angleDelta().y()
            if step:
                bar = self._bar()
                bar.setValue(bar.value() - step)
                return True
        return False

    def _bar(self):
        scroll = self._scroll
        if self._vertical:
            return scroll.verticalScrollBar()
        return scroll.horizontalScrollBar()

    def _rebuild(self) -> None:
        if self._rebuilding:
            return
        self._rebuilding = True
        try:
            self._rebuild_body()
        finally:
            self._rebuilding = False

    def _rebuild_body(self) -> None:
        for chip in self._chips:
            self._group.removeButton(chip)
            chip.deleteLater()
        self._chips.clear()
        old = self._host.layout()
        if old is not None:
            while old.count():
                item = old.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            QWidget().setLayout(old)
        if self._vertical:
            layout = QVBoxLayout(self._host)
            layout.setContentsMargins(8, 6, 8, 6)
            layout.setSpacing(4)
            self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._scroll.setWidgetResizable(True)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        else:
            layout = QHBoxLayout(self._host)
            layout.setContentsMargins(8, 4, 8, 4)
            layout.setSpacing(6)
            self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._scroll.setWidgetResizable(False)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.setFixedHeight(34)
        self._row = layout

        if not self._names:
            self._fit_host()
            return

        self._group.blockSignals(True)
        for i, name in enumerate(self._names):
            chip = QPushButton(name or f"Dub {i + 1}")
            chip.setObjectName("sequence_chip")
            chip.setCheckable(True)
            chip.setChecked(i == self._index)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip(chip.text())
            if self._vertical:
                chip.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            else:
                chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            chip.installEventFilter(self)
            self._group.addButton(chip, i)
            layout.addWidget(chip)
            self._chips.append(chip)
        if not self._vertical:
            layout.addStretch(1)
        if self._index < 0:
            self._group.setExclusive(False)
            for chip in self._chips:
                chip.setChecked(False)
            self._group.setExclusive(True)
        self._group.blockSignals(False)
        self._fit_host()
        self._reveal(self._index)
        self.updateGeometry()

    def _fit_host(self) -> None:
        if self._fitting:
            return
        self._fitting = True
        try:
            self._fit_body()
        finally:
            self._fitting = False

    def _fit_body(self) -> None:
        if self._vertical:
            self.setMinimumHeight(72)
            self.setMaximumHeight(16777215)
            return
        self.setFixedHeight(34)
        self.setMinimumHeight(34)
        self.setMaximumHeight(34)
        self._host.setFixedSize(max(self._host.sizeHint().width(), 1), 34)

    def _on_picked(self, index: int) -> None:
        if index >= 0:
            self._index = index
            self.picked.emit(index)

    def _reveal(self, index: int) -> None:
        if not (0 <= index < len(self._chips)):
            return
        chip = self._chips[index]
        if self._vertical:
            bar = self._scroll.verticalScrollBar()
            top = chip.y()
            bottom = top + chip.height()
            view = self._scroll.viewport().height()
            if top < bar.value():
                bar.setValue(top)
            elif bottom > bar.value() + view:
                bar.setValue(bottom - view)
            return
        bar = self._scroll.horizontalScrollBar()
        left = chip.x()
        right = left + chip.width()
        view = self._scroll.viewport().width()
        if left < bar.value():
            bar.setValue(left)
        elif right > bar.value() + view:
            bar.setValue(right - view)
