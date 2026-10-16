"""Preview stage, playback transport, and timeline sync."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QBrush, QColor
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QLabel, QFrame

from claynext.models.dubbing_service import timestamp_to_sec
from claynext.models.canvas import ratio_value
from claynext.gui.components.media_preview import MediaPlaybackWidget, MediaPreviewWidget
from claynext.gui.components.overlay_canvas import OverlayCanvas, PreviewStageHost
from claynext.gui.components.spinner import Spinner


class PreviewTools:
    """Video preview, overlay stage, and playhead sync."""

    def _build_preview_player(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("preview_editor")
        panel.setMinimumHeight(180)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root = QVBoxLayout(panel)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._player_mode = "timeline"
        self._timeline_gains = (1.0, 1.0, 0.0)
        self.player_header = self._build_player_header()

        self.preview = MediaPreviewWidget()
        self.overlay = OverlayCanvas()
        self.overlay.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.stage_host = PreviewStageHost(self.preview, self.overlay)
        self.preview.set_dock_host(self.stage_host, 0)
        # Editor tools: Move (V) / Hand (H) + wheel zoom on the frame canvas.
        self.overlay.bind_preview(self.preview)
        self.preview.media_cleared.connect(self._on_preview_close)
        self.preview.position_changed.connect(self._on_player_position)
        self.preview.duration_changed.connect(self._on_preview_duration)
        self.preview.playing_changed.connect(self._on_main_playing)
        self._clip_lanes: dict[bool, list] = {}
        for take in (False, True):
            out = QAudioOutput(panel)
            player = QMediaPlayer(panel)
            player.setAudioOutput(out)
            self._clip_lanes[take] = [player, out, ""]
        self.overlay.item_selected.connect(self._on_overlay_selected)
        self.overlay.items_changed.connect(self._on_overlays_changed)
        self.overlay.item_edited.connect(self._on_overlay_edited)
        self.overlay.video_clicked.connect(self._select_footage_from_preview)
        self.overlay.video_transform.connect(self._on_video_transform)
        self.preview.canvas_edited.connect(self._on_player_canvas_edited)

        self.stage_host.setMinimumHeight(120)
        self.stage_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._preview_load_overlay = self._build_preview_load_overlay(self.stage_host)
        self.stage_host._load_overlay = self._preview_load_overlay
        self.preview.loading_changed.connect(self._set_preview_loading)
        root.addWidget(self.stage_host, 1)
        self.preview.set_fullscreen_target(self.stage_host, panel, root.indexOf(self.stage_host))
        self.preview.fullscreen_changed.connect(self._on_preview_fullscreen)
        self.playback = MediaPlaybackWidget(compact=True)
        self.playback.set_dock_host(panel, index=1)
        self.playback.bind(self.preview)
        root.addWidget(self.playback, 0)
        return panel

    def _build_preview_load_overlay(self, host: QWidget) -> QFrame:
        overlay = QFrame(host)
        overlay.setObjectName("preview_load_overlay")
        overlay.hide()
        lay = QVBoxLayout(overlay)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addStretch(1)
        self.preview_spinner = Spinner(overlay, size=32, color="#a855f7")
        lay.addWidget(self.preview_spinner, 0, Qt.AlignmentFlag.AlignHCenter)
        self.lbl_preview_loading = QLabel("Preparing playback…")
        self.lbl_preview_loading.setObjectName("preview_load_label")
        self.lbl_preview_loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_preview_loading, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(1)
        return overlay

    def _set_preview_loading(self, loading: bool):
        overlay = getattr(self, "_preview_load_overlay", None)
        spinner = getattr(self, "preview_spinner", None)
        host = getattr(self, "stage_host", None)
        if overlay is None or spinner is None or host is None:
            return
        if loading:
            overlay.setGeometry(host.rect())
            overlay.raise_()
            spinner.start()
            overlay.show()
        else:
            spinner.stop()
            overlay.hide()

    def _build_player_header(self) -> QWidget:
        from claynext.gui.components.segment_tabs import SegmentTabs

        bar = QWidget()
        bar.setObjectName("dub_player_modes")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar.setFixedHeight(24)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.player_tabs = SegmentTabs(
            ["Source", "Timeline"],
            variant="segment",
            size="sm",
            tips=[
                "Preview a library file as it is · no dub voice or overlays",
                "Play the dub timeline · voice track, music bed, key points, and overlays",
            ],
        )
        self.player_tabs.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.player_modes = self.player_tabs.group
        self.btn_player_source = self.player_tabs.button(0)
        self.btn_player_timeline = self.player_tabs.button(1)
        self.player_tabs.changed.connect(self._on_player_mode_clicked)
        lay.addStretch(1)
        lay.addWidget(self.player_tabs, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addStretch(1)
        return bar

    def _on_library_deselected(self):
        self._source_preview_path = ""
        if self._player_mode != "source":
            self._sync_player_header()
            return
        if self._timeline_media():
            self.show_timeline_player()
        else:
            self._player_mode = "timeline"
            self.preview.clear()
            self._sync_player_header()

    def _on_player_mode_clicked(self, index: int):
        if index == 0:
            path = getattr(self, "_source_preview_path", "") or self.selected_file
            if path and os.path.isfile(path):
                self.preview_source(path)
            else:
                self._sync_player_header()
            return
        self.show_timeline_player()

    def _timeline_media(self) -> str:
        if not hasattr(self, "timeline"):
            return ""
        path = self.timeline.canvas.media_path
        return path if path and os.path.isfile(path) else ""

    def _sync_player_header(self):
        if not hasattr(self, "btn_player_source"):
            return
        source = getattr(self, "_source_preview_path", "") or self.selected_file
        self.btn_player_source.setEnabled(bool(source and os.path.isfile(source)))
        self.btn_player_timeline.setEnabled(bool(self._timeline_media()))
        is_source = self._player_mode == "source"
        self.btn_player_source.setChecked(is_source)
        self.btn_player_timeline.setChecked(not is_source)

    def preview_source(self, path: str):
        if not path or not os.path.isfile(path):
            return
        if self._player_mode == "timeline" and self._timeline_media():
            self._timeline_resume_ms = self.timeline.canvas.playhead_ms
        self._player_mode = "source"
        self._source_preview_path = path
        self._stop_clip_lanes()
        self.preview.set_stems("", "")
        self.preview.set_source_gain(1.0)
        self.preview.set_voice_gain(0.0)
        self.preview.set_bed_gain(0.0)
        if hasattr(self, "overlay"):
            self.overlay.set_live_caption("")
            self.overlay.setVisible(False)
        if getattr(self.preview, "_path", "") != path:
            self.preview.load(path)
        self._apply_preview_canvas()
        self._sync_player_header()

    def show_timeline_player(self):
        was_source = self._player_mode == "source"
        self._player_mode = "timeline"
        media = self._timeline_media()
        if hasattr(self, "overlay"):
            self.overlay.setVisible(True)
        if not media:
            if was_source:
                self.preview.clear()
            self._sync_player_header()
            return
        resume = getattr(self, "_timeline_resume_ms", None)
        if resume is None:
            resume = self.timeline.canvas.playhead_ms
        self._timeline_resume_ms = None
        if getattr(self.preview, "_path", "") != media:
            self.preview.load(media)
            self.preview.seek_ms(resume)
        elif was_source:
            self.preview.seek_ms(resume)
        stems = self._current_stems() if hasattr(self, "_current_stems") else {}
        self.preview.set_stems(str(stems.get("bed") or ""), str(stems.get("dialogue") or ""))
        self._apply_timeline_gains()
        self._apply_preview_canvas()
        self._sync_preview_overlays(force=True)
        self._sync_player_header()

    def _apply_preview_canvas(self):
        """Timeline mode shows the project canvas; source mode shows the file as it is."""
        if self._player_mode == "timeline" and self._timeline_media():
            state = self.timeline.footage_canvas()
            footage = self.timeline.canvas.footage_clips()
            self.preview.set_video_adjust(footage[0].extra.get("adjust") if footage else None)
            self.preview.set_canvas(state)
            self.overlay.set_video_frame(self.preview.video_ratio(), state)
        else:
            self.preview.set_video_adjust(None)
            self.preview.set_canvas(None, active=False)
            self.overlay.set_video_frame(None, None)
        # Overlay geometry is owned by PreviewStageHost (full wrapper + content_rect).
        # Never shrink it to stage_geometry — that double-offsets items when zoomed.
        if hasattr(self, "stage_host"):
            self.stage_host.sync_overlay()
        if hasattr(self, "track_props") and self._footage_bound():
            self.track_props.show_canvas_hint(self.preview.canvas_covered())

    def _on_preview_fullscreen(self, fullscreen: bool):
        """Fullscreen is a clean viewing mode: canvas, grade, and overlays, without edit handles."""
        self.overlay.set_video_edit(not fullscreen and self._footage_bound() and self._player_mode == "timeline")

    def _stage_aspect(self) -> float:
        """Width / height of the exported picture, which the preview stage mirrors."""
        ratio = ratio_value(self.timeline.footage_canvas()["ratio"], self.preview.video_ratio())
        if ratio:
            return ratio
        if hasattr(self, "overlay") and self.overlay.height() > 0:
            return self.overlay.width() / self.overlay.height()
        return 16 / 9

    def _footage_bound(self) -> bool:
        clip = self.track_props.clip
        return clip is not None and clip in self.timeline.canvas.footage_clips()

    def _set_footage_canvas(self, state: dict):
        self.timeline.set_footage_canvas(state)
        self._apply_preview_canvas()

    def _on_player_canvas_edited(self, state: dict):
        if self._player_mode != "timeline" or not self._timeline_media():
            return
        self._set_footage_canvas(state)
        if self._footage_bound():
            self.track_props.set_canvas_state(self.timeline.footage_canvas())
        self._store_project_session()

    def _on_video_transform(self, transform: dict):
        state = self.timeline.footage_canvas()
        state.update(transform)
        self.timeline.set_footage_canvas(state)
        self.preview.set_canvas(self.timeline.footage_canvas())
        if self._footage_bound():
            self.track_props.show_transform(transform)
            self.track_props.show_canvas_hint(self.preview.canvas_covered())

    def _select_footage_from_preview(self):
        footage = self.timeline.canvas.footage_clips()
        if self._player_mode != "timeline" or not footage:
            return
        clip = footage[0]
        self.timeline.canvas.selected_ids = {clip.id}
        self.timeline.canvas.update()
        self.timeline._on_clip_selected(clip.id)
        if self.track_props.current_tab() != "video":
            self.track_props._set_tab("video")

    def _apply_timeline_gains(self):
        source, voice, bed = self._timeline_gains
        self.preview.set_source_gain(source)
        self.preview.set_voice_gain(voice)
        self.preview.set_bed_gain(bed)

    def _on_preview_close(self):
        if self._player_mode == "source" and self._timeline_media():
            QTimer.singleShot(0, self.show_timeline_player)
        else:
            self._sync_player_header()

    def _on_preview_duration(self, ms: int):
        if self._player_mode != "timeline":
            return
        if hasattr(self, "timeline") and self.timeline.has_footage() and ms > 0:
            self.timeline.set_duration_ms(ms)

    def _on_timeline_mix(self, source: float, voice: float, bed: float = 0.0):
        self._timeline_gains = (source, voice, bed)
        if self._player_mode == "timeline":
            self._apply_timeline_gains()

    def _on_timeline_seek(self, ms: int):
        if self._player_mode != "timeline":
            self._timeline_resume_ms = ms
            self.show_timeline_player()
        self.preview.seek_ms(ms)
        self._reset_clip_lanes()
        self._sync_voice_clip(ms)
        self._sync_preview_overlays()
        if self.prop_stack.currentIndex() == 0:
            self._sync_props_audio()

    def _main_playing(self) -> bool:
        return self.preview.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def _on_main_playing(self, playing: bool):
        if not playing or self._player_mode != "timeline":
            for lane in self._clip_lanes.values():
                lane[0].pause()
            return
        self._reset_clip_lanes()
        self._sync_voice_clip(self.preview.player.position())

    def _reset_clip_lanes(self):
        for lane in self._clip_lanes.values():
            lane[2] = ""

    def _stop_clip_lanes(self):
        for lane in self._clip_lanes.values():
            lane[0].stop()
            lane[2] = ""

    def _sync_voice_clip(self, ms: int):
        if not hasattr(self, "timeline"):
            return
        for take, lane in self._clip_lanes.items():
            self._sync_clip_lane(lane, self.timeline.canvas.voice_clip_at(ms, take=take), ms)

    def _sync_clip_lane(self, lane: list, clip, ms: int):
        player, out, current = lane
        if clip is None:
            if current:
                player.stop()
                lane[2] = ""
            return
        gain = self.timeline.canvas.clip_gain(clip, ms)
        out.setVolume(min(1.0, gain))
        out.setMuted(gain <= 0.001)
        offset = ms - clip.start_ms + int(clip.extra.get("in_ms") or 0)
        if clip.id != current:
            lane[2] = clip.id
            player.setSource(QUrl.fromLocalFile(str(clip.extra["path"])))
            player.setPosition(max(0, offset))
            if self._main_playing():
                player.play()
            return
        if self._main_playing():
            if abs(player.position() - offset) > 250:
                player.setPosition(max(0, offset))
            if player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                player.play()

    def _on_record_toggled(self, recording: bool):
        if not recording:
            if self._main_playing():
                self.preview.player.pause()
            return
        if self._player_mode != "timeline":
            self.show_timeline_player()
        if self._timeline_media():
            self.preview.player.play()

    def _on_record_message(self, message: str, is_error: bool):
        if is_error:
            self.log.warn(message)
            return
        self.log.info(message)
        self._store_project_session()

    def _on_timeline_drop(self, path: str):
        if not path or not os.path.isfile(path):
            return
        path = os.path.abspath(path)
        self.set_dub_source(path)
        self._source_preview_path = path
        # Panel drop already calls set_media; still sync if the signal arrived alone.
        if self.timeline.canvas.media_path != path:
            self.timeline.set_media(path)
        # Force the player onto the new source (path equality alone can miss a replace).
        self._player_mode = "timeline"
        if hasattr(self, "overlay"):
            self.overlay.setVisible(True)
        self.preview.load(path)
        self.preview.seek_ms(0)
        self.timeline.set_playhead_ms(0)
        stems = self._current_stems() if hasattr(self, "_current_stems") else {}
        self.preview.set_stems(str(stems.get("bed") or ""), str(stems.get("dialogue") or ""))
        self._apply_timeline_gains()
        self._apply_preview_canvas()
        self._sync_preview_overlays(force=True)
        self._sync_player_header()
        if hasattr(self, "_store_project_session"):
            self._store_project_session()
        self.log.info(f"Footage replaced · {os.path.basename(path)}")

    def _on_player_position(self, ms: int):
        if self._player_mode != "timeline":
            return
        if hasattr(self, "timeline"):
            self.timeline.set_playhead_ms(ms)
            self._sync_preview_overlays()
            self._sync_voice_clip(ms)
            if self.prop_stack.currentIndex() == 0:
                self._sync_props_audio()
        row = -1
        for i, seg in enumerate(self._segments):
            start = int(timestamp_to_sec(seg.get("start", "")) * 1000)
            end = int(timestamp_to_sec(seg.get("end", "")) * 1000)
            if end <= start:
                end = start + 1
            if start <= ms < end:
                row = i
                break
        if hasattr(self, "overlay") and hasattr(self, "timeline"):
            cues = self.timeline.canvas.caption_cues()
            start, end, caption = next((cue for cue in cues if cue[0] <= ms < cue[1]), (0, 0, ""))
            self.overlay.set_live_caption(caption, start, end, has_lines=bool(cues))
        if self._filling_table or not self._segments:
            return
        if row == self._playing_row:
            return
        prev = self._playing_row
        self._playing_row = row
        for r in {prev, row}:
            if r < 0 or r >= self.table.rowCount():
                continue
            brush = QBrush(QColor(99, 102, 241, 38)) if r == row else QBrush()
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item:
                    item.setBackground(brush)

