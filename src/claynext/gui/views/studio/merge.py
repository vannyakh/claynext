"""Hot merge: drag source episodes into one movie order."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QDialogButtonBox, QHeaderView, QAbstractItemView,
)

from claynext.gui.worker import Worker
from claynext.adapters.ffmpeg_adapter import probe_duration
from claynext.gui.components.timeline.helpers import fmt_ms


class MergeOrderDialog(QDialog):
    """Preview table of episodes. Drag rows to set the full-movie order."""

    def __init__(
        self,
        paths: list[str],
        parent=None,
        *,
        title_text: str = "Episode order",
        hint_text: str = "Drag rows to arrange the source episodes. Merge renders them as one movie.",
        accept_label: str = "Merge movie",
        window_title: str = "Hot merge",
    ):
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self.setMinimumSize(520, 360)
        self._paths = [path for path in paths if path and os.path.isfile(path)]
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        title = QLabel(title_text)
        title.setObjectName("dub_panel_title")
        hint = QLabel(hint_text)
        hint.setObjectName("dub_switch_hint")
        hint.setWordWrap(True)
        self.table = QTableWidget(0, 3)
        self.table.setObjectName("transcript_table")
        self.table.setHorizontalHeaderLabels(["#", "Episode", "Duration"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setDropIndicatorShown(True)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.table.setDragDropOverwriteMode(False)
        self.table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(2, 72)
        self.table.model().rowsMoved.connect(lambda *_args: self._renumber())
        for path in self._paths:
            self._add_row(path, "…")
        lay.addWidget(title)
        lay.addWidget(hint)
        lay.addWidget(self.table, 1)
        buttons = QDialogButtonBox()
        self.merge_btn = buttons.addButton(accept_label, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.merge_btn.setEnabled(self.table.rowCount() >= 2)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        if self._paths:
            worker = Worker(self._durations, list(self._paths))
            worker.signals.result.connect(self._apply_durations)
            from PySide6.QtCore import QThreadPool
            QThreadPool.globalInstance().start(worker)

    def _add_row(self, path: str, duration: str):
        row = self.table.rowCount()
        self.table.insertRow(row)
        number = QTableWidgetItem(str(row + 1))
        number.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        name = QTableWidgetItem(os.path.basename(path))
        name.setData(Qt.ItemDataRole.UserRole, path)
        name.setToolTip(path)
        length = QTableWidgetItem(duration)
        length.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )
        for item in (number, name, length):
            item.setFlags(flags)
        self.table.setItem(row, 0, number)
        self.table.setItem(row, 1, name)
        self.table.setItem(row, 2, length)

    def _renumber(self):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setText(str(row + 1))
        if hasattr(self, "merge_btn"):
            self.merge_btn.setEnabled(self.table.rowCount() >= 2)

    @staticmethod
    def _durations(paths: list[str], progress_callback=None) -> list[str]:
        labels = []
        for path in paths:
            seconds = probe_duration(path)
            labels.append(fmt_ms(int(seconds * 1000)) if seconds > 0 else "—")
        return labels

    def _apply_durations(self, labels):
        if not isinstance(labels, list):
            return
        by_path = dict(zip(self._paths, labels))
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 1)
            cell = self.table.item(row, 2)
            if name and cell:
                cell.setText(by_path.get(name.data(Qt.ItemDataRole.UserRole), "—"))

    def ordered_paths(self) -> list[str]:
        paths = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            path = item.data(Qt.ItemDataRole.UserRole) if item else ""
            if path:
                paths.append(str(path))
        return paths

