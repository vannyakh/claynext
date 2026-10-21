"""Timeline shell: tool row, lane rail, ruler, and sequence scroll."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, Signal, QSize, QThreadPool, QPoint, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QScrollArea, QSizePolicy, QFrame, QSplitter, QToolButton, QMenu, QButtonGroup,
    QFileDialog,
)

from claynext.constants.theme_constants import COLOR_ACCENT_ROSE
from claynext.constants.timeline_constants import (
    FX_KINDS, LANE_COLLAPSED_W, LANE_MAX_W, LANE_MIN_W, LANE_RATIO, LANE_W, OVERLAY_KINDS, PRESET,
)
from claynext.adapters.ffmpeg_adapter import probe_duration
from claynext.adapters.ffmpeg_service import (
    extract_audio, extract_wave_envelope, normalize_envelope, probe_media,
)
from claynext.gui.icons import icon
from claynext.models.text_style import apply_case, clean_text_style
from claynext.models.thumbnails import extract_filmstrip
from claynext.models.adjust import adjust_filter, clean_adjust
from claynext.models.canvas import canvas_filter, clean_canvas, is_neutral
from claynext.models.fx import clean_fx, fx_filters, fx_label
from claynext.gui.worker import Worker
from claynext.utils.paths import OUTPUTS_DIR, STUDIO_CACHE
from claynext.gui.components.render.shape import shape_drawing
from claynext.gui.components.render.text import (
    burn_metrics, caption_width, fit_caption, font_for, measure_box, wrap_text,
)
from claynext.gui.components.timeline.canvas import TimelineCanvas
from claynext.gui.components.timeline.helpers import fmt_ms, fmt_tc, image_frame, kind_for_path, paths_from_mime
from claynext.gui.components.timeline.lane_rail import LaneRail
from claynext.gui.components.timeline.models import TimelineClip
from claynext.gui.components.timeline.recorder import VoiceRecorder
from claynext.gui.components.timeline.ruler import TimelineRuler
from claynext.gui.components.timeline.sequence_bar import SequenceBar
from claynext.gui.components.timeline.scrub_tip import TimelineScrubTip
from claynext.gui.components.timeline.track_menu import TrackMenuHandlers, open_track_menu

_VO_TRACK = "Voice-over"


class TimelinePanel(QWidget):
    seek_requested = Signal(int)
    audio_muted = Signal(bool)
    mix_changed = Signal(float, float, float)
    auto_mix_done = Signal(int, int, bool)
    auto_mix_failed = Signal(str)
    media_dropped = Signal(str)
    clips_changed = Signal()
    clip_selected = Signal(str)
    selection_changed = Signal(str, str)
    composition_changed = Signal(int)
    record_toggled = Signal(bool)
    record_message = Signal(str, bool)
    transition_split_clicked = Signal(str, int)  # left_clip_id, cut_ms
    transition_selected = Signal(str)  # left_clip_id
    transcript_action = Signal(str)  # show|retry|translate|tts|all|import|export
    studio_action = Signal(str)  # vocal|translate|scan|generate|import_srt|export_srt|bgm|export_video

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("timeline_panel")
        self.setAcceptDrops(True)
        self._pool = QThreadPool.globalInstance()
        self.speech_source = ""
        self._strip_worker = None
        self._wave_worker = None
        self._scrub_tip: TimelineScrubTip | None = None
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sequences = SequenceBar(self)
        self.sequences.picked.connect(self._on_composition)

        tools = QFrame()
        tools.setObjectName("timeline_tools")
        row = QHBoxLayout(tools)
        row.setContentsMargins(8, 2, 8, 2)
        row.setSpacing(6)

        # ── Left: History, Tool Modes & Clip Actions ──
        left_box = QHBoxLayout()
        left_box.setContentsMargins(0, 0, 0, 0)
        left_box.setSpacing(4)

        undo_tip = f"Undo ({QKeySequence(QKeySequence.StandardKey.Undo).toString(QKeySequence.SequenceFormat.NativeText)})"
        redo_tip = f"Redo ({QKeySequence(QKeySequence.StandardKey.Redo).toString(QKeySequence.SequenceFormat.NativeText)})"
        self.btn_undo = self._tool_btn("undo", undo_tip)
        self.btn_redo = self._tool_btn("redo", redo_tip)
        left_box.addWidget(self.btn_undo)
        left_box.addWidget(self.btn_redo)
        left_box.addWidget(self._tool_sep())

        # Tool Modes: Select (V) vs Razor (C)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)

        self.btn_tool_select = self._tool_btn("cursor", "Selection Tool (V) · Move, trim, select clips", checkable=True)
        self.btn_tool_select.setChecked(True)
        self.tool_group.addButton(self.btn_tool_select)
        left_box.addWidget(self.btn_tool_select)

        self.btn_tool_razor = self._tool_btn("scissors", "Razor Tool (C) · Click any clip to split at mouse position", checkable=True)
        self.tool_group.addButton(self.btn_tool_razor)
        left_box.addWidget(self.btn_tool_razor)
        left_box.addWidget(self._tool_sep())

        self.btn_tool_select.toggled.connect(lambda on: self._on_tool_mode_changed("select" if on else "razor"))

        # Clip Editing Operations
        self.btn_split = self._tool_btn("split", "Split clip at playhead (S)")
        self.btn_split.clicked.connect(self._split_at_playhead)
        left_box.addWidget(self.btn_split)

        self.btn_dup = self._tool_btn("copy", "Duplicate selected clips (⌘D / Ctrl+D)")
        self.btn_dup.clicked.connect(self._duplicate_selected)
        left_box.addWidget(self.btn_dup)

        self.btn_delete = self._tool_btn("trash", "Delete selected clips (Delete / Backspace)")
        left_box.addWidget(self.btn_delete)
        left_box.addWidget(self._tool_sep())

        self.btn_snap = self._tool_btn("snap", "Snap edges to the playhead and other clips (N)", checkable=True)
        self.btn_snap.setChecked(True)
        self.btn_snap.toggled.connect(self._set_snap)
        left_box.addWidget(self.btn_snap)

        self.duck_level = 0.2
        self.duck_fade_ms = 150
        self.btn_duck = self._tool_btn("duck", "Auto mix · replace original speech, keep music and effects (D)")
        self._duck_tip = self.btn_duck.toolTip()
        self.btn_duck.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        duck_menu = QMenu(self.btn_duck)
        duck_menu.setObjectName("media_lib_menu")
        self.act_auto_mix = duck_menu.addAction("Auto mix · detect original voices")
        self.act_auto_mix.setToolTip("Find every spoken line and swap only those spans to the music bed")
        self.act_auto_mix.setShortcut(QKeySequence("D"))
        self.act_auto_mix.triggered.connect(lambda: self.auto_mix())
        self.act_speech = duck_menu.addAction("Remove speech under voice")
        self.act_speech.setToolTip("Mute only the original speech under dubbed lines")
        self.act_speech.triggered.connect(lambda: self.auto_duck(0.0))
        self.act_duck = duck_menu.addAction("Duck footage under voice")
        self.act_duck.setToolTip("Duck background footage volume under active voice spans")
        self.act_duck.triggered.connect(lambda: self.auto_duck(self.duck_level))
        duck_menu.addSeparator()
        act_clear = duck_menu.addAction("Clear key points")
        act_clear.triggered.connect(lambda: self.canvas.clear_keys())
        duck_menu.aboutToShow.connect(self._refresh_duck_menu)
        self.btn_duck.setMenu(duck_menu)
        left_box.addWidget(self.btn_duck)

        self.btn_rec = QToolButton()
        self.btn_rec.setObjectName("timeline_rec_btn")
        self.btn_rec.setIcon(icon("mic", color="#d4d4d4", size=14))
        self.btn_rec.setText("Rec")
        self.btn_rec.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_rec.setToolTip("Record voice-over at the playhead (R) · use headphones")
        self.btn_rec.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.btn_rec.setProperty("recording", False)
        self.btn_rec.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rec_menu = QMenu(self.btn_rec)
        self.rec_menu.setObjectName("media_lib_menu")
        self.rec_menu.aboutToShow.connect(self._fill_rec_menu)
        self.btn_rec.setMenu(self.rec_menu)
        self.btn_rec.clicked.connect(self.toggle_recording)
        left_box.addWidget(self.btn_rec)
        left_box.addWidget(self._tool_sep())

        # Dubbing feature tools — one menu keeps the bar lean
        self.btn_studio = self._tool_btn(
            "sparkles", "Studio tools · isolate, translate, voices, export"
        )
        self.btn_studio.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        studio_menu = QMenu(self.btn_studio)
        studio_menu.setObjectName("media_lib_menu")
        for tip, action, icn in (
            ("Vocal isolation · extract BGM bed", "vocal", "volume"),
            ("AI translate subtitles", "translate", "globe"),
            ("Scan characters & assign voices", "scan", "chat"),
            ("Generate all dialogue audio", "generate", "sparkles"),
            ("Import SRT / VTT / JSON", "import_srt", "folder"),
            ("Export SRT subtitles", "export_srt", "download"),
            ("Load background music", "bgm", "activity"),
            ("Export video", "export_video", "video"),
        ):
            act = studio_menu.addAction(icon(icn, color="#cdd8e5", size=13), tip)
            act.triggered.connect(lambda _=False, a=action: self.studio_action.emit(a))
            setattr(self, f"act_studio_{action}", act)
        self.btn_studio.setMenu(studio_menu)
        left_box.addWidget(self.btn_studio)

        row.addLayout(left_box)
        row.addStretch(1)

        # ── Center: Cut Navigation & Digital Timecode Badge ──
        center_box = QHBoxLayout()
        center_box.setContentsMargins(0, 0, 0, 0)
        center_box.setSpacing(4)

        self.btn_prev_cut = self._tool_btn("chevron-left", "Jump to Previous Cut ([)")
        self.btn_prev_cut.clicked.connect(self._jump_prev_cut)
        center_box.addWidget(self.btn_prev_cut)

        self.lbl_timecode = QLabel()
        self.lbl_timecode.setObjectName("timeline_timecode_badge")
        self.lbl_timecode.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_timecode.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_timecode.setToolTip("Current playhead position / Sequence duration")
        center_box.addWidget(self.lbl_timecode)

        self.btn_next_cut = self._tool_btn("chevron-right", "Jump to Next Cut (])")
        self.btn_next_cut.clicked.connect(self._jump_next_cut)
        center_box.addWidget(self.btn_next_cut)

        row.addLayout(center_box)
        row.addStretch(1)

        # ── Right: Fit, Zoom & View Displays ──
        right_box = QHBoxLayout()
        right_box.setContentsMargins(0, 0, 0, 0)
        right_box.setSpacing(4)

        self.btn_zoom_fit = self._tool_btn("aspect", "Fit sequence to window (Shift+Z)")
        self.btn_zoom_fit.clicked.connect(self.zoom_to_fit)
        right_box.addWidget(self.btn_zoom_fit)
        right_box.addWidget(self._tool_sep())

        self.btn_zoom_out = self._tool_btn("zoom-out", "Zoom out (−)")
        self.btn_zoom_out.clicked.connect(lambda: self.zoom.setValue(self.zoom.value() - 8))
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setObjectName("timeline_zoom")
        self.zoom.setRange(12, 140)
        self.zoom.setValue(36)
        self.zoom.setFixedWidth(88)
        self.zoom.setToolTip("Zoom timeline (⌘± / Ctrl±)")
        self.zoom.valueChanged.connect(self._on_zoom)
        self.btn_zoom_in = self._tool_btn("zoom-in", "Zoom in (+)")
        self.btn_zoom_in.clicked.connect(lambda: self.zoom.setValue(self.zoom.value() + 8))

        right_box.addWidget(self.btn_zoom_out)
        right_box.addWidget(self.zoom)
        right_box.addWidget(self.btn_zoom_in)
        right_box.addWidget(self._tool_sep())

        self.btn_toggle_wave = self._tool_btn("activity", "Toggle audio waveforms", checkable=True)
        self.btn_toggle_wave.setChecked(True)
        self.btn_toggle_wave.toggled.connect(self._on_toggle_waveforms)
        right_box.addWidget(self.btn_toggle_wave)

        self._compact_tracks = False
        self.btn_toggle_tracks = self._tool_btn("timeline", "Toggle compact track heights", checkable=True)
        self.btn_toggle_tracks.setChecked(False)
        self.btn_toggle_tracks.toggled.connect(self._on_toggle_compact_tracks)
        right_box.addWidget(self.btn_toggle_tracks)

        row.addLayout(right_box)
        root.addWidget(tools)

        self.canvas = TimelineCanvas()
        self.canvas.seek_requested.connect(self._on_canvas_seek)
        self.canvas.clips_changed.connect(self._on_clips_changed)
        self.canvas.clip_selected.connect(self._on_clip_selected)
        self.canvas.files_dropped.connect(self._on_files_dropped)
        self.canvas.track_picked.connect(self._on_track_picked)
        self.canvas.height_changed.connect(self._resize_track)
        self.canvas.gains_changed.connect(self._emit_mix)
        self.canvas.history_changed.connect(self._sync_history)
        self.canvas.transition_split_clicked.connect(self.transition_split_clicked)
        self.canvas.transition_selected.connect(self.transition_selected)
        self.btn_undo.clicked.connect(self._undo)
        self.btn_redo.clicked.connect(self._redo)
        self.btn_delete.clicked.connect(self.canvas.remove_selected)

        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.setObjectName("timeline_split")
        self.split.setChildrenCollapsible(False)

        self.rail = LaneRail()
        self.rail.add_track.connect(self._add_track)
        self.rail.dub_focus_toggled.connect(self._on_dub_focus)
        self.rail.mute_toggled.connect(self._mute_track)
        self.rail.solo_toggled.connect(self._solo_track)
        self.rail.locked_toggled.connect(self._lock_track)
        self.rail.hidden_toggled.connect(self._hide_track)
        self.rail.opacity_changed.connect(self._opacity_track)
        self.rail.volume_changed.connect(self._volume_track)
        self.rail.delete_requested.connect(self._delete_track)
        self.rail.duplicate_requested.connect(self._duplicate_track)
        self.rail.selected.connect(self._on_track_picked)
        self.rail.height_changed.connect(self._resize_track)
        self.rail.renamed.connect(self._rename_track)
        self.rail.reorder_requested.connect(self._reorder_track)
        self.rail.files_dropped.connect(lambda paths: self._on_files_dropped(paths, ""))
        self.rail.style_dropped.connect(self.add_text_style)
        self.rail.hide_requested.connect(self._toggle_lane)
        self.rail.setMinimumWidth(LANE_COLLAPSED_W)
        self._lane_hidden = False
        self._layouting = False

        seq = QWidget()
        seq.setObjectName("timeline_sequence")
        seq_l = QVBoxLayout(seq)
        seq_l.setContentsMargins(0, 0, 0, 0)
        seq_l.setSpacing(0)
        self.ruler = TimelineRuler(self.canvas)
        self.ruler.seek_requested.connect(self._on_ruler_seek)
        seq_l.addWidget(self.ruler)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("timeline_scroll")
        self.scroll.setWidgetResizable(False)
        self.scroll.setWidget(self.canvas)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.horizontalScrollBar().valueChanged.connect(self.ruler.set_offset)
        self.scroll.verticalScrollBar().valueChanged.connect(self._sync_v)
        self.rail.scroll.verticalScrollBar().valueChanged.connect(self._sync_v_from_rail)
        self.canvas.context_menu_requested.connect(self._open_canvas_context_menu)
        self.rail.context_menu_requested.connect(self._open_header_context_menu)
        self.canvas.hover_scrub_changed.connect(self._on_hover_scrub)
        self._scrub_tip = TimelineScrubTip(self)
        seq_l.addWidget(self.scroll, 1)

        self.split.addWidget(self.rail)
        self.split.addWidget(seq)
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([LANE_W, 800])
        root.addWidget(self.split, 1)

        QShortcut(QKeySequence("Delete"), self).activated.connect(self.canvas.remove_selected)
        QShortcut(QKeySequence("Backspace"), self).activated.connect(self.canvas.remove_selected)
        QShortcut(QKeySequence("S"), self).activated.connect(self._split_at_playhead)
        QShortcut(QKeySequence("V"), self).activated.connect(lambda: self.btn_tool_select.setChecked(True))
        QShortcut(QKeySequence("C"), self).activated.connect(lambda: self.btn_tool_razor.setChecked(True))
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self._duplicate_selected)
        QShortcut(QKeySequence("Shift+Z"), self).activated.connect(self.zoom_to_fit)
        QShortcut(QKeySequence("["), self).activated.connect(self._jump_prev_cut)
        QShortcut(QKeySequence("]"), self).activated.connect(self._jump_next_cut)
        QShortcut(QKeySequence("N"), self).activated.connect(self.btn_snap.toggle)
        QShortcut(QKeySequence("D"), self).activated.connect(lambda: self.auto_mix())
        QShortcut(QKeySequence("R"), self).activated.connect(self.toggle_recording)
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(lambda: self.zoom.setValue(self.zoom.value() + 8))
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(lambda: self.zoom.setValue(self.zoom.value() - 8))
        QShortcut(QKeySequence("L"), self).activated.connect(self._toggle_selected_track_lock)
        QShortcut(QKeySequence("M"), self).activated.connect(self._toggle_selected_track_mute)
        # Undo/Redo shortcuts are bound on the dubbing window so ⌘Z works while the timeline is open.
        self.act_auto_mix.setShortcut(QKeySequence())  # panel shortcut owns D
        QShortcut(QKeySequence("Ctrl+Shift+E"), self).activated.connect(
            lambda: self.extract_audio_from_video(to_track=True)
        )
        self._extract_busy = False
        self.recorder = VoiceRecorder(self)
        self.recorder.started.connect(self._on_rec_started)
        self.recorder.elapsed.connect(self._on_rec_elapsed)
        self.recorder.finished.connect(self._on_rec_finished)
        self.recorder.failed.connect(self._on_rec_failed)
        self._sync_history()
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._rebuild_rail()
        self._update_timecode_display()
        self._refresh_meta()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_timeline()

    def showEvent(self, event):
        super().showEvent(event)
        self._layout_timeline()

    def _layout_timeline(self):
        if self._layouting or not hasattr(self, "split"):
            return
        self._layouting = True
        w = max(1, self.width())
        sizes = self.split.sizes()
        current_lane = sizes[0] if sizes and sizes[0] > 0 else LANE_W
        if self._lane_hidden:
            lane = LANE_COLLAPSED_W
        elif current_lane >= LANE_MIN_W:
            lane = max(LANE_MIN_W, min(LANE_MAX_W, current_lane))
        else:
            lane = max(LANE_MIN_W, min(LANE_MAX_W, int(w * LANE_RATIO)))
        self.split.setSizes([lane, max(80, w - lane)])
        self.rail.apply_compact(self._lane_hidden or lane < 76)
        vp = self.scroll.viewport()
        self.canvas.fit_to_height(max(48, vp.height()))
        self.rail.sync_heights(self.canvas.tracks)
        self._layouting = False

    def _toggle_selected_track_lock(self):
        for t in self.canvas.tracks:
            if t.selected:
                self._lock_track(t.id, not t.locked)
                break

    def _toggle_selected_track_mute(self):
        for t in self.canvas.tracks:
            if t.selected and t.kind in {"voice", "audio"} and not getattr(t, "silent", False):
                self._mute_track(t.id, not t.muted)
                break

    def _toggle_lane(self):
        self._lane_hidden = not self._lane_hidden
        self._layout_timeline()

    def _sync_v(self, val: int):
        bar = self.rail.scroll.verticalScrollBar()
        if bar.value() != val:
            bar.setValue(val)

    def _sync_v_from_rail(self, val: int):
        bar = self.scroll.verticalScrollBar()
        if bar.value() != val:
            bar.setValue(val)

    def _undo(self):
        self.canvas.undo()
        self._rebuild_rail()

    def _redo(self):
        self.canvas.redo()
        self._rebuild_rail()

    def _sync_history(self):
        self.btn_undo.setEnabled(self.canvas.can_undo())
        self.btn_redo.setEnabled(self.canvas.can_redo())

    def gains(self) -> tuple[float, float, float]:
        return self.canvas.gains()

    def _emit_mix(self):
        source, voice, bed = self.canvas.gains()
        self.mix_changed.emit(source, voice, bed)

    def _refresh_duck_menu(self):
        self.act_duck.setText(f"Duck footage under voice ({int(self.duck_level * 100)}%)")
        ready = bool(self.canvas.bed_path)
        self.act_speech.setText(
            "Remove speech under voice (keep music + effects)" if ready
            else "Mute footage under voice (music bed still building)"
        )

    def set_speech_bed(self, path: str):
        self.canvas.bed_path = path if path and os.path.isfile(path) else ""
        self.act_duck.setEnabled(True)
        self._emit_mix()

    def _split_at_playhead(self):
        count = self.canvas.split_at_playhead()
        if count:
            self._refresh_meta()

    def _on_tool_mode_changed(self, mode: str):
        self.canvas.set_tool_mode(mode)

    def _duplicate_selected(self):
        count = self.canvas.duplicate_selected()
        if count:
            self._refresh_meta()

    def _jump_prev_cut(self):
        self.canvas.jump_to_prev_cut()
        self._update_timecode_display()
        self.ruler.update()
        self._follow_playhead()

    def _jump_next_cut(self):
        self.canvas.jump_to_next_cut()
        self._update_timecode_display()
        self.ruler.update()
        self._follow_playhead()

    def _on_toggle_waveforms(self, on: bool):
        self.canvas.set_show_waveforms(on)

    def _on_toggle_compact_tracks(self, compact: bool):
        self._compact_tracks = compact
        for t in self.canvas.tracks:
            if compact:
                h = 32 if t.kind == "video" else 26
            else:
                preset_info = PRESET.get(t.kind)
                h = preset_info[1] if preset_info else 40
            self.canvas.set_track_height(t.id, h)
        self.rail.sync_heights(self.canvas.tracks)
        self.canvas._relayout(notify=False)

    def _on_dub_focus(self, on: bool):
        """Show Source, caption text, and Voice lanes for movie dubbing."""
        self.canvas.set_dub_focus(on)
        self.rail.sync_heights(self.canvas.tracks)

    def zoom_to_fit(self):
        dur_sec = max(1.0, self.canvas.duration_ms / 1000.0)
        vp_w = max(100, self.scroll.viewport().width() - 40)
        target_pps = max(12.0, min(140.0, vp_w / dur_sec))
        self.zoom.setValue(int(target_pps))

    def _update_timecode_display(self):
        if not hasattr(self, "lbl_timecode"):
            return
        curr = fmt_tc(self.canvas.playhead_ms)
        dur = fmt_tc(self.canvas.duration_ms)
        self.lbl_timecode.setText(
            f'<span style="color:#f8fafc; font-weight:600;">{curr}</span> '
            f'<span style="color:#475569;">/</span> '
            f'<span style="color:#94a3b8;">{dur}</span>'
        )

    def _on_canvas_seek(self, ms: int):
        self._update_timecode_display()
        self.ruler.update()
        self.seek_requested.emit(ms)

    @staticmethod
    def _tool_sep() -> QFrame:
        line = QFrame()
        line.setObjectName("timeline_tool_sep")
        line.setFixedWidth(1)
        line.setFixedHeight(16)
        return line

    def _tool_btn(self, name: str, tip: str, *, checkable: bool = False) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("timeline_tool_btn")
        btn.setIcon(icon(name, color="#d4d4d4", size=14))
        btn.setToolTip(tip)
        btn.setFixedSize(24, 24)
        btn.setIconSize(QSize(14, 14))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setCheckable(checkable)
        btn.setAutoRaise(True)
        return btn

    def _set_snap(self, on: bool):
        self.canvas.snap = bool(on)
        self.btn_snap.setToolTip("Snapping on (N)" if on else "Snapping off (N)")
        self.btn_snap.setIcon(icon("snap", color="#f8fafc" if on else "#d4d4d4", size=14))

    def _on_zoom(self, val: int):
        self.canvas.set_zoom(val)
        self.ruler.update()
        self._follow_playhead()

    def _on_ruler_seek(self, ms: int):
        self.canvas.set_playhead_ms(ms)
        self._update_timecode_display()
        self.seek_requested.emit(ms)
        self.ruler.update()

    def _rebuild_rail(self, keep_empty: str = ""):
        """Drop empty lanes, then refresh track headers. The top row is layer 1."""
        changed = self.canvas.prune_transition_tracks()
        if not getattr(self.canvas, "_suspend_prune", False):
            if self.canvas.silence_picture():
                changed = True
            if self.canvas.unpack_voice_conflicts():
                changed = True
            changed = self.canvas.prune_empty_tracks(keep_empty) or changed
        if changed:
            self.canvas._relayout(notify=False)
        self.rail.rebuild(self.canvas.tracks)

    def _on_clips_changed(self):
        self._rebuild_rail()
        self._refresh_meta()
        self.ruler.update()
        self.clips_changed.emit()

    def add_text_style(self, style: dict) -> TimelineClip | None:
        if not style:
            return None
        kind = str(style.get("kind") or "text")
        if kind == "transition":
            # Only on main Cover (video) source — never Voice / Audio / FX.
            video = next((t for t in self.canvas.tracks if t.kind == "video"), None)
            if video is None:
                return None

            def _on_cover(clip) -> bool:
                return bool(clip and clip.track_id == video.id)

            tr_dict = {
                "transition": style.get("transition", "fade_black"),
                "intensity": int(style.get("intensity", 80)),
                "duration_ms": max(200, min(6000, int(style.get("duration_ms", 1200)))),
                "name": str(style.get("name") or "Transition"),
            }
            target_clip = None
            if self.canvas.selected_transition_clip_id:
                cand = self.canvas.clip_by_id(self.canvas.selected_transition_clip_id)
                if _on_cover(cand):
                    target_clip = cand
            elif self.canvas.selected_seam_clip_id:
                cand = self.canvas.clip_by_id(self.canvas.selected_seam_clip_id)
                if _on_cover(cand):
                    target_clip = cand

            if not target_clip:
                seams = self.canvas.find_split_seams()
                if seams:
                    best_seam = min(seams, key=lambda s: abs(s["cut_ms"] - self.canvas.playhead_ms))
                    target_clip = best_seam["left_clip"]

            if not target_clip:
                ms = self.canvas.playhead_ms
                for clip in self.canvas.clips:
                    if (
                        clip.track_id == video.id
                        and not clip.locked
                        and clip.start_ms + 100 < ms < clip.end_ms - 100
                    ):
                        new_clip = self.canvas.split_clip(clip, ms)
                        if new_clip:
                            target_clip = clip
                            break

            if target_clip:
                self.canvas.push_history()
                target_clip.extra["transition"] = tr_dict
                self.canvas.selected_transition_clip_id = target_clip.id
                self.canvas.selected_seam_clip_id = target_clip.id
                self._on_clips_changed()
                self.canvas.update()
                return target_clip
            return None

        dur = 4000
        start = None
        fit = self.canvas.fit_master_placement(kind)
        if fit:
            start, dur = fit
        elif self.canvas.duration_ms:
            dur = max(800, min(8000, self.canvas.duration_ms - self.canvas.playhead_ms or 4000))
        if kind in FX_KINDS:
            return self.canvas.add_clip(kind, fx_label(kind, style), duration_ms=dur, extra={"fx": dict(style)})
        label = str(style.get("text") or style.get("name") or kind)
        return self.canvas.add_clip(
            kind, label, duration_ms=dur, extra={"overlay": dict(style)}, start_ms=start,
        )

    def apply_watermark(self, style: dict) -> TimelineClip | None:
        """Replace the current watermark and cover the whole movie with `style`."""
        if not style:
            return None
        self.canvas.push_history()
        drop = {
            clip.id
            for clip in self.canvas.clips
            if clip.extra.get("watermark")
            or (
                isinstance(clip.extra.get("overlay"), dict)
                and clip.extra["overlay"].get("watermark")
            )
        }
        if drop:
            self.canvas.clips = [clip for clip in self.canvas.clips if clip.id not in drop]
            self.canvas.selected_ids -= drop
        mark = dict(style)
        mark["watermark"] = True
        clip = self.add_text_style(mark)
        if clip is None:
            if drop:
                self.canvas.prune_empty_tracks()
                self._on_clips_changed()
            return None
        clip.extra["watermark"] = True
        overlay = clip.extra.get("overlay")
        if isinstance(overlay, dict):
            overlay["watermark"] = True
            if mark.get("path"):
                overlay["path"] = mark["path"]
                clip.extra["path"] = mark["path"]
        track = self.canvas.track_by_id(clip.track_id)
        mates = [row for row in self.canvas.clips if row.track_id == clip.track_id]
        if track is not None and mates and all(row.extra.get("watermark") for row in mates):
            track.name = "Watermark"
            self.rail.refresh_flags()
        return clip

    def update_watermark(self, clip_id: str, style: dict) -> TimelineClip | None:
        """Write a style window result onto the watermark already on the timeline."""
        clip = self.canvas.clip_by_id(clip_id)
        if clip is None:
            return self.apply_watermark(style)
        self.canvas.push_history()
        mark = dict(style)
        mark["watermark"] = True
        mark["id"] = clip.id
        kind = str(mark.get("kind") or clip.kind or "text")
        clip.kind = kind
        clip.label = str(mark.get("text") or mark.get("name") or clip.label)
        clip.extra["watermark"] = True
        if mark.get("path"):
            clip.extra["path"] = mark["path"]
        clip.extra["overlay"] = mark
        self.canvas.update()
        self._on_clips_changed()
        return clip

    def overlay_clips(self, ms: int | None = None) -> list[TimelineClip]:
        t = self.canvas.playhead_ms if ms is None else int(ms)
        span = self.canvas.master_span()
        if span:
            start, length = span
            if not (start <= t < start + length):
                return []
        return [
            c for c in self.canvas.clips
            if c.kind in OVERLAY_KINDS and c.start_ms <= t < c.end_ms and not self._track_hidden(c)
        ]

    def export_fx(self, include_hidden: bool = False) -> list[dict]:
        """Effect and filter clips as {"kind", "effect" | "filter", "intensity", "start_ms", "end_ms"}, plus in-split transitions."""
        order = {t.id: i for i, t in enumerate(self.canvas.tracks)}
        # Top lane (index 0) is the front layer, so it is applied last.
        rows = []
        for clip in sorted(self.canvas.clips, key=lambda c: (-order.get(c.track_id, 0), c.start_ms)):
            if clip.kind not in FX_KINDS or (not include_hidden and self._track_hidden(clip)):
                continue
            rows.append({"kind": clip.kind, **clean_fx(clip.kind, clip.extra.get("fx")),
                         "start_ms": clip.start_ms, "end_ms": clip.end_ms, "track_id": clip.track_id})
        for clip in self.canvas.clips:
            if clip.kind != "video" or (not include_hidden and self._track_hidden(clip)):
                continue
            for fx in clip.extra.get("applied_fx") or []:
                if not isinstance(fx, dict):
                    continue
                kind = str(fx.get("kind") or "effect")
                if kind not in FX_KINDS:
                    kind = "effect"
                rows.append({
                    "kind": kind,
                    **clean_fx(kind, fx),
                    "start_ms": clip.start_ms,
                    "end_ms": clip.end_ms,
                    "track_id": clip.track_id,
                    "clip_id": clip.id,
                })
        video_ids = {t.id for t in self.canvas.tracks if t.kind == "video"}
        primary_video = next((t.id for t in self.canvas.tracks if t.kind == "video"), "")
        for clip in sorted(self.canvas.clips, key=lambda c: (-order.get(c.track_id, 0), c.start_ms)):
            # Transitions only on the main Cover source track.
            if clip.track_id != primary_video or clip.track_id not in video_ids:
                continue
            tr = clip.extra.get("transition")
            if not tr or not isinstance(tr, dict):
                continue
            if not include_hidden and self._track_hidden(clip):
                continue
            dur = max(200, min(6000, int(tr.get("duration_ms", 1200))))
            half = dur // 2
            cut_ms = clip.end_ms
            start_ms = max(clip.start_ms, cut_ms - half)
            end_ms = cut_ms + half
            rows.append({
                "kind": "transition",
                "transition": tr.get("transition", "fade_black"),
                "intensity": int(tr.get("intensity", 80)),
                "start_ms": start_ms,
                "end_ms": end_ms,
                "track_id": clip.track_id,
                "clip_id": clip.id,
            })
        return rows

    def apply_fx(self, rows: list[dict]):
        self.canvas.clips = [c for c in self.canvas.clips if c.kind not in FX_KINDS]
        for row in rows or []:
            kind = str(row.get("kind") or "")
            if kind == "transition":
                # Restore only onto the main Cover (video) source track.
                primary = next((t.id for t in self.canvas.tracks if t.kind == "video"), "")
                cid = str(row.get("clip_id") or "")
                clip = self.canvas.clip_by_id(cid) if cid else None
                if clip and clip.track_id != primary:
                    clip = None
                if not clip and primary:
                    mid = int(row.get("start_ms", 0)) + (int(row.get("end_ms", 0)) - int(row.get("start_ms", 0))) // 2
                    for c in self.canvas.clips:
                        if c.track_id == primary and abs(c.end_ms - mid) <= 100:
                            clip = c
                            break
                if clip:
                    dur = int(row.get("end_ms", 0)) - int(row.get("start_ms", 0))
                    clip.extra["transition"] = {
                        "transition": row.get("transition", "fade_black"),
                        "intensity": int(row.get("intensity", 80)),
                        "duration_ms": max(200, min(6000, dur if dur > 0 else 1200)),
                        "name": str(row.get("name") or "Transition"),
                    }
                continue
            start, end = int(row.get("start_ms") or 0), int(row.get("end_ms") or 0)
            if kind not in FX_KINDS or end <= start:
                continue
            track = self.canvas.track_by_id(str(row.get("track_id") or ""))
            self.canvas.add_clip(kind, fx_label(kind, row), duration_ms=end - start, extra={"fx": dict(row)},
                                 track_id=track.id if track and track.kind == kind else "", start_ms=start)
        self.canvas.selected_ids.clear()
        self._rebuild_rail()

    def update_fx_extra(self, clip_id: str, fx: dict):
        for clip in self.canvas.clips:
            if clip.id == clip_id and clip.kind in FX_KINDS:
                clip.extra["fx"] = clean_fx(clip.kind, fx)
                clip.label = fx_label(clip.kind, clip.extra["fx"])
                self.canvas.update()
                return

    def _track_hidden(self, clip: TimelineClip) -> bool:
        track = self.canvas.track_by_id(clip.track_id)
        return bool(track and track.hidden)

    def export_overlays(self, include_hidden: bool = False, aspect: float | None = None) -> list[dict]:
        """Overlay clips for saving or burning; with the picture `aspect`, live captions carry their wrapped lines."""
        from claynext.gui.components.inspector.google_fonts import register_google_fonts

        register_google_fonts()
        order = {track.id: index for index, track in enumerate(self.canvas.tracks)}
        rows = []
        overlay_clips = sorted(
            (clip for clip in self.canvas.clips if clip.kind in OVERLAY_KINDS),
            key=lambda clip: (-order.get(clip.track_id, 0), clip.start_ms),
        )
        for clip in overlay_clips:
            if clip.kind not in OVERLAY_KINDS:
                continue
            if not include_hidden and self._track_hidden(clip):
                continue
            ov = dict(clip.extra.get("overlay") or {})
            ov["id"] = clip.id
            ov["kind"] = clip.kind
            ov["start_ms"] = clip.start_ms
            ov["end_ms"] = clip.end_ms
            ov.pop("duration_ms", None)
            if clip.extra.get("path"):
                ov["path"] = clip.extra["path"]
            if clip.extra.get("watermark"):
                ov["watermark"] = True
            if clip.kind in {"text", "caption"}:
                text = str(ov.get("text") or "")
                if clip.kind == "caption" and aspect:
                    style = clean_text_style(ov)
                    limit = caption_width(float(ov.get("x", 0.5)), aspect, style)
                    if style.get("caption_fit"):
                        fitted, text = fit_caption(style, text, limit)
                        ov["font_size"] = fitted["font_size"]
                    else:
                        text = wrap_text(style, text, limit)
                    ov["text"] = text
                ov["box_w"], ov["box_h"] = measure_box(ov, text)
                if aspect:
                    ov.update(self._burn_font(ov, text))
            if clip.kind == "shape" and aspect:
                w, h = float(ov.get("w") or 0.3), float(ov.get("h") or 0.3)
                ov["drawing"] = [[c[0]] + [v * h for v in c[1:]] for c in shape_drawing(str(ov.get("shape") or "rect"), w / max(h, 1e-3))]
            if clip.kind == "caption" and ov.get("live") and aspect:
                ov["cues"] = self._caption_cues(ov, clip, aspect)
            rows.append(ov)
        return rows

    @staticmethod
    def _burn_font(ov: dict, text: str) -> dict:
        """The font that really draws `text` and its metrics, so the burn-in matches the preview."""
        style = clean_text_style(ov)
        font = font_for(style["font"], apply_case(text, style["case"]))
        return {"font": font, "metrics": burn_metrics(font, style["bold"], style["italic"])}

    def _caption_cues(self, ov: dict, clip: TimelineClip, aspect: float) -> list[dict]:
        style = clean_text_style(ov)
        limit = caption_width(float(ov.get("x", 0.5)), aspect, style)
        cues = []
        for start, end, text in self.canvas.caption_cues():
            start, end = max(start, clip.start_ms), min(end, clip.end_ms)
            if end <= start:
                continue
            if style.get("caption_fit"):
                fitted, lines = fit_caption(style, text, limit)
            else:
                fitted, lines = style, wrap_text(style, text, limit)
            box_w, box_h = measure_box(fitted, lines)
            cues.append({
                "start_ms": start, "end_ms": end, "text": lines,
                "font_size": fitted["font_size"],
                "box_w": box_w, "box_h": box_h,
                **self._burn_font(fitted, lines),
            })
        return cues

    def replace_overlay_clips(self, overlays: list[dict]):
        keep = [c for c in self.canvas.clips if c.kind not in OVERLAY_KINDS]
        self.canvas.clips = keep
        for ov in overlays or []:
            kind = str(ov.get("kind") or "text")
            label = str(ov.get("text") or kind)
            start = int(ov.get("start_ms") or 0)
            end = int(ov.get("end_ms") or 0)
            dur = end - start if end > start else (self.canvas.duration_ms or 5000)
            extra = {"overlay": dict(ov), "path": ov.get("path", "")}
            if ov.get("watermark"):
                extra["watermark"] = True
            self.canvas.add_clip(kind, label, duration_ms=dur, extra=extra, start_ms=start)
        if not int(getattr(self, "_sequence_load", 0)):
            self._rebuild_rail()

    def update_overlay_extra(self, clip_id: str, overlay: dict):
        for clip in self.canvas.clips:
            if clip.id == clip_id:
                clip.extra["overlay"] = dict(overlay)
                if overlay.get("path"):
                    clip.extra["path"] = overlay["path"]
                clip.label = str(overlay.get("text") or clip.label)
                self.canvas.update()
                return

    def _refresh_meta(self):
        self._update_timecode_display()

    def _on_hover_scrub(self, ms: int, clip_id: str, track_id: str, local_x: int):
        """Show CapCut-style tip (name + time) above the scrub guide line."""
        tip = self._scrub_tip
        if tip is None:
            return
        if ms < 0 or local_x < 0:
            tip.hide()
            return
        clip = next((c for c in self.canvas.clips if c.id == clip_id), None) if clip_id else None
        track = self.canvas.track_by_id(track_id)
        if clip is not None:
            name = str(clip.label or (track.name if track else "Clip"))
            icn = track.icon if track else "video"
            accent = track.color if track else "#94a3b8"
        elif track is not None:
            name = track.name
            icn = track.icon
            accent = track.color
        else:
            name = self.canvas.media_name or "Timeline"
            icn = "video"
            accent = "#94a3b8"
        tip.set_content(name=name, ms=ms, icon_name=icn, accent=accent)
        # Anchor just above the hovered track (CapCut-style)
        ty = self.canvas.track_top(track_id) if track_id else 0
        global_pt = self.canvas.mapToGlobal(QPoint(local_x, max(0, ty)))
        tip.show_at(global_pt)

    def _show_context_scrub_tip(self, *, name: str, ms: int, icon_name: str, accent: str, global_pos: QPoint):
        tip = self._scrub_tip
        if tip is None:
            return
        tip.set_content(name=name, ms=ms, icon_name=icon_name, accent=accent)
        tip.show_at(global_pos)

    def _open_header_context_menu(self, track_id: str, global_pos: QPoint):
        track = self.canvas.track_by_id(track_id)
        if track is None:
            return
        for t in self.canvas.tracks:
            t.selected = t.id == track_id
        self.rail.refresh_flags()
        self._show_context_scrub_tip(
            name=track.name,
            ms=self.canvas.playhead_ms,
            icon_name=track.icon,
            accent=track.color,
            global_pos=global_pos,
        )
        open_track_menu(
            self,
            track,
            self._track_menu_handlers(track),
            global_pos,
        )
        if self._scrub_tip:
            self._scrub_tip.hide()

    def _open_canvas_context_menu(self, track_id: str, clip_id: str, global_pos: QPoint):
        track = self.canvas.track_by_id(track_id)
        if track is None:
            return
        clip = next((c for c in self.canvas.clips if c.id == clip_id), None) if clip_id else None
        # Remember click time for "Split Here" (map from global → canvas local).
        local = self.canvas.mapFromGlobal(global_pos)
        click_ms = self.canvas.ms_at(local.x())
        name = (clip.label if clip else None) or track.name
        self._show_context_scrub_tip(
            name=str(name),
            ms=click_ms,
            icon_name=track.icon,
            accent=track.color,
            global_pos=global_pos,
        )
        # Guide line at context click
        self.canvas._hover_tip_active = True
        self.canvas._hover_guide_x = local.x()
        self.canvas.update()
        open_track_menu(
            self,
            track,
            self._track_menu_handlers(track, clip=clip, click_ms=click_ms),
            global_pos,
            clip=clip,
        )
        self.canvas._clear_hover_scrub()
        if self._scrub_tip:
            self._scrub_tip.hide()

    def _track_menu_handlers(
        self,
        track,
        *,
        clip=None,
        click_ms: int | None = None,
    ) -> TrackMenuHandlers:
        tid = track.id
        rail = self.rail
        clip_id = clip.id if clip is not None else ""

        def _live_track():
            return self.canvas.track_by_id(tid)

        def _live_clip():
            if not clip_id:
                return None
            return next((c for c in self.canvas.clips if c.id == clip_id), None)

        def _select_clip():
            c = _live_clip()
            if c is None:
                return None
            self.canvas.selected_ids = {c.id}
            self.canvas.clip_selected.emit(c.id)
            self.canvas.update()
            return c

        def _rename():
            row = next((r for r in getattr(rail, "_rows", []) if r.track.id == tid), None)
            if row is not None:
                row.start_rename()
                return
            # Fallback: prompt-less inline name bump if header row missing.
            t = _live_track()
            if t is not None:
                self._rename_track(tid, t.name)

        def _move(delta: int):
            idx = next((i for i, t in enumerate(self.canvas.tracks) if t.id == tid), -1)
            if idx < 0:
                return
            to = max(0, min(len(self.canvas.tracks) - 1, idx + delta))
            if to != idx:
                self._reorder_track(idx, to)

        def _clear_track_keys():
            self.canvas.push_history()
            changed = False
            for c in self.canvas.clips:
                if c.track_id == tid and c.extra.get("keys"):
                    c.extra.pop("keys", None)
                    changed = True
            if not changed:
                if self.canvas._undo:
                    self.canvas._undo.pop()
                    self.canvas.history_changed.emit()
                return
            self.canvas.gains_changed.emit()
            self.canvas.update()
            self._emit_mix()

        def _add_clip():
            t = _live_track()
            if t is None or t.locked:
                return
            fit = self.canvas.fit_master_placement(t.kind)
            if fit:
                start, dur = fit
                self.canvas.add_clip(t.kind, t.name, track_id=tid, duration_ms=dur, start_ms=start)
            else:
                self.canvas.add_clip(t.kind, t.name, track_id=tid)
            self._rebuild_rail()
            self._refresh_meta()
            self.clips_changed.emit()

        def _split_here():
            c = _select_clip()
            if c is None or click_ms is None:
                return
            if self.canvas.split_clip(c, int(click_ms)):
                self._refresh_meta()
                self.clips_changed.emit()

        def _split_playhead():
            _select_clip()
            self._split_at_playhead()
            self.clips_changed.emit()

        def _duplicate_clip():
            if _select_clip() is None:
                return
            self._duplicate_selected()
            self.clips_changed.emit()

        def _delete_clip():
            if _select_clip() is None:
                return
            self.canvas.remove_selected()
            self._refresh_meta()
            self.clips_changed.emit()

        def _toggle_key():
            c = _select_clip()
            if c is None:
                return
            self.canvas.toggle_key_at(c, self.canvas.playhead_ms)
            self._emit_mix()

        def _clear_clip_keys():
            c = _select_clip()
            if c is None:
                return
            self.canvas.push_history()
            c.extra.pop("keys", None)
            self.canvas.gains_changed.emit()
            self.canvas.update()
            self._emit_mix()

        def _record():
            t = _live_track()
            if t is None:
                return
            if self.recorder.is_recording():
                self.recorder.stop()
                return
            # Record onto the clicked voice/audio track (not a forced Voice-over lane).
            target = t if t.kind in {"voice", "audio"} else self._voiceover_track()
            self.canvas.rec_track = target.id
            for row in getattr(rail, "_rows", []):
                row.track.selected = row.track.id == target.id
            rail.refresh_flags()
            self.recorder.start(self.canvas.playhead_ms)

        def _auto_mix():
            self.auto_mix()

        def _zoom_fit():
            self.zoom_to_fit()

        def _set_locked(on: bool):
            self._lock_track(tid, on)

        def _set_muted(on: bool):
            self._mute_track(tid, on)

        def _set_solo(on: bool):
            self._solo_track(tid, on)

        def _set_volume(v: int):
            self._volume_track(tid, v)
            self.rail.refresh_flags()

        def _set_hidden(on: bool):
            self._hide_track(tid, on)

        def _set_opacity(v: int):
            self._opacity_track(tid, v)
            self.rail.refresh_flags()

        def _set_height(h: int):
            self._resize_track(tid, h)

        def _dup_track():
            self._duplicate_track(tid)
            self.clips_changed.emit()

        def _del_track():
            self._delete_track(tid)
            self.clips_changed.emit()

        def _tx(action: str):
            return lambda: self.transcript_action.emit(action)

        source = track.kind in {"video", "voice", "audio"}
        master = self.canvas.source_track()
        is_master = master is not None and master.id == track.id
        return TrackMenuHandlers(
            rename=_rename,
            set_locked=_set_locked,
            set_muted=_set_muted,
            set_solo=_set_solo,
            set_volume=_set_volume,
            set_hidden=_set_hidden,
            set_opacity=_set_opacity,
            set_height=_set_height,
            move_up=lambda: _move(-1),
            move_down=lambda: _move(1),
            duplicate_track=_dup_track,
            delete_track=None if is_master else _del_track,
            clear_track_keys=_clear_track_keys,
            auto_mix=_auto_mix,
            record_voice=_record,
            add_clip_at_playhead=_add_clip,
            zoom_fit=_zoom_fit,
            split_at_playhead=_split_playhead if clip_id else None,
            split_here=_split_here if clip_id else None,
            duplicate_clip=_duplicate_clip if clip_id else None,
            delete_clip=_delete_clip if clip_id else None,
            toggle_key=_toggle_key if clip_id else None,
            clear_clip_keys=_clear_clip_keys if clip_id else None,
            show_transcripts=_tx("show") if source else None,
            retry_transcript=_tx("retry") if source else None,
            retry_translate=_tx("translate") if source else None,
            retry_tts=_tx("tts") if source else None,
            retry_all=_tx("all") if source else None,
            import_script=_tx("import") if source else None,
            export_script=_tx("export") if source else None,
            extract_audio_to_track=(
                (lambda: self.extract_audio_from_video(to_track=True))
                if track.kind == "video" else None
            ),
            extract_audio_save=(
                (lambda: self.extract_audio_from_video(to_track=False))
                if track.kind == "video" else None
            ),
            studio_action=(
                (lambda action: self.studio_action.emit(str(action)))
                if track.kind in {"video", "voice", "audio"} else None
            ),
        )

    def _source_video_path(self) -> str:
        """Resolve Cover / master video path for audio extraction."""
        media = str(getattr(self.canvas, "media_path", "") or "")
        if media and os.path.isfile(media):
            return media
        for clip in self.canvas.footage_clips():
            path = str((clip.extra or {}).get("path") or "")
            if path and os.path.isfile(path):
                return path
        return ""

    def extract_audio_from_video(self, *, to_track: bool = True, save_path: str | None = None):
        """Split audio from the Cover video → Audio track and/or export file."""
        if self._extract_busy:
            self.record_message.emit("Audio extract already running…", True)
            return
        source = self._source_video_path()
        if not source:
            self.record_message.emit("Extract audio · no video on Cover track", True)
            return

        stem = Path(source).stem
        if to_track and not save_path:
            out_dir = STUDIO_CACHE / "extracted_audio"
            out_dir.mkdir(parents=True, exist_ok=True)
            dest = str(out_dir / f"{stem}_audio.wav")
        else:
            suggested = str((OUTPUTS_DIR / f"{stem}_audio.wav"))
            if save_path:
                dest = save_path
            else:
                path, _ = QFileDialog.getSaveFileName(
                    self,
                    "Save Extracted Audio",
                    suggested,
                    "WAV (*.wav);;MP3 (*.mp3);;AAC / M4A (*.m4a);;All Files (*.*)",
                )
                if not path:
                    return
                dest = path

        self._extract_busy = True
        self.record_message.emit(f"Extracting audio · {os.path.basename(source)}…", False)

        worker = Worker(extract_audio, source, dest)
        worker.signals.result.connect(
            lambda path, place=to_track: self._on_extract_audio_done(path, place_on_track=place)
        )
        worker.signals.error.connect(self._on_extract_audio_failed)
        QThreadPool.globalInstance().start(worker)

    def _on_extract_audio_done(self, path: str, *, place_on_track: bool = True):
        self._extract_busy = False
        if not path or not os.path.isfile(path):
            self.record_message.emit("Extract audio · empty output", True)
            return
        if place_on_track:
            track = self.canvas.ensure_track("audio")
            dur = max(1000, int(probe_duration(path) * 1000))
            self.canvas.add_clip(
                "audio",
                os.path.basename(path),
                duration_ms=dur,
                extra={"path": path, "file_ms": dur, "extracted": True},
                track_id=track.id,
                start_ms=0,
            )
            self._load_wave(path)
            self._rebuild_rail()
            self._refresh_meta()
            self.clips_changed.emit()
            self.record_message.emit(
                f"Audio split to track · {os.path.basename(path)}", False
            )
        else:
            self.record_message.emit(
                f"Audio saved · {os.path.basename(path)}", False
            )

    def _on_extract_audio_failed(self, message: str, _tb: str = ""):
        self._extract_busy = False
        self.record_message.emit(f"Extract audio failed · {message}", True)

    def _add_track(self, kind: str):
        if kind == "transition":
            return
        # Blur is an effect clip, not its own lane type.
        if kind == "blur":
            track = self.canvas.add_track("effect")
            if track is None:
                return
            n = sum(1 for t in self.canvas.tracks if t.name == "Blur" or t.name.startswith("Blur "))
            track.name = "Blur" if n <= 1 else f"Blur {n}"
            clip = self.canvas.add_clip(
                "effect", "Blur", track_id=track.id,
                extra={"fx": {"kind": "effect", "effect": "blur", "intensity": 80, "name": "Blur"}},
            )
            self._rebuild_rail()
            if clip is not None:
                self.selection_changed.emit(clip.id, clip.track_id)
            return
        # Captions are text. A new video lane is overlay footage, not another master.
        if kind == "caption":
            kind = "text"
        track = self.canvas.add_track(kind)
        if track is None:
            return
        if kind not in {"video", "voice", "audio"}:
            fit = self.canvas.fit_master_placement(kind)
            if fit:
                start, dur = fit
                clip = self.canvas.add_clip(
                    kind, track.name, track_id=track.id, duration_ms=dur, start_ms=start,
                )
            else:
                clip = self.canvas.add_clip(kind, track.name, track_id=track.id)
        else:
            clip = None
        self._rebuild_rail(keep_empty="" if clip is not None else track.id)
        if clip is not None:
            self.selection_changed.emit(clip.id, clip.track_id)
        else:
            self.selection_changed.emit("", track.id)

    def _resize_track(self, tid: str, height: int):
        self.canvas.set_track_height(tid, height)
        self.rail.sync_heights(self.canvas.tracks)
        if not self._layouting:
            self.canvas._relayout(notify=False)

    def _rename_track(self, tid: str, name: str):
        track = self.canvas.track_by_id(tid)
        if track and name:
            self.canvas.push_history()
            track.name = name
            self.canvas.update()

    def _mute_track(self, tid: str, muted: bool):
        track = self.canvas.track_by_id(tid)
        if not track:
            return
        self.canvas.push_history()
        track.muted = muted
        self.canvas.update()
        self.rail.refresh_flags()
        self._emit_mix()

    def _solo_track(self, tid: str, solo: bool):
        track = self.canvas.track_by_id(tid)
        if not track:
            return
        self.canvas.push_history()
        track.solo = solo
        self.canvas.update()
        self.rail.refresh_flags()
        self._emit_mix()

    def _lock_track(self, tid: str, locked: bool):
        track = self.canvas.track_by_id(tid)
        if not track:
            return
        self.canvas.push_history()
        track.locked = locked
        self.canvas.update()
        self.rail.refresh_flags()
        self.clips_changed.emit()

    def _hide_track(self, tid: str, hidden: bool):
        track = self.canvas.track_by_id(tid)
        if not track:
            return
        track.hidden = hidden
        self.canvas.update()
        self.rail.refresh_flags()
        self.clips_changed.emit()

    def _opacity_track(self, tid: str, value: int):
        track = self.canvas.track_by_id(tid)
        if track:
            track.opacity = max(0, min(100, int(value)))
            self.canvas.update()
            self.rail.refresh_flags()
            self.clips_changed.emit()

    def _volume_track(self, tid: str, value: int):
        track = self.canvas.track_by_id(tid)
        if track:
            track.volume = max(0, min(200, value))
            self.canvas.update()
            self.rail.refresh_flags()
            self._emit_mix()

    def _delete_track(self, tid: str):
        if not self.canvas.delete_track(tid):
            self.record_message.emit("Source track stays — it is the master footage", True)
            return
        self._rebuild_rail()
        self._refresh_meta()
        self.clips_changed.emit()
        self.selection_changed.emit("", "")

    def _duplicate_track(self, tid: str):
        self.canvas.duplicate_track(tid)
        self._rebuild_rail()
        self._refresh_meta()
        self.clips_changed.emit()

    def _reorder_track(self, from_idx: int, to_idx: int):
        self.canvas.reorder_track(from_idx, to_idx)
        self._rebuild_rail()
        self.rail.sync_heights(self.canvas.tracks)
        self.clips_changed.emit()

    def _on_clip_selected(self, cid: str):
        self.clip_selected.emit(cid)
        track_id = ""
        if cid:
            clip = next((c for c in self.canvas.clips if c.id == cid), None)
            track_id = clip.track_id if clip else ""
        else:
            cleared = False
            for t in self.canvas.tracks:
                if t.selected:
                    t.selected = False
                    cleared = True
            if cleared:
                self._rebuild_rail()
        self.selection_changed.emit(cid, track_id)

    def _on_track_picked(self, tid: str, multi: bool):
        for t in self.canvas.tracks:
            if t.id == tid:
                t.selected = (not t.selected) if multi else True
            elif not multi:
                t.selected = False
        if not multi:
            self.canvas.selected_ids.clear()
        self._rebuild_rail()
        self.canvas.update()
        self.selection_changed.emit("", tid)

    def _on_files_dropped(self, paths: list, track_id: str, at: tuple[float, float] | None = None, into_selected: bool = True):
        track = self.canvas.track_by_id(track_id) if track_id else None
        replaced_video = False
        filled_frame = False
        drop_at = at
        for path in paths:
            path = os.path.abspath(path) if path else ""
            kind = kind_for_path(path)
            if not kind:
                continue
            if kind == "video":
                # New video on the timeline replaces master source on the Cover track.
                self.set_media(path)
                self.media_dropped.emit(path)
                replaced_video = True
                continue
            if kind == "image" and into_selected and not filled_frame:
                frame = self._selected_frame()
                if frame is not None:
                    self.replace_overlay_path(frame.id, path)
                    filled_frame = True
                    continue
            target = track if track and (track.kind == kind or track.kind in {kind, "image", "audio"}) else None
            if target is None:
                target = self.canvas.ensure_track(kind if kind != "audio" else "audio")
            dur = 3000
            start = None
            extra = {"path": path}
            if kind == "audio":
                dur = max(1000, int(probe_duration(path) * 1000))
                extra["file_ms"] = dur
                self._load_wave(path)
            else:
                fit = self.canvas.fit_master_placement(kind)
                if fit:
                    start, dur = fit
            if kind == "image":
                width, height = image_frame(path, self._picture_aspect())
                place = drop_at or (0.5, 0.5)
                drop_at = None
                extra["overlay"] = {
                    "path": path,
                    "text": os.path.basename(path),
                    "x": place[0],
                    "y": place[1],
                    "w": width,
                    "h": height,
                    "lock_aspect": True,
                }
            self.canvas.add_clip(
                kind, os.path.basename(path), duration_ms=dur, extra=extra,
                track_id=target.id, start_ms=start,
            )
        if not replaced_video:
            self._rebuild_rail()

    def set_compositions(self, names: list[str], index: int = 0):
        self.sequences.set_names(names, index)

    def _on_composition(self, index: int):
        if index >= 0:
            self.composition_changed.emit(index)

    def export_state(self) -> dict:
        """Full timeline, so closing the tool can reopen the same lanes and clips."""
        import json

        state = self.canvas._snapshot()
        state["duration_ms"] = int(self.canvas.duration_ms or 0)
        state["media"] = self.canvas.media_path or ""
        for row in state.get("tracks") or []:
            track = self.canvas.track_by_id(str(row.get("id") or ""))
            row["silent"] = bool(getattr(track, "silent", False))
        return json.loads(json.dumps(state, default=str))

    def apply_state(self, state: dict) -> None:
        """Put a saved timeline back. Clips keep the lanes they were stored on."""
        if not isinstance(state, dict) or not isinstance(state.get("clips"), list) or not state["clips"]:
            return
        self.begin_sequence()
        try:
            self.canvas._restore(state)
            media = str(state.get("media") or "")
            if media:
                self.canvas.media_path = os.path.abspath(media) if os.path.isfile(media) else media
                self.canvas.media_name = os.path.basename(media)
            duration = int(state.get("duration_ms") or 0)
            if duration > 0:
                self.canvas.duration_ms = duration
            for row in state.get("tracks") or []:
                if not isinstance(row, dict) or not row.get("silent"):
                    continue
                track = self.canvas.track_by_id(str(row.get("id") or ""))
                if track is not None:
                    track.silent = True
                    track.muted = True
        finally:
            self.end_sequence()
        self._rebuild_rail()
        self._refresh_meta()
        self.ruler.update()
        paths = [
            str(clip.extra.get("path"))
            for clip in self.canvas.clips
            if clip.kind in {"voice", "audio"}
            and clip.extra.get("path")
            and os.path.isfile(str(clip.extra.get("path")))
            and str(clip.extra.get("path")) not in self.canvas._waves
        ]
        if paths:
            self._load_waves(paths)

    def export_tracks(self) -> list[dict]:
        rows = []
        for track in self.canvas.tracks:
            if track.kind == "transition":
                continue
            rows.append({
                "id": track.id,
                "kind": track.kind,
                "name": track.name,
                "height": track.height,
                "color": track.color,
                "icon": track.icon,
                "locked": track.locked,
                "muted": track.muted,
                "solo": getattr(track, "solo", False),
                "hidden": track.hidden,
                "opacity": track.opacity,
                "volume": track.volume,
            })
        return rows

    def apply_tracks(self, rows: list[dict]):
        from claynext.constants.timeline_constants import TRACK_MAX_H, TRACK_MIN_H
        from claynext.gui.components.timeline.models import TimelineTrack, new_track

        incoming: list[TimelineTrack] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            kind = str(row.get("kind") or "video")
            if kind == "transition":
                continue
            fresh = new_track(kind)
            try:
                height = int(row.get("height") or fresh.height)
            except (TypeError, ValueError):
                height = fresh.height
            try:
                opacity = int(row.get("opacity") or 100)
            except (TypeError, ValueError):
                opacity = 100
            try:
                volume = int(row.get("volume", 100))
            except (TypeError, ValueError):
                volume = 100
            incoming.append(TimelineTrack(
                id=str(row.get("id") or fresh.id),
                kind=kind,
                name=str(row.get("name") or fresh.name),
                height=max(TRACK_MIN_H, min(TRACK_MAX_H, height)),
                color=str(row.get("color") or fresh.color),
                icon=str(row.get("icon") or fresh.icon),
                locked=bool(row.get("locked")),
                muted=bool(row.get("muted")),
                solo=bool(row.get("solo", False)),
                hidden=bool(row.get("hidden")),
                opacity=max(0, min(100, opacity)),
                volume=max(0, min(200, volume)),
            ))
        if not incoming:
            return
        if not any(track.kind in {"caption", "text"} for track in incoming):
            caption = new_track("caption")
            video_at = next((i for i, track in enumerate(incoming) if track.kind == "video"), -1)
            incoming.insert(video_at + 1 if video_at >= 0 else 0, caption)
        valid = {track.id for track in incoming}
        fallback: dict[str, str] = {}
        for track in incoming:
            fallback.setdefault(track.kind, track.id)
        for clip in self.canvas.clips:
            if clip.track_id not in valid:
                clip.track_id = fallback.get(clip.kind, incoming[0].id)
        self.canvas.tracks = incoming
        self.canvas.prune_transition_tracks()
        self.canvas._relayout(notify=False)
        self._rebuild_rail()
        self.rail.sync_heights(self.canvas.tracks)
        self._emit_mix()

    def is_recording(self) -> bool:
        return self.recorder.is_recording()

    def toggle_recording(self):
        if self.recorder.is_recording():
            self.recorder.stop()
            return
        track = self._voiceover_track()
        self.canvas.rec_track = track.id
        self.recorder.start(self.canvas.playhead_ms)

    def stop_recording(self):
        self.recorder.stop()

    def _voiceover_track(self):
        track = next((t for t in self.canvas.tracks if t.kind == "voice" and t.name == _VO_TRACK), None)
        if track is None:
            track = self.canvas.add_track("voice")
            track.name = _VO_TRACK
            self._rebuild_rail()
        return track

    def _fill_rec_menu(self):
        self.rec_menu.clear()
        devices = VoiceRecorder.inputs()
        if not devices:
            self.rec_menu.addAction("No microphone found").setEnabled(False)
            return
        current = self.recorder.device_id
        for device_id, name, is_default in devices:
            act = self.rec_menu.addAction(name + ("  · default" if is_default else ""))
            act.setCheckable(True)
            act.setChecked(device_id == current or (not current and is_default))
            act.setEnabled(not self.recorder.is_recording())
            act.triggered.connect(lambda _=False, d=device_id: self.recorder.set_device(d))

    def _set_rec_ui(self, recording: bool, text: str = "Rec"):
        self.btn_rec.setProperty("recording", recording)
        color = COLOR_ACCENT_ROSE if recording else "#d4d4d4"
        self.btn_rec.setIcon(icon("stop" if recording else "mic", color=color, size=13))
        self.btn_rec.setText(text)
        self.btn_rec.style().unpolish(self.btn_rec)
        self.btn_rec.style().polish(self.btn_rec)

    def _on_rec_started(self, start_ms: int):
        self.canvas.rec_start = start_ms
        self.canvas.rec_ms = 0
        self._set_rec_ui(True, "0:00")
        self.canvas.update()
        self.record_toggled.emit(True)

    def _on_rec_elapsed(self, ms: int):
        if self.canvas.rec_start < 0:
            return
        self.canvas.rec_ms = ms
        s = ms // 1000
        self.btn_rec.setText(f"{s // 60}:{s % 60:02d}")
        self.canvas.update()

    def _end_rec_ui(self):
        self.canvas.rec_start = -1
        self.canvas.rec_ms = 0
        self._set_rec_ui(False)
        self.canvas.update()
        self.record_toggled.emit(False)

    def _on_rec_finished(self, path: str, start_ms: int, duration_ms: int):
        track_id = self.canvas.rec_track
        self._end_rec_ui()
        if duration_ms <= 0:
            duration_ms = int(probe_duration(path) * 1000)
        if duration_ms < 200:
            self.record_message.emit("Take too short · discarded", True)
            return
        clip = self.add_take(path, start_ms, duration_ms, track_id=track_id)
        self.canvas.selected_ids = {clip.id}
        self._check_take(path)
        self.record_message.emit(f"Voice-over take · {fmt_ms(duration_ms)} at {fmt_ms(start_ms)}", False)

    def _on_rec_failed(self, message: str):
        self._end_rec_ui()
        self.record_message.emit(f"Recording failed · {message}", True)

    def add_take(self, path: str, start_ms: int, duration_ms: int, *, label: str = "", in_ms: int = 0,
                 file_ms: int = 0, volume: int | None = None, track_id: str = "") -> TimelineClip:
        track = self.canvas.track_by_id(track_id) if track_id else None
        if track is None:
            track = self._voiceover_track()
        self.canvas.push_history()
        n = sum(1 for c in self.canvas.clips if c.extra.get("take")) + 1
        extra = {"path": path, "take": True, "file_ms": int(file_ms or duration_ms), "in_ms": int(in_ms)}
        if volume is not None:
            extra["volume"] = int(volume)
        clip = TimelineClip(
            id=f"take-{os.path.splitext(os.path.basename(path))[0]}-{n}",
            track_id=track.id,
            kind="voice",
            start_ms=max(0, int(start_ms)),
            duration_ms=max(200, int(duration_ms)),
            label=label or f"Take {n}",
            locked=track.locked,
            extra=extra,
        )
        self.canvas.clips.append(clip)
        if clip.end_ms > self.canvas.duration_ms:
            self.canvas.duration_ms = clip.end_ms
        self.canvas._relayout()
        self._rebuild_rail()
        self._refresh_meta()
        self.clips_changed.emit()
        return clip

    def _check_take(self, path: str):
        worker = Worker(extract_wave_envelope, path, False)
        worker.signals.result.connect(lambda env, take=path: self._on_take_wave(take, env))
        self._take_worker = worker
        self._pool.start(worker)

    def _on_take_wave(self, path: str, env):
        if not isinstance(env, np.ndarray):
            return
        self.canvas.set_wave(normalize_envelope(env), path)
        if float(env.max(initial=0.0)) < 0.02:
            self.record_message.emit(
                "No sound in the take · allow microphone access for Claynext (or the app that launched it) "
                "in System Settings → Privacy & Security → Microphone",
                True,
            )

    def export_takes(self) -> list[dict]:
        rows = []
        for clip in self.canvas.clips:
            if not clip.extra.get("take"):
                continue
            row = {
                "path": str(clip.extra.get("path") or ""),
                "start_ms": clip.start_ms,
                "duration_ms": clip.duration_ms,
                "in_ms": int(clip.extra.get("in_ms") or 0),
                "file_ms": int(clip.extra.get("file_ms") or clip.duration_ms),
                "label": clip.label,
            }
            if "volume" in clip.extra:
                row["volume"] = int(clip.extra["volume"])
            row["fade_in"], row["fade_out"] = self.canvas.clip_fades(clip)
            rows.append(row)
        return rows

    def apply_takes(self, rows: list[dict]):
        self.canvas.clips = [c for c in self.canvas.clips if not c.extra.get("take")]
        paths = []
        for row in rows or []:
            path = str(row.get("path") or "") if isinstance(row, dict) else ""
            if not path or not os.path.isfile(path):
                continue
            clip = self.add_take(
                path, int(row.get("start_ms") or 0), int(row.get("duration_ms") or 0),
                label=str(row.get("label") or ""), in_ms=int(row.get("in_ms") or 0),
                file_ms=int(row.get("file_ms") or 0), volume=row.get("volume"),
            )
            for fade in ("fade_in", "fade_out"):
                if row.get(fade):
                    clip.extra[fade] = int(row[fade])
            paths.append(path)
        self.canvas._relayout()
        missing = [path for path in paths if path not in self.canvas._waves]
        if missing:
            self._load_waves(missing)

    def has_footage(self) -> bool:
        return bool(self.canvas.media_path)

    def drop_other_sequence(self, keep_path: str = "") -> None:
        """Clear the open sequence so a new source dub does not reuse it."""
        self.canvas.drop_other_sequence(keep_path)

    def begin_sequence(self) -> None:
        """Swap a sequence without repainting on every clip."""
        self._sequence_load = int(getattr(self, "_sequence_load", 0)) + 1
        self.setUpdatesEnabled(False)
        self.canvas.begin_quiet()

    def end_sequence(self) -> None:
        self._sequence_load = max(0, int(getattr(self, "_sequence_load", 0)) - 1)
        if self._sequence_load:
            return
        self.canvas.end_quiet()
        path = self.canvas.media_path or ""
        if path and path not in self.canvas._waves:
            self._load_wave(path)
        self._load_missing_voice_waves()
        if path and not self.canvas._frames:
            QTimer.singleShot(400, lambda p=path: self._load_strip(p))
        self.setUpdatesEnabled(True)
        self.canvas.update()

    def append_master(self, path: str, duration_ms: int = 0, start_ms: int | None = None) -> int:
        """Lay another movie onto the master track, after the movies already there."""
        start = self.canvas.append_master(path, duration_ms, start_ms)
        if int(getattr(self, "_sequence_load", 0)):
            return start
        self._rebuild_rail()
        self._refresh_meta()
        self.ruler.update()
        if path:
            self._load_wave(os.path.abspath(path))
        self.clips_changed.emit()
        return start

    def drop_master(self, path: str) -> None:
        """Remove a movie whose dub failed so the next one can follow the last good cut."""
        self.canvas.drop_master(path)
        if int(getattr(self, "_sequence_load", 0)):
            return
        self._rebuild_rail()
        self._refresh_meta()
        self.ruler.update()
        self.clips_changed.emit()

    def repack_masters(self) -> dict[str, int]:
        """Close gaps left when a movie in a merged sequence fails."""
        deltas = self.canvas.repack_masters()
        if int(getattr(self, "_sequence_load", 0)):
            return deltas
        self._rebuild_rail()
        self._refresh_meta()
        self.ruler.update()
        self.clips_changed.emit()
        return deltas

    def replace_masters(self, rows: list[dict]) -> None:
        self.canvas.replace_masters(rows)
        if int(getattr(self, "_sequence_load", 0)):
            return
        self._rebuild_rail()
        self._refresh_meta()
        self.ruler.update()
        for row in rows or []:
            path = str(row.get("path") or "") if isinstance(row, dict) else ""
            if path and os.path.isfile(path):
                self._load_wave(os.path.abspath(path))
        self.clips_changed.emit()

    def export_masters(self) -> list[dict]:
        return [
            {
                "path": str(clip.extra.get("path") or ""),
                "start_ms": int(clip.start_ms),
                "duration_ms": int(clip.duration_ms),
                "file_ms": int(clip.extra.get("file_ms") or clip.duration_ms),
                "label": clip.label,
            }
            for clip in self.canvas.master_clips()
        ]

    def place_source_dialogue(self, segments: list[dict], source: str) -> None:
        """Voice lines for one movie. Lines already on the sequence from other movies stay."""
        tracks = len(self.canvas.tracks)
        self.canvas.place_source_dialogue(segments, source)
        if len(self.canvas.tracks) != tracks:
            self._rebuild_rail()
        self._refresh_meta()
        self._load_missing_voice_waves()

    def set_media(self, path: str, duration_ms: int = 0):
        path = os.path.abspath(path) if path else ""
        current = os.path.abspath(self.canvas.media_path) if self.canvas.media_path else ""
        if path and path == current and int(getattr(self, "_sequence_load", 0)):
            return
        known = int(duration_ms or 0)
        self.canvas.set_media(path, known)
        master = self.canvas.master_clip() if path else None
        file_ms = int(master.extra.get("file_ms") or 0) if master is not None else 0
        # A missing probe leaves a one-second sliver. Read the real movie length next.
        if path and master is not None and not master.extra.get("user_trim") and file_ms <= 1500:
            self._probe_duration_later(path)
        if int(getattr(self, "_sequence_load", 0)):
            return
        self._rebuild_rail()
        self._refresh_meta()
        self.ruler.update()
        if path:
            # Wave first (cheap); defer filmstrip so preview playback can grab the pool.
            self._load_wave(path)
            QTimer.singleShot(400, lambda p=path: self._load_strip(p))
        self.clips_changed.emit()

    def _probe_duration_later(self, path: str) -> None:
        """Read the movie length off the interface thread after a sequence switch."""
        def probe(progress_callback=None):
            from claynext.adapters.ffmpeg_adapter import get_ffmpeg_adapter
            return int(get_ffmpeg_adapter().duration(path) * 1000)

        worker = Worker(probe)
        worker.signals.result.connect(lambda ms, media=path: self._apply_probed_duration(media, int(ms or 0)))
        pending = getattr(self, "_duration_workers", None)
        if not isinstance(pending, list):
            pending = []
            self._duration_workers = pending
        pending.append(worker)

        def _release(done=worker):
            held = getattr(self, "_duration_workers", None)
            if isinstance(held, list) and done in held:
                held.remove(done)

        worker.signals.finished.connect(_release)
        self._pool.start(worker)

    def _apply_probed_duration(self, path: str, duration_ms: int) -> None:
        current = os.path.abspath(self.canvas.media_path) if self.canvas.media_path else ""
        if not duration_ms or os.path.abspath(path) != current:
            return
        self.set_duration_ms(duration_ms)

    def lay_sync_stems(self, stems: list[dict]) -> None:
        """Mute the picture track and lay cleaned / isolated audio in sync with the film."""
        canvas = self.canvas
        video = next((t for t in canvas.tracks if t.kind == "video"), None)
        if video is not None:
            video.muted = True
        canvas.clips = [
            clip for clip in canvas.clips
            if not (clip.kind == "audio" and clip.extra.get("stem"))
        ]
        master = canvas.master_clip()
        start = int(master.start_ms) if master is not None else 0
        inn = int(master.extra.get("in_ms") or 0) if master is not None else 0
        dur = int(master.duration_ms) if master is not None and master.duration_ms else max(1000, int(canvas.duration_ms or 0))
        for item in stems or []:
            path = str(item.get("path") or "")
            if not path or not os.path.isfile(path):
                continue
            label = str(item.get("label") or "Audio")
            track = canvas.free_track("audio", start, start + dur)
            track.name = label
            track.muted = bool(item.get("mute"))
            canvas.add_clip(
                "audio",
                label,
                duration_ms=dur,
                start_ms=start,
                track_id=track.id,
                extra={
                    "path": path,
                    "stem": True,
                    "auto": True,
                    "file_ms": dur + inn,
                    "in_ms": inn,
                },
            )
            self._load_wave(path)
        self.hold_effects_bed()
        if int(getattr(self, "_sequence_load", 0)):
            return
        self._rebuild_rail()
        self.canvas.update()
        self._emit_mix()

    def hold_effects_bed(self) -> None:
        """Keep the full movie mix from playing over the translated voices when Effects is the bed."""
        canvas = self.canvas
        effects = [
            canvas.track_by_id(clip.track_id)
            for clip in canvas.clips
            if canvas.stem_role(clip) in {"effects", "music"}
        ]
        effects = [track for track in effects if track is not None and not track.muted]
        if not effects:
            return
        effects_ids = {track.id for track in effects}
        for clip in list(canvas.clips):
            if canvas.stem_role(clip) not in {"source", "vocals"}:
                continue
            track = canvas.track_by_id(clip.track_id)
            if track is None:
                continue
            if track.id in effects_ids:
                fresh = canvas.free_track("audio", clip.start_ms, clip.end_ms)
                fresh.name = clip.label or "Source audio"
                fresh.muted = True
                clip.track_id = fresh.id
            else:
                track.muted = True
        video = next((track for track in canvas.tracks if track.kind == "video"), None)
        if video is not None:
            video.muted = True
        self._emit_mix()

    def set_voice_audio(self, path: str):
        self.canvas.voice_path = path if path and os.path.isfile(path) else ""
        if self.canvas.voice_path:
            self._load_wave(self.canvas.voice_path)
        self.canvas.update()

    def set_duration_ms(self, ms: int):
        if ms > 0:
            self.canvas.set_duration_ms(ms)
            self._refresh_meta()
            self.ruler.update()

    def set_playhead_ms(self, ms: int):
        self.canvas.set_playhead_ms(ms)
        self._update_timecode_display()
        self.ruler.update()
        self._follow_playhead()

    def set_dialogue(self, segments: list[dict]):
        self.canvas.set_dialogue(segments)
        if int(getattr(self, "_sequence_load", 0)):
            return
        self._rebuild_rail()
        self._refresh_meta()
        self._load_missing_voice_waves()

    def sync_dialogue(self, segments: list[dict]) -> bool:
        """Update voice clips without rebuilding the track headers."""
        tracks = len(self.canvas.tracks)
        changed = self.canvas.sync_dialogue(segments)
        if len(self.canvas.tracks) != tracks:
            self._rebuild_rail()
        if changed:
            self._refresh_meta()
            self._load_missing_voice_waves()
            self.canvas.update()
        return changed

    def _load_missing_voice_waves(self) -> None:
        paths = [
            str(clip.extra.get("path"))
            for clip in self.canvas.clips
            if clip.kind == "voice" and clip.extra.get("path") and str(clip.extra.get("path")) not in self.canvas._waves
        ]
        if paths:
            self._load_waves(paths)

    def auto_duck(self, level: float) -> int:
        count = self.canvas.auto_duck(level, self.duck_fade_ms)
        self._emit_mix()
        return count

    def auto_mix(self, source: str = "") -> bool:
        """Detect original speech in the footage, then key those spans plus the voice clips."""
        from claynext.adapters.ai import get_ai_adapter
        def detect_voice_spans(src, **kw):
            chunks = get_ai_adapter().vad_chunk(src)
            return [(float(c.get("start_sec", 0.0)), float(c.get("end_sec", 0.0))) for c in chunks]

        source = source or self.speech_source or self.canvas.media_path
        if not source or not os.path.isfile(source) or not self.canvas.footage_clips():
            return False
        self.btn_duck.setEnabled(False)
        self.btn_duck.setToolTip("Detecting voices…")
        media = self.canvas.media_path
        worker = Worker(detect_voice_spans, source)
        worker.signals.result.connect(lambda spans, m=media: self._on_voice_spans(spans, m))
        worker.signals.error.connect(self._on_voice_spans_error)
        self._voice_worker = worker
        self._pool.start(worker)
        return True

    def _on_voice_spans(self, spans, media: str = ""):
        self._restore_duck_button()
        if media and media != self.canvas.media_path:
            return
        spans = list(spans or [])
        level = 0.0 if self.canvas.bed_path else self.duck_level
        count = self.canvas.auto_duck(level, self.duck_fade_ms, extra_spans=spans)
        self._emit_mix()
        speech_ms = sum(int(b) - int(a) for a, b in spans)
        self.auto_mix_done.emit(count, speech_ms, bool(self.canvas.bed_path))

    def _on_voice_spans_error(self, message: str, _stack: str):
        self._restore_duck_button()
        self.auto_mix_failed.emit(str(message))

    def _restore_duck_button(self):
        self.btn_duck.setEnabled(True)
        self.btn_duck.setToolTip(self._duck_tip)

    def export_footage(self) -> list[dict]:
        return [
            {
                "start_ms": clip.start_ms,
                "volume": self.canvas.clip_volume(clip),
                "keys": [list(key) for key in self.canvas.clip_keys(clip)],
                "adjust": dict(clip.extra.get("adjust") or {}),
                "filter": str(clip.extra.get("filter") or "none"),
                "fade_in": self.canvas.clip_fades(clip)[0],
                "fade_out": self.canvas.clip_fades(clip)[1],
                "auto_key": dict(clip.extra.get("auto_key") or {}),
                "canvas": dict(clip.extra.get("canvas") or {}),
                "transition": dict(clip.extra["transition"]) if clip.extra.get("transition") else None,
            }
            for clip in self.canvas.footage_clips()
        ]

    def add_images(self, paths: list[str], at: tuple[float, float] | None = None, into_selected: bool = True) -> None:
        """Place pictures as canvas elements. They are not library media."""
        self._on_files_dropped(list(paths or []), "", at=at, into_selected=into_selected)

    def replace_overlay_path(self, clip_id: str, path: str) -> None:
        """Swap the picture inside an image element and keep its frame."""
        path = os.path.abspath(path) if path else ""
        if not path or not os.path.isfile(path):
            return
        from claynext.gui.components.render.shape import FRAME_SHAPES

        for clip in self.canvas.clips:
            overlay = dict(clip.extra.get("overlay") or {})
            framed = clip.kind == "shape" and str(overlay.get("shape") or "") in FRAME_SHAPES
            if clip.id != clip_id or (clip.kind not in {"image", "logo"} and not framed):
                continue
            overlay["path"] = path
            overlay["text"] = os.path.basename(path)
            overlay["lock_aspect"] = True
            clip.extra["overlay"] = overlay
            clip.extra["path"] = path
            if not framed:
                clip.label = os.path.basename(path)
            self.canvas.update()
            self.clips_changed.emit()
            return

    def _selected_frame(self):
        from claynext.gui.components.render.shape import FRAME_SHAPES

        for clip_id in self.canvas.selected_ids:
            clip = self.canvas.clip_by_id(clip_id)
            overlay = (clip.extra.get("overlay") or {}) if clip is not None else {}
            if clip is not None and clip.kind == "shape" and str(overlay.get("shape") or "") in FRAME_SHAPES:
                return clip
        return None

    def _picture_aspect(self) -> float:
        from claynext.models.canvas import ratio_value

        ratio = ratio_value(self.footage_canvas().get("ratio", "original"), None)
        return float(ratio) if ratio else 16 / 9

    def footage_canvas(self) -> dict:
        """Canvas of the first footage clip (ratio, video transform, background)."""
        footage = self.canvas.footage_clips()
        return clean_canvas(footage[0].extra.get("canvas") if footage else None)

    def set_footage_canvas(self, canvas: dict):
        value = clean_canvas(canvas)
        for clip in self.canvas.footage_clips():
            if value == clean_canvas(None):
                clip.extra.pop("canvas", None)
            else:
                clip.extra["canvas"] = dict(value)

    def apply_footage(self, rows: list[dict]):
        footage = self.canvas.footage_clips()
        for clip, row in zip(footage, rows or []):
            if not isinstance(row, dict):
                continue
            clip.extra["volume"] = int(row.get("volume", 100))
            keys = row.get("keys")
            if isinstance(keys, list):
                clip.extra["keys"] = [list(key) for key in keys if isinstance(key, (list, tuple)) and len(key) == 2]
            if isinstance(row.get("adjust"), dict):
                clip.extra["adjust"] = clean_adjust(row["adjust"])
                clip.extra["filter"] = str(row.get("filter") or "none")
            for fade in ("fade_in", "fade_out"):
                if row.get(fade):
                    clip.extra[fade] = int(row[fade])
            if isinstance(row.get("auto_key"), dict):
                clip.extra["auto_key"] = dict(row["auto_key"])
            if row.get("canvas"):
                clip.extra["canvas"] = clean_canvas(row["canvas"])
            if isinstance(row.get("transition"), dict):
                clip.extra["transition"] = dict(row["transition"])
        self.canvas.update()
        self._emit_mix()

    def render_plan(self) -> dict:
        canvas = self.canvas
        voice: list[dict] = []
        replaced = canvas.effects_bed_active()
        for track in canvas.tracks:
            if track.kind not in {"voice", "audio"} or track.muted:
                continue
            for clip in canvas.clips:
                path = str(clip.extra.get("path") or "")
                if clip.track_id != track.id or not path:
                    continue
                role = canvas.stem_role(clip)
                if replaced and role in {"source", "vocals"}:
                    continue
                gain = canvas.clip_gain(clip, clip.start_ms, fades=False)
                if gain <= 0:
                    continue
                fade_in, fade_out = canvas.clip_fades(clip)
                voice.append({
                    "path": path,
                    "start_ms": clip.start_ms,
                    "duration_ms": clip.duration_ms,
                    "in_ms": int(clip.extra.get("in_ms") or 0),
                    "gain": gain,
                    "fade_in_ms": fade_in,
                    "fade_out_ms": fade_out,
                })
        keys: list[tuple[int, float]] = []
        bed_keys: list[tuple[int, float]] = []
        video = next((track for track in canvas.tracks if track.kind == "video"), None)
        # The Effects stem is the soundtrack. The picture's own mix would put the original dialogue under the dub.
        track_gain = 0.0 if replaced or not video or video.muted else video.volume / 100.0
        footage = sorted(canvas.footage_clips(), key=lambda clip: clip.start_ms)
        for clip in footage:
            points = [clip.start_ms] + [int(key[0]) for key in canvas.clip_keys(clip)] + [clip.end_ms - 1]
            fade_in, fade_out = canvas.clip_fades(clip)
            for step in range(1, 9):
                if fade_in:
                    points.append(clip.start_ms + fade_in * step // 8)
                if fade_out:
                    points.append(clip.end_ms - fade_out * step // 8)
            base = canvas.clip_volume(clip) / 100.0 * track_gain
            for ms in sorted(set(points)):
                if clip.start_ms <= ms < clip.end_ms:
                    mult = canvas.key_mult(clip, ms)
                    fade = canvas.fade_mult(clip, ms)
                    keys.append((ms, base * mult * fade))
                    bed_keys.append((ms, base * max(0.0, 1.0 - mult) * fade))
        bed = canvas.bed_path if any(gain > 0 for _ms, gain in bed_keys) else ""
        grade = adjust_filter(footage[0].extra.get("adjust")) if footage else ""
        frame = clean_canvas(footage[0].extra.get("canvas")) if footage else clean_canvas(None)
        fx = self.export_fx()
        info = probe_media(canvas.media_path) if canvas.media_path and (fx or grade or not is_neutral(frame)) else {}
        src_w, src_h = int(info.get("width") or 0), int(info.get("height") or 0)
        # Grade covers the frame (video and blur fill). Effects stay on the video, as in the preview.
        front = ",".join(fx_filters(fx, src_w, src_h)) if fx and src_w and src_h else ""
        video_filter = canvas_filter(frame, src_w, src_h, grade or "", front) if src_w else (grade or "")
        return {
            "video_filter": video_filter,
            "canvas": frame,
            "fx": fx,
            "voice": voice,
            "footage_keys": keys,
            "footage_gain": track_gain,
            "bed_path": bed,
            "bed_keys": bed_keys if bed else [],
        }

    def clear(self):
        self.canvas.set_media("", 0)
        self.canvas.set_frames([])
        self._rebuild_rail()
        self._refresh_meta()
        self.ruler.update()

    def _follow_playhead(self):
        x = int(self.canvas.x_at(self.canvas.playhead_ms))
        bar = self.scroll.horizontalScrollBar()
        view = self.scroll.viewport().width()
        if x < bar.value() + 24 or x > bar.value() + view - 40:
            bar.setValue(max(0, x - view // 3))

    def dragEnterEvent(self, event: QDragEnterEvent):
        if paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        paths = paths_from_mime(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self._on_files_dropped(paths, "")

    def _load_strip(self, path: str):
        if not path or path != self.canvas.media_path:
            return
        # Adaptive tile count — long movies stay light so preview can play
        dur_ms = int(self.canvas.duration_ms or 0)
        if dur_ms >= 3_600_000:
            count = 12
        elif dur_ms >= 1_200_000:
            count = 16
        elif dur_ms >= 300_000:
            count = 24
        else:
            count = 32
        worker = Worker(extract_filmstrip, path, count=count, height=48)
        worker.signals.result.connect(self._on_strip)
        self._strip_worker = worker
        # Low priority so preview play / wave workers run first
        self._pool.start(worker, -1)

    def _on_strip(self, frames):
        if isinstance(frames, list):
            self.canvas.set_frames(frames)

    def _load_wave(self, path: str):
        worker = Worker(extract_wave_envelope, path)
        worker.signals.result.connect(lambda env, media=path: self._on_wave(media, env))
        self._wave_worker = worker
        self._pool.start(worker)

    def _load_waves(self, paths: list[str]):
        def read_all(items: list[str], progress_callback=None) -> dict:
            return {path: extract_wave_envelope(path) for path in items}

        worker = Worker(read_all, list(paths))
        worker.signals.result.connect(self._on_waves)
        self._waves_worker = worker
        self._pool.start(worker)

    def _on_waves(self, result):
        if not isinstance(result, dict):
            return
        for path, env in result.items():
            if isinstance(env, np.ndarray) and len(env):
                self.canvas._waves[path] = env
        self.canvas.update()

    def _on_wave(self, path: str, peaks):
        if not isinstance(peaks, np.ndarray):
            return
        known = {str(clip.extra.get("path") or "") for clip in self.canvas.clips}
        known.add(self.canvas.voice_path)
        if path != self.canvas.media_path and path not in known:
            return
        self.canvas.set_wave(peaks, path)

