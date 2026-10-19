"""History, tracks, clips, splits, and transition seams."""
from __future__ import annotations

import uuid

from PySide6.QtCore import (
    Qt,
    QRectF,
    QPoint,
    QPointF,
)

from claynext.constants.timeline_constants import (
    FX_KINDS,
    OVERLAY_KINDS,
)
from claynext.models.fx import clean_fx
from claynext.gui.components.shape_render import (
    SHAPE_LABELS,
    shape_size,
)
from claynext.gui.components.timeline.canvas_const import _copy_extra
from claynext.gui.components.timeline.models import (
    TimelineClip,
    TimelineTrack,
    new_track,
)


class CanvasEdit:
    """History, tracks, clips, splits, and transition seams."""

    def find_split_seams(self) -> list[dict]:
        """Find touching adjacent clip pairs on the main Cover (video) track only.

        Transitions are source-footage UI — never shown on Voice / Audio / FX tracks.
        """
        seams: list[dict] = []
        # Primary Cover lane only (first video track).
        video_tracks = [t for t in self.tracks if t.kind == "video"]
        if not video_tracks:
            return seams
        track = video_tracks[0]
        track_clips = sorted([c for c in self.clips if c.track_id == track.id], key=lambda c: c.start_ms)
        for i in range(len(track_clips) - 1):
            c1 = track_clips[i]
            c2 = track_clips[i + 1]
            gap = c2.start_ms - c1.end_ms
            if abs(gap) > 80:
                continue
            cut_ms = c1.end_ms
            x_cut = self.x_at(cut_ms)
            y_track = self.track_top(track.id)
            h_track = track.height
            tr = c1.extra.get("transition")
            if tr and isinstance(tr, dict):
                dur_ms = max(200, min(6000, int(tr.get("duration_ms", 1200))))
                half_dur = dur_ms // 2
                start_ms = max(c1.start_ms, cut_ms - half_dur)
                end_ms = min(c2.end_ms, cut_ms + half_dur)
                x_start = self.x_at(start_ms)
                x_end = self.x_at(end_ms)
                w = max(28.0, x_end - x_start)
                box_h = min(h_track - 6, 26) if h_track >= 32 else max(16, h_track - 4)
                box_y = y_track + (h_track - box_h) / 2
                rect = QRectF(x_start, box_y, w, box_h)
                btn_rect = rect
                has_tr = True
            else:
                btn_size = min(22, max(16, h_track - 8)) if h_track >= 26 else max(14, h_track - 4)
                btn_x = x_cut - btn_size / 2
                btn_y = y_track + (h_track - btn_size) / 2
                rect = QRectF(btn_x, btn_y, btn_size, btn_size)
                btn_rect = rect
                has_tr = False
            seams.append({
                "track": track,
                "left_clip": c1,
                "right_clip": c2,
                "cut_ms": cut_ms,
                "x_cut": x_cut,
                "has_transition": has_tr,
                "transition": tr if has_tr else None,
                "rect": rect,
                "btn_rect": btn_rect,
            })
        return seams

    def prune_transition_tracks(self) -> bool:
        """Drop legacy Transition lanes; keep transition extras only on Cover seams."""
        keep: list[TimelineTrack] = []
        removed_ids: set[str] = set()
        for track in self.tracks:
            if track.kind == "transition":
                removed_ids.add(track.id)
                continue
            keep.append(track)
        changed = bool(removed_ids)
        if removed_ids:
            self.clips = [c for c in self.clips if c.track_id not in removed_ids]
        primary = next((t.id for t in keep if t.kind == "video"), "")
        for clip in self.clips:
            if clip.track_id != primary and clip.extra.pop("transition", None) is not None:
                changed = True
        if self.selected_transition_clip_id:
            sel = next((c for c in self.clips if c.id == self.selected_transition_clip_id), None)
            if sel is None or sel.track_id != primary:
                self.selected_transition_clip_id = ""
                changed = True
        self.tracks = keep
        return changed

    def _split_seam_at(self, pos: QPoint) -> tuple[dict, str] | None:
        """Hit test for split seam buttons or applied transition blocks."""
        for seam in self.find_split_seams():
            if seam["has_transition"]:
                r = seam["rect"]
                hit_box = r.adjusted(-4, -3, 4, 3)
                if hit_box.contains(QPointF(pos)):
                    if abs(pos.x() - r.left()) <= 6:
                        return (seam, "trim_left")
                    if abs(pos.x() - r.right()) <= 6:
                        return (seam, "trim_right")
                    return (seam, "body")
            else:
                r = seam["btn_rect"]
                hit_box = r.adjusted(-3, -3, 3, 3)
                if hit_box.contains(QPointF(pos)):
                    return (seam, "button")
        return None

    def push_history(self):
        if self._history_lock:
            return
        self._undo.append(self._snapshot())
        if len(self._undo) > 40:
            self._undo.pop(0)
        self._redo.clear()
        self.history_changed.emit()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self):
        if not self._undo:
            return
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())

    def redo(self):
        if not self._redo:
            return
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())

    def _snapshot(self) -> dict:
        return {
            "tracks": [
                {
                    "id": track.id,
                    "kind": track.kind,
                    "name": track.name,
                    "height": track.height,
                    "color": track.color,
                    "icon": track.icon,
                    "locked": track.locked,
                    "muted": track.muted,
                    "solo": getattr(track, "solo", False),
                    "hidden": track.hidden,
                    "opacity": track.opacity,
                    "volume": track.volume,
                    "selected": track.selected,
                }
                for track in self.tracks
            ],
            "clips": [
                {
                    "id": clip.id,
                    "track_id": clip.track_id,
                    "kind": clip.kind,
                    "start_ms": clip.start_ms,
                    "duration_ms": clip.duration_ms,
                    "label": clip.label,
                    "locked": clip.locked,
                    "extra": _copy_extra(clip.extra),
                }
                for clip in self.clips
            ],
            "playhead_ms": self.playhead_ms,
        }

    def _restore(self, state: dict):
        self._history_lock = True
        self.tracks = [
            TimelineTrack(
                id=row["id"],
                kind=row["kind"],
                name=row["name"],
                height=row["height"],
                color=row["color"],
                icon=row["icon"],
                locked=row["locked"],
                muted=row["muted"],
                solo=bool(row.get("solo", False)),
                hidden=row["hidden"],
                opacity=row["opacity"],
                volume=int(row.get("volume", 100)),
                selected=row["selected"],
            )
            for row in state.get("tracks") or []
        ]
        self.clips = [
            TimelineClip(
                id=row["id"],
                track_id=row["track_id"],
                kind=row["kind"],
                start_ms=row["start_ms"],
                duration_ms=row["duration_ms"],
                label=row["label"],
                locked=row["locked"],
                extra=_copy_extra(row.get("extra") or {}),
            )
            for row in state.get("clips") or []
        ]
        self.playhead_ms = int(state.get("playhead_ms") or 0)
        self.selected_ids.clear()
        self.prune_transition_tracks()
        self._history_lock = False
        self._relayout()
        self.history_changed.emit()
        self.gains_changed.emit()

    def _discard_history_if_same(self, before: dict | None):
        """Drop the last undo step when the edit did not change clips."""
        if not before or not self._undo:
            return
        after = self._snapshot()
        if after.get("clips") == before.get("clips") and after.get("tracks") == before.get("tracks"):
            self._undo.pop()
            self.history_changed.emit()

    @staticmethod
    def _split_caption_words(text: str, ratio: float) -> tuple[str, str]:
        """Split caption text on a word boundary near `ratio` (0–1 through the clip)."""
        words = str(text or "").split()
        if len(words) <= 1:
            return str(text or ""), str(text or "")
        cut = max(1, min(len(words) - 1, int(round(len(words) * max(0.0, min(1.0, ratio))))))
        return " ".join(words[:cut]), " ".join(words[cut:])

    def split_at_playhead(self) -> int:
        self.push_history()
        ms = self.playhead_ms
        made: list[TimelineClip] = []
        for clip in list(self.clips):
            track = self.track_by_id(clip.track_id)
            if clip.locked or (track and track.locked):
                continue
            if not (clip.start_ms + 80 < ms < clip.end_ms - 80):
                continue
            right_dur = clip.end_ms - ms
            left_in = int(clip.extra.get("in_ms") or 0)
            left_dur = ms - clip.start_ms
            ratio = left_dur / max(1, clip.duration_ms)
            clip.duration_ms = left_dur
            extra = dict(clip.extra)
            extra["in_ms"] = left_in + clip.duration_ms
            if isinstance(clip.extra.get("keys"), list):
                extra["keys"] = [list(key) for key in clip.extra["keys"]]
            extra.pop("master", None)
            right_label = clip.label
            if clip.kind in {"text", "caption"}:
                ov = dict(extra.get("overlay") or {})
                left_text, right_text = self._split_caption_words(str(ov.get("text") or clip.label), ratio)
                ov_left = dict(clip.extra.get("overlay") or {})
                ov_left["text"] = left_text
                # Split segments become independently editable; drop voice lock on both halves.
                ov_left.pop("voice_id", None)
                clip.extra["overlay"] = ov_left
                clip.label = left_text if len(left_text) <= 48 else f"{left_text[:47]}…"
                ov["text"] = right_text
                ov.pop("voice_id", None)
                extra["overlay"] = ov
                right_label = right_text if len(right_text) <= 48 else f"{right_text[:47]}…"
            made.append(TimelineClip(
                id=uuid.uuid4().hex[:10],
                track_id=clip.track_id,
                kind=clip.kind,
                start_ms=ms,
                duration_ms=right_dur,
                label=right_label,
                locked=False,
                extra=extra,
            ))
        if made:
            self.clips.extend(made)
            self.selected_ids = {clip.id for clip in made}
            self._relayout()
        elif self._undo:
            self._undo.pop()
            self.history_changed.emit()
        return len(made)

    def split_clip(self, clip: TimelineClip, ms: int) -> TimelineClip | None:
        track = self.track_by_id(clip.track_id)
        if clip.locked or (track and track.locked):
            return None
        if not (clip.start_ms + 80 < ms < clip.end_ms - 80):
            return None
        self.push_history()
        right_dur = clip.end_ms - ms
        left_in = int(clip.extra.get("in_ms") or 0)
        left_dur = ms - clip.start_ms
        ratio = left_dur / max(1, clip.duration_ms)
        clip.duration_ms = left_dur
        extra = dict(clip.extra)
        extra["in_ms"] = left_in + clip.duration_ms
        if isinstance(clip.extra.get("keys"), list):
            extra["keys"] = [list(key) for key in clip.extra["keys"]]
        extra.pop("master", None)
        right_label = clip.label
        if clip.kind in {"text", "caption"}:
            ov = dict(extra.get("overlay") or {})
            left_text, right_text = self._split_caption_words(str(ov.get("text") or clip.label), ratio)
            ov_left = dict(clip.extra.get("overlay") or {})
            ov_left["text"] = left_text
            ov_left.pop("voice_id", None)
            clip.extra["overlay"] = ov_left
            clip.label = left_text if len(left_text) <= 48 else f"{left_text[:47]}…"
            ov["text"] = right_text
            ov.pop("voice_id", None)
            extra["overlay"] = ov
            right_label = right_text if len(right_text) <= 48 else f"{right_text[:47]}…"
        new_clip = TimelineClip(
            id=uuid.uuid4().hex[:10],
            track_id=clip.track_id,
            kind=clip.kind,
            start_ms=ms,
            duration_ms=right_dur,
            label=right_label,
            locked=False,
            extra=extra,
        )
        self.clips.append(new_clip)
        self.selected_ids = {new_clip.id}
        self._relayout()
        self.clips_changed.emit()
        return new_clip

    def duplicate_selected(self) -> int:
        if not self.selected_ids:
            return 0
        targets = [c for c in self.clips if c.id in self.selected_ids]
        if not targets:
            return 0
        self.push_history()
        new_clips: list[TimelineClip] = []
        for c in targets:
            track = self.track_by_id(c.track_id)
            if c.locked or (track and track.locked):
                continue
            new_extra = _copy_extra(c.extra)
            dup = TimelineClip(
                id=uuid.uuid4().hex[:10],
                track_id=c.track_id,
                kind=c.kind,
                start_ms=c.end_ms,
                duration_ms=c.duration_ms,
                label=f"{c.label} (Copy)" if len(c.label) < 40 else c.label,
                locked=False,
                extra=new_extra,
            )
            new_clips.append(dup)
        if new_clips:
            self.clips.extend(new_clips)
            self.selected_ids = {c.id for c in new_clips}
            self._relayout()
            self.clips_changed.emit()
            self.update()
            return len(new_clips)
        elif self._undo:
            self._undo.pop()
            self.history_changed.emit()
        return 0

    def get_cut_points(self) -> list[int]:
        points = {0, max(0, self.duration_ms)}
        for c in self.clips:
            points.add(c.start_ms)
            points.add(c.end_ms)
        return sorted(points)

    def jump_to_prev_cut(self) -> int:
        points = self.get_cut_points()
        prev_points = [p for p in points if p < self.playhead_ms - 50]
        target = prev_points[-1] if prev_points else 0
        self.set_playhead_ms(target)
        self.seek_requested.emit(target)
        return target

    def jump_to_next_cut(self) -> int:
        points = self.get_cut_points()
        next_points = [p for p in points if p > self.playhead_ms + 50]
        target = next_points[0] if next_points else max(0, self.duration_ms)
        self.set_playhead_ms(target)
        self.seek_requested.emit(target)
        return target

    def set_tool_mode(self, mode: str):
        self.tool_mode = mode
        if mode == "razor":
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def add_track(self, kind: str) -> TimelineTrack | None:
        # Transitions attach to Cover cut seams — never a dedicated track.
        if kind == "transition":
            return None
        self.push_history()
        n = sum(1 for t in self.tracks if t.kind == kind) + 1
        track = new_track(kind, n)
        self.tracks.append(track)
        self._relayout()
        return track

    def delete_track(self, tid: str) -> bool:
        track = self.track_by_id(tid)
        if not track:
            return False
        source = self.source_track()
        if source is not None and source.id == tid:
            return False
        self.push_history()
        self.clips = [c for c in self.clips if c.track_id != tid]
        self.tracks = [t for t in self.tracks if t.id != tid]
        if not self.tracks:
            self.tracks = [new_track("video")]
        self._relayout()
        return True

    def duplicate_track(self, tid: str):
        src = self.track_by_id(tid)
        if not src:
            return
        import uuid
        self.push_history()
        n = sum(1 for t in self.tracks if t.kind == src.kind) + 1
        fresh = new_track(src.kind, n)
        fresh.color = src.color
        fresh.height = src.height
        fresh.opacity = src.opacity
        fresh.volume = src.volume
        fresh.locked = src.locked
        fresh.solo = getattr(src, "solo", False)
        idx = self.tracks.index(src) + 1
        self.tracks.insert(idx, fresh)
        for clip in [c for c in self.clips if c.track_id == src.id]:
            self.clips.append(TimelineClip(
                id=uuid.uuid4().hex[:10],
                track_id=fresh.id,
                kind=clip.kind,
                start_ms=clip.start_ms,
                duration_ms=clip.duration_ms,
                label=f"{clip.label} (copy)",
                locked=clip.locked,
                extra=_copy_extra(clip.extra),
            ))
        self._relayout()

    def add_clip(self, kind: str, label: str, duration_ms: int = 3000, extra: dict | None = None, track_id: str = "",
                 start_ms: int | None = None) -> TimelineClip | None:
        # Transitions attach via clip.extra on Cover cuts — not as timeline clips.
        if kind == "transition":
            return None
        start = self.playhead_ms if start_ms is None else int(start_ms)
        if self.duration_ms and start_ms is None:
            start = min(start, max(0, self.duration_ms - 400))
        duration_ms = max(400, int(duration_ms))
        track = self.track_by_id(track_id) if track_id else None
        if track is None and kind in OVERLAY_KINDS | FX_KINDS:
            track = self.free_track(kind, start, start + duration_ms)
        elif track is None:
            track = self.ensure_track(kind)
        payload = dict(extra or {})
        clip = TimelineClip(
            id=uuid.uuid4().hex[:10],
            track_id=track.id,
            kind=kind,
            start_ms=start,
            duration_ms=duration_ms,
            label=label,
            locked=track.locked,
            extra=payload,
        )
        if kind in FX_KINDS:
            clip.extra["fx"] = clean_fx(kind, payload.get("fx"))
        if kind in OVERLAY_KINDS:
            ov = dict(payload.get("overlay") or {})
            ov.setdefault("id", clip.id)
            ov.setdefault("kind", kind)
            ov.setdefault("text", label)
            ov.setdefault("path", payload.get("path", ""))
            if kind in {"shape", "mask"}:
                ov["shape"] = ov.get("shape") if ov.get("shape") in SHAPE_LABELS else "rect"
                ov.setdefault("w", shape_size(ov["shape"])[0])
                ov.setdefault("h", shape_size(ov["shape"])[1])
                ov.setdefault("y", 0.5)
            ov.setdefault("x", 0.5 if kind != "logo" else 0.86)
            ov.setdefault("y", 0.84 if kind == "caption" else (0.10 if kind == "logo" else 0.42))
            ov.setdefault("w", 0.14 if kind in {"logo", "image"} else 0.62)
            ov.setdefault("h", 0.14 if kind in {"logo", "image"} else 0.12)
            ov.setdefault("color", "#f8fafc")
            ov.setdefault("font_size", 10 if kind == "caption" else 20)
            ov.setdefault("opacity", 100)
            ov.setdefault("rotation", 0)
            ov.setdefault("live", kind == "caption")
            ov["id"] = clip.id
            clip.extra["overlay"] = ov
        self.clips.append(clip)
        self.selected_ids = {clip.id}
        self._relayout()
        return clip

    def remove_selected(self):
        self.push_history()
        keep = []
        for clip in self.clips:
            track = self.track_by_id(clip.track_id)
            locked = clip.locked or (track and track.locked)
            if clip.id in self.selected_ids and not locked and not clip.extra.get("master"):
                continue
            keep.append(clip)
        if len(keep) == len(self.clips):
            if self._undo:
                self._undo.pop()
                self.history_changed.emit()
            return
        self.clips = keep
        self.selected_ids.clear()
        self._relayout()
