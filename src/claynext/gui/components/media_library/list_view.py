"""Grid of library files that can be dragged onto the timeline."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QMimeData, QUrl
from PySide6.QtWidgets import QAbstractItemView, QListWidget

class _MediaList(QListWidget):
    """Grid view that can drag local files onto the timeline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

    def mimeData(self, items):
        mime = super().mimeData(items) or QMimeData()
        urls = []
        for item in items:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and os.path.isfile(path):
                urls.append(QUrl.fromLocalFile(path))
        if urls:
            mime.setUrls(urls)
        return mime
