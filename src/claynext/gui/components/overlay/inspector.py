"""Properties for a logo or image sitting on the preview."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QToolButton,
    QVBoxLayout, QWidget,
)

from claynext.constants.theme_constants import (
    COLOR_ACCENT_PURPLE, COLOR_TEXT_MUTED, COLOR_TEXT_SUB,
)
from claynext.gui.components.overlay.const import TEXT_KINDS
from claynext.gui.components.overlay.item import OverlayItem
from claynext.gui.components.scrub_spin import ScrubSpinBox
from claynext.gui.icons import icon

class OverlayInspector(QWidget):
    """Refactored Cyber Dark properties inspector for overlays (images, logos, text)."""

    changed = Signal()
    delete_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("overlay_inspector")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._item: OverlayItem | None = None
        self._block = False
        self._aspect_ratio = 1.0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Header card with icon + type badge + optional filename
        self.header_card = QWidget()
        self.header_card.setObjectName("dub_props_header_card")
        h_lay = QHBoxLayout(self.header_card)
        h_lay.setContentsMargins(6, 4, 6, 4)
        h_lay.setSpacing(6)

        self.kind_icon = QLabel()
        self.kind_icon.setFixedSize(18, 18)
        self.kind_icon.setPixmap(icon("image", color=COLOR_ACCENT_PURPLE, size=16).pixmap(16, 16))

        self.kind_badge = QLabel("OVERLAY")
        self.kind_badge.setObjectName("dub_props_chip")
        self.kind_badge.setStyleSheet(
            f"background-color: rgba(139, 92, 246, 0.15); color: {COLOR_ACCENT_PURPLE}; "
            f"border: 1px solid rgba(139, 92, 246, 0.4); border-radius: 4px; padding: 1px 6px; font-weight: 700; font-size: 10px;"
        )

        self.kind_lbl = QLabel("None selected")
        self.kind_lbl.setObjectName("dub_props_sublabel")
        self.kind_lbl.setStyleSheet(f"color: {COLOR_TEXT_SUB}; font-size: 11px;")

        h_lay.addWidget(self.kind_icon)
        h_lay.addWidget(self.kind_badge)
        h_lay.addWidget(self.kind_lbl, 1)
        lay.addWidget(self.header_card)

        # --- Text Specific Controls (Hidden for Images) ---
        self.text_group_widget = QWidget()
        txt_l = QVBoxLayout(self.text_group_widget)
        txt_l.setContentsMargins(0, 0, 0, 0)
        txt_l.setSpacing(6)

        self.edit_text = QLineEdit()
        self.edit_text.setPlaceholderText("Overlay text")
        self.edit_text.textChanged.connect(self._emit)
        txt_l.addWidget(self.edit_text)

        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(6)
        self.btn_color = QPushButton("Pick Color")
        self.btn_color.setObjectName("dub_props_ghost_btn")
        self.btn_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_color.clicked.connect(self._pick_color)
        self.spin_size = self._spin(10, 144, "Size ")
        color_row.addWidget(self.btn_color, 1)
        color_row.addWidget(self.spin_size, 1)
        txt_l.addLayout(color_row)
        lay.addWidget(self.text_group_widget)

        # --- Transform Controls (Position, Dimensions, Rotation, Opacity) ---
        self.transform_group_widget = QWidget()
        tr_l = QVBoxLayout(self.transform_group_widget)
        tr_l.setContentsMargins(0, 0, 0, 0)
        tr_l.setSpacing(6)

        # 1. Paired Position (X & Y)
        lbl_pos = QLabel("POSITION")
        lbl_pos.setObjectName("asr_field_label")
        tr_l.addWidget(lbl_pos)

        pos_row = QHBoxLayout()
        pos_row.setContentsMargins(0, 0, 0, 0)
        pos_row.setSpacing(6)
        self.spin_x = self._spin(0, 100, "X ", "%")
        self.spin_y = self._spin(0, 100, "Y ", "%")

        pos_row.addWidget(self.spin_x, 1)
        pos_row.addWidget(self.spin_y, 1)
        tr_l.addLayout(pos_row)

        # 2. Paired Size (Width & Height) + Aspect Lock
        lbl_size = QLabel("SIZE")
        lbl_size.setObjectName("asr_field_label")
        tr_l.addWidget(lbl_size)

        size_row = QHBoxLayout()
        size_row.setContentsMargins(0, 0, 0, 0)
        size_row.setSpacing(6)
        self.spin_w = self._spin(2, 200, "W ", "%", self._on_w_changed)
        self.spin_h = self._spin(2, 200, "H ", "%", self._on_h_changed)

        self.btn_lock_ratio = QToolButton()
        self.btn_lock_ratio.setObjectName("timeline_tool_btn")
        self.btn_lock_ratio.setCheckable(True)
        self.btn_lock_ratio.setChecked(True)
        self.btn_lock_ratio.setFixedSize(28, 28)
        self.btn_lock_ratio.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_lock_ratio.setToolTip("Lock aspect ratio")
        self._sync_lock_icon()
        self.btn_lock_ratio.toggled.connect(self._on_lock_toggled)

        size_row.addWidget(self.spin_w, 1)
        size_row.addWidget(self.spin_h, 1)
        size_row.addWidget(self.btn_lock_ratio)
        tr_l.addLayout(size_row)

        # 3. Paired Rotate & Opacity
        lbl_rot_op = QLabel("ROTATION & OPACITY")
        lbl_rot_op.setObjectName("asr_field_label")
        tr_l.addWidget(lbl_rot_op)

        rot_op_row = QHBoxLayout()
        rot_op_row.setContentsMargins(0, 0, 0, 0)
        rot_op_row.setSpacing(6)

        self.spin_rot = self._spin(-180, 180, "Rotate ", "°")
        self.spin_op = self._spin(5, 100, "Opacity ", "%")

        rot_op_row.addWidget(self.spin_rot, 1)
        rot_op_row.addWidget(self.spin_op, 1)
        tr_l.addLayout(rot_op_row)

        # 4. Quick Actions (Center & Reset)
        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 4, 0, 0)
        actions_row.setSpacing(6)

        self.btn_center = QPushButton("Center")
        self.btn_center.setObjectName("dub_props_ghost_btn")
        self.btn_center.setIcon(icon("align-center", color=COLOR_TEXT_SUB, size=12))
        self.btn_center.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_center.setToolTip("Center overlay on the canvas")
        self.btn_center.clicked.connect(self._center_overlay)

        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setObjectName("dub_props_ghost_btn")
        self.btn_reset.setIcon(icon("refresh", color=COLOR_TEXT_SUB, size=12))
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.setToolTip("Reset position, rotation, and opacity")
        self.btn_reset.clicked.connect(self._reset_transform)

        actions_row.addWidget(self.btn_center, 1)
        actions_row.addWidget(self.btn_reset, 1)
        tr_l.addLayout(actions_row)

        lay.addWidget(self.transform_group_widget)

        # --- Danger Remove Button ---
        lay.addSpacing(4)
        self.btn_del = QPushButton("Remove Overlay")
        self.btn_del.setObjectName("dub_danger_btn")
        self.btn_del.setIcon(icon("trash", color="#f87171", size=13))
        self.btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_del.setToolTip("Delete this overlay from the timeline")
        self.btn_del.clicked.connect(self.delete_requested.emit)
        lay.addWidget(self.btn_del)

        self.setEnabled(False)

    def _spin(self, low: int, high: int, prefix: str, suffix: str = "", changed=None) -> ScrubSpinBox:
        box = ScrubSpinBox()
        box.setRange(low, high)
        box.setPrefix(prefix)
        if suffix:
            box.setSuffix(suffix)
        box.setMaximumWidth(16777215)
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        box.valueChanged.connect(changed or self._emit)
        return box

    def _sync_lock_icon(self):
        locked = self.btn_lock_ratio.isChecked()
        name = "lock" if locked else "unlock"
        col = COLOR_ACCENT_PURPLE if locked else COLOR_TEXT_MUTED
        self.btn_lock_ratio.setIcon(icon(name, color=col, size=14))

    def _on_lock_toggled(self, locked: bool):
        self._sync_lock_icon()
        if self._item:
            self._item.lock_aspect = locked
        if locked and self.spin_h.value() > 0:
            self._aspect_ratio = self.spin_w.value() / max(1, self.spin_h.value())
        self._emit()

    def _on_w_changed(self, new_w: int):
        if not self._block:
            if self.btn_lock_ratio.isChecked() and self._aspect_ratio > 0:
                self._block = True
                new_h = max(2, min(200, int(round(new_w / self._aspect_ratio))))
                self.spin_h.setValue(new_h)
                self._block = False
            elif self.spin_h.value() > 0:
                self._aspect_ratio = new_w / max(1, self.spin_h.value())
        self._emit()

    def _on_h_changed(self, new_h: int):
        if not self._block:
            if self.btn_lock_ratio.isChecked() and self._aspect_ratio > 0:
                self._block = True
                new_w = max(2, min(200, int(round(new_h * self._aspect_ratio))))
                self.spin_w.setValue(new_w)
                self._block = False
            elif new_h > 0:
                self._aspect_ratio = self.spin_w.value() / max(1, new_h)
        self._emit()

    def _center_overlay(self):
        self.spin_x.setValue(50)
        self.spin_y.setValue(50)
        self._emit()

    def _reset_transform(self):
        self.spin_rot.setValue(0)
        self.spin_op.setValue(100)
        self.spin_x.setValue(50)
        self.spin_y.setValue(50)
        self._emit()

    def current(self):
        return self._item

    def bind(self, item: OverlayItem | None):
        self._item = item
        self.setEnabled(item is not None)
        if not item:
            self.kind_lbl.setText("None selected")
            self.kind_badge.setText("OVERLAY")
            return

        self._block = True
        is_text = item.kind in TEXT_KINDS
        self.kind_badge.setText(item.kind.upper())

        if item.path:
            filename = os.path.basename(item.path)
            self.kind_lbl.setText(filename)
            self.kind_lbl.setToolTip(item.path)
        else:
            self.kind_lbl.setText(item.text if is_text else item.kind.title())
            self.kind_lbl.setToolTip("")

        # Icon switch
        icon_name = "type" if is_text else ("image" if item.kind in {"image", "logo"} else "shapes")
        self.kind_icon.setPixmap(icon(icon_name, color=COLOR_ACCENT_PURPLE, size=16).pixmap(16, 16))

        # Show / hide text fields vs image fields
        self.text_group_widget.setVisible(is_text)

        self.edit_text.setText(item.text)
        self.spin_size.setValue(int(item.font_size))
        self.spin_rot.setValue(int(item.rotation))
        self.spin_x.setValue(int(item.x * 100))
        self.spin_y.setValue(int(item.y * 100))
        self.spin_w.setValue(int(item.w * 100))
        self.spin_h.setValue(int(item.h * 100))
        self.spin_op.setValue(int(item.opacity))
        self.btn_color.setStyleSheet(f"color:{item.color};")

        self.btn_lock_ratio.setChecked(bool(getattr(item, "lock_aspect", True)))
        self._sync_lock_icon()

        # Update initial aspect ratio
        if item.h > 0:
            self._aspect_ratio = (item.w / item.h)
        else:
            self._aspect_ratio = 1.0

        self._block = False

    def apply_to(self, item: OverlayItem):
        item.text = self.edit_text.text()
        item.font_size = self.spin_size.value()
        item.rotation = float(self.spin_rot.value())
        item.x = self.spin_x.value() / 100.0
        item.y = self.spin_y.value() / 100.0
        item.w = self.spin_w.value() / 100.0
        item.h = self.spin_h.value() / 100.0
        item.lock_aspect = self.btn_lock_ratio.isChecked()
        item.opacity = self.spin_op.value()

    def sync_live(self, item: OverlayItem):
        if self._item is None or getattr(self._item, "id", "") != getattr(item, "id", ""):
            return
        self._block = True
        self.spin_x.setValue(int(item.x * 100))
        self.spin_y.setValue(int(item.y * 100))
        self.spin_w.setValue(int(item.w * 100))
        self.spin_h.setValue(int(item.h * 100))
        self.spin_rot.setValue(int(item.rotation))
        if hasattr(item, "lock_aspect"):
            self.btn_lock_ratio.setChecked(bool(item.lock_aspect))
            self._sync_lock_icon()
        if item.h > 0:
            self._aspect_ratio = item.w / item.h
        self._block = False

    def _pick_color(self):
        if not self._item:
            return
        color = QColorDialog.getColor(QColor(self._item.color), self, "Overlay color")
        if color.isValid():
            self._item.color = color.name()
            self.btn_color.setStyleSheet(f"color:{self._item.color};")
            self.changed.emit()

    def _emit(self, *_):
        if not self._block:
            self.changed.emit()
