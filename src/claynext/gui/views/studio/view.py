"""Claynext Studio workspace. Tool behavior lives in sibling modules."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy, QMessageBox, QFileDialog

from claynext.controllers.store import get_store
from claynext.gui.components.shell.dock import DOCK_HEADER_H, DockWorkspace
from claynext.gui.components.timeline.sequence_bar import SEQUENCE_ROW_H
from claynext.gui.components.shell.icon_tabs import IconTabShelf
from claynext.gui.components.shell.log import LogPanel
from claynext.gui.components.timeline.panel import TimelinePanel
from claynext.gui.dialogs.project_settings_dialog import default_project_settings
from claynext.gui.views.studio.captions import CaptionTools
from claynext.gui.views.studio.characters import CharacterTools
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
from claynext.gui.views.studio.script_edit import ScriptEditTools
from claynext.gui.views.studio.script_export import ScriptExportTools
from claynext.gui.views.studio.script_jobs import ScriptJobTools
from claynext.gui.views.studio.script_panel import ScriptPanelTools
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
    ScriptPanelTools,
    CharacterTools,
    ScriptExportTools,
    ScriptJobTools,
    ScriptEditTools,
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
        self._restore_layout()
        self._restore_workspace_data()
        if self._startup_project_path:
            self.open_startup_project(self._startup_project_path)
        self._refresh_project_info()
        self._sync_timeline_visibility()
        self.log.info("Studio workspace ready")

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(0)

        self.workspace = DockWorkspace(self)
        root.addWidget(self.workspace, 1)

        self._init_dub_settings()
        media_panel = self._build_media_panel()
        text_panel = self._build_text_panel()
        voice_panel = self._build_voice_panel()
        tasks_panel = self._build_tasks_panel()
        properties_panel = self._build_properties_panel()
        preview_panel = self._build_preview_player()
        script_panel = self._build_script_panel()
        character_panel = self._build_character_panel()
        self.log = LogPanel(show_title=False)
        self.timeline = TimelinePanel()
        self.timeline.seek_requested.connect(self._on_timeline_seek)
        self.timeline.mix_changed.connect(self._on_timeline_mix)
        self.timeline.auto_mix_done.connect(self._on_auto_mix_done)
        self.timeline.auto_mix_failed.connect(self._on_auto_mix_failed)
        self._on_timeline_mix(*self.timeline.gains())
        self.timeline.duck_level = self.slider_duck.value() / 100.0
        self.timeline.duck_fade_ms = self.slider_fade_ms.value()
        self.slider_fade_ms.valueChanged.connect(lambda value: setattr(self.timeline, "duck_fade_ms", value))
        self.timeline.media_dropped.connect(self._on_timeline_drop)
        self.timeline.clips_changed.connect(self._sync_preview_overlays)
        self.timeline.clip_selected.connect(self._on_timeline_clip)
        self.timeline.selection_changed.connect(self._on_timeline_selection)
        self.timeline.composition_changed.connect(self._on_composition_changed)
        self.timeline.sequences.add_requested.connect(self._add_composition)
        self.timeline.sequences.reordered.connect(self._reorder_composition)
        self.timeline.sequences.rename_requested.connect(self._rename_composition)
        self.timeline.sequences.delete_requested.connect(self._delete_composition)
        self.timeline.sequences.export_requested.connect(self._export_composition)
        self.timeline.record_toggled.connect(self._on_record_toggled)
        self.timeline.record_message.connect(self._on_record_message)
        self.timeline.transition_split_clicked.connect(self._on_transition_split_clicked)
        self.timeline.transition_selected.connect(self._on_transition_selected)
        self.timeline.transcript_action.connect(self._on_timeline_transcript_action)
        self.timeline.studio_action.connect(self._on_studio_action)

        self.shelf = IconTabShelf(accent_color=DUB_ACCENT)
        self.shelf.add_tab("media", "folder", "Movie library · start dubbing", media_panel)
        self.shelf.add_tab("tasks", "list", "Pick a movie, start a dub task, and open finished tasks", tasks_panel)
        self.shelf.add_tab("script", "chat", "Dub script · edit lines, import / export", script_panel)
        self.shelf.add_tab("characters", "mic", "Characters · create a cast and assign voices", character_panel)
        self.shelf.add_tab("voices", "volume", "Preview voices and favorites", voice_panel)
        self.shelf.add_tab("text", "type", "On-screen text", text_panel)
        self.shelf.add_tab("effects", "sparkles", "Video effects", self._build_fx_panel("effect"))
        self.shelf.add_tab("filters", "filter", "Colour filters", self._build_fx_panel("filter"))
        self.shelf.add_tab("transitions", "transition", "Built-in transitions", self._build_fx_panel("transition"))
        self.shelf.add_tab("shapes", "shapes", "Elements (shapes, masks, callouts & blur)", self._build_fx_panel("shape"))
        self.shelf.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.shelf.setMinimumWidth(max(200, SHELF_MIN_W - 44))
        self.shelf.setMaximumWidth(16777215)

        host = self.workspace.host
        host.setCorner(Qt.Corner.TopLeftCorner, Qt.DockWidgetArea.TopDockWidgetArea)
        host.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.TopDockWidgetArea)
        host.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.BottomDockWidgetArea)
        host.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.timeline_stage = DockWorkspace(self)
        self.timeline_stage.setObjectName("timeline_stage")
        stage = self.timeline_stage.host
        stage.setCentralWidget(self.timeline)
        # A side dock keeps the full height of the timeline, not a short strip.
        stage.setCorner(Qt.Corner.TopLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        stage.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        stage.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        stage.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.timeline_stage.add_panel(
            "sequences", "Sequences", self.timeline.sequences,
            Qt.DockWidgetArea.TopDockWidgetArea, closable=False,
        )
        self.timeline.sequences.presence_changed.connect(self._show_sequences)
        seq_dock = self.timeline_stage.dock("sequences")
        if seq_dock is not None:
            seq_dock.setToolTip("Drag Sequences to the right edge to split it beside the timeline")
            seq_dock.dockLocationChanged.connect(self._place_sequences)
            seq_dock.topLevelChanged.connect(self._float_sequences)
        self._place_sequences(Qt.DockWidgetArea.TopDockWidgetArea)
        self.timeline_stage.save_default_layout()
        self.timeline_stage.set_visible("sequences", False)
        self.timeline_stage.layout_changed.connect(self._on_layout_changed)
        host.setCentralWidget(self.timeline_stage)

        self.workspace.add_panel(
            "shelf", "Studio Library & Setup", self.shelf, Qt.DockWidgetArea.TopDockWidgetArea,
            closable=False, min_width=SHELF_MIN_W, max_width=SHELF_MAX_W,
        )
        self.workspace.add_panel(
            "preview", "Video Preview", preview_panel, Qt.DockWidgetArea.TopDockWidgetArea,
            min_width=PANEL_MIN_W, max_width=PANEL_MAX_W,
        )
        self.workspace.split("shelf", "preview", Qt.Orientation.Horizontal)
        self.workspace.add_panel(
            "props", "Properties", properties_panel, Qt.DockWidgetArea.TopDockWidgetArea,
            min_width=PROPS_MIN_W, max_width=PROPS_MAX_W,
        )
        self.workspace.split("preview", "props", Qt.Orientation.Horizontal)
        self._sync_props_header()
        self.workspace.add_panel(
            "log", "Activity Log", self.log, Qt.DockWidgetArea.BottomDockWidgetArea,
            min_width=PANEL_MIN_W,
        )
        self.workspace.layout_changed.connect(self._on_layout_changed)
        self.workspace.set_visible("log", False)
        self.workspace.save_default_layout()
        self.shelf.tab_changed.connect(lambda *_: self._save_layout())
        self._build_panels_menu()
        self._bind_space_play()

    def _place_sequences(self, area):
        """A top dock stays a short row. Left or right becomes a column."""
        vertical = area in (
            Qt.DockWidgetArea.LeftDockWidgetArea,
            Qt.DockWidgetArea.RightDockWidgetArea,
        )
        bar = self.timeline.sequences
        bar.set_follow_size(False)
        bar.set_vertical(vertical)
        dock = self.timeline_stage.dock("sequences")
        if dock is None:
            return
        limit = 16777215
        if vertical:
            dock.setProperty("dock_min_w", 180)
            dock.setProperty("dock_max_w", 420)
            dock.setMinimumWidth(180)
            dock.setMaximumWidth(420)
            dock.setMinimumHeight(0)
            dock.setMaximumHeight(limit)
            dock.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            host = self.timeline_stage.host
            QTimer.singleShot(0, lambda d=dock, window=host: window.resizeDocks(
                [d], [max(window.height(), 120)], Qt.Orientation.Vertical,
            ))
        else:
            dock.setProperty("dock_min_w", None)
            dock.setProperty("dock_max_w", None)
            dock.setMinimumWidth(0)
            dock.setMaximumWidth(limit)
            row_h = DOCK_HEADER_H + SEQUENCE_ROW_H + 4
            dock.setMinimumHeight(row_h)
            dock.setMaximumHeight(row_h)
            host = self.timeline_stage.host
            QTimer.singleShot(0, lambda d=dock, window=host, height=row_h: window.resizeDocks(
                [d], [height], Qt.Orientation.Vertical,
            ))

    def _float_sequences(self, floating: bool):
        self.timeline.sequences.set_follow_size(bool(floating))
        if floating:
            dock = self.timeline_stage.dock("sequences")
            if dock is not None:
                dock.setMaximumHeight(16777215)
                dock.setMaximumWidth(16777215)

    def _show_sequences(self, show: bool):
        if not hasattr(self, "timeline_stage"):
            return
        if not bool(getattr(self, "_timeline_open", True)):
            show = False
        self.timeline_stage.set_visible("sequences", bool(show))

    def _on_studio_action(self, action: str):
        """Route timeline Studio tools menu actions."""
        key = str(action or "").strip().lower()
        handlers = {
            "vocal": self._on_vocal_isolation,
            "translate": self._on_translate_subtitles,
            "scan": self._on_scan_characters,
            "generate": self._on_generate_all_audio,
            "import_srt": self._on_import_srt,
            "export_srt": self._on_export_srt,
            "bgm": self._on_load_bgm,
            "export_video": self._on_export_video,
        }
        fn = handlers.get(key)
        if fn:
            fn()

    def _status(self, message: str):
        if hasattr(self, "log") and self.log is not None:
            self.log.info(message)

    def _on_translate_subtitles(self):
        if hasattr(self, "_translate_transcript_direct"):
            self._translate_transcript_direct()
            return
        if not self._segments:
            if hasattr(self, "log"):
                self.log.warn("Translate · no subtitles found")
            return
        if hasattr(self, "_regenerate_rows"):
            self._regenerate_rows(list(range(len(self._segments))))

    def _on_generate_all_audio(self):
        if not self._segments:
            if hasattr(self, "log"):
                self.log.warn("Generate audio · no subtitles found")
            return
        if hasattr(self, "_resynthesize_rows"):
            self._resynthesize_rows(list(range(len(self._segments))))

    def _on_scan_characters(self):
        if hasattr(self, "_run_ai_cast_analysis"):
            self._run_ai_cast_analysis()
            return
        if hasattr(self, "_open_frame_ocr_scanner"):
            self._open_frame_ocr_scanner()
            return
        if hasattr(self, "_autodetect_genders"):
            self._autodetect_genders(None, all_lines=True)
            return
        if hasattr(self, "shelf"):
            self.shelf.show_key("script")

    def _on_vocal_isolation(self):
        source = str(getattr(self, "selected_file", "") or "")
        if not source or not os.path.isfile(source):
            if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
                source = str(getattr(self.timeline.canvas, "source_path", "") or "")
        if not source or not os.path.isfile(source):
            tid = self._current_script_task_id() if hasattr(self, "_current_script_task_id") else -1
            task = self._task_by_id(tid) if tid >= 0 and hasattr(self, "_task_by_id") else None
            if task and task.get("source") and os.path.isfile(str(task.get("source"))):
                source = str(task.get("source"))

        if not source or not os.path.isfile(source):
            self._status("No movie loaded. Please load a movie or footage first.")
            if hasattr(self, "log"):
                self.log.warn("Isolate BGM bed · no movie file loaded on timeline")
            return

        if getattr(self, "_vocal_isolation_worker", None) is not None:
            if hasattr(self, "log"):
                self.log.warn("Stem separation already running")
            return

        from claynext.gui.worker import Worker
        from claynext.adapters.ffmpeg_service import ensure_speech_bed

        self._status("Isolating BGM bed via AI stem separation…")
        if hasattr(self, "_set_script_loading"):
            self._set_script_loading(True, "Isolating BGM Bed…", "Stem separation in progress")

        def _job(progress_callback=None):
            def _ping(pct: int, msg: str):
                if progress_callback:
                    progress_callback(pct, msg)
            return ensure_speech_bed(source, progress_callback=_ping, use_demucs=True)

        worker = Worker(_job)
        def _on_progress(p: int, m: str):
            self._status(f"Isolating BGM bed ({p}%) · {m}")
            if hasattr(self, "_set_script_loading_hint"):
                self._set_script_loading_hint(f"{p}% · {m}")

        worker.signals.progress.connect(_on_progress)
        worker.signals.result.connect(self._on_vocal_isolation_ready)
        worker.signals.error.connect(self._on_vocal_isolation_error)
        worker.signals.finished.connect(self._on_vocal_isolation_finished)
        self._vocal_isolation_worker = worker
        self.thread_pool.start(worker)

    def _on_vocal_isolation_ready(self, bed_path: str):
        if not bed_path or not os.path.isfile(bed_path):
            self._status("Could not isolate BGM bed")
            if hasattr(self, "log"):
                self.log.error("Stem separation produced no audio bed")
            return

        if hasattr(self, "timeline"):
            if hasattr(self.timeline, "set_speech_bed"):
                self.timeline.set_speech_bed(bed_path)
            elif hasattr(self.timeline, "canvas"):
                self.timeline.canvas.bed_path = bed_path
            if hasattr(self.timeline, "canvas"):
                self.timeline.canvas.update()
            if hasattr(self.timeline, "auto_duck"):
                self.timeline.auto_duck(0.0)

        if hasattr(self, "preview") and hasattr(self.preview, "player"):
            self.preview.player.set_stems(bed=bed_path)

        base = os.path.basename(bed_path)
        self._status(f"BGM bed isolated & applied: {base}")
        if hasattr(self, "log"):
            self.log.success(f"✨ BGM Bed Isolated & Applied: {base}")

    def _on_vocal_isolation_error(self, message: str, _stack: str):
        self._status(f"Vocal isolation failed: {message}")
        if hasattr(self, "log"):
            self.log.error(f"Vocal isolation error · {message}")

    def _on_vocal_isolation_finished(self):
        self._vocal_isolation_worker = None
        if hasattr(self, "_set_script_loading"):
            self._set_script_loading(False)

    def _on_load_bgm(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Background Music", "", "Audio Files (*.mp3 *.wav *.aac *.m4a *.flac)"
        )
        if path:
            self.timeline.canvas.bed_path = path
            self.timeline.canvas.update()
            self._status(f"BGM Loaded: {os.path.basename(path)}")

    def _on_import_srt(self):
        if hasattr(self, "_import_script"):
            self._import_script("srt")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import SRT Subtitles", "", "Subtitle Files (*.srt *.vtt *.json)"
        )
        if path:
            from claynext.gui.views.studio.helpers import import_segments
            segs = import_segments(path)
            if segs:
                self._fill_table(segs)
                self._status(f"Imported {len(segs)} subtitles from {os.path.basename(path)}")

    def _on_export_srt(self):
        if hasattr(self, "_export_subtitles"):
            self._export_subtitles("srt", "current")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export SRT Subtitles", "subtitles.srt", "SubRip Subtitles (*.srt)"
        )
        if path:
            from claynext.gui.views.studio.helpers import export_segments
            export_segments(path, "srt", self._segments)
            self._status(f"Exported subtitles to {os.path.basename(path)}")

    def _on_export_video(self):
        if hasattr(self, "open_export_dialog"):
            self.open_export_dialog("movie")
            return
        from claynext.gui.dialogs.export_dialog import ExportDialog
        dlg = ExportDialog(self)
        dlg.exec()

