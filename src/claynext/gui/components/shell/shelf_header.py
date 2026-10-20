"""Shared header strip for dubbing shelf tabs (Tasks, Voices, Text, …)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QToolButton, QVBoxLayout,
    QWidget,
)

from claynext.constants.theme_constants import COLOR_BG_SIDEBAR
from claynext.gui.icons import icon

# Tall strip with vertically centered title + action pills.
HEADER_H = 48
_ACTION_H = 24
_ICON_BTN = 24
_TITLE_PX = 15
_DIVIDER_H = 14


def make_shelf_divider() -> QFrame:
    """Thin vertical rule between action groups in a shelf header."""
    rule = QFrame()
    rule.setObjectName("shelf_header_divider")
    rule.setFrameShape(QFrame.Shape.NoFrame)
    rule.setFixedWidth(1)
    rule.setFixedHeight(_DIVIDER_H)
    rule.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return rule


def make_shelf_header(
    title: str,
    *extras: QWidget,
    meta: QWidget | None = None,
) -> QFrame:
    """Title bar with optional meta (left) and trailing actions (right)."""
    head = QFrame()
    head.setObjectName("dub_panel_header")
    head.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    head.setAutoFillBackground(True)
    pal = head.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor(COLOR_BG_SIDEBAR))
    pal.setColor(QPalette.ColorRole.Base, QColor(COLOR_BG_SIDEBAR))
    head.setPalette(pal)
    head.setFixedHeight(HEADER_H)
    head.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    # Outer column centers the row so title/buttons share equal top & bottom space.
    outer = QVBoxLayout(head)
    outer.setContentsMargins(14, 0, 12, 0)
    outer.setSpacing(0)
    outer.addStretch(1)

    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

    title_wrap = QHBoxLayout()
    title_wrap.setContentsMargins(0, 0, 0, 0)
    title_wrap.setSpacing(6)
    title_wrap.setAlignment(Qt.AlignmentFlag.AlignVCenter)

    label = QLabel(title)
    label.setObjectName("dub_panel_title")
    label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    font = QFont(label.font())
    font.setPixelSize(_TITLE_PX)
    font.setWeight(QFont.Weight.Normal)
    font.setBold(False)
    label.setFont(font)
    label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    title_wrap.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)

    if meta is not None:
        meta.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        meta.setMinimumWidth(0)
        title_wrap.addWidget(meta, 0, Qt.AlignmentFlag.AlignVCenter)

    row.addLayout(title_wrap, 0)
    row.addStretch(1)

    actions = QHBoxLayout()
    actions.setContentsMargins(0, 0, 0, 0)
    actions.setSpacing(5)
    actions.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

    for widget in extras:
        if widget is None:
            continue
        _fit_header_action(widget)
        actions.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

    row.addLayout(actions, 0)
    outer.addLayout(row)
    outer.addStretch(1)

    head.title_label = label  # type: ignore[attr-defined]
    head.meta_widget = meta  # type: ignore[attr-defined]
    return head


def make_shelf_button(
    text: str = "",
    *,
    tip: str = "",
    icon_name: str = "",
    menu: bool = False,
    icon_color: str = "#cdd8e5",
    short: str = "",
) -> QPushButton | QToolButton:
    """Compact header action — pill that fits inside the centered header row."""
    if menu or icon_name:
        btn = QToolButton()
        btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
            if menu else QToolButton.ToolButtonPopupMode.DelayedPopup
        )
        if text and icon_name:
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        elif text:
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        else:
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    else:
        btn = QPushButton()
    btn.setObjectName("shelf_header_btn")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if text:
        btn.setText(text)
    if tip:
        btn.setToolTip(tip)
    if icon_name:
        btn.setIcon(icon(icon_name, color=icon_color, size=15))
        btn.setIconSize(QSize(15, 15))
    btn.setProperty("shelf_label", text or "")
    btn.setProperty("shelf_short", short or "")
    btn.setProperty("shelf_density", "full" if text else "icon")
    _fit_header_action(btn)
    return btn


def set_shelf_button_density(btn: QWidget | None, density: str) -> None:
    """Switch a shelf pill between full label, short label, and icon-only."""
    if btn is None or not isinstance(btn, (QPushButton, QToolButton)):
        return
    label = str(btn.property("shelf_label") or "")
    short = str(btn.property("shelf_short") or "")
    mode = density if density in ("full", "short", "icon") else "full"
    if not label:
        mode = "icon"
    if mode == "short" and not short:
        mode = "icon" if density == "icon" else "full"

    prev = str(btn.property("shelf_density") or "")
    if prev == mode and (
        (mode == "icon" and not btn.text())
        or (mode == "short" and btn.text() == short)
        or (mode == "full" and btn.text() == label)
    ):
        return

    btn.setProperty("shelf_density", mode)
    if mode == "icon":
        btn.setText("")
        if isinstance(btn, QToolButton):
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        btn.setProperty("icon_only", "true")
        btn.setFixedSize(_ICON_BTN, _ICON_BTN)
        btn.setMinimumWidth(_ICON_BTN)
        btn.setMaximumWidth(_ICON_BTN)
        btn.setIconSize(QSize(14, 14))
    else:
        shown = short if mode == "short" else label
        btn.setText(shown)
        if isinstance(btn, QToolButton):
            btn.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon
                if not btn.icon().isNull()
                else Qt.ToolButtonStyle.ToolButtonTextOnly
            )
        btn.setProperty("icon_only", "false")
        btn.setFixedHeight(_ACTION_H)
        btn.setMinimumHeight(_ACTION_H)
        btn.setMaximumHeight(_ACTION_H)
        btn.setMinimumWidth(0)
        btn.setMaximumWidth(16777215)
        btn.setIconSize(QSize(15, 15))
        # Prefer natural width; avoid forcing huge minimums that cause overlap.
        hint = btn.sizeHint().width()
        btn.setMinimumWidth(min(max(40, hint), 120 if mode == "short" else 148))

    btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    style = btn.style()
    if style is not None:
        style.unpolish(btn)
        style.polish(btn)
    btn.update()


def _fit_header_action(widget: QWidget):
    """Size actions to the centered content band — never taller than 24px."""
    if widget.objectName() == "shelf_header_divider":
        return
    if not widget.objectName():
        widget.setObjectName("shelf_header_btn")
    widget.setFixedHeight(_ACTION_H)
    widget.setMaximumHeight(_ACTION_H)
    if isinstance(widget, (QPushButton, QToolButton)) and not widget.text():
        widget.setProperty("icon_only", "true")
        widget.setFixedSize(_ICON_BTN, _ICON_BTN)
        widget.setIconSize(QSize(14, 14))
        widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return

    if isinstance(widget, (QPushButton, QToolButton)):
        hint = widget.sizeHint().width()
        widget.setMinimumWidth(min(max(48, hint), 148))
        widget.setMaximumWidth(16777215)
        widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return

    widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
