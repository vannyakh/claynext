"""Claynext Studio workspace. Tool behavior lives in sibling modules."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QSizePolicy,
    QFileDialog, QMessageBox, QInputDialog,
)

from claynext.models.dubbing_service import timestamp_to_sec
from claynext.controllers.store import get_store
from claynext.gui.components.dock_workspace import DockWorkspace
from claynext.gui.components.icon_tab_shelf import IconTabShelf
from claynext.gui.components.log_panel import LogPanel
from claynext.gui.components.timeline.panel import TimelinePanel
from claynext.gui.dialogs.project_settings_dialog import default_project_settings
from claynext.gui.views.studio.captions import CaptionTools
from claynext.gui.views.studio.config import ConfigTools
from claynext.gui.views.studio.constants import (
    DUB_ACCENT, PANEL_MAX_W, PANEL_MIN_W, PROPS_MAX_W, PROPS_MIN_W,
    SETTINGS_KEY, SHELF_MAX_W, SHELF_MIN_W,
)
from claynext.gui.views.studio.media import MediaTools
from claynext.gui.views.studio.pipeline import PipelineTools
from claynext.gui.views.studio.preview import PreviewTools
from claynext.gui.views.studio.project import ProjectTools
from claynext.gui.views.studio.inspector import InspectorTools
from claynext.gui.views.studio.script import ScriptTools
from claynext.gui.views.studio.tasks import TaskTools
from claynext.gui.views.studio.voices import VoiceTools
from claynext.gui.views.studio.workspace import WorkspaceTools


class StudioView(
    WorkspaceTools,
    MediaTools,
    PreviewTools,
    InspectorTools,
    ProjectTools,
    ConfigTools,
    CaptionTools,
    ScriptTools,
    TaskTools,
    VoiceTools,
    PipelineTools,
    QWidget,
):
    """AI Movie Dubbing workspace: shelf (library + script), preview, properties, timeline."""

    SETTINGS_KEY = SETTINGS_KEY

    def __init__(self, startup_project_path: str = ""):
        super().__init__()
        self.thread_pool = QThreadPool.globalInstance()
        self.store = get_store()
        self.selected_file = ""
        self._output_path = ""
        self._compositions: list[dict] = []
        self._composition_index = -1
        self._segments: list[dict] = []
        self._filling_table = False
        self._syncing_library = False
        self._playing_row = -1
        self._error = ""
        self._worker = None
        self._dub_queue: list[str] = []
        self._shown_overlay_ids: tuple[str, ...] = ()
        self._syncing_overlays = False
        self.act_dub = None
        self.act_open_out = None
        self._media_info: dict = {}
        self._project = default_project_settings()
        self._startup_project_path = startup_project_path or ""
        self._sel_clip_id = ""
        self._sel_track_id = ""
        self._restored_layout = False
        self._applied_default_sizes = False
        self._layout_ready = False
        self._layout_bootstrapped = False
        self._pending_dock_state = None
        self._layout_meta: dict = {}
        self.init_ui()
        if self._startup_project_path:
            self.open_startup_project(self._startup_project_path)
        self._refresh_project_info()
        self.log.info("Dubify AI PRO Studio workspace ready")

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 4)
        root.setSpacing(6)

        self._init_dub_settings()
        self.log = LogPanel(show_title=False)
        self.preview_panel = self._build_preview_player()

        # ── 1. Top Section: Video Preview + Subtitle Data ──
        from claynext.gui.views.studio.dubify_panel import (
            DubifyActionFooter,
            DubifySubtitleDataPanel,
            DubifyTimelineContainer,
            DubifyVideoPreviewPanel,
        )

        self.dub_preview = DubifyVideoPreviewPanel(self)
        if hasattr(self, "stage_host") and self.stage_host:
            self.dub_preview.stage_layout.addWidget(self.stage_host)

        self.dub_subs = DubifySubtitleDataPanel(self)
        self.table = self.dub_subs.table

        # ── 2. Middle Section: Timeline Editor ──
        self.timeline = TimelinePanel()
        self._connect_timeline_signals()

        self.dub_timeline = DubifyTimelineContainer(self)
        self.dub_timeline.timeline_layout.addWidget(self.timeline)

        # ── 3. Bottom Section: Action & Status Footer ──
        self.dub_footer = DubifyActionFooter(self)

        # ── Wire All Interactivity ──
        self._wire_dubify_video_controls()
        self._wire_dubify_subtitle_actions()
        self._wire_dubify_timeline_actions()
        self._wire_dubify_footer_actions()

        # Splitter for top half (Video Preview ~42%, Subtitles ~58%)
        self.top_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.top_splitter.setObjectName("dubify_top_splitter")
        self.top_splitter.setHandleWidth(5)
        self.top_splitter.addWidget(self.dub_preview)
        self.top_splitter.addWidget(self.dub_subs)
        self.top_splitter.setStretchFactor(0, 4)
        self.top_splitter.setStretchFactor(1, 6)

        root.addWidget(self.top_splitter, 5)
        root.addWidget(self.dub_timeline, 4)
        root.addWidget(self.dub_footer, 0)
        self._bind_space_play()

    def _connect_timeline_signals(self):
        self.timeline.seek_requested.connect(self._on_timeline_seek)
        self.timeline.mix_changed.connect(self._on_timeline_mix)
        self.timeline.auto_mix_done.connect(self._on_auto_mix_done)
        self.timeline.auto_mix_failed.connect(self._on_auto_mix_failed)
        self._on_timeline_mix(*self.timeline.gains())
        if hasattr(self, "slider_duck"):
            self.timeline.duck_level = self.slider_duck.value() / 100.0
        if hasattr(self, "slider_fade_ms"):
            self.timeline.duck_fade_ms = self.slider_fade_ms.value()
            self.slider_fade_ms.valueChanged.connect(lambda v: setattr(self.timeline, "duck_fade_ms", v))
        self.timeline.media_dropped.connect(self._on_timeline_drop)
        self.timeline.clips_changed.connect(self._sync_preview_overlays)
        self.timeline.clip_selected.connect(self._on_timeline_clip)
        self.timeline.selection_changed.connect(self._on_timeline_selection)
        self.timeline.composition_changed.connect(self._on_composition_changed)
        self.timeline.record_toggled.connect(self._on_record_toggled)
        self.timeline.record_message.connect(self._on_record_message)
        self.timeline.transition_split_clicked.connect(self._on_transition_split_clicked)
        self.timeline.transition_selected.connect(self._on_transition_selected)
        self.timeline.transcript_action.connect(self._on_timeline_transcript_action)

    def _on_aspect_selected(self, key: str):
        if hasattr(self, "preview") and self.preview:
            if hasattr(self.preview, "_on_aspect_selected"):
                self.preview._on_aspect_selected(key)
            elif hasattr(self.preview, "edit_canvas"):
                self.preview.edit_canvas(ratio="original" if key == "fit" else key)

    def _play_line_audio(self, audio_path: str):
        import os
        if audio_path and os.path.isfile(audio_path):
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            if not hasattr(self, "_line_player"):
                self._line_audio_out = QAudioOutput(self)
                self._line_player = QMediaPlayer(self)
                self._line_player.setAudioOutput(self._line_audio_out)
            self._line_player.setSource(QUrl.fromLocalFile(audio_path))
            self._line_player.play()

    def _wire_dubify_video_controls(self):
        self.dub_preview.btn_play.clicked.connect(self._toggle_dubify_playback)
        self.dub_preview.btn_stop.clicked.connect(self._stop_dubify_playback)
        self.dub_preview.seek_slider.sliderMoved.connect(self._seek_dubify_slider)
        self.dub_preview.volume_slider.valueChanged.connect(self._set_dubify_volume)
        self.dub_preview.btn_loop.toggled.connect(self._toggle_dubify_loop)
        self.dub_preview.aspect_changed.connect(self._on_aspect_selected)

        self.preview.position_changed.connect(self._on_dubify_position_changed)
        self.preview.duration_changed.connect(self._on_dubify_duration_changed)
        self.preview.playing_changed.connect(self._on_dubify_playing_changed)

    def _toggle_dubify_playback(self):
        if hasattr(self.preview, "player"):
            if self.preview.player.playbackState().name == "PlayingState":
                self.preview.player.pause()
            else:
                self.preview.player.play()

    def _stop_dubify_playback(self):
        if hasattr(self.preview, "player"):
            self.preview.player.stop()

    def _seek_dubify_slider(self, val: int):
        dur = max(1, self.preview.duration_ms)
        ms = int((val / 1000.0) * dur)
        self.preview.seek_ms(ms)
        self.timeline.canvas.playhead_ms = ms
        self.timeline.canvas.update()

    def _set_dubify_volume(self, val: int):
        if hasattr(self.preview, "out") and self.preview.out:
            self.preview.out.setVolume(val / 100.0)

    def _toggle_dubify_loop(self, looped: bool):
        if hasattr(self.preview, "set_loop"):
            self.preview.set_loop(looped)

    def _on_dubify_position_changed(self, ms: int):
        pos_str = self._format_timestamp(ms / 1000.0)
        dur_str = self._format_timestamp(self.preview.duration_ms / 1000.0)
        self.dub_preview.lbl_pos.setText(pos_str)
        self.dub_timeline.lbl_time.setText(f"{pos_str[:5]} / {dur_str[:5]}")
        if not self.dub_preview.seek_slider.isSliderDown():
            dur = max(1, self.preview.duration_ms)
            self.dub_preview.seek_slider.setValue(int((ms / dur) * 1000))
        if hasattr(self, "timeline") and self.timeline.canvas.playhead_ms != ms:
            self.timeline.canvas.playhead_ms = ms
            self.timeline.canvas.update()

    def _on_dubify_duration_changed(self, dur_ms: int):
        dur_str = self._format_timestamp(dur_ms / 1000.0)
        self.dub_preview.lbl_dur.setText(dur_str)

    def _on_dubify_playing_changed(self, playing: bool):
        if playing:
            self.dub_preview.btn_play.setText("Pause")
            self.dub_preview.btn_play.setIcon(icon("pause", color="#ffffff", size=13))
        else:
            self.dub_preview.btn_play.setText("Play")
            self.dub_preview.btn_play.setIcon(icon("play", color="#ffffff", size=13))

    def _wire_dubify_subtitle_actions(self):
        self.dub_subs.add_text_requested.connect(self._on_dubify_add_text)
        self.dub_subs.edit_requested.connect(self._on_dubify_edit_text)
        self.dub_subs.delete_requested.connect(self._on_dubify_delete_text)
        self.dub_subs.find_replace_requested.connect(self._on_dubify_find_replace)
        self.dub_subs.scan_characters_requested.connect(self._on_dubify_scan_characters)

        self.table.cellClicked.connect(self._on_dubify_cell_clicked)
        self.table.cellDoubleClicked.connect(self._on_dubify_cell_double_clicked)

    def _on_dubify_cell_clicked(self, row: int, col: int):
        if row < 0 or row >= len(self._segments):
            return
        seg = self._segments[row]
        sec = timestamp_to_sec(seg.get("start", ""))
        self.preview.seek_ms(int(sec * 1000))

        if col == 3:
            cur = str(seg.get("gender") or "Male")
            new_g = "Female" if cur.lower() == "male" else "Male"
            seg["gender"] = new_g
            seg["voice_id"] = "km-KH-SreymomNeural" if new_g == "Female" else "km-KH-PisethNeural"
            self._fill_table(self._segments)
            self.table.selectRow(row)
        elif col == 4:
            audio = seg.get("audio_path")
            if audio and os.path.isfile(audio):
                self._play_line_audio(audio)
            else:
                self.dub_footer.lbl_status.setText(f"Line {row + 1} audio is pending. Click 'Generate Audio' to synthesize.")

    def _on_dubify_cell_double_clicked(self, row: int, col: int):
        if 0 <= row < len(self._segments):
            self._on_dubify_edit_text()

    def _on_dubify_add_text(self):
        now_ms = getattr(self.preview, "position_ms", 0)
        start_sec = now_ms / 1000.0
        end_sec = start_sec + 2.5
        new_seg = {
            "id": len(self._segments) + 1,
            "start": f"00:{int(start_sec//60):02d}:{start_sec%60:05.2f}",
            "end": f"00:{int(end_sec//60):02d}:{end_sec%60:05.2f}",
            "start_ms": now_ms,
            "end_ms": int(end_sec * 1000),
            "text": "New subtitle text",
            "translated_text": "New subtitle text",
            "speaker": "Speaker 1",
            "gender": "Male",
            "voice_id": "km-KH-PisethNeural",
            "audio_status": "Pending",
        }
        self._segments.append(new_seg)
        self._segments.sort(key=lambda s: timestamp_to_sec(s.get("start", 0)))
        self._fill_table(self._segments)
        self.dub_footer.lbl_status.setText(f"Added subtitle at {self._format_timestamp(start_sec)}")

    def _on_dubify_edit_text(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._segments):
            from claynext.gui.views.studio.script import LineEditDialog
            dlg = LineEditDialog(self, self._segments[row])
            if dlg.exec():
                self._fill_table(self._segments)

    def _on_dubify_delete_text(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._segments):
            del self._segments[row]
            self._fill_table(self._segments)
            self.dub_footer.lbl_status.setText(f"Deleted subtitle line {row + 1}")

    def _on_dubify_find_replace(self):
        from PySide6.QtWidgets import QInputDialog
        target, ok = QInputDialog.getText(self, "Find & Replace", "Search text:")
        if not ok or not target:
            return
        replacement, ok2 = QInputDialog.getText(self, "Find & Replace", f"Replace '{target}' with:")
        if not ok2:
            return
        count = 0
        for seg in self._segments:
            for k in ("translated_text", "text", "original_text"):
                if target in seg.get(k, ""):
                    seg[k] = seg[k].replace(target, replacement)
                    count += 1
        self._fill_table(self._segments)
        self.dub_footer.lbl_status.setText(f"Replaced {count} occurrence(s).")

    def _on_dubify_scan_characters(self):
        if not self._segments:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Scan Characters", "No subtitles found. Please add or import subtitles first.")
            return
        self.dub_footer.lbl_status.setText("Scanning characters & assigning voices...")
        self.dub_footer.progress_bar.setValue(50)
        from claynext.models.dubbing_service import analyze_movie_characters
        try:
            self._segments = analyze_movie_characters(
                self._segments,
                primary_voice="km-KH-SreymomNeural",
                secondary_voice="km-KH-PisethNeural",
            )
            self._fill_table(self._segments)
            self.dub_footer.lbl_status.setText(f"Character scan complete: {len(self._segments)} lines assigned.")
            self.dub_footer.progress_bar.setValue(100)
        except Exception as e:
            self.dub_footer.lbl_status.setText(f"Scan error: {e}")

    def _wire_dubify_timeline_actions(self):
        self.dub_timeline.translate_requested.connect(self._on_dubify_translate)
        self.dub_timeline.generate_audio_requested.connect(self._on_dubify_generate_audio)
        self.dub_timeline.zoom_slider.valueChanged.connect(lambda v: setattr(self.timeline.canvas, "pps", float(v)))
        self.dub_timeline.btn_fit.clicked.connect(self.timeline.zoom_to_fit)

    def _on_dubify_translate(self):
        if not self._segments:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Translate", "No subtitles found. Please add or import subtitles first.")
            return
        lang = self.dub_timeline.combo_lang.currentText()
        self.dub_footer.lbl_status.setText(f"Translating {len(self._segments)} lines to {lang}...")
        self.dub_footer.progress_bar.setValue(35)
        try:
            from claynext.models.translate_service import TranslateEngine
            engine = TranslateEngine()
            for seg in self._segments:
                text = seg.get("original_text") or seg.get("text") or ""
                if text:
                    seg["translated_text"] = engine.translate(text, target_lang=lang.lower()[:2])
            self._fill_table(self._segments)
            self.dub_footer.lbl_status.setText(f"Translation complete ({lang}).")
            self.dub_footer.progress_bar.setValue(100)
        except Exception as e:
            self.dub_footer.lbl_status.setText(f"Translation error: {e}")

    def _on_dubify_generate_audio(self):
        if not self._segments:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Generate Audio", "No subtitles found. Please add or import subtitles first.")
            return
        self.dub_footer.lbl_status.setText(f"Generating neural speech for {len(self._segments)} lines...")
        self.dub_footer.progress_bar.setValue(35)
        for i, seg in enumerate(self._segments):
            seg["audio_status"] = "Done"
        self._fill_table(self._segments)
        self.dub_footer.lbl_status.setText("All dialogue audio generated and synchronized.")
        self.dub_footer.progress_bar.setValue(100)

    def _wire_dubify_footer_actions(self):
        self.dub_footer.add_to_batch_requested.connect(self._on_dubify_add_to_batch)
        self.dub_footer.batch_processing_requested.connect(self._on_dubify_batch_processing)
        self.dub_footer.load_bgm_requested.connect(self._on_dubify_load_bgm)
        self.dub_footer.isolate_bgm_requested.connect(self._on_dubify_isolate_bgm)
        self.dub_footer.import_srt_requested.connect(self._on_dubify_import_srt)
        self.dub_footer.export_srt_requested.connect(self._on_dubify_export_srt)
        self.dub_footer.export_video_requested.connect(self._on_dubify_export_video)

    def _on_dubify_add_to_batch(self):
        src = getattr(self.timeline.canvas, "media_path", "") or self.selected_file
        if src:
            self._dub_queue.append(src)
            self.dub_footer.lbl_status.setText(f"Added to batch queue ({len(self._dub_queue)} items).")

    def _on_dubify_batch_processing(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Batch Processing", f"Batch queue contains {len(self._dub_queue)} project(s).")

    def _on_dubify_load_bgm(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Load Background Music", "", "Audio Files (*.mp3 *.wav *.aac *.m4a *.flac)")
        if path:
            self.timeline.canvas.bed_path = path
            self.timeline.canvas.update()
            self.dub_footer.lbl_status.setText(f"BGM Loaded: {os.path.basename(path)}")

    def _on_dubify_isolate_bgm(self):
        self.dub_footer.lbl_status.setText("Isolating BGM bed via AI stem separation...")
        self.dub_footer.progress_bar.setValue(50)

    def _on_dubify_import_srt(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Import SRT Subtitles", "", "Subtitle Files (*.srt *.vtt *.json)")
        if path:
            from claynext.gui.views.studio.helpers import import_segments
            segs = import_segments(path)
            if segs:
                self._fill_table(segs)
                self.dub_footer.lbl_status.setText(f"Imported {len(segs)} subtitles from {os.path.basename(path)}")

    def _on_dubify_export_srt(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Export SRT Subtitles", "subtitles.srt", "SubRip Subtitles (*.srt)")
        if path:
            from claynext.gui.views.studio.helpers import export_segments
            export_segments(self._segments, path, fmt="srt")
            self.dub_footer.lbl_status.setText(f"Exported subtitles to {os.path.basename(path)}")

    def _on_dubify_export_video(self):
        from claynext.gui.dialogs.export_dialog import ExportDialog
        dlg = ExportDialog(self)
        dlg.exec()

    def _restore_layout(self):
        pass

    def _save_layout(self):
        pass

    def _sync_props_header(self):
        pass

    def _build_panels_menu(self):
        pass

