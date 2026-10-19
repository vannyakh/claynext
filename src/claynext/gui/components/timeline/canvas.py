"""Sequence canvas: tracks, clips, filmstrip, and playhead."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPoint, QRectF
from PySide6.QtWidgets import QWidget

from claynext.gui.components.timeline.canvas_const import _as_envelope
from claynext.gui.components.timeline.canvas_edit import CanvasEdit
from claynext.gui.components.timeline.canvas_input import CanvasInput
from claynext.gui.components.timeline.canvas_layout import CanvasLayout
from claynext.gui.components.timeline.canvas_media import CanvasMedia
from claynext.gui.components.timeline.canvas_paint import CanvasPaint
from claynext.gui.components.timeline.canvas_volume import CanvasVolume
from claynext.gui.components.timeline.models import TimelineTrack, new_track


class TimelineCanvas(
    CanvasLayout,
    CanvasMedia,
    CanvasEdit,
    CanvasVolume,
    CanvasPaint,
    CanvasInput,
    QWidget,
):
    seek_requested = Signal(int)
    clip_selected = Signal(str)
    clips_changed = Signal()
    files_dropped = Signal(list, str)
    track_picked = Signal(str, bool)
    height_changed = Signal(str, int)
    history_changed = Signal()
    gains_changed = Signal()
    transition_split_clicked = Signal(str, int)  # left_clip_id, cut_ms
    transition_selected = Signal(str)  # left_clip_id
    # track_id, clip_id ("" if empty lane), global cursor pos
    context_menu_requested = Signal(str, str, QPoint)
    # Hover scrub tip: ms, clip_id, track_id, local canvas x (for guide line)
    hover_scrub_changed = Signal(int, str, str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("timeline_canvas")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.pps = 36.0
        self.duration_ms = 0
        self.playhead_ms = 0
        self.media_path = ""
        self.media_name = ""
        self.tracks: list[TimelineTrack] = [
            new_track("video"),
            new_track("voice"),
        ]
        self.clips: list[TimelineClip] = []
        self.selected_ids: set[str] = set()
        self.selected_seam_clip_id: str = ""
        self.selected_transition_clip_id: str = ""
        self._hover_seam_clip_id: str = ""
        self._hover_seam_part: str = ""
        self._hover_guide_x: int = -1
        self._hover_tip_active = False
        self._transition_trim: tuple[str, str, int, int] | None = None
        self._frames: list[QPixmap] = []
        self._wave = _as_envelope(None)
        self._waves: dict[str, np.ndarray] = {}
        self._exposed = QRectF()
        self.voice_path = ""
        self.bed_path = ""
        self.snap = True
        self._scrub = False
        self._drag_ids: list[str] = []
        self._drag_origin_ms: dict[str, int] = {}
        self._press_x = 0
        self._trim: tuple[str, str, int, int, int, int] | None = None
        self._trim_origin: tuple[int, int, int] | None = None
        self._marquee: QRect | None = None
        self._drop_track = ""
        self._resize_tid = ""
        self._resize_y = 0
        self._resize_h = 0
        self._fill_h = 0
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        self._history_lock = False
        self._edit_before: dict | None = None
        self._volume_cid = ""
        self._volume_key = -1
        self._volume_key_ms = 0
        self._volume_x = 0
        self._last_gains = (1.0, 1.0, 0.0)
        self.rec_track = ""
        self.rec_start = -1
        self.rec_ms = 0
        self.tool_mode = "select"
        self.show_waveforms = True
        self.dub_focus = True  # Cover + Voice only (movie dub workflow)

