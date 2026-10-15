"""
Claynext Studio Icon System.
Loads and recolors SVG icons from the assets/icons directory.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from claynext.utils.paths import BASE_DIR

ASSETS_DIR = BASE_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
IMAGES_DIR = ASSETS_DIR / "images"

# Default icon stroke colors for dark / light themes
ICON_ON_DARK = "#c5d0dc"
ICON_ON_LIGHT = "#1c1e21"


@lru_cache(maxsize=128)
def _read_svg(name: str) -> str:
    """Read and cache raw SVG source from the icons directory."""
    path = ICONS_DIR / f"{name}.svg"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


@lru_cache(maxsize=512)
def icon(name: str, color: str = ICON_ON_DARK, size: int = 18) -> QIcon:
    """
    Return an SVG icon recolored with `color`, rendered crisply at 2x DPI.
    The SVG must use `currentColor` as its stroke/fill value.
    """
    svg_src = _read_svg(name)
    if not svg_src:
        return QIcon()

    svg_recolored = svg_src.replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(svg_recolored.encode("utf-8")))
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    pixmap.setDevicePixelRatio(2.0)
    return QIcon(pixmap)


def icon_fg(dark: bool) -> str:
    """Return the correct icon stroke color for the current theme."""
    return ICON_ON_DARK if dark else ICON_ON_LIGHT


get_icon = icon


@lru_cache(maxsize=64)
def image_pixmap(name: str, height: int = 32) -> QPixmap:
    """Load a PNG image from the images directory, scaled to height."""
    path = IMAGES_DIR / f"{name}.png"
    pixmap = QPixmap(str(path))
    if pixmap.isNull() or pixmap.height() == height:
        return pixmap
    return pixmap.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)


def image_icon(name: str, height: int = 32) -> QIcon:
    """Load a PNG image as a QIcon."""
    return QIcon(image_pixmap(name, height))
