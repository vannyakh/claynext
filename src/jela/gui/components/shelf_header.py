"""Shared header strip for dubbing shelf tabs (Tasks, Voices, Text, …)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QToolButton, QVBoxLayout,
    QWidget,
)

from jela.constants.theme_constants import COLOR_BG_SIDEBAR
from jela.core.icons import icon

# Tall strip with vertically centered title + action pills.
HEADER_H = 48
_ACTION_H = 24
_ICON_BTN = 24
_TITLE_PX = 15


def make_shelf_header(title: str, *extras: QWidget) -> QFrame:
    """Title bar with optional trailing actions — vertically centered in the strip."""
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
    row.setSpacing(6)
    row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

    label = QLabel(title)
    label.setObjectName("dub_panel_title")
    label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    font = QFont(label.font())
    font.setPixelSize(_TITLE_PX)
    font.setWeight(QFont.Weight.Normal)
    font.setBold(False)
    label.setFont(font)
    row.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)
    row.addStretch(1)

    actions = QHBoxLayout()
    actions.setContentsMargins(0, 4, 0, 0)
    actions.setSpacing(6)
    actions.setAlignment(Qt.AlignmentFlag.AlignVCenter)

    for widget in extras:
        if widget is None:
            continue
        _fit_header_action(widget)
        actions.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

    row.addLayout(actions)
    outer.addLayout(row)
    outer.addStretch(1)

    head.title_label = label  # type: ignore[attr-defined]
    return head


def make_shelf_button(
    text: str = "",
    *,
    tip: str = "",
    icon_name: str = "",
    menu: bool = False,
    icon_color: str = "#cdd8e5",
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
    _fit_header_action(btn)
    return btn


def _fit_header_action(widget: QWidget):
    """Size actions to the centered content band — never taller than 24px."""
    if not widget.objectName():
        widget.setObjectName("shelf_header_btn")
    widget.setFixedHeight(_ACTION_H)
    widget.setMaximumHeight(_ACTION_H)
    if isinstance(widget, (QPushButton, QToolButton)) and not widget.text():
        widget.setProperty("icon_only", "true")
        widget.setFixedSize(_ICON_BTN, _ICON_BTN)
        widget.setIconSize(QSize(14, 14))


    elif isinstance(widget, (QPushButton, QToolButton)):
        hint = max(56, widget.sizeHint().width())
        widget.setMinimumWidth(hint)
    widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
