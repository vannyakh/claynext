"""Catalog table for the models settings panel."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QPushButton, QTableWidget,
    QTableWidgetItem, QWidget,
)


def paint_progress(btn: QPushButton, percent: int) -> None:
    """Fill the install button from the left as the download advances."""
    pct = max(0, min(99, int(percent)))
    stop = pct / 100
    btn.setText(f"{pct}%")
    btn.setEnabled(False)
    btn.setStyleSheet(
        "QPushButton {"
        "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        f"stop:0 #6366f1, stop:{stop:.3f} #6366f1, "
        f"stop:{stop:.3f} #2a3350, stop:1 #2a3350);"
        "color: #ffffff; border: none; border-radius: 6px;"
        "font-size: 11px; font-weight: 600; padding: 0 8px;"
        "}"
    )


class ModelsTable(QTableWidget):
    """Model, type, size, status, and the install button."""

    install_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settings_models_table")
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["Model", "Type", "Size", "Status", ""])
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(3, 112)
        self.setColumnWidth(4, 128)
        self.setViewportMargins(0, 0, 16, 0)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(40)
        self.setShowGrid(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._buttons: dict[str, QPushButton] = {}

    def button(self, repo_id: str) -> QPushButton | None:
        return self._buttons.get(repo_id)

    def fill(self, models: list[dict], installing: str | None, percent: int) -> None:
        self.setRowCount(0)
        self._buttons = {}
        for row, item in enumerate(models):
            self.insertRow(row)
            name = QTableWidgetItem(item["name"])
            name.setToolTip(item.get("hint") or item.get("description") or item["id"])
            self.setItem(row, 0, name)

            kind_item = QTableWidgetItem(str(item.get("category", "")).upper())
            kind_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, 1, kind_item)

            size_item = QTableWidgetItem(item.get("size_label", ""))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, 2, size_item)

            repo_id = item["id"]
            action = str(item.get("action") or "install")
            installing_row = installing == repo_id
            if installing_row:
                status_text, status_color = "Installing", "#6366f1"
            elif action == "unsupported":
                status_text, status_color = "Unsupported", "#f59e0b"
            elif action == "cloud":
                status_text, status_color = "Cloud", "#64748b"
            elif item.get("ready"):
                status_text, status_color = "Downloaded", "#10b981"
            else:
                status_text, status_color = "Available", "#64748b"
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setForeground(QColor(status_color))
            if item.get("hint"):
                status_item.setToolTip(str(item["hint"]))
            self.setItem(row, 3, status_item)

            labels = {"ready": "Ready", "cloud": "Cloud", "unsupported": "No"}
            btn = QPushButton(labels.get(action, "Install"))
            btn.setObjectName("settings_model_btn")
            btn.setProperty("tone", "ready" if action in {"ready", "cloud", "unsupported"} else "install")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.setEnabled(action == "install" and not installing)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(24)
            btn.setMinimumWidth(78)
            if item.get("hint"):
                btn.setToolTip(str(item["hint"]))
            if installing_row:
                paint_progress(btn, percent)
            btn.clicked.connect(lambda _=False, rid=repo_id: self.install_requested.emit(rid))
            self._buttons[repo_id] = btn
            wrap = QWidget()
            wrap_l = QHBoxLayout(wrap)
            wrap_l.setContentsMargins(4, 6, 18, 6)
            wrap_l.addStretch(1)
            wrap_l.addWidget(btn)
            self.setCellWidget(row, 4, wrap)
