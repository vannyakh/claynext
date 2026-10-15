"""Recent projects panel: search, view mode, and project list/grid."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QSize, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from claynext.services.dub_project import (
    delete_project,
    forget_project,
    list_recent_projects,
    load_project,
    update_project,
)
from claynext.gui.components.home_mode_toggle import MODE_GRID, MODE_LIST, HomeModeToggle
from claynext.gui.components.home_project_card import (
    GRID_CARD_H,
    GRID_CARD_W,
    GRID_CELL,
    LIST_CARD_H,
    HomeProjectCard,
)
from claynext.gui.dialogs.project_settings_dialog import ProjectSettingsDialog, default_project_settings


class HomeRecentPanel(QWidget):
    """Recent projects browser used by Project Home."""

    open_requested = Signal(str)
    changed = Signal()  # emitted after rename/delete/remove-from-recent

    def __init__(self, view_mode: str = MODE_LIST, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []
        self._view_mode = MODE_GRID if view_mode == MODE_GRID else MODE_LIST

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 32, 24, 18)
        lay.setSpacing(16)

        head = QHBoxLayout()
        head.setSpacing(10)
        title = QLabel("Recent")
        title.setObjectName("home_section")
        head.addWidget(title)

        self.search = QLineEdit()
        self.search.setObjectName("home_search")
        self.search.setPlaceholderText("Search projects…")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedHeight(32)
        self.search.setMinimumWidth(220)
        self.search.setMaximumWidth(320)
        self.search.textChanged.connect(self._apply_filter)
        head.addWidget(self.search, 1)

        self.mode_toggle = HomeModeToggle(self._view_mode)
        self.mode_toggle.mode_changed.connect(self.set_view_mode)
        head.addWidget(self.mode_toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        # Header stays pinned at top; content below fills remaining height.
        lay.addLayout(head, 0)

        self.empty = QLabel("No recent projects yet.\nCreate a new project to get started.")
        self.empty.setObjectName("home_empty")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.list = QListWidget()
        self.list.setObjectName("home_recent")
        self.list.setSpacing(8)
        self.list.setUniformItemSizes(False)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        self.list.itemActivated.connect(self._on_item_activated)
        self.list.itemDoubleClicked.connect(self._on_item_activated)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._show_context_menu)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)  # index 0
        self.stack.addWidget(self.list)   # index 1
        lay.addWidget(self.stack, 1)

        self._apply_view_mode()
        self.stack.setCurrentWidget(self.empty)

    def _show_context_menu(self, pos):
        item = self.list.itemAt(pos)
        if item is None:
            return
        self.list.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction("Open", self._open_selected)
        menu.addAction("Update Project…", self._update_selected)
        menu.addSeparator()
        menu.addAction(
            "Show in Finder" if os.name == "posix" else "Show in Explorer",
            self._reveal_selected,
        )
        menu.addAction("Remove from Recent", self._forget_selected)
        menu.addSeparator()
        menu.addAction("Delete Project…", self._delete_selected)
        menu.exec(self.list.mapToGlobal(pos))

    @property
    def view_mode(self) -> str:
        return self._view_mode

    def set_view_mode(self, mode: str):
        next_mode = MODE_GRID if mode == MODE_GRID else MODE_LIST
        self._view_mode = next_mode
        QSettings("Claynext", "ClaynextStudio").setValue("home/view_mode", self._view_mode)
        self.mode_toggle.set_mode(self._view_mode, emit=False)
        self._apply_view_mode()
        self._rebuild_list(self._filtered_rows())

    def refresh(self):
        self._rows = list_recent_projects()
        self._apply_filter()

    def _apply_view_mode(self):
        if self._view_mode == MODE_GRID:
            self.list.setViewMode(QListView.ViewMode.IconMode)
            self.list.setFlow(QListView.Flow.LeftToRight)
            self.list.setWrapping(True)
            self.list.setGridSize(GRID_CELL)
            self.list.setSpacing(12)
            self.list.setUniformItemSizes(True)
        else:
            self.list.setViewMode(QListView.ViewMode.ListMode)
            self.list.setFlow(QListView.Flow.TopToBottom)
            self.list.setWrapping(False)
            self.list.setGridSize(QSize())
            self.list.setSpacing(8)
            self.list.setUniformItemSizes(True)

    def _filtered_rows(self) -> list[dict]:
        query = self.search.text().strip().lower()
        if not query:
            return list(self._rows)
        out: list[dict] = []
        for row in self._rows:
            hay = " ".join([
                str(row.get("name") or ""),
                str(row.get("path") or ""),
                os.path.basename(str(row.get("path") or "")),
            ]).lower()
            if query in hay:
                out.append(row)
        return out

    def _apply_filter(self, *_args):
        rows = self._filtered_rows()
        query = self.search.text().strip()
        if not self._rows:
            self.empty.setText("No recent projects yet.\nCreate a new project to get started.")
        elif not rows and query:
            self.empty.setText(f"No projects match “{query}”.")
        else:
            self.empty.setText("No recent projects yet.\nCreate a new project to get started.")
        self.stack.setCurrentWidget(self.list if rows else self.empty)
        self._rebuild_list(rows)

    def _rebuild_list(self, rows: list[dict]):
        self.list.clear()
        for row in rows:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, row["path"])
            item.setToolTip(str(row.get("path") or ""))
            if self._view_mode == MODE_GRID:
                item.setSizeHint(QSize(GRID_CARD_W, GRID_CARD_H))
            else:
                item.setSizeHint(QSize(100, LIST_CARD_H))
            self.list.addItem(item)
            card = HomeProjectCard(row, mode=self._view_mode)
            card.open_requested.connect(self.open_requested.emit)
            self.list.setItemWidget(item, card)

    def _on_item_activated(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.open_requested.emit(str(path))

    def _selected_path(self) -> str:
        item = self.list.currentItem()
        if not item:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    def _open_selected(self):
        path = self._selected_path()
        if path:
            self.open_requested.emit(path)

    def _reveal_selected(self):
        path = self._selected_path()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    def _forget_selected(self):
        path = self._selected_path()
        if not path:
            return
        forget_project(path)
        self.refresh()
        self.changed.emit()

    def _update_selected(self):
        path = self._selected_path()
        if not path:
            return
        try:
            data = load_project(path)
        except Exception as exc:
            QMessageBox.warning(self, "Update Project", f"Could not read project.\n{exc}")
            return

        settings = default_project_settings(name=str(data.get("name") or "Untitled"))
        project = data.get("project") if isinstance(data.get("project"), dict) else {}
        settings.update(project)
        settings["name"] = str(data.get("name") or settings.get("name") or "Untitled")
        settings["path"] = path
        settings["save_to"] = str(Path(path).parent)

        dlg = ProjectSettingsDialog(settings, self)
        dlg.setWindowTitle("Update Project")
        if hasattr(dlg, "btn_save"):
            dlg.btn_save.setText("Save")
        if not dlg.exec():
            return

        result = dlg.result_settings()
        new_name = str(result.get("name") or "Untitled").strip() or "Untitled"
        try:
            update_project(
                path,
                name=new_name,
                settings=result,
                rename_file=new_name != str(data.get("name") or ""),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Update Project", f"Could not update project.\n{exc}")
            return
        self.refresh()
        self.changed.emit()

    def _delete_selected(self):
        path = self._selected_path()
        if not path:
            return
        name = Path(path).name
        for row in self._rows:
            if row.get("path") == path:
                name = str(row.get("name") or name)
                break
        reply = QMessageBox.question(
            self,
            "Delete Project",
            f"Delete “{name}” permanently?\n\n{path}\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_project(path, delete_file=True)
        except Exception as exc:
            QMessageBox.warning(self, "Delete Project", f"Could not delete project.\n{exc}")
            return
        self.refresh()
        self.changed.emit()
