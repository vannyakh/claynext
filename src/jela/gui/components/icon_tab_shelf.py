"""Icon-tab shelf for the Dub workspace (Tasks / Script / Media / Text / …)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QToolButton, QStackedWidget, QButtonGroup, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QSize

from jela.core.icons import icon
from jela.constants.theme_constants import COLOR_PRIMARY


class IconTabShelf(QWidget):
    tab_changed = Signal(int)

    def __init__(self, parent=None, accent_color: str | None = None):
        super().__init__(parent)
        self.setObjectName("dub_shelf")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.accent_color = accent_color or COLOR_PRIMARY
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.rail = QWidget()
        self.rail.setObjectName("dub_shelf_rail")
        self.rail.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.rail.setFixedWidth(44)
        rail_l = QVBoxLayout(self.rail)
        # Extra top inset so the first tab isn’t clipped by the dock chrome.
        rail_l.setContentsMargins(5, 14, 5, 10)
        rail_l.setSpacing(6)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self._on_tab)
        self._btns: list[tuple[QToolButton, str]] = []
        rail_l.addStretch(1)

        self.stack = QStackedWidget()
        self.stack.setObjectName("dub_shelf_stack")
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.rail, 0)
        root.addWidget(self.stack, 1)

    def add_tab(self, key: str, icon_name: str, tip: str, page: QWidget) -> int:
        idx = self.stack.count()
        btn = QToolButton()
        btn.setObjectName("dub_shelf_tab")
        btn.setCheckable(True)
        btn.setAutoRaise(True)
        btn.setFixedSize(34, 34)
        btn.setIconSize(QSize(16, 16))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tip)
        btn.setProperty("tab_key", key)
        btn.setIcon(icon(icon_name, color="#94a3b8", size=16))

        if idx == 0:
            btn.setChecked(True)
            btn.setIcon(icon(icon_name, color=self.accent_color, size=16))
        self._group.addButton(btn, idx)
        self._btns.append((btn, icon_name))
        lay = self.rail.layout()
        lay.insertWidget(lay.count() - 1, btn)
        page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.stack.addWidget(page)
        return idx

    def _on_tab(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, (btn, name) in enumerate(self._btns):
            color = self.accent_color if i == index else "#94a3b8"
            btn.setIcon(icon(name, color=color, size=16))
        self.tab_changed.emit(index)

    def set_tab_icon(self, key: str, icon_name: str, tip: str = ""):
        for i, (btn, _) in enumerate(self._btns):
            if btn.property("tab_key") != key:
                continue
            self._btns[i] = (btn, icon_name)
            color = self.accent_color if btn.isChecked() else "#94a3b8"
            btn.setIcon(icon(icon_name, color=color, size=16))
            if tip:
                btn.setToolTip(tip)
            return

    def current_key(self) -> str:
        btn = self._group.checkedButton()
        return str(btn.property("tab_key") or "") if btn else ""

    def show_key(self, key: str):
        for i, (btn, _) in enumerate(self._btns):
            if btn.property("tab_key") == key:
                self.show_tab(i)
                return

    def show_tab(self, index: int):
        btn = self._group.button(index)
        if btn:
            btn.setChecked(True)
            self._on_tab(index)
