"""Pointer, keyboard, trim, and file-drop handling."""
from __future__ import annotations

from PySide6.QtCore import (
    Qt,
    QRect,
    QRectF,
    QPoint,
    QEvent,
)
from PySide6.QtGui import (
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QContextMenuEvent,
)
from PySide6.QtWidgets import QToolTip

from claynext.constants.timeline_constants import FX_KINDS
from claynext.models.fx import (
    clean_fx,
    fx_label,
)
from claynext.models.transitions import TRANSITION_LABELS
from claynext.gui.components.inspector.styles import parse_text_style
from claynext.gui.components.timeline.canvas_const import (
    TRIM_MIN_MS,
    TRIM_REACH,
)
from claynext.gui.components.timeline.helpers import (
    has_drop,
    paths_from_mime,
)
from claynext.gui.components.timeline.models import TimelineClip


class CanvasInput:
    """Pointer, keyboard, trim, and file-drop handling."""

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip:
            pos = event.pos()
            hit = self._split_seam_at(pos)
            if hit:
                seam, part = hit
                if seam["has_transition"]:
                    tr = seam["transition"]
                    tr_name = str(tr.get("name") or TRANSITION_LABELS.get(tr.get("transition"), "Transition"))
                    dur = int(tr.get("duration_ms", 1200)) / 1000.0
                    QToolTip.showText(event.globalPos(), f"{tr_name} ({dur:.1f}s) · Drag handles to resize, Del to remove", self)
                else:
                    QToolTip.showText(event.globalPos(), "Add Transition (Click to choose transition)", self)
                return True
        return super().event(event)

    def _near_playhead(self, x: int) -> bool:
        return abs(x - self.x_at(self.playhead_ms)) <= 8

    def _scrub_to(self, x: int):
        ms = self.ms_at(x)
        if self.duration_ms:
            ms = min(ms, self.duration_ms)
        self.playhead_ms = ms
        self.seek_requested.emit(ms)
        self.update()

    def _trim_at(self, pos: QPoint) -> tuple[TimelineClip, str] | None:
        """Unlocked clip whose left / right edge is under `pos`."""
        track = self.track_at_y(pos.y())
        if track is None or track.locked:
            return None
        best = None
        for clip in self.clips:
            if clip.track_id != track.id or clip.locked:
                continue
            rect = self.clip_rect(clip)
            reach = TRIM_REACH if rect.width() >= 3 * TRIM_REACH else max(2.0, rect.width() / 4)
            for side, x in (("left", rect.left()), ("right", rect.right())):
                dist = abs(pos.x() - x)
                if dist <= reach and (best is None or dist < best[2]):
                    best = (clip, side, dist)
        return (best[0], best[1]) if best else None

    def _source_ms(self, clip: TimelineClip) -> int:
        """Length of the media behind a clip, or 0 for clips that can be any length."""
        path = str(clip.extra.get("path") or "")
        if clip.kind not in {"video", "voice", "audio"} or not path:
            return 0
        if clip.extra.get("file_ms"):
            return int(clip.extra["file_ms"])
        if path == self.media_path and self.duration_ms:
            return self.duration_ms
        return int(clip.extra.get("in_ms") or 0) + clip.duration_ms

    def _trim_limits(self, clip: TimelineClip) -> tuple[int, int]:
        """Earliest start and latest end the clip's edges may be dragged to."""
        lo, hi = 0, 10 ** 9
        for other in self.clips:
            if other.track_id != clip.track_id or other.id == clip.id:
                continue
            if other.end_ms <= clip.start_ms:
                lo = max(lo, other.end_ms)
            elif other.start_ms >= clip.end_ms:
                hi = min(hi, other.start_ms)
        source = self._source_ms(clip)
        if source:
            in_ms = int(clip.extra.get("in_ms") or 0)
            lo = max(lo, clip.start_ms - in_ms)
            hi = min(hi, clip.start_ms - in_ms + source)
        return lo, hi

    def _drag_trim(self, x: int):
        cid, side, start, end, lo, hi = self._trim
        clip = next((c for c in self.clips if c.id == cid), None)
        if clip is None:
            return
        ms = self._snap_ms(self.ms_at(x), {cid})
        if side == "left":
            new_start = max(lo, min(ms, end - TRIM_MIN_MS))
            if self._source_ms(clip):
                clip.extra["in_ms"] = max(0, int(clip.extra.get("in_ms") or 0) + new_start - clip.start_ms)
            clip.start_ms = new_start
            clip.duration_ms = end - new_start
        else:
            clip.duration_ms = max(TRIM_MIN_MS, min(ms, hi) - start)
        self.update()

    def contextMenuEvent(self, event: QContextMenuEvent):
        pos = event.pos()
        track = self.track_at_y(pos.y())
        if track is None:
            event.ignore()
            return
        clip = self.clip_at(pos)
        # Select the track (and clip) under the cursor before showing the menu.
        for t in self.tracks:
            t.selected = t.id == track.id
        self.track_picked.emit(track.id, False)
        if clip:
            self.selected_ids = {clip.id}
            self.clip_selected.emit(clip.id)
        else:
            self.selected_ids.clear()
            self.clip_selected.emit("")
        self.update()
        self.context_menu_requested.emit(
            track.id,
            clip.id if clip else "",
            event.globalPos(),
        )
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # contextMenuEvent handles RMB; avoid scrubbing/drag side effects.
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position().toPoint()
        if self.tool_mode == "razor":
            clip = self.clip_at(pos)
            if clip:
                ms = self.ms_at(pos.x())
                if self.split_clip(clip, ms):
                    self.set_playhead_ms(ms)
                    self.seek_requested.emit(ms)
                    self.update()
                return
            self.set_playhead_ms(self.ms_at(pos.x()))
            self.seek_requested.emit(self.playhead_ms)
            self.update()
            return
        volume_clip = self._volume_clip_at(pos)
        trim = self._trim_at(pos)
        if trim and volume_clip and self._key_at(volume_clip, pos) >= 0:
            trim = None
        if volume_clip and not trim:
            self.push_history()
            self._volume_cid = volume_clip.id
            self._volume_x = pos.x()
            self._volume_key = self._key_at(volume_clip, pos)
            if self._volume_key >= 0:
                self._volume_key_ms = int(self.clip_keys(volume_clip)[self._volume_key][0])
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self._set_volume_at(volume_clip, pos.y())
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            self.update()
            return
        if trim:
            clip, side = trim
            self.push_history()
            self._edit_before = self._undo[-1] if self._undo else None
            self.selected_ids = {clip.id}
            self._trim = (clip.id, side, clip.start_ms, clip.end_ms, *self._trim_limits(clip))
            self._trim_origin = (clip.start_ms, clip.duration_ms, int(clip.extra.get("in_ms") or 0))
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            self.clip_selected.emit(clip.id)
            self.update()
            return
        if self._near_playhead(pos.x()):
            self._scrub = True
            self._scrub_to(pos.x())
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            return
        edge = self._edge_track(pos.y())
        if edge:
            self._resize_tid = edge.id
            self._resize_y = int(event.globalPosition().y())
            self._resize_h = edge.height
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            return
        seam_hit = self._split_seam_at(pos)
        if seam_hit:
            seam, part = seam_hit
            c1 = seam["left_clip"]
            if not seam["has_transition"]:
                self.selected_seam_clip_id = c1.id
                self.selected_transition_clip_id = ""
                self.transition_split_clicked.emit(c1.id, seam["cut_ms"])
                self.update()
                return
            else:
                self.selected_transition_clip_id = c1.id
                self.selected_seam_clip_id = c1.id
                self.selected_ids.clear()
                if part in ("trim_left", "trim_right"):
                    self._transition_trim = (c1.id, part, seam["cut_ms"], int(seam["transition"].get("duration_ms", 1200)))
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                else:
                    self.transition_selected.emit(c1.id)
                    self.transition_split_clicked.emit(c1.id, seam["cut_ms"])
                self.update()
                return
        self.selected_seam_clip_id = ""
        self.selected_transition_clip_id = ""
        clip = self.clip_at(pos)
        track = self.track_at_y(pos.y())
        multi = bool(event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier | Qt.KeyboardModifier.ShiftModifier))
        if clip:
            if multi:
                self.selected_ids ^= {clip.id}
            elif clip.id not in self.selected_ids:
                self.selected_ids = {clip.id}
            track_lock = track.locked if track else False
            if not clip.locked and not track_lock:
                self.push_history()
                self._edit_before = self._undo[-1] if self._undo else None
                self._drag_ids = [c.id for c in self.clips if c.id in self.selected_ids]
                self._drag_origin_ms = {c.id: c.start_ms for c in self.clips if c.id in self._drag_ids}
                self._press_x = pos.x()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.clip_selected.emit(clip.id)
        else:
            # Empty / black lane click clears clip + track selection (rail still picks tracks).
            if not multi:
                self.selected_ids.clear()
                for t in self.tracks:
                    t.selected = False
                self.clip_selected.emit("")
            self._marquee = QRect(pos, pos)
            ms = self.ms_at(pos.x())
            if self.duration_ms:
                ms = min(ms, self.duration_ms)
            self.playhead_ms = ms
            self.seek_requested.emit(ms)
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self.tool_mode == "razor":
            self._clear_hover_scrub()
            clip = self.clip_at(pos)
            track = self.track_at_y(pos.y())
            locked = (clip and clip.locked) or (track and track.locked)
            self.setCursor(Qt.CursorShape.CrossCursor if clip and not locked else Qt.CursorShape.ArrowCursor)
            return
        if self._transition_trim:
            cid, part, cut_ms, orig_dur = self._transition_trim
            clip = next((c for c in self.clips if c.id == cid), None)
            if clip and "transition" in clip.extra:
                dx = abs(pos.x() - self.x_at(cut_ms))
                new_dur = max(200, min(6000, int((dx / max(1.0, self.pps)) * 2000)))
                clip.extra["transition"]["duration_ms"] = new_dur
                self.clips_changed.emit()
                self.update()
            return
        if self._volume_cid:
            clip = next((c for c in self.clips if c.id == self._volume_cid), None)
            if clip:
                if self._volume_key >= 0:
                    self._move_key(clip, pos.x())
                self._set_volume_at(clip, pos.y())
            return
        if self._scrub:
            self._clear_hover_scrub()
            self._scrub_to(pos.x())
            return
        if self._trim:
            self._clear_hover_scrub()
            self._drag_trim(pos.x())
            return
        if self._resize_tid:
            self._clear_hover_scrub()
            delta = int(event.globalPosition().y()) - self._resize_y
            self.height_changed.emit(self._resize_tid, self._resize_h + delta)
            return
        if self._drag_ids:
            self._clear_hover_scrub()
            delta = self.ms_at(pos.x()) - self.ms_at(self._press_x)
            lead_id = self._drag_ids[0]
            lead_start = max(0, self._drag_origin_ms.get(lead_id, 0) + delta)
            lead_start = self._snap_ms(lead_start, set(self._drag_ids))
            delta = lead_start - self._drag_origin_ms.get(lead_id, 0)
            for cid in self._drag_ids:
                clip = next((c for c in self.clips if c.id == cid), None)
                if clip:
                    clip.start_ms = max(0, self._drag_origin_ms.get(cid, 0) + delta)
            self.update()
            return
        if self._marquee is not None:
            self._marquee.setBottomRight(pos)
            box = self._marquee.normalized()
            hit = {c.id for c in self.clips if self.clip_rect(c).intersects(QRectF(box))}
            self.selected_ids = hit
            self.update()
            return
        seam_hit = self._split_seam_at(pos)
        if seam_hit:
            seam, part = seam_hit
            new_hover = seam["left_clip"].id
            if new_hover != self._hover_seam_clip_id or part != self._hover_seam_part:
                self._hover_seam_clip_id = new_hover
                self._hover_seam_part = part
                self.update()
            if part in ("trim_left", "trim_right"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            else:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            return
        elif self._hover_seam_clip_id:
            self._hover_seam_clip_id = ""
            self._hover_seam_part = ""
            self.update()
        volume_clip = self._volume_clip_at(pos)
        if self._trim_at(pos) and not (volume_clip and self._key_at(volume_clip, pos) >= 0):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            return
        if volume_clip:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            return
        if self._near_playhead(pos.x()):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            return
        if self._edge_track(pos.y()):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            return
        clip = self.clip_at(pos)
        track = self.track_at_y(pos.y())
        locked = (clip and clip.locked) or (track and track.locked)
        self.setCursor(Qt.CursorShape.OpenHandCursor if clip and not locked else Qt.CursorShape.ArrowCursor)
        self._update_hover_scrub(pos, clip, track)

    def _update_hover_scrub(self, pos, clip, track):
        """Emit CapCut-style scrub tip data while hovering a clip / lane."""
        if self._scrub or self._drag_ids or self._trim or self._marquee is not None:
            self._clear_hover_scrub()
            return
        ms = max(0, int(self.ms_at(pos.x())))
        if self.duration_ms:
            ms = min(ms, self.duration_ms)
        if clip is None and track is None:
            self._clear_hover_scrub()
            return
        cid = clip.id if clip else ""
        tid = track.id if track else (clip.track_id if clip else "")
        x = int(pos.x())
        # Throttle tip/repaint — every mouse pixel was starving preview paint
        if (
            self._hover_tip_active
            and abs(self._hover_guide_x - x) < 4
            and abs(getattr(self, "_hover_tip_ms", -1) - ms) < 250
            and getattr(self, "_hover_tip_cid", "") == cid
        ):
            return
        self._hover_tip_active = True
        self._hover_guide_x = x
        self._hover_tip_ms = ms
        self._hover_tip_cid = cid
        self.update()
        self.hover_scrub_changed.emit(ms, cid, tid, x)

    def _clear_hover_scrub(self):
        if not self._hover_tip_active and self._hover_guide_x < 0:
            return
        self._hover_tip_active = False
        self._hover_guide_x = -1
        self._hover_tip_ms = -1
        self._hover_tip_cid = ""
        self.update()
        self.hover_scrub_changed.emit(-1, "", "", -1)

    def leaveEvent(self, event):
        if self._hover_seam_clip_id:
            self._hover_seam_clip_id = ""
            self._hover_seam_part = ""
            self.update()
        self._clear_hover_scrub()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._transition_trim:
            self._transition_trim = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._relayout()
        if self._volume_cid:
            clip = next((c for c in self.clips if c.id == self._volume_cid), None)
            if clip and isinstance(clip.extra.get("keys"), list):
                clip.extra["keys"].sort(key=lambda key: key[0])
            self._volume_cid = ""
            self._volume_key = -1
            self.setCursor(Qt.CursorShape.ArrowCursor)
        if self._scrub:
            self._scrub = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        if self._resize_tid:
            self._resize_tid = ""
            self.setCursor(Qt.CursorShape.ArrowCursor)
        if self._trim:
            cid = self._trim[0]
            origin = self._trim_origin
            self._trim = None
            self._trim_origin = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            clip = next((c for c in self.clips if c.id == cid), None)
            same = bool(
                clip and origin
                and (clip.start_ms, clip.duration_ms, int(clip.extra.get("in_ms") or 0)) == origin
            )
            if same:
                self._discard_history_if_same(getattr(self, "_edit_before", None))
            else:
                self._relayout()
            self._edit_before = None
            self.clip_selected.emit(cid)
        if self._drag_ids:
            changed = any(
                (c.start_ms != self._drag_origin_ms.get(c.id, c.start_ms))
                for c in self.clips if c.id in self._drag_ids
            )
            self._drag_ids = []
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if not changed:
                self._discard_history_if_same(getattr(self, "_edit_before", None))
            else:
                self.clips_changed.emit()
            self._edit_before = None
        if self._marquee is not None:
            box = self._marquee.normalized()
            # Tiny click (no drag) already cleared on press; marquee with no hits stays empty.
            if box.width() > 3 or box.height() > 3:
                hit = {c.id for c in self.clips if self.clip_rect(c).intersects(QRectF(box))}
                self.selected_ids = hit
                self.clip_selected.emit(next(iter(hit), ""))
            self._marquee = None
        self.update()

    def mouseDoubleClickEvent(self, event):
        pos = event.position().toPoint()
        volume_clip = self._volume_clip_at(pos)
        if volume_clip and self.toggle_key(volume_clip, pos):
            return
        clip = self.clip_at(pos)
        if clip:
            self.playhead_ms = clip.start_ms
            self.seek_requested.emit(clip.start_ms)
            return
        track = self.track_at_y(int(event.position().y()))
        if track and track.kind not in {"video", "voice", "audio"}:
            self.add_clip(track.kind, track.name, track_id=track.id)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.selected_transition_clip_id:
                clip = self.clip_by_id(self.selected_transition_clip_id)
                if clip and "transition" in clip.extra:
                    self.push_history()
                    clip.extra.pop("transition", None)
                    self.selected_transition_clip_id = ""
                    self.clips_changed.emit()
                    self.update()
                    return
            self.remove_selected()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.selected_ids.clear()
            self.selected_seam_clip_id = ""
            self.selected_transition_clip_id = ""
            self.update()
            self.clip_selected.emit("")
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if has_drop(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        if has_drop(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        style = parse_text_style(event.mimeData())
        if style:
            event.acceptProposedAction()
            track = self.track_at_y(int(event.position().y()))
            kind = str(style.get("kind") or "text")
            if kind == "transition":
                # Transitions only apply on the main Cover (video) source track.
                video = next((t for t in self.tracks if t.kind == "video"), None)
                if video is None:
                    return
                drop_x = int(event.position().x())
                seams = self.find_split_seams()
                tr_dict = {
                    "transition": style.get("transition", "fade_black"),
                    "intensity": int(style.get("intensity", 80)),
                    "duration_ms": max(200, min(6000, int(style.get("duration_ms", 1200)))),
                    "name": str(style.get("name") or "Transition"),
                }
                if seams:
                    best_seam = min(seams, key=lambda s: abs(s["x_cut"] - drop_x))
                    self.push_history()
                    best_seam["left_clip"].extra["transition"] = tr_dict
                    self.selected_transition_clip_id = best_seam["left_clip"].id
                    self.selected_seam_clip_id = best_seam["left_clip"].id
                    self.clips_changed.emit()
                    self.update()
                    return
                # No seam yet — split Cover clip under the drop and attach the transition.
                drop_ms = self.ms_at(drop_x)
                clip = self.clip_at(event.position().toPoint())
                if (
                    clip
                    and clip.track_id == video.id
                    and not clip.locked
                    and clip.start_ms + 100 < drop_ms < clip.end_ms - 100
                ):
                    new_clip = self.split_clip(clip, drop_ms)
                    if new_clip:
                        clip.extra["transition"] = tr_dict
                        self.selected_transition_clip_id = clip.id
                        self.selected_seam_clip_id = clip.id
                        self.clips_changed.emit()
                        self.update()
                        return
                return
            # Dropping an effect or filter onto footage keeps it on that clip
            # and opens its settings in the inspector (Premiere-style), not a new lane.
            if kind in FX_KINDS:
                hit = self.clip_at(event.position().toPoint())
                if hit is not None and hit.kind == "video" and not hit.locked:
                    fx = clean_fx(kind, style if isinstance(style, dict) else {})
                    fx["kind"] = kind
                    applied = list(hit.extra.get("applied_fx") or [])
                    applied.append(fx)
                    hit.extra["applied_fx"] = applied
                    self.selected_ids = {hit.id}
                    for lane in self.tracks:
                        lane.selected = lane.id == hit.track_id
                    self.clip_selected.emit(hit.id)
                    self.clips_changed.emit()
                    self.update()
                    return
            start = self.ms_at(int(event.position().x()))
            dur = 4000
            fit = self.fit_master_placement(kind)
            if fit:
                start, dur = fit
            elif self.duration_ms:
                start = min(start, max(0, self.duration_ms - 800))
                dur = max(800, min(6000, self.duration_ms - start))
            busy = track is not None and any(
                c.track_id == track.id and c.start_ms < start + dur and start < c.end_ms for c in self.clips
            )
            if track is not None and (track.kind != kind or track.locked or busy):
                track = None
            if kind in FX_KINDS:
                try:
                    label = fx_label(kind, style if isinstance(style, dict) else {})
                except Exception:
                    label = str(kind).title()
                extra = {"fx": style if isinstance(style, dict) else {}}
            else:
                label = str(style.get("text") or style.get("name") or kind)
                extra = {"overlay": style}
            self.add_clip(
                kind, label, duration_ms=dur, extra=extra,
                track_id=track.id if track else "", start_ms=start,
            )
            return
        paths = paths_from_mime(event.mimeData())
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        track = self.track_at_y(int(event.position().y()))
        self.files_dropped.emit(paths, track.id if track else "")
