"""Compact list/grid view-mode toggle for Project Home."""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QToolButton

from claynext.constants.theme_constants import COLOR_TEXT_SUB, primary_color
from claynext.gui.icons import icon

MODE_LIST = "list"
MODE_GRID = "grid"


class HomeModeToggle(QFrame):
    """Fixed 70×34 segmented control: list | grid."""

    mode_changed = Signal(str)

    def __init__(self, mode: str = MODE_LIST, parent=None):
        super().__init__(parent)
        self.setObjectName("home_mode_wrap")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedSize(70, 34)
        self._mode = MODE_GRID if mode == MODE_GRID else MODE_LIST

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_list = self._make_btn("list", "List view")
        self.btn_grid = self._make_btn("grid", "Grid view")
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.btn_list)
        group.addButton(self.btn_grid)
        self.btn_list.clicked.connect(lambda: self.set_mode(MODE_LIST))
        self.btn_grid.clicked.connect(lambda: self.set_mode(MODE_GRID))
        lay.addWidget(self.btn_list)
        lay.addWidget(self.btn_grid)
        self._sync()

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str, *, emit: bool = True):
        next_mode = MODE_GRID if mode == MODE_GRID else MODE_LIST
        changed = next_mode != self._mode
        self._mode = next_mode
        self._sync()
        if emit and changed:
            self.mode_changed.emit(self._mode)

    def _make_btn(self, name: str, tip: str) -> QToolButton:
        btn = QToolButton(self)
        btn.setObjectName("home_mode_btn")
        btn.setCheckable(True)
        btn.setAutoRaise(False)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setToolTip(tip)
        btn.setIcon(icon(name, color=COLOR_TEXT_SUB, size=14))
        btn.setIconSize(QSize(14, 14))
        btn.setFixedSize(28, 24)
        return btn

    def _sync(self):
        self.btn_list.setChecked(self._mode == MODE_LIST)
        self.btn_grid.setChecked(self._mode == MODE_GRID)
        accent = primary_color()
        self.btn_list.setIcon(
            icon("list", color=accent if self._mode == MODE_LIST else COLOR_TEXT_SUB, size=14)
        )
        self.btn_grid.setIcon(
            icon("grid", color=accent if self._mode == MODE_GRID else COLOR_TEXT_SUB, size=14)
        )

