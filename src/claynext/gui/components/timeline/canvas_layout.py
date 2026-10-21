"""Track geometry, zoom, and time mapping."""
from __future__ import annotations

from PySide6.QtCore import (
    QRectF,
    QPoint,
    QSize,
)

from claynext.constants.timeline_constants import (
    DUB_FOCUS_KINDS,
    PRESET,
    TRACK_MAX_H,
    TRACK_MIN_H,
)
from claynext.gui.components.timeline.canvas_const import HIDDEN_VIEW_OPACITY
from claynext.gui.components.timeline.models import (
    TimelineClip,
    TimelineTrack,
    new_track,
)


class CanvasLayout:
    """Track geometry, zoom, and time mapping."""

    def lane_visible(self, track: TimelineTrack | None) -> bool:
        if track is None:
            return False
        if self.dub_focus and track.kind not in DUB_FOCUS_KINDS:
            return False
        return True

    def set_dub_focus(self, on: bool):
        self.dub_focus = bool(on)
        self._relayout(notify=False)

    def track_by_id(self, tid: str) -> TimelineTrack | None:
        return next((t for t in self.tracks if t.id == tid), None)

    def clip_by_id(self, cid: str) -> TimelineClip | None:
        return next((c for c in self.clips if c.id == cid), None)

    def tracks_of(self, kind: str) -> list[TimelineTrack]:
        return [t for t in self.tracks if t.kind == kind]

    def ensure_track(self, kind: str) -> TimelineTrack:
        # Transitions live on Cover seams — never create a Transition lane.
        if kind == "transition":
            kind = "video"
        found = self.tracks_of(kind)
        if found:
            return found[0]
        n = sum(1 for t in self.tracks if t.kind == kind) + 1
        track = new_track(kind, n)
        # The top row is layer 1. A new lane opens there.
        self.tracks.insert(0, track)
        return track

    def free_track(self, kind: str, start_ms: int, end_ms: int) -> TimelineTrack:
        """First unlocked track of `kind` with nothing in [start, end); otherwise a new one beside them."""
        if kind == "transition":
            return self.ensure_track("video")
        same = self.tracks_of(kind)
        for track in same:
            busy = any(
                c.track_id == track.id and c.start_ms < end_ms and start_ms < c.end_ms
                for c in self.clips
            )
            if not track.locked and not busy:
                return track
        track = new_track(kind, len(same) + 1)
        self.tracks.insert(0, track)
        return track

    def track_top(self, tid: str) -> int:
        y = 0
        for t in self.tracks:
            if not self.lane_visible(t):
                continue
            if t.id == tid:
                return y
            y += t.height
        return y

    def track_at_y(self, y: int) -> TimelineTrack | None:
        cur = 0
        for t in self.tracks:
            if not self.lane_visible(t):
                continue
            if cur <= y < cur + t.height:
                return t
            cur += t.height
        return None

    def total_height(self) -> int:
        tracks_h = sum(t.height for t in self.tracks if self.lane_visible(t))
        return max(48, tracks_h, int(self._fill_h or 0))

    def content_width(self) -> int:
        dur_s = max(8.0, self.duration_ms / 1000.0) if self.duration_ms else 16.0
        return int(dur_s * self.pps + 80)

    def sizeHint(self):
        return QSize(self.content_width(), self.total_height())

    def minimumSizeHint(self):
        return QSize(self.content_width(), self.total_height())

    def begin_quiet(self) -> None:
        """Hold layout and signals while a sequence is swapped in."""
        self._quiet = int(getattr(self, "_quiet", 0)) + 1

    def end_quiet(self) -> None:
        self._quiet = max(0, int(getattr(self, "_quiet", 0)) - 1)
        if self._quiet == 0:
            self._relayout(notify=True)

    def _relayout(self, *, notify: bool = True):
        if int(getattr(self, "_quiet", 0)):
            return
        vw = self.parent().width() if self.parent() is not None else 0
        w = max(self.content_width(), int(vw), 1)
        h = self.total_height()
        if self.minimumWidth() != w or self.minimumHeight() != h or self.width() != w or self.height() != h:
            self.setMinimumSize(w, h)
            self.resize(w, h)
        self.update()
        if notify:
            self.clips_changed.emit()

    def reorder_track(self, from_idx: int, to_idx: int):
        """Move a lane. `to_idx` is the insert slot in the list before the move (top is 0)."""
        count = len(self.tracks)
        if not (0 <= from_idx < count):
            return
        to_idx = max(0, min(count, int(to_idx)))
        if from_idx == to_idx or from_idx + 1 == to_idx:
            return
        track = self.tracks.pop(from_idx)
        if to_idx > from_idx:
            to_idx -= 1
        self.tracks.insert(to_idx, track)
        self._relayout()

    def fit_to_height(self, h: int):
        self._fill_h = max(48, int(h))
        for t in self.tracks:
            preset_h = PRESET.get(t.kind, (t.name, TRACK_MIN_H, t.color, t.icon))[1]
            if t.height > 96:
                t.height = preset_h
            else:
                t.height = max(TRACK_MIN_H, min(TRACK_MAX_H, t.height))
        self._relayout(notify=False)

    def set_track_height(self, tid: str, height: int):
        track = self.track_by_id(tid)
        if not track:
            return
        track.height = max(TRACK_MIN_H, min(TRACK_MAX_H, int(height)))
        self._relayout(notify=False)

    def set_zoom(self, pps: float):
        self.pps = max(12.0, min(160.0, float(pps)))
        self._relayout()

    def set_duration_ms(self, ms: int):
        """Remember the source length. A master the user already trimmed stays trimmed."""
        ms = max(0, int(ms))
        for clip in self.clips:
            if clip.kind == "video" and clip.extra.get("master"):
                file_ms = int(clip.extra.get("file_ms") or 0)
                inn = int(clip.extra.get("in_ms") or 0)
                untrimmed = (
                    not clip.extra.get("user_trim")
                    and clip.start_ms == 0
                    and inn == 0
                )
                clip.extra["file_ms"] = max(file_ms, ms)
                if untrimmed and ms > clip.duration_ms:
                    clip.duration_ms = max(ms, 1000)
                    clip.label = self.media_name or clip.label or "Footage"
        self.duration_ms = max(self.duration_ms, ms)
        if hasattr(self, "fit_source_to_timeline"):
            self.fit_source_to_timeline()
        self._relayout()

    def set_playhead_ms(self, ms: int):
        old = self.playhead_ms
        self.playhead_ms = max(0, int(ms))
        now = self.gains()
        if now != self._last_gains:
            self._last_gains = now
            self.gains_changed.emit()
        x0 = int(self.x_at(min(old, self.playhead_ms))) - 8
        x1 = int(self.x_at(max(old, self.playhead_ms))) + 8
        self.update(x0, 0, max(16, x1 - x0), max(1, self.height()))

    def ms_at(self, x: int) -> int:
        return max(0, int(x / max(self.pps, 1) * 1000))

    def x_at(self, ms: int) -> float:
        return (ms / 1000.0) * self.pps

    def clip_at(self, pos: QPoint) -> TimelineClip | None:
        track = self.track_at_y(pos.y())
        if not track:
            return None
        ms = self.ms_at(pos.x())
        hits = [c for c in self.clips if c.track_id == track.id and c.start_ms <= ms < c.end_ms]
        return hits[-1] if hits else None

    def clip_rect(self, clip: TimelineClip) -> QRectF:
        track = self.track_by_id(clip.track_id)
        h = track.height if track else 28
        top = self.track_top(clip.track_id)
        x = self.x_at(clip.start_ms)
        w = max(10.0, (clip.duration_ms / 1000.0) * self.pps)
        return QRectF(x, top + 1, w, max(10.0, h - 2))

    def _view_opacity(self, track: TimelineTrack | None) -> float:
        """Painter opacity for timeline drawing; eye-off dims instead of removing clips."""
        if track is None:
            return 1.0
        return HIDDEN_VIEW_OPACITY if track.hidden else 1.0

    def _edge_track(self, y: int) -> TimelineTrack | None:
        cur = 0
        for t in self.tracks:
            bottom = cur + t.height
            if abs(y - bottom) <= 4:
                return t
            cur = bottom
        return None
