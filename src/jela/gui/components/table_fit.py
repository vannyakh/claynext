"""Tables whose text columns stretch to fill, then scroll sideways once they would get too narrow."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget


class _FlexColumns(QObject):
    def __init__(self, table: QTableWidget, columns: tuple[int, ...], min_width: int):
        super().__init__(table)
        self.table = table
        self.columns = columns
        self.min_width = min_width
        self.scrolling: bool | None = None
        table.viewport().installEventFilter(self)
        table.horizontalHeader().sectionResized.connect(self._on_section_resized)
        self.apply()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Resize:
            self.apply()
        return False

    def _on_section_resized(self, index: int, _old: int, _new: int):
        if index not in self.columns:
            self.apply()

    def apply(self):
        header = self.table.horizontalHeader()
        fixed = sum(
            header.sectionSize(col)
            for col in range(header.count())
            if col not in self.columns and not header.isSectionHidden(col)
        )
        room = self.table.viewport().width() - fixed
        scrolling = room < self.min_width * len(self.columns)
        if scrolling == self.scrolling:
            return
        self.scrolling = scrolling
        mode = QHeaderView.ResizeMode.Interactive if scrolling else QHeaderView.ResizeMode.Stretch
        for col in self.columns:
            header.setSectionResizeMode(col, mode)
            if scrolling:
                header.resizeSection(col, self.min_width)
        self.table.resizeRowsToContents()


def fit_or_scroll(table: QTableWidget, columns: tuple[int, ...], min_width: int = 220):
    """Stretch `columns` to fill the table; below `min_width` each, keep that width and scroll horizontally."""
    table.horizontalHeader().setStretchLastSection(False)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table._flex_columns = _FlexColumns(table, columns, min_width)
