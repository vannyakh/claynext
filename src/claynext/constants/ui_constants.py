"""
Claynext Studio navigation items, layout constants, and icon asset mappings.
"""
import os
import sys

from PySide6.QtCore import Qt

# ─── Platform Detection ──────────────────────────────────────────────
# Custom frameless chrome is used on Windows only.
# macOS / Linux keep native window chrome + system menu bar.
# Override with CLAYNEXT_CUSTOM_CHROME=1 or =0.
_env_chrome = os.environ.get("CLAYNEXT_CUSTOM_CHROME", "").lower()
if _env_chrome in ("1", "true", "yes"):
    CUSTOM_WINDOW_CHROME = True
elif _env_chrome in ("0", "false", "no"):
    CUSTOM_WINDOW_CHROME = False
else:
    CUSTOM_WINDOW_CHROME = sys.platform == "win32"

# ─── Navigation Menu Items ───────────────────────────────────────────
NAV_ITEMS = [
    {
        "id": "studio",
        "label": "Claynext Studio",
        "short_label": "Studio",
        "index": 0,
        "desc": "AI Movie Dubbing & Timeline Editor",
        "icon": "volume",
        "logo_img": "icon_tool_dubbing",
        "banner": "banner_dubbing",
        "badge": "Studio",
        "color": "#a855f7",
        "tags": ["Multilingual", "Voice Cloning", "Timeline", "Studio Mix"],
        "long_desc": "End-to-end voice dubbing pipeline with vocal separation, translation, timbre voice cloning, timeline editing, and audio remixing.",
    },
]

# ─── Window Dimensions ───────────────────────────────────────────────
DEFAULT_WINDOW_WIDTH  = 1280
DEFAULT_WINDOW_HEIGHT = 800
MIN_WINDOW_WIDTH      = 1024
MIN_WINDOW_HEIGHT     = 680

# ─── Layout Dimensions ───────────────────────────────────────────────
SIDEBAR_WIDTH     = 220
SIDEBAR_MIN_WIDTH = 200
SIDEBAR_MAX_WIDTH = 240
HEADER_HEIGHT     = 48
TITLEBAR_HEIGHT   = 40
STATUSBAR_HEIGHT  = 26

# ─── Frameless Window Edge Resize ────────────────────────────────────
FRAME_MARGIN = 5
EDGE_CURSORS = {
    Qt.Edge.LeftEdge:                             Qt.CursorShape.SizeHorCursor,
    Qt.Edge.RightEdge:                            Qt.CursorShape.SizeHorCursor,
    Qt.Edge.TopEdge:                              Qt.CursorShape.SizeVerCursor,
    Qt.Edge.BottomEdge:                           Qt.CursorShape.SizeVerCursor,
    Qt.Edge.LeftEdge | Qt.Edge.TopEdge:           Qt.CursorShape.SizeFDiagCursor,
    Qt.Edge.RightEdge | Qt.Edge.BottomEdge:       Qt.CursorShape.SizeFDiagCursor,
    Qt.Edge.RightEdge | Qt.Edge.TopEdge:          Qt.CursorShape.SizeBDiagCursor,
    Qt.Edge.LeftEdge | Qt.Edge.BottomEdge:        Qt.CursorShape.SizeBDiagCursor,
}

# ─── Icon Asset Name Mappings ────────────────────────────────────────
ICON_NAMES = {
    "win_minimize": "win-minimize",
    "win_maximize": "win-maximize",
    "win_restore":  "win-restore",
    "win_close":    "win-close",
    "settings":     "settings",
    "folder":       "folder",
    "refresh":      "refresh",
    "copy":         "copy",
    "download":     "download",
    "play":         "play",
    "pause":        "pause",
    "stop":         "stop",
    "list":         "list",
    "grid":         "grid",
    "more":         "more",
    "activity":     "activity",
    "cpu":          "cpu",
    "gpu":          "gpu",
    "log":          "log",
    "external":     "external",
    # Nav tool icons
    "mic":          "mic",
    "volume":       "volume",
    "chat":         "chat",
    "globe":        "globe",
    "eye":          "eye",
    "video":        "video",
}
