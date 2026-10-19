"""Sticky track headers beside the timeline sequence."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QMenu, QScrollArea, QToolButton,
    QVBoxLayout, QWidget,
)

from claynext.constants.timeline_constants import (
    ADD_TRACK_PRESETS, DUB_FOCUS_KINDS, LANE_MAX_W, LANE_MIN_W, RULER_H,
)
from claynext.gui.icons import icon
from claynext.gui.components.inspector.styles import parse_text_style
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
    dub_focus_toggled = Signal(bool)
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
        self._dub_focus = True
        self._init_ui()

    def _build_add_menu(self, parent_widget) -> QMenu:
        menu = QMenu(parent_widget)
        menu.setObjectName("timeline_add_menu")
        for kind, name, _h, col, icn in ADD_TRACK_PRESETS:
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

        # Dub focus: Source, caption text, and Voice — not a pro NLE track mixer
        self.chk_dub_focus = QCheckBox("Dub")
        self.chk_dub_focus.setObjectName("timeline_dub_focus")
        self.chk_dub_focus.setChecked(True)
        self.chk_dub_focus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_dub_focus.setToolTip(
            "Dub focus · Source, caption text, and Voice\n"
            "Uncheck to reveal overlay, audio, and effect lanes"
        )
        self.chk_dub_focus.toggled.connect(self._on_dub_focus)

        hl.addWidget(hide)
        hl.addWidget(self.title, 1)
        hl.addWidget(self.chk_dub_focus)
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

        source_id = next((t.id for t in tracks if t.kind == "video"), "")
        visible_n = sum(1 for t in tracks if self._lane_shown(t.kind))
        self.title.setText(
            f"Tracks ({visible_n})" if self._dub_focus else f"Tracks ({len(tracks)})"
        )

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
            row.set_deletable(track.id != source_id)
            row.setVisible(self._lane_shown(track.kind))
            self.stack_lay.insertWidget(self.stack_lay.count() - 1, row)
            self._rows.append(row)

        # Bottom Quick Add Track Card (hidden in dub focus — translate workflow)
        self._card_add = QToolButton()
        self._card_add.setObjectName("timeline_add_track_card")
        self._card_add.setIcon(icon("plus", color="#818cf8", size=11))
        self._card_add.setText("Add track")
        self._card_add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._card_add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._card_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self._card_add.setFixedHeight(26)
        self._card_add.setToolTip("Add a track · or drop media here")
        self._card_add.setMenu(self._build_add_menu(self._card_add))
        self.stack_lay.insertWidget(self.stack_lay.count() - 1, self._card_add)

        self.apply_compact(self._compact)
        self._apply_dub_focus_ui()

    def _lane_shown(self, kind: str) -> bool:
        return (not self._dub_focus) or kind in DUB_FOCUS_KINDS

    def _on_dub_focus(self, on: bool):
        self._dub_focus = bool(on)
        self._apply_dub_focus_ui()
        self.dub_focus_toggled.emit(self._dub_focus)

    def _apply_dub_focus_ui(self):
        shown = 0
        for row in self._rows:
            vis = self._lane_shown(row.track.kind)
            row.setVisible(vis)
            if vis:
                shown += 1
        if self._card_add is not None:
            self._card_add.setVisible((not self._dub_focus) and (not self._compact))
        total = len(self._rows)
        self.title.setText(
            f"Tracks ({shown})" if self._dub_focus else f"Tracks ({total})"
        )

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
        for row in self._rows:
            row.apply_compact(compact)
        self._apply_dub_focus_ui()

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

