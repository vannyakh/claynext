"""Sticky track headers beside the timeline sequence."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QScrollArea, QToolButton,
    QVBoxLayout, QWidget,
)

from claynext.constants.timeline_constants import (
    LANE_MAX_W, LANE_MIN_W, RULER_H, TRACK_PRESETS,
)
from claynext.gui.icons import icon
from claynext.gui.components.text_styles_panel import parse_text_style
from claynext.gui.components.timeline.helpers import has_drop, paths_from_mime
from claynext.gui.components.timeline.models import TimelineTrack
from claynext.gui.components.timeline.track_header import TrackHeader


class LaneRail(QWidget):
    add_track = Signal(str)
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
    renamed = Signal(str, str)
    reorder_requested = Signal(int, int)
    files_dropped = Signal(list)
    style_dropped = Signal(dict)
    hide_requested = Signal()
    # track_id, global cursor pos — panel owns the real menu + handlers
    context_menu_requested = Signal(str, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("timeline_lane_rail")
        self.setMinimumWidth(LANE_MIN_W)
        self.setMaximumWidth(LANE_MAX_W)
        self._rows: list[TrackHeader] = []
        self._compact = False
        self._card_add = None
        self._init_ui()

    def _build_add_menu(self, parent_widget) -> QMenu:
        menu = QMenu(parent_widget)
        menu.setObjectName("timeline_add_menu")
        for kind, name, _h, col, icn in TRACK_PRESETS:
            act = QAction(icon(icn, color=col, size=13), f"{name} track", self)
            act.triggered.connect(lambda _=False, k=kind: self.add_track.emit(k))
            menu.addAction(act)
        return menu

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QFrame()
        head.setObjectName("timeline_lane_title")
        head.setFixedHeight(RULER_H)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(6, 0, 6, 0)
        hl.setSpacing(6)

        hide = QToolButton()
        hide.setObjectName("timeline_lane_btn")
        hide.setIcon(icon("list", color="#a3a3a3", size=12))
        hide.setFixedSize(18, 18)
        hide.setToolTip("Toggle compact track lane")
        hide.clicked.connect(self.hide_requested.emit)

        self.title = QLabel("Tracks")
        self.title.setObjectName("timeline_lane_title_text")

        self.btn_add = QToolButton()
        self.btn_add.setObjectName("timeline_plus_btn")
        self.btn_add.setIcon(icon("plus", color="#ffffff", size=11))
        self.btn_add.setFixedSize(22, 20)
        self.btn_add.setToolTip("Add timeline track")
        self.btn_add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setMenu(self._build_add_menu(self.btn_add))

        hl.addWidget(hide)
        hl.addWidget(self.title, 1)
        hl.addWidget(self.btn_add)
        root.addWidget(head)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("timeline_lane_scroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background-color: #080c12; border: none;")

        self.stack = QWidget()
        self.stack.setObjectName("timeline_lane_stack")
        self.stack.setStyleSheet("background-color: #080c12;")
        self.stack.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.stack_lay = QVBoxLayout(self.stack)
        self.stack_lay.setContentsMargins(0, 0, 0, 0)
        self.stack_lay.setSpacing(0)
        self.stack_lay.addStretch(1)

        self.scroll.setWidget(self.stack)
        root.addWidget(self.scroll, 1)
        self.setAcceptDrops(True)

    def rebuild(self, tracks: list[TimelineTrack]):
        # Clear existing rows and bottom card
        while self.stack_lay.count() > 1:
            item = self.stack_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._rows.clear()

        # Update track count
        self.title.setText(f"Tracks ({len(tracks)})")

        for track in tracks:
            row = TrackHeader(track)
            row.mute_toggled.connect(self.mute_toggled)
            row.solo_toggled.connect(self.solo_toggled)
            row.locked_toggled.connect(self.locked_toggled)
            row.hidden_toggled.connect(self.hidden_toggled)
            row.opacity_changed.connect(self.opacity_changed)
            row.volume_changed.connect(self.volume_changed)
            row.delete_requested.connect(self.delete_requested)
            row.duplicate_requested.connect(self.duplicate_requested)
            row.selected.connect(self.selected)
            row.height_changed.connect(self.height_changed)
            row.renamed.connect(self.renamed)
            row.reorder_dragged.connect(self._on_row_reorder)
            row.context_menu_requested.connect(self.context_menu_requested)
            self.stack_lay.insertWidget(self.stack_lay.count() - 1, row)
            self._rows.append(row)

        # Bottom Quick Add Track Card
        self._card_add = QToolButton()
        self._card_add.setObjectName("timeline_add_track_card")
        self._card_add.setIcon(icon("plus", color="#818cf8", size=11))
        self._card_add.setText(" Add Track")
        self._card_add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._card_add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._card_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self._card_add.setFixedHeight(28)
        self._card_add.setStyleSheet("""
            QToolButton#timeline_add_track_card {
                background-color: rgba(18, 26, 38, 0.6);
                border: 1px dashed #2a3a50;
                border-radius: 6px;
                color: #94a3b8;
                font-size: 11px;
                font-weight: 500;
                padding: 4px 10px;
                margin: 8px 8px 4px 8px;
            }
            QToolButton#timeline_add_track_card:hover {
                background-color: rgba(99, 102, 241, 0.14);
                border: 1px dashed #6366f1;
                color: #ffffff;
            }
            QToolButton#timeline_add_track_card::menu-indicator {
                image: none;
                width: 0;
            }
        """)
        self._card_add.setToolTip("Click to add a track or drag media files here")
        self._card_add.setMenu(self._build_add_menu(self._card_add))
        self.stack_lay.insertWidget(self.stack_lay.count() - 1, self._card_add)

        self.apply_compact(self._compact)

    def _on_row_reorder(self, track_id: str, delta_y: int):
        from_idx = next((i for i, row in enumerate(self._rows) if row.track.id == track_id), -1)
        if from_idx < 0:
            return
        to_idx = from_idx + (1 if delta_y > 0 else -1)
        if 0 <= to_idx < len(self._rows):
            self.reorder_requested.emit(from_idx, to_idx)

    def apply_compact(self, compact: bool):
        self._compact = compact
        self.title.setVisible(not compact)
        if self._card_add is not None:
            self._card_add.setVisible(not compact)
        for row in self._rows:
            row.apply_compact(compact)

    def refresh_flags(self):
        for row in self._rows:
            row.refresh_flags()

    def sync_heights(self, tracks: list[TimelineTrack]):
        for row, track in zip(self._rows, tracks):
            if row.height() != track.height:
                row.apply_height(track.height)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if has_drop(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        style = parse_text_style(event.mimeData())
        if style:
            event.acceptProposedAction()
            self.style_dropped.emit(style)
            return
        paths = paths_from_mime(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self.files_dropped.emit(paths)
        else:
            event.ignore()
