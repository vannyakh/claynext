"""Clip level, fades, keyframes, and auto-duck."""
from __future__ import annotations

from PySide6.QtCore import (
    Qt,
    QPoint,
)
from PySide6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QFont,
)

from claynext.gui.components.timeline.models import (
    TimelineClip,
    TimelineTrack,
)


class CanvasVolume:
    """Clip level, fades, keyframes, and auto-duck."""

    def _snap_ms(self, ms: int, ignore: set[str]) -> int:
        if not self.snap:
            return ms
        thresh = max(40, int(8 / max(self.pps, 1) * 1000))
        points = [0, self.playhead_ms]
        if self.duration_ms:
            points.append(self.duration_ms)
        for clip in self.clips:
            if clip.id in ignore:
                continue
            points.extend((clip.start_ms, clip.end_ms))
        best = ms
        best_d = thresh + 1
        for point in points:
            dist = abs(point - ms)
            if dist <= thresh and dist < best_d:
                best = point
                best_d = dist
        return best

    def _volume_span(self, track: TimelineTrack) -> tuple[int, int]:
        top = self.track_top(track.id)
        if track.kind == "video" and track.height >= 52:
            wave_h = max(32, int((track.height - 2) * 0.42))
            band_top = top + track.height - wave_h
            return band_top + 3, max(8, wave_h - 8)
        return top + 4, max(8, track.height - 8)

    @staticmethod
    def clip_volume(clip: TimelineClip) -> int:
        try:
            return max(0, min(200, int(clip.extra.get("volume", 100))))
        except (TypeError, ValueError):
            return 100

    @staticmethod
    def clip_keys(clip: TimelineClip) -> list[list[float]]:
        keys = clip.extra.get("keys")
        if not isinstance(keys, list):
            return []
        return [key for key in keys if isinstance(key, (list, tuple)) and len(key) == 2]

    def key_mult(self, clip: TimelineClip, ms: int) -> float:
        keys = sorted(self.clip_keys(clip), key=lambda key: key[0])
        if not keys:
            return 1.0
        if ms <= keys[0][0]:
            return float(keys[0][1])
        if ms >= keys[-1][0]:
            return float(keys[-1][1])
        for (a_ms, a_val), (b_ms, b_val) in zip(keys, keys[1:]):
            if a_ms <= ms <= b_ms:
                span = max(1.0, float(b_ms - a_ms))
                return float(a_val) + (float(b_val) - float(a_val)) * ((ms - a_ms) / span)
        return 1.0

    @staticmethod
    def clip_fades(clip: TimelineClip) -> tuple[int, int]:
        span = max(1, clip.duration_ms)
        try:
            fade_in = max(0, int(clip.extra.get("fade_in") or 0))
            fade_out = max(0, int(clip.extra.get("fade_out") or 0))
        except (TypeError, ValueError):
            return 0, 0
        return min(fade_in, span), min(fade_out, span)

    def fade_mult(self, clip: TimelineClip, ms: int) -> float:
        fade_in, fade_out = self.clip_fades(clip)
        mult = 1.0
        if fade_in:
            mult = min(mult, max(0.0, (ms - clip.start_ms) / fade_in))
        if fade_out:
            mult = min(mult, max(0.0, (clip.end_ms - ms) / fade_out))
        return min(1.0, mult)

    def level_at(self, clip: TimelineClip, ms: int, fades: bool = True) -> float:
        level = self.clip_volume(clip) * self.key_mult(clip, ms)
        return level * self.fade_mult(clip, ms) if fades else level

    def key_index_near(self, clip: TimelineClip, ms: int, tolerance: int = 40) -> int:
        for index, (key_ms, _val) in enumerate(self.clip_keys(clip)):
            if abs(int(key_ms) - ms) <= tolerance:
                return index
        return -1

    def toggle_key_at(self, clip: TimelineClip, ms: int) -> bool:
        """Add a key at `ms` (or remove the one there); True when a key now exists."""
        self.push_history()
        keys = self.clip_keys(clip)
        index = self.key_index_near(clip, ms)
        if index >= 0:
            keys.pop(index)
        else:
            keys.append([int(ms), round(self.key_mult(clip, ms), 3)])
        clip.extra["keys"] = sorted(keys, key=lambda key: key[0])
        self.gains_changed.emit()
        self.update()
        return index < 0

    def set_level_at(self, clip: TimelineClip, ms: int, level: float):
        """Set the clip level at `ms`: moves the key there, or the base volume."""
        level = max(0.0, min(200.0, float(level)))
        index = self.key_index_near(clip, ms)
        keys = self.clip_keys(clip)
        if index >= 0:
            base = max(1, self.clip_volume(clip))
            keys[index][1] = round(max(0.0, min(2.0, level / base)), 3)
        else:
            mult = max(0.05, self.key_mult(clip, ms))
            clip.extra["volume"] = int(max(0, min(200, round(level / mult))))
        self.gains_changed.emit()
        self.update()

    def neighbour_key(self, clip: TimelineClip, ms: int, step: int) -> int | None:
        times = sorted(int(key[0]) for key in self.clip_keys(clip))
        if step < 0:
            before = [t for t in times if t < ms - 40]
            return before[-1] if before else None
        after = [t for t in times if t > ms + 40]
        return after[0] if after else None

    def _level_to_y(self, track: TimelineTrack, level: float) -> int:
        origin, span = self._volume_span(track)
        return int(origin + span - (max(0.0, min(200.0, level)) / 200.0) * span)

    def _y_to_level(self, track: TimelineTrack, y: int) -> float:
        origin, span = self._volume_span(track)
        return max(0.0, min(200.0, (1.0 - ((y - origin) / span)) * 200.0))

    def _volume_y(self, track: TimelineTrack, clip: TimelineClip, ms: int | None = None) -> int:
        at = clip.start_ms if ms is None else ms
        return self._level_to_y(track, self.level_at(clip, at))

    def _key_at(self, clip: TimelineClip, pos: QPoint) -> int:
        track = self.track_by_id(clip.track_id)
        if not track:
            return -1
        for index, (ms, _val) in enumerate(self.clip_keys(clip)):
            x = self.x_at(int(ms))
            y = self._level_to_y(track, self.level_at(clip, int(ms)))
            if abs(pos.x() - x) <= 5 and abs(pos.y() - y) <= 5:
                return index
        return -1

    def _volume_clip_at(self, pos: QPoint) -> TimelineClip | None:
        track = self.track_at_y(pos.y())
        if not track or track.kind not in {"video", "voice", "audio"}:
            return None
        clip = self.clip_at(pos)
        if not clip or clip.kind not in {"video", "voice", "audio"}:
            return None
        if self._key_at(clip, pos) >= 0:
            return clip
        if abs(pos.y() - self._volume_y(track, clip, self.ms_at(pos.x()))) > 5:
            return None
        return clip

    def _paint_volume_line(self, p: QPainter, clip: TimelineClip):
        track = self.track_by_id(clip.track_id)
        if not track or clip.kind not in {"video", "voice", "audio"}:
            return
        rect = self.clip_rect(clip)
        left, right = rect.left() + 2, rect.right() - 2
        if right - left < 4:
            return
        inside = sorted(
            (key for key in self.clip_keys(clip) if clip.start_ms < key[0] < clip.end_ms),
            key=lambda key: key[0],
        )
        fade_in, fade_out = self.clip_fades(clip)
        line_ms = {clip.start_ms, clip.end_ms, *(int(ms) for ms, _val in inside)}
        if fade_in:
            line_ms.add(clip.start_ms + fade_in)
        if fade_out:
            line_ms.add(clip.end_ms - fade_out)
        points = []
        for ms in sorted(line_ms):
            x = left if ms <= clip.start_ms else right if ms >= clip.end_ms else self.x_at(ms)
            points.append(QPoint(int(x), self._volume_y(track, clip, ms)))
        p.save()
        p.setOpacity(self._view_opacity(track))
        p.setPen(QPen(QColor("#f8fafc"), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolyline(points)
        p.setBrush(QColor("#fbbf24"))
        p.setPen(QPen(QColor("#0b1016"), 1))
        for ms, _val in inside:
            p.drawEllipse(QPoint(int(self.x_at(int(ms))), self._volume_y(track, clip, int(ms))), 3, 3)
        if clip.id == self._volume_cid:
            font = QFont()
            font.setPixelSize(9)
            font.setBold(True)
            p.setFont(font)
            p.setPen(QColor("#f8fafc"))
            ms = self._volume_key_ms if self._volume_key >= 0 else self.ms_at(self._volume_x)
            level = int(round(self.level_at(clip, ms)))
            y = self._volume_y(track, clip, ms)
            p.drawText(int(self.x_at(ms)) + 6, max(int(rect.top()) + 10, y - 4), f"{level}%")
        p.restore()

    def _set_volume_at(self, clip: TimelineClip, y: int):
        track = self.track_by_id(clip.track_id)
        if not track:
            return
        level = self._y_to_level(track, y)
        if self._volume_key >= 0:
            keys = self.clip_keys(clip)
            if self._volume_key < len(keys):
                base = max(1, self.clip_volume(clip))
                keys[self._volume_key][1] = round(max(0.0, min(2.0, level / base)), 3)
        else:
            mult = max(0.05, self.key_mult(clip, self.ms_at(self._volume_x)))
            clip.extra["volume"] = int(max(0, min(200, round(level / mult))))
        self.gains_changed.emit()
        self.update()

    def _move_key(self, clip: TimelineClip, x: int):
        keys = self.clip_keys(clip)
        index = self._volume_key
        if index < 0 or index >= len(keys):
            return
        order = sorted(range(len(keys)), key=lambda i: keys[i][0])
        pos = order.index(index)
        low = keys[order[pos - 1]][0] + 10 if pos > 0 else clip.start_ms
        high = keys[order[pos + 1]][0] - 10 if pos + 1 < len(order) else clip.end_ms
        keys[index][0] = int(max(low, min(high, self.ms_at(x))))
        self._volume_key_ms = int(keys[index][0])

    def toggle_key(self, clip: TimelineClip, pos: QPoint) -> bool:
        if clip.kind not in {"video", "voice", "audio"}:
            return False
        self.push_history()
        index = self._key_at(clip, pos)
        keys = self.clip_keys(clip)
        if index >= 0:
            keys.pop(index)
        else:
            ms = self.ms_at(pos.x())
            keys.append([ms, round(self.key_mult(clip, ms), 3)])
        clip.extra["keys"] = sorted(keys, key=lambda key: key[0])
        self.gains_changed.emit()
        self.update()
        return True

    def auto_duck(
        self, level: float, fade_ms: int = 150, extra_spans: list | None = None, include_voice: bool = True,
    ) -> int:
        spans = self.voice_spans() if include_voice else []
        spans = sorted(spans + [(int(a), int(b)) for a, b in (extra_spans or []) if b > a])
        footage = self.footage_clips()
        if not footage:
            return 0
        self.push_history()
        fade = max(20, int(fade_ms))
        level = max(0.0, min(1.0, float(level)))
        merged: list[list[int]] = []
        for start, end in spans:
            if merged and start - fade * 2 <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        for clip in footage:
            keys: list[list[float]] = []
            for start, end in merged:
                if end <= clip.start_ms or start >= clip.end_ms:
                    continue
                keys.append([max(clip.start_ms, start - fade), 1.0])
                keys.append([max(clip.start_ms, start), level])
                keys.append([min(clip.end_ms, end), level])
                keys.append([min(clip.end_ms, end + fade), 1.0])
            clip.extra["keys"] = keys
        self.gains_changed.emit()
        self.update()
        return len(merged)

    def clear_keys(self):
        self.push_history()
        for clip in self.clips:
            clip.extra.pop("keys", None)
        self.gains_changed.emit()
        self.update()
