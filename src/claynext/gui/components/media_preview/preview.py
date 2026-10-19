"""Player stage: poster, video, and the project canvas."""
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QLabel, QStackedWidget
from PySide6.QtCore import (
    Qt,
    Signal,
    QPoint,
    QRect,
)
from PySide6.QtGui import QImage

from claynext.constants.theme_constants import COLOR_BG_CARD
from claynext.models.canvas import clean_canvas

from claynext.gui.components.media_preview.const import ZOOM_DEFAULT
from claynext.gui.components.media_preview.image import _fill_panel
from claynext.gui.components.media_preview.preview_canvas import PreviewCanvas
from claynext.gui.components.media_preview.preview_player import PreviewPlayer
from claynext.gui.components.media_preview.preview_view import PreviewView
from claynext.gui.components.media_preview.surface import _VideoSurface

class MediaPreviewWidget(PreviewCanvas, PreviewPlayer, PreviewView, QWidget):
    """
    Pure player stage (poster / video). Transport lives in MediaPlaybackWidget.
    """
    media_changed = Signal(str)
    media_cleared = Signal()
    loading_changed = Signal(bool)
    position_changed = Signal(int)
    duration_changed = Signal(int)
    playing_changed = Signal(bool)
    close_requested = Signal()
    fullscreen_changed = Signal(bool)
    aspect_changed = Signal(str)
    canvas_edited = Signal(dict)
    view_tool_changed = Signal(str)
    zoom_changed = Signal(float)

    AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}

    ASPECT_PRESETS = {
        "fit": (None, Qt.AspectRatioMode.KeepAspectRatio),
        "fill": (None, Qt.AspectRatioMode.IgnoreAspectRatio),
        "cover": (None, Qt.AspectRatioMode.KeepAspectRatioByExpanding),
        "16:9": (16.0 / 9.0, Qt.AspectRatioMode.IgnoreAspectRatio),
        "9:16": (9.0 / 16.0, Qt.AspectRatioMode.IgnoreAspectRatio),
        "1:1": (1.0, Qt.AspectRatioMode.IgnoreAspectRatio),
        "4:3": (4.0 / 3.0, Qt.AspectRatioMode.IgnoreAspectRatio),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("media_preview")
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._path = ""
        self._play_path = ""
        self._is_video = False
        self._fullscreen = False
        self._fs_window = None
        self._fs_target: tuple[QWidget, QWidget, int] | None = None
        self._title = ""
        self._load_gen = 0
        self._source_ready = False
        self._pending_play = False
        self._pending_seek = -1
        self._compat_worker = None
        self._aspect_key = "fit"
        self._custom_ratio = None
        self._video_natural_ratio = None

        # View zoom & pan — magnifies the wrapper view only; project canvas (fit) is unchanged.
        self._view_tool = "move"
        self._zoom_factor = ZOOM_DEFAULT
        self._pan_x = 0
        self._pan_y = 0
        self._dragging = False
        self._drag_start_pos = QPoint()
        self._drag_start_pan = (0, 0)
        self._fit_rect = QRect()

        self.init_ui()
        self._setup_player()

    def init_ui(self):
        # Clip magnified frame to the wrapper so zoom is a view, not a layout blow-out.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.canvas_frame = QWidget(self)
        self.canvas_frame.setObjectName("media_canvas")
        _fill_panel(self.canvas_frame, COLOR_BG_CARD)

        self.bg_label = QLabel(self.canvas_frame)
        self.bg_label.setObjectName("media_bg_label")
        self.bg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bg_label.setScaledContents(True)
        self.bg_label.hide()

        self.stage = QStackedWidget(self.canvas_frame)
        self.stage.setObjectName("media_stage")

        self.placeholder = QLabel("Select media to play")
        self.placeholder.setObjectName("media_placeholder")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.poster = QLabel()
        self.poster.setObjectName("media_poster")
        self.poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster.setScaledContents(False)

        self.video = _VideoSurface()
        self.video.setObjectName("media_video")
        self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)

        self.stage.addWidget(self.placeholder)
        self.stage.addWidget(self.poster)
        self.stage.addWidget(self.video)
        for surface in (self, self.stage, self.placeholder, self.poster, self.video):
            _fill_panel(surface, COLOR_BG_CARD)

        self.stage.installEventFilter(self)
        self.video.installEventFilter(self)
        self.poster.installEventFilter(self)
        self._canvas = clean_canvas(None)
        self._canvas_active = False
        self._canvas_covered = True
        self._adjust: dict = {}
        self._blur_src = QImage()
        self._blur_clock = 0.0
