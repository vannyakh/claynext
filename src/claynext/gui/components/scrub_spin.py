"""Compact number field: type, step buttons, and vertical drag-to-scrub."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QFocusEvent, QMouseEvent, QValidator
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLineEdit, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from claynext.gui.icons import icon


class _IntValidator(QValidator):
    def __init__(self, low: int, high: int, parent=None):
        super().__init__(parent)
        self.low = low
        self.high = high

    def validate(self, text: str, pos: int):
        raw = text.strip()
        if raw in {"", "-", "+"}:
            return QValidator.State.Intermediate, text, pos
        try:
            value = int(raw)
        except ValueError:
            return QValidator.State.Invalid, text, pos
        if self.low <= value <= self.high:
            return QValidator.State.Acceptable, text, pos
        if (value < self.low and raw.startswith("-")) or (value > self.high and not raw.startswith("-")):
            return QValidator.State.Intermediate, text, pos
        return QValidator.State.Intermediate, text, pos


class ScrubSpinBox(QFrame):
    """Number combo: manual edit, ▲▼ steps, drag up/down on the value to scrub."""

    valueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("scrub_spin")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(30)
        self.setMinimumWidth(84)
        self.setMaximumWidth(110)
        self.setCursor(Qt.CursorShape.SizeVerCursor)

        self._low = 0
        self._high = 99
        self._value = 0
        self._step = 1
        self._prefix = ""
        self._suffix = ""
        self._format: Callable[[int], str] | None = None
        self._scrubbing = False
        self._press_y = 0
        self._press_value = 0
        self._moved = False
        self._block = False

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self._edit = QLineEdit(self)
        self._edit.setObjectName("scrub_spin_edit")
        self._edit.setFrame(False)
        self._edit.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._edit.setCursor(Qt.CursorShape.SizeVerCursor)
        self._edit.setValidator(_IntValidator(self._low, self._high, self))
        self._edit.editingFinished.connect(self._commit_edit)
        self._edit.installEventFilter(self)
        row.addWidget(self._edit, 1)

        steps = QWidget(self)
        steps.setObjectName("scrub_spin_steps")
        steps.setFixedWidth(18)
        step_l = QVBoxLayout(steps)
        step_l.setContentsMargins(0, 1, 1, 1)
        step_l.setSpacing(0)

        self._btn_up = QToolButton(steps)
        self._btn_down = QToolButton(steps)
        for btn, name, tip in (
            (self._btn_up, "chevron-up", "Increase"),
            (self._btn_down, "chevron-down", "Decrease"),
        ):
            btn.setObjectName("scrub_spin_step")
            btn.setAutoRaise(True)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(16, 13)
            btn.setIconSize(QSize(9, 9))
            btn.setIcon(icon(name, color="#9fb0c3", size=9))
            btn.setToolTip(tip)
        self._btn_up.clicked.connect(lambda: self.stepBy(1))
        self._btn_down.clicked.connect(lambda: self.stepBy(-1))
        step_l.addWidget(self._btn_up, 1)
        step_l.addWidget(self._btn_down, 1)
        row.addWidget(steps)

        self._refresh_text()

    # ── QSpinBox-compatible API ────────────────────────────────────
    def value(self) -> int:
        return self._value

    def setValue(self, value: int):
        # Match QSpinBox: emit so paired sliders stay in sync (callers use _block / blockSignals).
        self._set_value(int(value), emit=not self.signalsBlocked())

    def setRange(self, low: int, high: int):
        self._low = int(low)
        self._high = int(high)
        if isinstance(self._edit.validator(), _IntValidator):
            self._edit.validator().low = self._low
            self._edit.validator().high = self._high
        self._set_value(self._value, emit=False)

    def setPrefix(self, text: str):
        self._prefix = str(text or "")
        self._refresh_text()

    def setSuffix(self, text: str):
        self._suffix = str(text or "")
        self._refresh_text()

    def setFormat(self, fn: Callable[[int], str] | None):
        """Optional display formatter when not editing (e.g. dB labels)."""
        self._format = fn
        self._refresh_text()

    def setKeyboardTracking(self, _on: bool):
        return

    def setButtonSymbols(self, *_):
        return

    def setSingleStep(self, step: int):
        self._step = max(1, int(step))

    def setAlignment(self, align):
        self._edit.setAlignment(align)

    def stepBy(self, steps: int):
        self._set_value(self._value + int(steps) * self._step, emit=True)

    def minimum(self) -> int:
        return self._low

    def maximum(self) -> int:
        return self._high

    # ── internals ──────────────────────────────────────────────────
    def _set_value(self, value: int, *, emit: bool):
        value = max(self._low, min(self._high, int(value)))
        changed = value != self._value
        self._value = value
        self._refresh_text()
        if emit and changed:
            self.valueChanged.emit(self._value)

    def _refresh_text(self):
        if self._edit.hasFocus() and not self._scrubbing:
            return
        self._block = True
        if self._format is not None:
            self._edit.setText(self._format(self._value))
        else:
            self._edit.setText(f"{self._prefix}{self._value}{self._suffix}")
        self._edit.setCursorPosition(0)
        self._block = False

    def _parse_edit(self) -> int | None:
        raw = self._edit.text().strip()
        if self._prefix and raw.startswith(self._prefix):
            raw = raw[len(self._prefix):]
        if self._suffix and raw.endswith(self._suffix):
            raw = raw[: -len(self._suffix)]
        raw = raw.strip()
        try:
            return int(raw)
        except ValueError:
            return None

    def _commit_edit(self):
        parsed = self._parse_edit()
        if parsed is None:
            self._refresh_text()
            return
        self._set_value(parsed, emit=True)
        self._refresh_text()

    def eventFilter(self, obj, event):
        if obj is self._edit:
            et = event.type()
            if et == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
                if event.button() == Qt.MouseButton.LeftButton and not self._edit.hasFocus():
                    self._begin_scrub(event)
                    return True
            if et == QEvent.Type.MouseButtonDblClick and isinstance(event, QMouseEvent):
                self._edit.setFocus(Qt.FocusReason.MouseFocusReason)
                self._block = True
                self._edit.setText(str(self._value))
                self._edit.selectAll()
                self._block = False
                self._edit.setCursor(Qt.CursorShape.IBeamCursor)
                return True
            if et == QEvent.Type.FocusIn:
                self.setProperty("focused", True)
                self.style().unpolish(self)
                self.style().polish(self)
                self._edit.setCursor(Qt.CursorShape.IBeamCursor)
                self._block = True
                self._edit.setText(str(self._value))
                self._edit.selectAll()
                self._block = False
            if et == QEvent.Type.FocusOut:
                self.setProperty("focused", False)
                self.style().unpolish(self)
                self.style().polish(self)
                self._edit.setCursor(Qt.CursorShape.SizeVerCursor)
                self._commit_edit()
        return super().eventFilter(obj, event)

    def _begin_scrub(self, event: QMouseEvent):
        self._scrubbing = True
        self._moved = False
        self._press_y = int(event.globalPosition().y())
        self._press_value = self._value
        self._edit.clearFocus()
        self.grabMouse()
        self.setCursor(Qt.CursorShape.SizeVerCursor)

    def _update_scrub(self, event: QMouseEvent):
        dy = self._press_y - int(event.globalPosition().y())
        if abs(dy) >= 2:
            self._moved = True
        # Default 2px/step; Shift = 1px (fine); Alt/Ctrl = 3× (coarse)
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ShiftModifier:
            step = dy
        elif mods & (
            Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.MetaModifier
        ):
            step = dy * 3
        else:
            step = dy // 2
        self._set_value(self._press_value + step * self._step, emit=True)

    def _end_scrub(self, event: QMouseEvent):
        self.releaseMouse()
        self._scrubbing = False
        self.unsetCursor()
        if not self._moved:
            self._edit.setFocus(Qt.FocusReason.MouseFocusReason)
            self._edit.selectAll()
        self._refresh_text()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and not self._edit.geometry().contains(event.position().toPoint()):
            # Click on frame around edit still scrubs
            self._begin_scrub(event)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._scrubbing:
            self._update_scrub(event)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._scrubbing:
            self._end_scrub(event)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def focusOutEvent(self, event: QFocusEvent):
        self._commit_edit()
        super().focusOutEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            self.stepBy(1 if delta > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)

