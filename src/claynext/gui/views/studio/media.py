"""Media library shelf and file selection."""
from __future__ import annotations

import os

from PySide6.QtWidgets import QWidget, QVBoxLayout

from claynext.adapters.ffmpeg_service import probe_media
from claynext.models.thumbnails import IMAGE_EXTS
from claynext.gui.components.media_library import MediaLibraryWidget


class MediaTools:
    """Library shelf, open-file flow, and last-session restore."""

    def _build_media_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("media_panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(0)
        self.media_lib = MediaLibraryWidget()
        self.media_lib.file_selected.connect(self.on_file_selected)
        self.media_lib.selection_cleared.connect(self._on_library_deselected)
        self.media_lib.status_message.connect(self._on_media_status)
        self.media_lib.files_changed.connect(self._on_library_count)
        self.media_lib.localize_requested.connect(self.start_dubbing)
        self.media_lib.images_added.connect(self._place_image_elements)
        layout.addWidget(self.media_lib, 1)
        return panel

    def _on_media_status(self, msg: str):
        self.log.info(msg)

    def _on_library_count(self, count: int):
        if not self._syncing_library:
            self.store.sync_library(self.media_lib.paths())
        if count == 0:
            self.selected_file = ""
            self._source_preview_path = ""
            self._media_info = {}
            self._refresh_project_info()
            self._show_inspector_tab(2)
            if self._compositions:
                self._apply_composition(self._composition_index)
            else:
                self.preview.clear()
                self.timeline.clear()
                self._fill_table([])
                self._sync_preview_overlays(force=True)
                self._sync_timeline_visibility()

    def browse_media(self):
        self.media_lib.browse_add()

    def _place_image_elements(self, paths: list[str]):
        pictures = [p for p in paths or [] if p and os.path.isfile(p)]
        if not pictures or not hasattr(self, "timeline"):
            return
        self.timeline.add_images(pictures)
        name = os.path.basename(pictures[-1])
        self.log.info(f"Image element · {name}" if len(pictures) == 1 else f"Image elements · {len(pictures)}")

    def on_file_selected(self, file_path: str):
        if not file_path or not os.path.isfile(file_path):
            self._on_library_deselected()
            return
        if os.path.splitext(file_path)[1].lower() in IMAGE_EXTS:
            self._place_image_elements([file_path])
            return
        self.store.upsert_media(file_path)
        self.store.mark_opened(file_path)
        self.preview_source(file_path)

    def set_dub_source(self, file_path: str):
        if not file_path or not os.path.isfile(file_path):
            return
        if os.path.splitext(file_path)[1].lower() in IMAGE_EXTS:
            self._place_image_elements([file_path])
            return
        self.store.upsert_media(file_path)
        if file_path not in self.media_lib.paths():
            self.media_lib.add_files([file_path], select_last=False)
        previous = self.selected_file or ""
        changed = file_path != previous
        self.selected_file = file_path
        if not self._compositions:
            self._output_path = ""
            if self.act_open_out:
                self.act_open_out.setEnabled(False)
        name = os.path.basename(file_path)
        self._clear_error()
        try:
            self._media_info = probe_media(file_path)
        except Exception:
            self._media_info = {"name": name, "path": file_path}
        stem = os.path.splitext(name)[0]
        previous_stem = os.path.splitext(os.path.basename(previous))[0] if previous else ""
        current_name = str(self._project.get("name") or "")
        if not current_name or current_name == "Untitled" or (changed and current_name == previous_stem):
            self._project["name"] = stem
        self._project["media"] = file_path
        self._refresh_project_info()
        if hasattr(self, "_sync_player_header"):
            self._sync_player_header()
        if changed:
            self.log.info(f"Dub source · {name}")

    def _restore_workspace_data(self):
        # A chosen project file is the whole workspace. The last-session
        # library belongs to Studio launched with no project.
        if getattr(self, "_startup_project_path", ""):
            return
        rows = self.store.list_library()
        paths = []
        dropped_images = False
        for row in rows:
            path = row["path"]
            if not os.path.isfile(path):
                continue
            if os.path.splitext(path)[1].lower() in IMAGE_EXTS:
                dropped_images = True
                continue
            paths.append(path)
        last = self.store.last_opened_path()
        self._syncing_library = True
        if paths:
            self.media_lib.set_paths(paths, select=last if last in paths else None, quiet=True)
        self._syncing_library = False
        if dropped_images:
            self.store.sync_library(paths)
        if hasattr(self, "_restore_project_session"):
            self._restore_project_session()

