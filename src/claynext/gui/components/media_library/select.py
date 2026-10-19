"""Row checks, selection, and file drops for the media library."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QListWidgetItem,
    QTableWidgetItem,
    QCheckBox,
)
from PySide6.QtCore import Qt, QItemSelectionModel, QItemSelection
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from claynext.gui.components.media_library.const import _COL_CHECK, _COL_INDEX, _COL_NAME

class LibrarySelect:
    def _make_row_check(self, path: str, checked: bool) -> QWidget:
        """Tight centered checkbox widget for the trim check column."""
        wrap = QWidget()
        wrap.setObjectName("media_lib_check_wrap")
        wrap.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        box = QCheckBox()
        box.setObjectName("media_lib_row_check")
        box.setCursor(Qt.CursorShape.PointingHandCursor)
        box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        box.setChecked(checked)
        box.setProperty("media_path", path)
        box.stateChanged.connect(lambda state, p=path: self._on_row_check(p, state))
        lay.addWidget(box)
        return wrap

    def _row_check_at(self, row: int) -> QCheckBox | None:
        wrap = self.list_view.cellWidget(row, _COL_CHECK)
        if wrap is None:
            return None
        return wrap.findChild(QCheckBox, "media_lib_row_check")

    def _list_selected_paths(self) -> set[str]:
        selected: set[str] = set()
        for item in self.list_view.selectedItems():
            path = item.data(Qt.ItemDataRole.UserRole)
            if path:
                selected.add(path)
        return selected

    def _select_list_rows(self, rows: list[int], *, primary_row: int | None = None):
        """Select many rows without clear-on-each-selectRow."""
        self.list_view.blockSignals(True)
        model = self.list_view.model()
        sel_model = self.list_view.selectionModel()
        if not rows:
            sel_model.clearSelection()
            self.list_view.blockSignals(False)
            return
        selection = QItemSelection()
        last_col = self.list_view.columnCount() - 1
        for row in rows:
            left = model.index(row, 0)
            right = model.index(row, last_col)
            selection.select(left, right)
        sel_model.select(
            selection,
            QItemSelectionModel.SelectionFlag.ClearAndSelect
            | QItemSelectionModel.SelectionFlag.Rows,
        )
        focus = primary_row if primary_row is not None else rows[-1]
        sel_model.setCurrentIndex(
            model.index(focus, _COL_NAME),
            QItemSelectionModel.SelectionFlag.NoUpdate,
        )
        self.list_view.blockSignals(False)

    def _sync_row_checks(self):
        selected = self._list_selected_paths() if self._view_mode == "list" else set()
        self._syncing_checks = True
        for row in range(self.list_view.rowCount()):
            box = self._row_check_at(row)
            cell = self.list_view.item(row, _COL_CHECK)
            if not box or not cell:
                continue
            path = cell.data(Qt.ItemDataRole.UserRole)
            box.blockSignals(True)
            box.setChecked(path in selected)
            box.blockSignals(False)
        self._syncing_checks = False
        self._update_header_check()

    def _update_header_check(self):
        rows = self.list_view.rowCount()
        hdr = self.list_view.header_check
        hdr.blockSignals(True)
        if rows <= 0:
            hdr.setCheckState(Qt.CheckState.Unchecked)
            hdr.blockSignals(False)
            return
        n_checked = 0
        for r in range(rows):
            box = self._row_check_at(r)
            if box and box.isChecked():
                n_checked += 1
        if n_checked == 0:
            hdr.setCheckState(Qt.CheckState.Unchecked)
        elif n_checked == rows:
            hdr.setCheckState(Qt.CheckState.Checked)
        else:
            hdr.setCheckState(Qt.CheckState.PartiallyChecked)
        hdr.blockSignals(False)

    def _on_header_check(self, _checked: bool = False):
        rows = self.list_view.rowCount()
        if rows <= 0:
            return
        all_on = all(
            (box := self._row_check_at(r)) is not None and box.isChecked()
            for r in range(rows)
        )
        select_all = not all_on

        self._syncing_checks = True
        for row in range(rows):
            box = self._row_check_at(row)
            if not box:
                continue
            box.blockSignals(True)
            box.setChecked(select_all)
            box.blockSignals(False)
        self._syncing_checks = False

        self._select_list_rows(list(range(rows)) if select_all else [])
        self._update_header_check()
        self._on_selection()

    def _on_row_check(self, path: str, state: int):
        if self._syncing_checks or not path:
            return
        checked = Qt.CheckState(state) == Qt.CheckState.Checked
        selected = self._list_selected_paths()
        if checked:
            selected.add(path)
        else:
            selected.discard(path)
        rows = [
            r for r in range(self.list_view.rowCount())
            if (self.list_view.item(r, _COL_INDEX) or QTableWidgetItem()).data(
                Qt.ItemDataRole.UserRole
            ) in selected
        ]
        self._select_list_rows(rows)
        self._update_header_check()
        self._on_selection()

    def _on_selection(self):
        if self._view_mode == "list":
            self._sync_row_checks()
        self._update_detail_footer()
        paths = self.selected_paths()
        if not paths:
            if self._had_selection:
                self._had_selection = False
                self.selection_cleared.emit()
            return
        self._had_selection = True
        self.file_selected.emit(paths[-1])

    def _on_footer_preview(self, path: str):
        if path:
            self.file_selected.emit(path)

    def _on_activate(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.file_selected.emit(path)

    def _on_table_activate(self, row: int, _column: int):
        cell = self.list_view.item(row, _COL_INDEX)
        path = cell.data(Qt.ItemDataRole.UserRole) if cell else None
        if path:
            self.file_selected.emit(path)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        expanded = []
        for p in paths:
            if os.path.isdir(p):
                for name in os.listdir(p):
                    fp = os.path.join(p, name)
                    if os.path.isfile(fp):
                        expanded.append(fp)
            else:
                expanded.append(p)
        self.add_files(expanded)
        event.acceptProposedAction()
