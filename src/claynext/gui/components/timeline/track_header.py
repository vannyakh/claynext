"""Single track row in the timeline lane rail."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QToolButton,
    QSlider, QSizePolicy,
)

from claynext.constants.theme_constants import COLOR_PRIMARY, accent_wash
from claynext.constants.timeline_constants import (
    FX_KINDS, OVERLAY_KINDS, TRACK_DIVIDER, TRACK_MAX_H, TRACK_MIN_H,
)
from claynext.gui.icons import icon
from claynext.gui.components.timeline.models import TimelineTrack

_SOUND_KINDS = {"video", "voice", "audio"}
_VISUAL_KINDS = OVERLAY_KINDS | FX_KINDS | {"video"}


class TrackHeader(QWidget):
    mute_toggled = Signal(str, bool)
    solo_toggled = Signal(str, bool)
    locked_toggled = Signal(str, bool)
    hidden_toggled = Signal(str, bool)
    opacity_changed = Signal(str, int)
    volume_changed = Signal(str, int)
    delete_requested = Signal(str)
    duplicate_requested = Signal(str)
    selected = Signal(str, bool)
    height_changed = Signal(str, int)
    reorder_dragged = Signal(str, int)
    renamed = Signal(str, str)
    context_menu_requested = Signal(str, QPoint)

    def __init__(self, track: TimelineTrack, parent=None):
        super().__init__(parent)
        self.track = track
        self.setObjectName("timeline_track_header")
        self.setFixedHeight(track.height)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self._resize = False
        self._press_y = 0
        self._press_h = track.height
        self._dragging_track = False
        self._drag_start_y = 0
        self._compact = False
        self._current_tall = None
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 3, 6, 3)
        root.setSpacing(2)

        # ─── Top Row: Icon, Name, Kind, Lock ───
        self.row_top = QHBoxLayout()
        self.row_top.setContentsMargins(0, 0, 0, 0)
        self.row_top.setSpacing(4)

        self.grip = QLabel()
        self.grip.setObjectName("timeline_track_grip")
        self.grip.setFixedSize(10, 14)
        self.grip.setPixmap(icon("grab", color="#4b5563", size=9).pixmap(10, 14))
        self.grip.setToolTip("Drag to reorder track")
        self.grip.setCursor(Qt.CursorShape.SizeAllCursor)

        self.ico = QLabel()
        self.ico.setObjectName("timeline_track_icon")
        self.ico.setFixedSize(14, 14)
        self.ico.setPixmap(icon(self.track.icon, color=self.track.color, size=12).pixmap(14, 14))
        self.ico.setToolTip(self.track.kind.title())

        self.name = QLabel(self.track.name)
        self.name.setObjectName("timeline_track_name")
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.name.setToolTip("Double-click to rename · right-click for track menu")

        self.name_edit = QLineEdit(self.track.name)
        self.name_edit.setObjectName("timeline_track_name_edit")
        self.name_edit.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.name_edit.hide()
        self.name_edit.editingFinished.connect(self._finish_rename)

        self.badge_kind = QLabel(self.track.kind.upper())
        self.badge_kind.setObjectName("timeline_badge_kind")
        self.badge_kind.setFixedHeight(14)
        self.badge_kind.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Tint badge with track accent
        col = QColor(self.track.color)
        self.badge_kind.setStyleSheet(
            f"color: {col.name()};"
            f"background: rgba({col.red()}, {col.green()}, {col.blue()}, 0.14);"
            f"border: 1px solid rgba({col.red()}, {col.green()}, {col.blue()}, 0.35);"
            "border-radius: 3px; padding: 0 4px; font-size: 8px; font-weight: 700;"
        )

        self.btn_lock = QToolButton()
        self.btn_lock.setObjectName("timeline_btn_lock")
        self.btn_lock.setCheckable(True)
        self.btn_lock.setChecked(self.track.locked)
        self.btn_lock.setFixedSize(18, 18)
        self.btn_lock.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_lock.setIcon(icon(
            "lock" if self.track.locked else "unlock",
            color="#f59e0b" if self.track.locked else "#64748b",
            size=11,
        ))
        self.btn_lock.setToolTip("Unlock track" if self.track.locked else "Lock track (prevent edits/moves)")
        self.btn_lock.toggled.connect(self._on_lock)

        # Delete stays in context menu — keep a compact affordance on hover only
        self.btn_del = QToolButton()
        self.btn_del.setObjectName("timeline_btn_del")
        self.btn_del.setFixedSize(18, 18)
        self.btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_del.setIcon(icon("trash", color="#94a3b8", size=11))
        self.btn_del.setToolTip("Delete track")
        self.btn_del.clicked.connect(lambda: self.delete_requested.emit(self.track.id))
        self.btn_del.hide()

        self.row_top.addWidget(self.grip)
        self.row_top.addWidget(self.ico)
        self.row_top.addWidget(self.name, 1)
        self.row_top.addWidget(self.name_edit, 1)
        self.row_top.addWidget(self.badge_kind)
        self.row_top.addWidget(self.btn_lock)
        self.row_top.addWidget(self.btn_del)
        root.addLayout(self.row_top)

        # ─── Sound / Visibility Controls ───
        self.btn_mute = None
        self.btn_solo = None
        if self.track.kind in _SOUND_KINDS:
            self.btn_mute = QToolButton()
            self.btn_mute.setObjectName("timeline_btn_mute")
            self.btn_mute.setCheckable(True)
            self.btn_mute.setChecked(self.track.muted)
            self.btn_mute.setFixedSize(18, 18)
            self.btn_mute.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_mute.setIcon(icon(
                "volume-off" if self.track.muted else "volume",
                color="#ef4444" if self.track.muted else "#94a3b8",
                size=11,
            ))
            self.btn_mute.setToolTip("Unmute track" if self.track.muted else "Mute track")
            self.btn_mute.toggled.connect(self._on_mute)

            self.btn_solo = QToolButton()
            self.btn_solo.setObjectName("timeline_btn_solo")
            self.btn_solo.setCheckable(True)
            self.btn_solo.setChecked(getattr(self.track, "solo", False))
            self.btn_solo.setText("S")
            self.btn_solo.setFixedSize(18, 18)
            self.btn_solo.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_solo.setToolTip("Solo track (isolate audio in mix)")
            self.btn_solo.toggled.connect(self._on_solo)

        self.btn_eye = QToolButton()
        self.btn_eye.setObjectName("timeline_btn_eye")
        self.btn_eye.setCheckable(True)
        self.btn_eye.setChecked(self.track.hidden)
        self.btn_eye.setFixedSize(18, 18)
        self.btn_eye.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_eye.setIcon(icon(
            "eye-off" if self.track.hidden else "eye",
            color="#64748b" if self.track.hidden else "#94a3b8",
            size=11,
        ))
        self.btn_eye.setToolTip(
            "Show in preview" if self.track.hidden else "Hide from preview · keep dimmed on timeline"
        )
        self.btn_eye.toggled.connect(self._on_hide)

        # ─── Bottom Row Widget (for tall mode: height >= 52) ───
        self.row_bottom_widget = QWidget()
        self.row_bottom_widget.setObjectName("timeline_track_controls")
        self.row_bottom = QHBoxLayout(self.row_bottom_widget)
        self.row_bottom.setContentsMargins(18, 0, 0, 0)
        self.row_bottom.setSpacing(4)

        if self.btn_mute is not None:
            self.row_bottom.addWidget(self.btn_mute)
        if self.btn_solo is not None:
            self.row_bottom.addWidget(self.btn_solo)
        self.row_bottom.addWidget(self.btn_eye)

        self.vol_slider = None
        self.opacity_slider = None
        self.vol_label = None

        # Volume is mix-level only (no header slider) — mute shows on the clip wave.
        # Overlay tracks keep a compact opacity scrubber.
        if self.track.kind in _VISUAL_KINDS and self.track.kind != "video":
            self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
            self.opacity_slider.setObjectName("timeline_track_slider")
            self.opacity_slider.setRange(0, 100)
            self.opacity_slider.setValue(self.track.opacity)
            self.opacity_slider.setFixedHeight(12)
            self.opacity_slider.setMinimumWidth(48)
            self.opacity_slider.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            self.opacity_slider.setToolTip(f"Opacity: {self.track.opacity}% · double-click resets 100%")
            self.opacity_slider.valueChanged.connect(self._on_opacity_changed)

            self.vol_label = QLabel(f"{self.track.opacity}%")
            self.vol_label.setObjectName("timeline_track_level_lbl")
            self.vol_label.setFixedWidth(28)
            self.vol_label.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.row_bottom.addWidget(self.opacity_slider, 1)
            self.row_bottom.addWidget(self.vol_label)

        self.row_bottom.addStretch(1)
        root.addWidget(self.row_bottom_widget)

        self._update_tier()
        self._apply_selected()

    def _update_tier(self):
        is_tall = (self.track.height >= 52) and (not self._compact)
        if is_tall == self._current_tall:
            return
        self._current_tall = is_tall
        if is_tall:
            self.badge_kind.setVisible(not self._compact)
            self.row_bottom_widget.show()
            # Move sound / eye controls into row_bottom
            if self.btn_mute is not None:
                self.row_top.removeWidget(self.btn_mute)
                self.row_bottom.insertWidget(0, self.btn_mute)
            if self.btn_solo is not None:
                self.row_top.removeWidget(self.btn_solo)
                self.row_bottom.insertWidget(1, self.btn_solo)
            self.row_top.removeWidget(self.btn_eye)
            idx = 2 if self.btn_solo is not None else (1 if self.btn_mute is not None else 0)
            self.row_bottom.insertWidget(idx, self.btn_eye)
        else:
            self.badge_kind.hide()
            self.row_bottom_widget.hide()
            # Move controls into row_top before btn_del
            idx = self.row_top.indexOf(self.btn_del)
            if idx < 0:
                idx = self.row_top.count()
            if self.btn_mute is not None:
                self.row_bottom.removeWidget(self.btn_mute)
                self.row_top.insertWidget(idx, self.btn_mute)
                idx += 1
            if self.btn_solo is not None:
                self.row_bottom.removeWidget(self.btn_solo)
                self.row_top.insertWidget(idx, self.btn_solo)
                idx += 1
            self.row_bottom.removeWidget(self.btn_eye)
            self.row_top.insertWidget(idx, self.btn_eye)

    def _on_lock(self, on: bool):
        self.track.locked = on
        self.btn_lock.setIcon(icon(
            "lock" if on else "unlock",
            color="#f59e0b" if on else "#64748b",
            size=11,
        ))
        self.btn_lock.setToolTip("Unlock track" if on else "Lock track (prevent edits/moves)")
        self.locked_toggled.emit(self.track.id, on)
        self.update()

    def _on_mute(self, on: bool):
        self.track.muted = on
        self.btn_mute.setIcon(icon(
            "volume-off" if on else "volume",
            color="#ef4444" if on else "#94a3b8",
            size=11,
        ))
        self.btn_mute.setToolTip("Unmute track" if on else "Mute track")
        self.mute_toggled.emit(self.track.id, on)

    def _on_solo(self, on: bool):
        self.track.solo = on
        self.solo_toggled.emit(self.track.id, on)

    def _on_hide(self, on: bool):
        self.track.hidden = on
        self.btn_eye.setIcon(icon(
            "eye-off" if on else "eye",
            color="#64748b" if on else "#94a3b8",
            size=11,
        ))
        self.btn_eye.setToolTip(
            "Show in preview" if on else "Hide from preview · keep dimmed on timeline"
        )
        self.hidden_toggled.emit(self.track.id, on)

    def _on_opacity_changed(self, val: int):
        self.track.opacity = val
        if self.vol_label is not None:
            self.vol_label.setText(f"{val}%")
        self.opacity_changed.emit(self.track.id, val)

    def start_rename(self):
        self.name.hide()
        self.name_edit.setText(self.track.name)
        self.name_edit.show()
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _finish_rename(self):
        if self.name_edit.isHidden():
            return
        self.name_edit.hide()
        self.name.show()
        name = self.name_edit.text().strip()
        if name and name != self.track.name:
            self.name.setText(name)
            self.renamed.emit(self.track.id, name)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.name_edit.isVisible():
            self.name_edit.setText(self.track.name)
            self._finish_rename()
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._near_resize(event.position().y()):
            if self.opacity_slider is not None and self.opacity_slider.geometry().contains(event.position().toPoint()):
                self.opacity_slider.setValue(100)
                event.accept()
                return
            self.start_rename()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _open_menu(self, global_pos: QPoint):
        # Panel owns the menu + working handlers (kind actions, clip ops, etc.).
        self.context_menu_requested.emit(self.track.id, global_pos)

    def contextMenuEvent(self, event):
        # Use contextMenuEvent only — also handling RMB in mousePress causes
        # a double exec() on Windows and the menu appears to never show.
        self._open_menu(event.globalPos())
        event.accept()

    def _apply_selected(self):
        self.setProperty("picked", "true" if self.track.selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def _near_resize(self, y: float) -> bool:
        return y >= self.height() - 5

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._near_resize(event.position().y()):
            self._resize = True
            self._press_y = int(event.globalPosition().y())
            self._press_h = self.track.height
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            multi = bool(event.modifiers() & (
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.MetaModifier
                | Qt.KeyboardModifier.ShiftModifier
            ))
            self.selected.emit(self.track.id, multi)
            self._dragging_track = True
            self._drag_start_y = int(event.globalPosition().y())
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize:
            delta = int(event.globalPosition().y()) - self._press_y
            h = max(TRACK_MIN_H, min(TRACK_MAX_H, self._press_h + delta))
            self.height_changed.emit(self.track.id, h)
            return
        if getattr(self, "_dragging_track", False):
            delta_y = int(event.globalPosition().y()) - self._drag_start_y
            if abs(delta_y) > 16:
                self.reorder_dragged.emit(self.track.id, delta_y)
                self._drag_start_y = int(event.globalPosition().y())
            return
        self.setCursor(
            Qt.CursorShape.SizeVerCursor if self._near_resize(event.position().y())
            else Qt.CursorShape.ArrowCursor
        )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resize = False
        if getattr(self, "_dragging_track", False):
            self._dragging_track = False
            self.unsetCursor()
        super().mouseReleaseEvent(event)

    def refresh_flags(self):
        if self.btn_mute is not None:
            self.btn_mute.blockSignals(True)
            self.btn_mute.setChecked(self.track.muted)
            self.btn_mute.setIcon(icon(
                "volume-off" if self.track.muted else "volume",
                color="#ef4444" if self.track.muted else "#94a3b8",
                size=11,
            ))
            self.btn_mute.setToolTip("Unmute track" if self.track.muted else "Mute track")
            self.btn_mute.blockSignals(False)

        if self.btn_solo is not None:
            self.btn_solo.blockSignals(True)
            self.btn_solo.setChecked(getattr(self.track, "solo", False))
            self.btn_solo.blockSignals(False)

        self.btn_lock.blockSignals(True)
        self.btn_lock.setChecked(self.track.locked)
        self.btn_lock.setIcon(icon(
            "lock" if self.track.locked else "unlock",
            color="#f59e0b" if self.track.locked else "#64748b",
            size=11,
        ))
        self.btn_lock.setToolTip("Unlock track" if self.track.locked else "Lock track (prevent edits/moves)")
        self.btn_lock.blockSignals(False)

        self.btn_eye.blockSignals(True)
        self.btn_eye.setChecked(self.track.hidden)
        self.btn_eye.setIcon(icon(
            "eye-off" if self.track.hidden else "eye",
            color="#64748b" if self.track.hidden else "#94a3b8",
            size=11,
        ))
        self.btn_eye.setToolTip(
            "Show in preview" if self.track.hidden else "Hide from preview · keep dimmed on timeline"
        )
        self.btn_eye.blockSignals(False)

        if self.opacity_slider is not None:
            self.opacity_slider.blockSignals(True)
            self.opacity_slider.setValue(self.track.opacity)
            self.opacity_slider.blockSignals(False)
            if self.vol_label is not None:
                self.vol_label.setText(f"{self.track.opacity}%")

        self._apply_selected()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.track.selected:
            painter.fillRect(self.rect(), accent_wash(32))
        else:
            painter.fillRect(self.rect(), QColor("#0c0f14"))
        # 3px accent color stripe on left edge
        painter.fillRect(0, 0, 3, self.height(), QColor(self.track.color))
        # Bottom divider
        painter.setPen(QColor(TRACK_DIVIDER))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        # Subtle tint overlay if locked
        if self.track.locked:
            painter.fillRect(3, 0, self.width() - 3, self.height() - 1, QColor(245, 158, 11, 14))
        painter.end()

    def apply_height(self, h: int):
        self.setFixedHeight(h)
        self._update_tier()

    def apply_compact(self, compact: bool):
        self._compact = compact
        self.name.setVisible(not compact)
        self.grip.setVisible(not compact)
        self._update_tier()

    def enterEvent(self, event):
        if not self._compact:
            self.btn_del.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.btn_del.hide()
        super().leaveEvent(event)

