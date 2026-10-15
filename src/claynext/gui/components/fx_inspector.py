"""Properties for an effect or filter clip: which look, and how strong."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QGridLayout, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from claynext.models.fx import EFFECTS, FILTER_LOOKS, clean_fx
from claynext.models.transitions import TRANSITIONS
from claynext.gui.components.fx_shelf import fx_tile
from claynext.gui.components.scrub_spin import ScrubSpinBox


class FxInspector(QWidget):
    changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("overlay_inspector")
        self._kind = "effect"
        self._fx = clean_fx("effect", None)
        self._block = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.grids: dict[str, tuple[QWidget, QButtonGroup, list[str]]] = {}
        catalogs = (
            ("effect", [(k, label) for k, label, _h in EFFECTS]),
            ("filter", list(FILTER_LOOKS)),
            ("transition", [(k, label) for k, label, _h in TRANSITIONS]),
        )
        for kind, rows in catalogs:
            page = QWidget()
            grid = QGridLayout(page)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(6)
            group = QButtonGroup(self)
            for i, (key, label) in enumerate(rows):
                btn = QToolButton()
                btn.setObjectName("dub_text_tile")
                btn.setCheckable(True)
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                btn.setIcon(fx_tile(kind, key))
                btn.setIconSize(QSize(64, 40))
                btn.setText(label)
                btn.setFixedSize(QSize(78, 66))
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                group.addButton(btn, i)
                grid.addWidget(btn, i // 3, i % 3)
            keys = [key for key, _l in rows]
            group.idClicked.connect(lambda i, k=kind, ks=keys: self._pick(k, ks[i]))
            self.grids[kind] = (page, group, keys)
            lay.addWidget(page)

        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel("Intensity")
        title.setObjectName("asr_field_label")
        self.spin = ScrubSpinBox()
        self.spin.setRange(0, 100)
        self.spin.setSuffix("%")
        self.spin.setToolTip("Drag up/down to scrub · click to type · ▲▼ to step")
        self.spin.valueChanged.connect(self._on_intensity)
        head.addWidget(title, 1)
        head.addWidget(self.spin, 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(head)
        self.hint = QLabel("")
        self.hint.setObjectName("dub_switch_hint")
        self.hint.setStyleSheet("padding-left: 0;")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)

    def bind(self, kind: str, fx: dict | None):
        self._kind = kind if kind in self.grids else "effect"
        self._fx = clean_fx(self._kind, fx)
        self._block = True
        for name, (page, _group, _keys) in self.grids.items():
            page.setVisible(name == self._kind)
        self.spin.setValue(self._fx["intensity"])
        self._sync()
        self._block = False

    def _sync(self):
        _page, group, keys = self.grids[self._kind]
        key = self._fx[self._kind]
        group.setExclusive(False)
        for i, btn in enumerate(group.buttons()):
            btn.setChecked(keys[i] == key)
        group.setExclusive(True)
        if self._kind == "filter":
            tip = "Grades every frame under the clip · 100% is the full look."
        elif self._kind == "transition":
            tip = "Plays at the playhead · drag edges to set length · place on cuts for fades & wipes."
        else:
            tip = "Plays over the whole clip · drag its edges on the timeline to change when."
        self.hint.setText(tip)

    def _pick(self, kind: str, key: str):
        if self._block or kind != self._kind:
            return
        self._fx[kind] = key
        self._sync()
        self.changed.emit(dict(self._fx))

    def _on_intensity(self, value: int):
        self._fx["intensity"] = int(value)
        if not self._block:
            self.changed.emit(dict(self._fx))

