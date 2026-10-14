"""
Jela Studio Icon System.
Loads and recolors SVG icons from the assets/icons directory.
Inspired by CamDot's icon pipeline with LRU caching and 2x rendering.
"""
import os
from functools import lru_cache

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtSvg import QSvgRenderer


_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.dirname(_CORE_DIR)
_PKG_DIR = os.path.dirname(_SRC_DIR)
_PROJECT_ROOT = os.path.dirname(_PKG_DIR)

ASSETS_DIR = os.path.join(_PROJECT_ROOT, "assets")
ICONS_DIR = os.path.join(ASSETS_DIR, "icons")
IMAGES_DIR = os.path.join(ASSETS_DIR, "images")

# Default icon stroke colors for dark / light themes
ICON_ON_DARK = "#c5d0dc"
ICON_ON_LIGHT = "#1c1e21"


@lru_cache(maxsize=128)
def _read_svg(name: str) -> str:
    """Read and cache raw SVG source from the icons directory."""
    path = os.path.join(ICONS_DIR, f"{name}.svg")
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


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

    from PySide6.QtGui import QPainter
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
    path = os.path.join(IMAGES_DIR, f"{name}.png")
    pixmap = QPixmap(path)
    if pixmap.isNull() or pixmap.height() == height:
        return pixmap
    return pixmap.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)


def image_icon(name: str, height: int = 32) -> QIcon:
    """Load a PNG image as a QIcon."""
    return QIcon(image_pixmap(name, height))
