"""Sequence list. A wide dock shows one row; a right dock shows a column."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from claynext.gui.icons import icon

# Room for a 26px chip plus padding, so the row never crops the button.
SEQUENCE_ROW_H = 42
_CHIP_ROW_H = 26


class SequenceBar(QFrame):
    """Dub sequences. Drag the Sequences title to dock this panel on the right."""

    picked = Signal(int)
    presence_changed = Signal(bool)
    reordered = Signal(int, int)
    rename_requested = Signal(int)
    delete_requested = Signal(int)
    export_requested = Signal(int)
    add_requested = Signal()

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
        self._scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay.addWidget(self._scroll, 1)

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
        self._press_index = -1
        self._reorder_to = -1
        self._reordering = False
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
            return QSize(220, max(self.height(), 34 * max(1, len(self._chips)) + 12))
        return QSize(max(240, self._host.sizeHint().width()), SEQUENCE_ROW_H)

    def minimumSizeHint(self) -> QSize:
        if self._vertical:
            return QSize(160, 72)
        return QSize(80, SEQUENCE_ROW_H)

    def eventFilter(self, watched: QObject, event) -> bool:
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.RightButton:
            index = self._chip_index(watched)
            if index >= 0:
                self._open_menu(index, event.globalPosition().toPoint())
                return True
            return False
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = int(event.globalPosition().y() if self._vertical else event.globalPosition().x())
            bar = self._bar()
            self._drag_scroll = bar.value()
            self._sliding = False
            self._reordering = False
            self._press_index = self._chip_index(watched)
            self._reorder_to = self._press_index
            return False
        if kind == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton:
            pos = int(event.globalPosition().y() if self._vertical else event.globalPosition().x())
            delta = pos - self._drag_pos
            if self._press_index >= 0 and len(self._chips) > 1 and abs(delta) > 8:
                self._reordering = True
                self._sliding = False
                self._reorder_to = self._drop_index(event.globalPosition().toPoint())
                self._mark_drop(self._reorder_to)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return True
            if abs(delta) > 4 and not self._reordering:
                self._sliding = True
                self._bar().setValue(self._drag_scroll - delta)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return True
            return False
        if kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            self.unsetCursor()
            reordering = self._reordering
            src, dst = self._press_index, self._reorder_to
            self._reordering = False
            self._press_index = -1
            self._mark_drop(-1)
            if reordering:
                if isinstance(watched, QPushButton):
                    watched.setDown(False)
                if 0 <= src < len(self._names) and 0 <= dst < len(self._names) and src != dst:
                    self.reordered.emit(src, dst)
                return True
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
            layout.setContentsMargins(10, 12, 10, 12)
            layout.setSpacing(6)
            self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self._scroll.setWidgetResizable(True)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        else:
            layout = QHBoxLayout(self._host)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(6)
            self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._scroll.setWidgetResizable(False)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.setFixedHeight(SEQUENCE_ROW_H)
        self._row = layout
        add = self._make_add()
        if self._vertical:
            layout.addWidget(add, 0, Qt.AlignmentFlag.AlignLeft)

        if not self._names:
            if not self._vertical:
                layout.addWidget(add, 0, Qt.AlignmentFlag.AlignVCenter)
            layout.addStretch(1)
            self._fit_host()
            return

        self._group.blockSignals(True)
        for i, name in enumerate(self._names):
            chip = QPushButton(name or f"Dub {i + 1}")
            chip.setObjectName("sequence_chip")
            chip.setCheckable(True)
            chip.setChecked(i == self._index)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip("Drag to reorder\nRight-click to rename, delete, or export")
            chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if self._vertical:
                chip.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                chip.setFixedHeight(32)
            else:
                chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                chip.setFixedHeight(_CHIP_ROW_H)
            chip.installEventFilter(self)
            self._group.addButton(chip, i)
            if self._vertical:
                layout.addWidget(chip)
            else:
                layout.addWidget(chip, 0, Qt.AlignmentFlag.AlignVCenter)
            self._chips.append(chip)
        if not self._vertical:
            layout.addWidget(add, 0, Qt.AlignmentFlag.AlignVCenter)
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

    def _make_add(self) -> QPushButton:
        button = QPushButton()
        button.setObjectName("sequence_add")
        size = 32 if self._vertical else 26
        button.setIcon(icon("plus", size=14))
        button.setIconSize(QSize(14, 14))
        button.setFixedSize(size, size)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip("New sequence")
        button.clicked.connect(self.add_requested.emit)
        return button

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
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self._host.setMinimumSize(0, 0)
            self._host.setMaximumSize(16777215, 16777215)
            self._host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            return
        self.setFixedHeight(SEQUENCE_ROW_H)
        self.setMinimumHeight(SEQUENCE_ROW_H)
        self.setMaximumHeight(SEQUENCE_ROW_H)
        self._host.setFixedSize(max(self._host.sizeHint().width(), 1), SEQUENCE_ROW_H)

    def _chip_index(self, watched: QObject) -> int:
        if isinstance(watched, QPushButton):
            try:
                return self._chips.index(watched)
            except ValueError:
                return -1
        return -1

    def _drop_index(self, global_pos: QPoint) -> int:
        local = self._host.mapFromGlobal(global_pos)
        coord = local.y() if self._vertical else local.x()
        for i, chip in enumerate(self._chips):
            start = chip.y() if self._vertical else chip.x()
            span = chip.height() if self._vertical else chip.width()
            if coord < start + span / 2:
                return i
        return max(0, len(self._chips) - 1)

    def _mark_drop(self, index: int) -> None:
        for i, chip in enumerate(self._chips):
            chip.setProperty("drop", "true" if i == index and i != self._press_index else "false")
            style = chip.style()
            if style is not None:
                style.unpolish(chip)
                style.polish(chip)

    def _open_menu(self, index: int, global_pos: QPoint) -> None:
        if not (0 <= index < len(self._chips)):
            return
        self._chips[index].setDown(False)
        menu = QMenu(self)
        menu.setObjectName("timeline_context_menu")
        rename = menu.addAction(icon("type", size=14), "Rename")
        delete = menu.addAction(icon("trash", size=14), "Delete")
        menu.addSeparator()
        export = menu.addAction(icon("download", size=14), "Export")
        chosen = menu.exec(global_pos)
        if chosen == rename:
            self.rename_requested.emit(index)
        elif chosen == delete:
            self.delete_requested.emit(index)
        elif chosen == export:
            self.export_requested.emit(index)

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
