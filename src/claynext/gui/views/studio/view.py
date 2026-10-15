"""Claynext Studio workspace. Tool behavior lives in sibling modules."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy

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
        self.timeline.record_toggled.connect(self._on_record_toggled)
        self.timeline.record_message.connect(self._on_record_message)
        self.timeline.transition_split_clicked.connect(self._on_transition_split_clicked)
        self.timeline.transition_selected.connect(self._on_transition_selected)
        self.timeline.transcript_action.connect(self._on_timeline_transcript_action)

        self.shelf = IconTabShelf(accent_color=DUB_ACCENT)
        self.shelf.add_tab("tasks", "list", "Pick a movie, start a dub task, and open finished tasks", tasks_panel)
        self.shelf.add_tab("script", "chat", "Dub script · edit lines, import / export", script_panel)
        self.shelf.add_tab("voices", "volume", "Preview voices and favorites", voice_panel)
        self.shelf.add_tab("media", "folder", "Movie library · start dubbing", media_panel)
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
        host.setCentralWidget(self.timeline)

        self.workspace.add_panel(
            "shelf", "Studio Library & Setup", self.shelf, Qt.DockWidgetArea.TopDockWidgetArea,
            closable=False, min_width=SHELF_MIN_W, max_width=SHELF_MAX_W,
        )
        self.workspace.add_panel(
            "preview", "Video Preview", preview_panel, Qt.DockWidgetArea.TopDockWidgetArea,
            min_width=PANEL_MIN_W, max_width=PANEL_MAX_W,
        )
        self.workspace.split("shelf", "preview", Qt.Orientation.Horizontal)
        self.workspace.set_header_widget("preview", self.player_header)
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
