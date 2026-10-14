"""Reusable search input and select dropdown with sm / md / lg heights."""
from __future__ import annotations

from typing import Literal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QLineEdit, QSizePolicy

FieldSize = Literal["sm", "md", "lg"]

# Distinct chrome heights so search and select never look like twins.
_FIELD_H: dict[str, int] = {
    "sm": 24,
    "md": 30,
    "lg": 34,
}


def field_height(size: FieldSize | str = "md") -> int:
    return _FIELD_H.get(size, _FIELD_H["md"])


class SearchField(QLineEdit):
    """Expanding find / filter input. Default size is ``md`` (taller than SelectField)."""

    def __init__(
        self,
        placeholder: str = "Search…",
        *,
        size: FieldSize = "md",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("minj_search")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.set_field_size(size)

    def set_field_size(self, size: FieldSize | str):
        size = size if size in _FIELD_H else "md"
        self.setProperty("size", size)
        self.setFixedHeight(field_height(size))
        self.style().unpolish(self)
        self.style().polish(self)


class SelectField(QComboBox):
    """Compact option dropdown. Default size is ``sm`` (shorter than SearchField)."""

    value_changed = Signal(object)

    def __init__(
        self,
        *,
        size: FieldSize = "sm",
        width: int | None = 148,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("minj_select")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.setMinimumContentsLength(10)
        self.setMaxVisibleItems(14)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if width is not None:
            self.setFixedWidth(width)
        self.set_field_size(size)
        self.currentIndexChanged.connect(self._emit_value)

    def set_field_size(self, size: FieldSize | str):
        size = size if size in _FIELD_H else "sm"
        self.setProperty("size", size)
        self.setFixedHeight(field_height(size))
        self.style().unpolish(self)
        self.style().polish(self)

    def current_value(self):
        return self.currentData()

    def set_value(self, data) -> bool:
        idx = self.findData(data)
        if idx < 0:
            return False
        self.setCurrentIndex(idx)
        return True

    def _emit_value(self, _index: int = 0):
        self.value_changed.emit(self.currentData())
