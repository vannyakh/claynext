"""Shared property rows, swatches, and section chrome."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPixmap,
)

from claynext.constants.theme_constants import COLOR_BORDER, COLOR_TEXT_SUB
from claynext.gui.components.controls.section import CollapsibleSection
from claynext.gui.components.controls.scrub_spin import ScrubSpinBox
from claynext.gui.icons import icon

class PropsChrome:
    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("asr_field_label")
        return label

    @staticmethod
    def _swatch_btn(tip: str, size: QSize) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("dub_canvas_swatch")
        btn.setCheckable(True)
        btn.setToolTip(tip)
        btn.setFixedSize(size)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    @staticmethod
    def _color_icon(color: str, side: int) -> QIcon:
        pix = QPixmap(side, side)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QColor(COLOR_BORDER))
        p.setBrush(QColor(color))
        p.drawRoundedRect(0, 0, side - 1, side - 1, 4, 4)
        p.end()
        return QIcon(pix)

    def _section(
        self,
        title: str,
        *,
        open: bool = True,
        bare: bool = False,
        divider: bool = False,
        collapsible: bool = True,
    ) -> tuple[QWidget, QVBoxLayout]:
        """Clean inspector block — purple header + optional chevron."""
        if bare:
            box = QWidget()
            box.setObjectName("dub_config_section")
            body_l = QVBoxLayout(box)
            body_l.setContentsMargins(0, 0, 0, 4)
            body_l.setSpacing(6)
            self._root.addWidget(box)
            return box, body_l
        sec = CollapsibleSection(title, open=open, divider=divider, collapsible=collapsible)
        self._root.addWidget(sec)
        return sec, sec.body_layout

    @staticmethod
    def _hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("dub_switch_hint")
        label.setStyleSheet("padding-left: 0;")
        label.setWordWrap(True)
        return label

    def _paired_spin_cell(
        self, label_text: str, low: int, high: int, prefix: str = "", suffix: str = "",
    ) -> tuple[QWidget, QLabel, ScrubSpinBox]:
        cell = QWidget()
        l = QVBoxLayout(cell)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(2)
        lbl = QLabel(label_text)
        lbl.setObjectName("asr_field_label")
        spin = ScrubSpinBox()
        spin.setRange(low, high)
        if prefix:
            spin.setPrefix(prefix)
        if suffix:
            spin.setSuffix(suffix)
        spin.setMaximumWidth(16777215)
        spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        l.addWidget(lbl)
        l.addWidget(spin)
        return cell, lbl, spin

    def _spin_row(
        self, layout: QVBoxLayout, text: str, low: int, high: int, suffix: str = "",
    ) -> tuple[QLabel, ScrubSpinBox]:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        label = QLabel(text)
        label.setObjectName("asr_field_label")
        spin = ScrubSpinBox()
        spin.setRange(low, high)
        spin.setSuffix(suffix)
        spin.setToolTip("Drag up/down to scrub · click to type · ▲▼ to step")
        row.addWidget(label, 1)
        row.addWidget(spin, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(row)
        return label, spin

    @staticmethod
    def _key_btn(text: str, tip: str, icon_name: str = "") -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("timeline_tool_btn")
        if icon_name:
            btn.setIcon(icon(icon_name, color=COLOR_TEXT_SUB, size=12))
        else:
            btn.setText(text)
        btn.setToolTip(tip)
        btn.setFixedSize(24, 24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn
