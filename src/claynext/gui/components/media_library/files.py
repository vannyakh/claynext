"""Paths, thumbnails, and file actions for the media library."""
from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtWidgets import (
    QWidget,
    QListWidgetItem,
    QFileDialog,
    QTableWidgetItem,
)
from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtGui import QBrush, QColor, QIcon

from claynext.constants.theme_constants import COLOR_TEXT_MUTED, COLOR_TEXT_SUB
from claynext.gui.icons import icon
from claynext.models.thumbnails import VIDEO_EXTS, IMAGE_EXTS

from claynext.gui.components.media_library.const import (
    _COL_CHECK, _COL_DUR, _COL_INDEX, _COL_NAME, _COL_PREVIEW, _COL_SIZE, _COL_TYPE,
)
from claynext.gui.components.media_library.jobs import _DurJob, _ThumbJob

class LibraryFiles:
    def _active_view(self) -> QWidget:
        return self.grid_view if self._view_mode == "grid" else self.list_view

    def _kind_for(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        if ext in VIDEO_EXTS:
            return "Video"
        if ext in self.AUDIO_EXTS:
            return "Audio"
        if ext in IMAGE_EXTS:
            return "Image"
        return "Media"

    def paths(self) -> list[str]:
        return list(self._paths)

    def set_paths(self, paths: list[str], *, select: str | None = None, quiet: bool = False):
        seen: list[str] = []
        for path in paths:
            abs_path = os.path.abspath(path)
            if abs_path in seen or not os.path.isfile(abs_path):
                continue
            ext = os.path.splitext(abs_path)[1].lower()
            if ext not in self.MEDIA_EXTS:
                continue
            seen.append(abs_path)
        self._paths = seen
        self._refresh_items()
        self._apply_view_mode()
        self._update_count()
        if not quiet:
            self.files_changed.emit(len(self._paths))
        target = None
        if select and select in self._paths:
            target = select
        elif self._paths:
            target = self._paths[0]
        if target:
            self.select_path(target)

    def add_files(self, paths: list[str], *, select_last: bool = True):
        added = []
        for path in paths:
            if not path:
                continue
            abs_path = os.path.abspath(path)
            ext = os.path.splitext(abs_path)[1].lower()
            if ext not in self.MEDIA_EXTS:
                continue
            if abs_path in self._paths:
                continue
            if not os.path.isfile(abs_path):
                continue
            self._paths.append(abs_path)
            added.append(abs_path)

        if not added:
            return

        self._refresh_items()
        self._apply_view_mode()
        self._update_count()
        self.files_changed.emit(len(self._paths))
        self.status_message.emit(f"Added {len(added)} media file(s)")

        if select_last:
            self.select_paths(added)

    def browse_add(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Media Files",
            "",
            "Media Files (*.mp4 *.mkv *.avi *.mov *.webm *.mp3 *.wav *.flac *.png *.jpg *.jpeg *.webp *.gif);;All Files (*.*)",
        )
        if paths:
            self.add_files(paths)

    def remove_selected(self):
        view = self._active_view()
        selected = [item.data(Qt.ItemDataRole.UserRole) for item in view.selectedItems()]
        selected = [p for p in selected if p]
        if not selected:
            self.status_message.emit("No media selected to remove")
            return
        self._paths = [p for p in self._paths if p not in selected]
        for p in selected:
            self._thumb_cache.pop(p, None)
            self._meta_cache.pop(p, None)
            self._dur_cache.pop(p, None)
        self._refresh_items()
        self._apply_view_mode()
        self._update_count()
        self.files_changed.emit(len(self._paths))
        self.status_message.emit(f"Removed {len(selected)} file(s)")
        if not self._paths:
            self.file_selected.emit("")

    def clear_all(self):
        if not self._paths:
            return
        n = len(self._paths)
        self._paths.clear()
        self._thumb_cache.clear()
        self._meta_cache.clear()
        self._dur_cache.clear()
        self.list_view.setRowCount(0)
        self.grid_view.clear()
        self._apply_view_mode()
        self._update_count()
        self.files_changed.emit(0)
        self.status_message.emit(f"Cleared {n} file(s)")
        self.file_selected.emit("")

    def reveal_selected(self):
        view = self._active_view()
        items = view.selectedItems()
        path = items[-1].data(Qt.ItemDataRole.UserRole) if items else None
        if not path or not os.path.exists(path):
            self.status_message.emit("Nothing to reveal")
            return
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", "-R", path], check=False)
            elif sys.platform.startswith("win"):
                subprocess.run(["explorer", "/select,", os.path.normpath(path)], check=False)
            else:
                subprocess.run(["xdg-open", os.path.dirname(path)], check=False)
        except Exception:
            self.status_message.emit("Could not reveal file")

    def selected_paths(self) -> list[str]:
        paths: list[str] = []
        seen: set[str] = set()
        if self._view_mode == "grid":
            items = self.grid_view.selectedItems()
        else:
            items = self.list_view.selectedItems()
        for item in items:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and path not in seen:
                seen.add(path)
                paths.append(path)
        return paths

    def clear_selection(self):
        for view in (self.list_view, self.grid_view):
            view.blockSignals(True)
            view.clearSelection()
            view.blockSignals(False)
        self._sync_row_checks()
        self._update_detail_footer()

    def select_path(self, path: str):
        self.select_paths([path])

    def select_paths(self, paths: list[str]):
        wanted = []
        for path in paths:
            if path and path not in wanted:
                wanted.append(path)
        wanted_set = set(wanted)
        primary = wanted[-1] if wanted else ""

        self.grid_view.blockSignals(True)
        self.grid_view.clearSelection()
        current_grid = None
        for i in range(self.grid_view.count()):
            item = self.grid_view.item(i)
            item_path = item.data(Qt.ItemDataRole.UserRole) if item else None
            if item and item_path in wanted_set:
                item.setSelected(True)
                if item_path == primary:
                    current_grid = item
        if current_grid is not None:
            self.grid_view.setCurrentItem(current_grid, QItemSelectionModel.SelectionFlag.NoUpdate)
            current_grid.setSelected(True)
        self.grid_view.blockSignals(False)

        rows: list[int] = []
        primary_row: int | None = None
        for row in range(self.list_view.rowCount()):
            cell = self.list_view.item(row, _COL_INDEX)
            path = cell.data(Qt.ItemDataRole.UserRole) if cell else None
            if path in wanted_set:
                rows.append(row)
                if path == primary:
                    primary_row = row
        self._select_list_rows(rows, primary_row=primary_row)
        self._sync_row_checks()
        self._update_detail_footer()

        self._had_selection = bool(primary)
        if primary:
            self.file_selected.emit(primary)

    def _fallback_icon(self, path: str) -> QIcon:
        ext = os.path.splitext(path)[1].lower()
        if ext in VIDEO_EXTS:
            return icon("video", color="#38bdf8", size=32)
        if ext in self.AUDIO_EXTS:
            return icon("volume", color="#a855f7", size=32)
        if ext in IMAGE_EXTS:
            return icon("grid", color="#a78bfa", size=32)
        return icon("folder", color="#94a3b8", size=32)

    def _refresh_items(self):
        selected = set(self.selected_paths())

        self.list_view.blockSignals(True)
        self.grid_view.blockSignals(True)
        self.list_view.setRowCount(0)
        self.grid_view.clear()

        muted = QBrush(QColor(COLOR_TEXT_MUTED))
        sub = QBrush(QColor(COLOR_TEXT_SUB))

        for path in self._visible_paths():
            name = os.path.basename(path)
            ext = os.path.splitext(path)[1].lower()
            kind = self._kind_for(path)
            size_txt = self._size_label(path)
            dur_txt = self._duration_label(path)
            ico = self._thumb_cache.get(path) or self._fallback_icon(path)
            checked = path in selected

            row = self.list_view.rowCount()
            self.list_view.insertRow(row)

            index_item = QTableWidgetItem(str(row + 1))
            index_item.setData(Qt.ItemDataRole.UserRole, path)
            index_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            index_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            index_item.setForeground(muted)
            self.list_view.setItem(row, _COL_INDEX, index_item)

            check_item = QTableWidgetItem()
            check_item.setData(Qt.ItemDataRole.UserRole, path)
            check_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.list_view.setItem(row, _COL_CHECK, check_item)
            self.list_view.setCellWidget(
                row, _COL_CHECK, self._make_row_check(path, checked)
            )

            preview = QTableWidgetItem()
            preview.setIcon(ico)
            preview.setData(Qt.ItemDataRole.UserRole, path)
            preview.setToolTip(path)
            preview.setFlags(preview.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.list_view.setItem(row, _COL_PREVIEW, preview)

            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, path)
            name_item.setToolTip(path)
            self.list_view.setItem(row, _COL_NAME, name_item)

            type_item = QTableWidgetItem(kind)
            type_item.setData(Qt.ItemDataRole.UserRole, path)
            type_item.setForeground(sub)
            self.list_view.setItem(row, _COL_TYPE, type_item)

            dur_item = QTableWidgetItem(dur_txt)
            dur_item.setData(Qt.ItemDataRole.UserRole, path)
            dur_item.setForeground(muted)
            self.list_view.setItem(row, _COL_DUR, dur_item)

            size_item = QTableWidgetItem(size_txt)
            size_item.setData(Qt.ItemDataRole.UserRole, path)
            size_item.setForeground(muted)
            self.list_view.setItem(row, _COL_SIZE, size_item)

            tip_dur = f" · {dur_txt}" if dur_txt != "—" else ""
            grid_item = QListWidgetItem(ico, name)
            grid_item.setData(Qt.ItemDataRole.UserRole, path)
            grid_item.setToolTip(f"{name}\n{kind}{tip_dur} · {size_txt}\n{path}")
            grid_item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.grid_view.addItem(grid_item)
            if checked:
                grid_item.setSelected(True)

            if ext in VIDEO_EXTS | IMAGE_EXTS and path not in self._thumb_cache:
                self._thumb_pool.start(_ThumbJob(path, 96, self._thumb_signals))
            if kind in ("Video", "Audio") and path not in self._dur_cache:
                self._thumb_pool.start(_DurJob(path, self._dur_signals))

        restore_rows = [
            r for r in range(self.list_view.rowCount())
            if (self.list_view.item(r, _COL_INDEX) or QTableWidgetItem()).data(
                Qt.ItemDataRole.UserRole
            ) in selected
        ]
        self._select_list_rows(restore_rows)
        self.list_view.blockSignals(False)
        self.grid_view.blockSignals(False)
        self._update_header_check()
        self._update_detail_footer()

    def _on_thumb_ready(self, path: str, ico: object):
        if path not in self._paths or not isinstance(ico, QIcon) or ico.isNull():
            return
        self._thumb_cache[path] = ico
        for row in range(self.list_view.rowCount()):
            cell = self.list_view.item(row, _COL_PREVIEW)
            if cell and cell.data(Qt.ItemDataRole.UserRole) == path:
                cell.setIcon(ico)
                break
        for i in range(self.grid_view.count()):
            item = self.grid_view.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                item.setIcon(ico)
                break
        self._update_detail_footer()

    def _on_duration_ready(self, path: str, seconds: float, info: dict | None = None):
        if path not in self._paths:
            return
        self._dur_cache[path] = max(0.0, float(seconds or 0.0))
        if info:
            self._meta_cache[path] = info
        label = self._format_duration(self._dur_cache[path])
        for row in range(self.list_view.rowCount()):
            cell = self.list_view.item(row, _COL_DUR)
            if cell and cell.data(Qt.ItemDataRole.UserRole) == path:
                cell.setText(label if self._dur_cache[path] > 0 else "—")
                break
        self._update_detail_footer()

    def _duration_label(self, path: str) -> str:
        kind = self._kind_for(path)
        if kind not in ("Video", "Audio"):
            return "—"
        if path not in self._dur_cache:
            return "…"
        secs = self._dur_cache[path]
        return self._format_duration(secs) if secs > 0 else "—"

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total = max(0, int(round(seconds)))
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @classmethod
    def _size_label(cls, path_or_bytes: str | int | float) -> str:
        if isinstance(path_or_bytes, (int, float)):
            return cls._format_bytes(float(path_or_bytes))
        try:
            size = os.path.getsize(str(path_or_bytes))
            return cls._format_bytes(float(size))
        except OSError:
            return "—"

    @staticmethod
    def _format_bytes(size: float) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return "—"
