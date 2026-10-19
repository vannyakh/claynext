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
        self.tracks.append(track)
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
        index = self.tracks.index(same[-1]) + 1 if same else len(self.tracks)
        self.tracks.insert(index, track)
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

    def _relayout(self, *, notify: bool = True):
        vw = self.parent().width() if self.parent() is not None else 0
        w = max(self.content_width(), int(vw), 1)
        h = self.total_height()
        self.setMinimumSize(w, h)
        self.resize(w, h)
        self.update()
        if notify:
            self.clips_changed.emit()

    def reorder_track(self, from_idx: int, to_idx: int):
        if 0 <= from_idx < len(self.tracks) and 0 <= to_idx < len(self.tracks) and from_idx != to_idx:
            track = self.tracks.pop(from_idx)
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
                clip.extra["file_ms"] = ms
                if self.duration_ms <= 0 or clip.duration_ms >= self.duration_ms - 50:
                    clip.duration_ms = max(ms, 1000)
                    clip.label = self.media_name or "Footage"
        self.duration_ms = max(self.duration_ms, ms)
        self._relayout()

    def set_playhead_ms(self, ms: int):
        self.playhead_ms = max(0, int(ms))
        now = self.gains()
        if now != self._last_gains:
            self._last_gains = now
            self.gains_changed.emit()
        self.update()

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
