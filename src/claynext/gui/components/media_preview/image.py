"""Colour grade, effects, and blur for preview frames."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QPalette,
    QPixmap,
)

from claynext.models.adjust import grade_rgb
from claynext.models.canvas import PREVIEW_BLUR_DIV
from claynext.models.fx import apply_fx

def _fill_panel(widget, color: str) -> None:
    """Paint a playback surface with the panel color so letterbox matches the frame."""
    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(color))
    widget.setPalette(palette)
    widget.setAutoFillBackground(True)

def grade_image(image: QImage, adjust: dict | None) -> QImage:
    """Colour-grade a QImage with the footage adjustments (live preview approximation)."""
    if not adjust or image.isNull():
        return image
    img = image.convertToFormat(QImage.Format.Format_RGB888)
    w, h, line = img.width(), img.height(), img.bytesPerLine()
    rgb = np.frombuffer(img.constBits(), np.uint8, count=line * h).reshape(h, line)[:, : w * 3].reshape(h, w, 3)
    out = np.ascontiguousarray(grade_rgb(rgb, adjust))
    return QImage(out.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()

def fx_image(image: QImage, spans: list[dict], now_ms: int) -> QImage:
    """Timeline effects and filter looks on a QImage (live preview of fx_filters)."""
    if not spans or image.isNull():
        return image
    img = image.convertToFormat(QImage.Format.Format_RGB888)
    w, h, line = img.width(), img.height(), img.bytesPerLine()
    rgb = np.frombuffer(img.constBits(), np.uint8, count=line * h).reshape(h, line)[:, : w * 3].reshape(h, w, 3)
    out = np.ascontiguousarray(apply_fx(rgb, spans, now_ms))
    return QImage(out.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()

def blur_image(image: QImage, size: QSize, level: int) -> QPixmap:
    """Cover-crop `image` to `size` and soften it to the canvas blur level."""
    w, h = size.width(), size.height()
    if image.isNull() or w <= 0 or h <= 0:
        return QPixmap()
    smooth = Qt.TransformationMode.SmoothTransformation
    cover = image.scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, smooth)
    cover = cover.copy((cover.width() - w) // 2, (cover.height() - h) // 2, w, h)
    div = PREVIEW_BLUR_DIV.get(level, 18)
    small = cover.scaled(max(2, w // div), max(2, h // div), Qt.AspectRatioMode.IgnoreAspectRatio, smooth)
    mid = small.scaled(max(2, w // 4), max(2, h // 4), Qt.AspectRatioMode.IgnoreAspectRatio, smooth)
    return QPixmap.fromImage(mid.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, smooth))
