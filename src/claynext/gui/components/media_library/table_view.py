"""List table and the row painter for the media library."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QAbstractItemView,
    QTableWidget,
    QHeaderView,
    QCheckBox,
    QApplication,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
)
from PySide6.QtCore import (
    Qt,
    QSize,
    QUrl,
    QMimeData,
    QPoint,
    QRectF,
    QModelIndex,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QFont,
)

from claynext.constants.theme_constants import (
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_SUB,
    COLOR_PRIMARY,
)
from claynext.gui.components.media_library.const import (
    _COL_CHECK, _COL_DUR, _COL_INDEX, _COL_NAME, _COL_PREVIEW, _COL_SIZE, _COL_TYPE,
)

class _MediaTableDelegate(QStyledItemDelegate):
    """Sleek Cyber Dark table delegate for media rows, icons, and indicators."""

    def __init__(self, parent=None, accent: str = COLOR_PRIMARY):
        super().__init__(parent)
        self.accent = QColor(COLOR_PRIMARY)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = option.rect
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        col = index.column()

        # Row Background
        if is_selected:
            # Translucent primary accent wash
            painter.fillRect(rect, QColor(99, 102, 241, 44))
            # Subtle top and bottom border
            pen_border = QPen(QColor(99, 102, 241, 90), 1)
            painter.setPen(pen_border)
            painter.drawLine(rect.topLeft(), rect.topRight())
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        elif is_hover:
            painter.fillRect(rect, QColor(255, 255, 255, 9))
            painter.setPen(QPen(QColor(30, 45, 64, 120), 1))
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        else:
            painter.setPen(QPen(QColor(30, 45, 64, 120), 1))
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        # Accent bar indicator on first column when selected
        if is_selected and col == _COL_INDEX:
            painter.setBrush(QBrush(QColor(COLOR_PRIMARY)))
            painter.setPen(Qt.PenStyle.NoPen)
            indicator = QRectF(rect.x() + 2, rect.y() + 8, 3, rect.height() - 16)
            painter.drawRoundedRect(indicator, 1.5, 1.5)

        # Checkbox column is rendered via cellWidget
        if col == _COL_CHECK:
            pass
        elif col == _COL_PREVIEW:
            ico = index.data(Qt.ItemDataRole.DecorationRole)
            if isinstance(ico, QIcon) and not ico.isNull():
                thumb_w, thumb_h = 44, 32
                tx = rect.x() + (rect.width() - thumb_w) // 2
                ty = rect.y() + (rect.height() - thumb_h) // 2
                thumb_rect = QRectF(tx, ty, thumb_w, thumb_h)

                clip_path = QPainterPath()
                clip_path.addRoundedRect(thumb_rect, 4, 4)
                painter.save()
                painter.setClipPath(clip_path)
                pix = ico.pixmap(QSize(thumb_w * 2, thumb_h * 2))
                painter.drawPixmap(thumb_rect.toRect(), pix)
                painter.restore()

                painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(thumb_rect, 4, 4)
        else:
            text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
            align = int(index.data(Qt.ItemDataRole.TextAlignmentRole) or (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))

            font = painter.font()
            if col == _COL_NAME:
                font.setWeight(QFont.Weight.DemiBold)
                painter.setFont(font)
                color = QColor("#ffffff" if is_selected else COLOR_TEXT_MAIN)
            elif col == _COL_INDEX:
                font.setWeight(QFont.Weight.Bold if is_selected else QFont.Weight.Normal)
                painter.setFont(font)
                color = QColor("#c4b5fd" if is_selected else COLOR_TEXT_MUTED)
            elif col == _COL_TYPE:
                font.setWeight(QFont.Weight.Medium)
                painter.setFont(font)
                color = QColor("#d8b4fe" if is_selected else COLOR_TEXT_SUB)
            else:
                color = QColor("#e2e8f0" if is_selected else COLOR_TEXT_MUTED)

            painter.setPen(color)
            pad_x = 8 if col == _COL_NAME else 4
            text_rect = rect.adjusted(pad_x, 0, -pad_x, 0)
            elided = painter.fontMetrics().elidedText(
                text,
                Qt.TextElideMode.ElideMiddle if col == _COL_NAME else Qt.TextElideMode.ElideRight,
                text_rect.width(),
            )
            painter.drawText(text_rect, align, elided)

        painter.restore()

class _MediaTable(QTableWidget):
    """Columned list: index, batch checkbox, rubber-band select, file drag-out."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("media_lib_list")
        self.setColumnCount(7)
        self.setHorizontalHeaderLabels(["#", "", "", "Name", "Type", "Duration", "Size"])
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(48)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setIconSize(QSize(44, 44))
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.setItemDelegate(_MediaTableDelegate(self))

        # Drag disabled so click-drag rubber-bands a selection; file DnD is manual.
        self.setDragEnabled(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self._press_pos: QPoint | None = None
        self._press_on_selected = False
        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(True)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(_COL_INDEX, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(_COL_CHECK, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(_COL_PREVIEW, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_TYPE, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(_COL_DUR, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(_COL_SIZE, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(_COL_INDEX, 28)
        self.setColumnWidth(_COL_CHECK, 28)
        self.setColumnWidth(_COL_PREVIEW, 54)
        self.setColumnWidth(_COL_TYPE, 68)
        self.setColumnWidth(_COL_DUR, 74)
        self.setColumnWidth(_COL_SIZE, 76)

        self.header_check = QCheckBox(header)
        self.header_check.setObjectName("media_lib_row_check")
        self.header_check.setToolTip("Select all")
        self.header_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header_check.setTristate(True)
        self.header_check.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header.sectionResized.connect(self._place_header_check)
        header.geometriesChanged.connect(self._place_header_check)

    def _place_header_check(self, *_args):
        header = self.horizontalHeader()
        x = header.sectionViewportPosition(_COL_CHECK)
        w = header.sectionSize(_COL_CHECK)
        h = header.height()
        box_w, box_h = 16, 16
        self.header_check.setGeometry(
            x + max(0, (w - box_w) // 2),
            max(0, (h - box_h) // 2),
            box_w,
            box_h,
        )
        self.header_check.show()
        self.header_check.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self._place_header_check()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            self._press_pos = pos
            item = self.itemAt(pos)
            self._press_on_selected = bool(item and item.isSelected())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if (
            self._press_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and self._press_on_selected
            and self.selectedItems()
        ):
            dist = (event.position().toPoint() - self._press_pos).manhattanLength()
            if dist >= QApplication.startDragDistance():
                self._press_pos = None
                self.startDrag(Qt.DropAction.CopyAction)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._press_pos = None
        self._press_on_selected = False
        super().mouseReleaseEvent(event)

    def mimeData(self, items):
        mime = super().mimeData(items) or QMimeData()
        urls = []
        seen: set[str] = set()
        for item in items:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and path not in seen and os.path.isfile(path):
                seen.add(path)
                urls.append(QUrl.fromLocalFile(path))
        if urls:
            mime.setUrls(urls)
        return mime
