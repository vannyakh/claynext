"""Compact segmented tab control — shared by Properties, Dub config, Text, Preview."""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal,
)
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QPushButton, QSizePolicy, QWidget,
)

from claynext.constants.theme_constants import (
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_SUB,
)

_ANIM_MS = 180


def _chrome_tab_path(rect: QRectF, *, top_r: float = 6.0, ear: float = 5.0) -> QPainterPath:
    """Browser-style folder tab: refined rounded top, smooth concave ears."""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    top = y + 1.0
    bottom = y + h
    left = x + ear
    right = x + w - ear
    path = QPainterPath()
    path.moveTo(x, bottom)
    path.cubicTo(
        QPointF(x + ear * 0.35, bottom),
        QPointF(x + ear * 0.55, bottom - ear * 0.15),
        QPointF(left, bottom - ear),
    )
    path.lineTo(left, top + top_r)
    path.quadTo(QPointF(left, top), QPointF(left + top_r, top))
    path.lineTo(right - top_r, top)
    path.quadTo(QPointF(right, top), QPointF(right, top + top_r))
    path.lineTo(right, bottom - ear)
    path.cubicTo(
        QPointF(x + w - ear * 0.55, bottom - ear * 0.15),
        QPointF(x + w - ear * 0.35, bottom),
        QPointF(x + w, bottom),
    )
    path.lineTo(x, bottom)
    path.closeSubpath()
    return path


def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


class ChromeTabButton(QPushButton):
    """Custom-painted Chrome folder tab with a soft select fade (normal-weight label)."""

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("chrome_tab_btn")
        self.setCheckable(True)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(88)
        self.setMinimumHeight(26)
        self._active = 1.0 if self.isChecked() else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(_ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_active_changed)
        self.toggled.connect(self._animate_active)

    def _on_active_changed(self, value):
        self._active = float(value)
        self.update()

    def _animate_active(self, checked: bool):
        self._anim.stop()
        self._anim.setStartValue(self._active)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def enterEvent(self, event):
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        rect = QRectF(self.rect()).adjusted(0.5, 0.0, -0.5, 0.0)
        path = _chrome_tab_path(rect, top_r=6.0, ear=5.0)
        t = self._active

        if t > 0.01:
            grad = QLinearGradient(0, rect.top(), 0, rect.bottom())
            top = _lerp_color(QColor(255, 255, 255, 0), QColor("#1e2a3c"), t)
            bot = _lerp_color(QColor(255, 255, 255, 0), QColor("#121b27"), t)
            grad.setColorAt(0.0, top)
            grad.setColorAt(1.0, bot)
            painter.fillPath(path, grad)
        elif self.underMouse():
            grad_hover = QLinearGradient(0, rect.top(), 0, rect.bottom())
            grad_hover.setColorAt(0.0, QColor(255, 255, 255, 12))
            grad_hover.setColorAt(1.0, QColor(255, 255, 255, 4))
            painter.fillPath(path, grad_hover)

        idle = QColor(COLOR_TEXT_MUTED)
        hot = QColor(COLOR_TEXT_MAIN)
        if self.underMouse() and t < 0.5:
            color = _lerp_color(idle, hot, 0.55)
        else:
            color = _lerp_color(idle, hot, t)

        font = QFont(self.font())
        font.setPixelSize(11)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(QPen(color))
        painter.drawText(rect.adjusted(8, 0, -8, -1), Qt.AlignmentFlag.AlignCenter, self.text())


class SegmentTrack(QFrame):
    """Pill track with a sliding selection indicator under normal-weight labels."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("claynext_seg")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._anim: QVariantAnimation | None = None
        self._pill_x = 0.0
        self._pill_w = 0.0
        self._pill_y = 1.0
        self._pill_h = 18.0
        self._pill_inset = 1.0
        self._pill_radius = 5.0

    def showEvent(self, event):
        super().showEvent(event)
        # Sync pill once geometry is real.
        self._sync_pill(animate=False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_pill(animate=False)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._pill_w < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pill = QRectF(self._pill_x, self._pill_y, self._pill_w, self._pill_h)
        path = QPainterPath()
        r = min(self._pill_radius, pill.height() * 0.5)
        path.addRoundedRect(pill, r, r)
        grad = QLinearGradient(pill.topLeft(), pill.bottomLeft())
        grad.setColorAt(0.0, QColor("#1a2536"))
        grad.setColorAt(1.0, QColor("#121c28"))
        painter.fillPath(path, grad)
        painter.setPen(QPen(QColor("#283c54"), 1.0))
        painter.drawPath(path)

    def _checked_button(self) -> QPushButton | None:
        for child in self.findChildren(QPushButton):
            if child.isChecked():
                return child
        return None

    def _sync_pill(self, *, animate: bool = True):
        btn = self._checked_button()
        if btn is None:
            return
        geo = btn.geometry()
        inset = self._pill_inset
        # Inset so the pill sits inside the track padding.
        target = QRectF(
            geo.x(),
            inset,
            geo.width(),
            max(14.0, self.height() - inset * 2.0),
        )
        if not animate or self._pill_w < 2:
            self._pill_x = target.x()
            self._pill_w = target.width()
            self._pill_y = target.y()
            self._pill_h = target.height()
            self.update()
            return
        self._animate_pill(target)

    def _animate_pill(self, target: QRectF):
        start = (self._pill_x, self._pill_y, self._pill_w, self._pill_h)
        end = (target.x(), target.y(), target.width(), target.height())
        if self._anim is not None:
            self._anim.stop()
        anim = QVariantAnimation(self)
        anim.setDuration(_ANIM_MS)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)

        def _step(value):
            t = float(value)
            self._pill_x = start[0] + (end[0] - start[0]) * t
            self._pill_y = start[1] + (end[1] - start[1]) * t
            self._pill_w = start[2] + (end[2] - start[2]) * t
            self._pill_h = start[3] + (end[3] - start[3]) * t
            self.update()

        anim.valueChanged.connect(_step)
        self._anim = anim
        anim.start()

    def move_pill_to_checked(self):
        self._sync_pill(animate=True)


class SegmentTabs(QFrame):
    """Exclusive tab strip.

    ``variant``:
      - ``segment`` — pill track with sliding indicator (Properties / Dub / Text)
      - ``chrome`` — browser-style folder tabs (Preview Source / Timeline)

    ``chrome=True`` wraps a segment track in the sticky properties header strip.
    """

    changed = Signal(int)

    def __init__(
        self,
        labels: list[str],
        *,
        parent: QWidget | None = None,
        chrome: bool = False,
        variant: str = "segment",
        size: str = "md",
        fill: bool = False,
        tips: list[str] | None = None,
        current: int = 0,
    ):
        super().__init__(parent)
        self._keys = list(labels)
        tips = list(tips or [])
        variant = "chrome" if variant == "chrome" else "segment"
        compact = size == "sm" and variant == "segment"
        # Compact + fill: short height, equal segments across the host width.
        compact_fill = compact and fill
        self._variant = variant
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed if (compact and not fill) else QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        outer = QHBoxLayout(self)
        outer.setSpacing(0)

        if variant == "chrome":
            self.setObjectName("chrome_tabs_host")
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setAlignment(Qt.AlignmentFlag.AlignBottom)
            track = QFrame()
            track.setObjectName("chrome_tabs_row")
            track.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            track_l = QHBoxLayout(track)
            track_l.setContentsMargins(0, 0, 0, 0)
            track_l.setSpacing(-6)
            btn_factory = ChromeTabButton
            btn_stretch = False
            self._track = None
        elif chrome:
            self.setObjectName("claynext_seg_chrome")
            outer.setContentsMargins(8, 4, 8, 4)
            track = SegmentTrack()
            track_l = QHBoxLayout(track)
            track_l.setContentsMargins(2, 2, 2, 2)
            track_l.setSpacing(1)
            btn_factory = None
            btn_stretch = True
            self._track = track
        elif compact:
            self.setObjectName("claynext_seg_sm")
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setAlignment(
                Qt.AlignmentFlag.AlignVCenter
                if compact_fill
                else (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            )
            track = SegmentTrack()
            track.setSizePolicy(
                QSizePolicy.Policy.Expanding if compact_fill else QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Fixed,
            )
            track.setFixedHeight(22)
            track._pill_inset = 1.0
            track._pill_radius = 4.0
            track_l = QHBoxLayout(track)
            track_l.setContentsMargins(1, 1, 1, 1)
            track_l.setSpacing(0)
            btn_factory = None
            btn_stretch = compact_fill
            self._track = track
        else:
            self.setObjectName("claynext_seg_host")
            outer.setContentsMargins(0, 0, 0, 0)
            track = SegmentTrack()
            track_l = QHBoxLayout(track)
            track_l.setContentsMargins(2, 2, 2, 2)
            track_l.setSpacing(1)
            btn_factory = None
            btn_stretch = True
            self._track = track

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i, label in enumerate(self._keys):
            if btn_factory is not None:
                btn = btn_factory(label)
            else:
                btn = QPushButton(label)
                btn.setObjectName("claynext_seg_btn")
                btn.setCheckable(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                font = QFont(btn.font())
                font.setWeight(QFont.Weight.Normal)
                font.setPixelSize(10 if compact else 11)
                btn.setFont(font)
                if compact:
                    btn.setFixedHeight(20)
                    if not compact_fill:
                        btn.setMinimumWidth(64)
            btn.setChecked(i == current)
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding if btn_stretch else QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Fixed,
            )
            if variant == "chrome":
                btn.setMinimumWidth(96)
            if i < len(tips) and tips[i]:
                btn.setToolTip(tips[i])
            self._group.addButton(btn, i)
            track_l.addWidget(btn, 1 if btn_stretch else 0)
        if variant == "chrome":
            self._raise_checked()
        self._group.idClicked.connect(self._on_id_clicked)
        outer.addWidget(track, 0 if (variant == "chrome" or (compact and not compact_fill)) else 1)

    def _on_id_clicked(self, index: int):
        if self._variant == "chrome":
            self._raise_checked()
        elif self._track is not None:
            self._track.move_pill_to_checked()
        self.changed.emit(index)

    def _raise_checked(self):
        """Active Chrome tab draws above neighbors so ears nest cleanly."""
        checked = self._group.checkedButton()
        if checked is not None:
            checked.raise_()

    @property
    def group(self) -> QButtonGroup:
        return self._group

    def labels(self) -> list[str]:
        return list(self._keys)

    def current(self) -> int:
        return max(0, self._group.checkedId())

    def set_current(self, index: int):
        btn = self._group.button(int(index))
        if btn is not None:
            btn.setChecked(True)
            if self._variant == "chrome":
                self._raise_checked()
            elif self._track is not None:
                self._track.move_pill_to_checked()

    def button(self, index: int) -> QPushButton | None:
        return self._group.button(int(index))

