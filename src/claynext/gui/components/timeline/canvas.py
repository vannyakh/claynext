"""Sequence canvas: tracks, clips, filmstrip, and playhead."""
from __future__ import annotations

import math
import os
import uuid

import numpy as np
from PySide6.QtCore import Qt, Signal, QRect, QRectF, QPoint, QPointF, QSize, QEvent
from PySide6.QtGui import (
    QPainter, QColor, QPen, QFont, QPixmap, QLinearGradient,
    QDragEnterEvent, QDragMoveEvent, QDropEvent, QContextMenuEvent,
)
from PySide6.QtWidgets import QWidget, QToolTip

from claynext.constants.timeline_constants import (
    BG_TL, CLIP_TEAL, FX_KINDS, OVERLAY_KINDS, PLAYHEAD, PRESET, TRACK_DIVIDER, TRACK_MAX_H, TRACK_MIN_H,
)
from claynext.constants.theme_constants import COLOR_ACCENT_ROSE, COLOR_TEXT_MAIN
from claynext.models.dubbing_service import timestamp_to_sec
from claynext.adapters.ffmpeg_service import WAVE_RATE, probe_duration
from claynext.gui.icons import icon
from claynext.models.text_style import anim_spans, clean_text_style
from claynext.models.fx import clean_fx, fx_label
from claynext.models.transitions import TRANSITION_LABELS
from claynext.gui.components.shape_render import SHAPE_LABELS, shape_size
from claynext.gui.components.text_styles_panel import parse_text_style
from claynext.gui.components.timeline.helpers import fmt_tc, has_drop, paths_from_mime
from claynext.gui.components.timeline.models import TimelineClip, TimelineTrack, new_track


WAVE_PITCH = 3  # px per waveform bar slot (2 px bar + 1 px gap) at every zoom level
TRIM_REACH = 6
TRIM_MIN_MS = 200
# Eye-off keeps clips on the timeline; only dims them (preview/export still skip the track).
HIDDEN_VIEW_OPACITY = 0.34


def _as_envelope(peaks) -> np.ndarray:
    if peaks is None:
        return np.zeros(0, dtype=np.float32)
    return np.clip(np.asarray(peaks, dtype=np.float32), 0.0, 1.0)


def _copy_extra(extra: dict) -> dict:
    out = dict(extra)
    if isinstance(out.get("keys"), list):
        out["keys"] = [list(key) for key in out["keys"]]
    for key in ("overlay", "fx", "transition"):
        if isinstance(out.get(key), dict):
            out[key] = dict(out[key])
    return out


class TimelineCanvas(QWidget):
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

    def track_by_id(self, tid: str) -> TimelineTrack | None:
        return next((t for t in self.tracks if t.id == tid), None)

    def clip_by_id(self, cid: str) -> TimelineClip | None:
        return next((c for c in self.clips if c.id == cid), None)

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

    def _paint_split_seams(self, p: QPainter):
        """Paint interactive cut seam badges and applied transition blocks directly on the cut point."""
        seams = self.find_split_seams()
        if not seams:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for seam in seams:
            c1 = seam["left_clip"]
            track = seam["track"]
            y_track = self.track_top(track.id)
            h_track = track.height
            x_cut = seam["x_cut"]
            is_hover = (self._hover_seam_clip_id == c1.id)
            is_selected = (self.selected_transition_clip_id == c1.id)

            if seam["has_transition"]:
                rect = seam["rect"]
                tr = seam["transition"]
                key = str(tr.get("transition") or "fade_black")
                tr_name = str(tr.get("name") or TRANSITION_LABELS.get(key, "Transition"))

                # 1. Background gradient block
                grad = QLinearGradient(rect.topLeft(), rect.topRight())
                grad.setColorAt(0.0, QColor(79, 70, 229, 210))  # #4f46e5 Indigo
                grad.setColorAt(1.0, QColor(2, 132, 199, 210))  # #0284c7 Sky
                p.setBrush(grad)

                if is_selected:
                    p.setPen(QPen(QColor("#f8fafc"), 2.0))
                elif is_hover:
                    p.setPen(QPen(QColor("#38bdf8"), 1.5))
                else:
                    p.setPen(QPen(QColor(56, 189, 248, 160), 1.0))
                p.drawRoundedRect(rect, 4, 4)

                # 2. Vertical cut indicator line at exact split seam
                p.setPen(QPen(QColor(255, 255, 255, 140), 1.0, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(x_cut, rect.top() + 2), QPointF(x_cut, rect.bottom() - 2))

                # 3. Trim handles on left and right when selected or hovered
                if is_selected or is_hover:
                    p.setPen(QPen(QColor(255, 255, 255, 210), 1.5))
                    p.drawLine(QPointF(rect.left() + 3, rect.top() + 4), QPointF(rect.left() + 3, rect.bottom() - 4))
                    p.drawLine(QPointF(rect.right() - 3, rect.top() + 4), QPointF(rect.right() - 3, rect.bottom() - 4))

                # 4. Icon & Text
                icn_size = min(14, int(rect.height()) - 6)
                dur_ms = int(tr.get("duration_ms", 1200))
                dur_str = f"{dur_ms / 1000.0:.1f}s"
                font = QFont()
                font.setPixelSize(9)
                font.setBold(True)
                p.setFont(font)
                p.setPen(QColor("#ffffff"))

                if rect.width() < 56:
                    if icn_size >= 8:
                        icn = icon("transition", color="#ffffff", size=icn_size)
                        icn.paint(p, QRect(int(rect.center().x() - icn_size / 2), int(rect.center().y() - icn_size / 2), icn_size, icn_size))
                else:
                    if icn_size >= 8:
                        icn = icon("transition", color="#ffffff", size=icn_size)
                        icn.paint(p, QRect(int(rect.left() + 6), int(rect.center().y() - icn_size / 2), icn_size, icn_size))

                    text_left = rect.left() + icn_size + 9
                    dur_w = p.fontMetrics().horizontalAdvance(dur_str) + 8
                    show_pill = rect.width() >= 95
                    name_avail = rect.width() - (icn_size + 14) - (dur_w + 6 if show_pill else 0)

                    if name_avail >= 20:
                        elided = p.fontMetrics().elidedText(tr_name, Qt.TextElideMode.ElideRight, int(name_avail))
                        p.drawText(
                            QRectF(text_left, rect.top(), name_avail, rect.height()),
                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                            elided,
                        )

                    if show_pill:
                        pill_rect = QRectF(rect.right() - dur_w - 5, rect.center().y() - 7, dur_w, 14)
                        p.setBrush(QColor(0, 0, 0, 110))
                        p.setPen(Qt.PenStyle.NoPen)
                        p.drawRoundedRect(pill_rect, 3, 3)
                        p.setPen(QColor(255, 255, 255, 220))
                        p.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, dur_str)
            else:
                # Empty split cut seam button [⧖]
                btn_rect = seam["btn_rect"]

                # Subtle vertical notch at split seam line
                p.setPen(QPen(QColor(255, 255, 255, 80), 1.0))
                p.drawLine(QPointF(x_cut, y_track), QPointF(x_cut, y_track + h_track))

                # Rounded cut button
                if is_hover or (self.selected_seam_clip_id == c1.id):
                    bg_col = QColor(30, 41, 59, 250)
                    pen_col = QColor("#6366f1")
                    pen_w = 1.5
                    icn_col = "#ffffff"
                else:
                    bg_col = QColor(15, 23, 42, 230)
                    pen_col = QColor("#475569")
                    pen_w = 1.0
                    icn_col = "#94a3b8"

                p.setBrush(bg_col)
                p.setPen(QPen(pen_col, pen_w))
                p.drawRoundedRect(btn_rect, 4, 4)

                icn_s = min(14, int(btn_rect.width()) - 4)
                if icn_s >= 8:
                    icn = icon("transition", color=icn_col, size=icn_s)
                    icn.paint(p, QRect(int(btn_rect.center().x() - icn_s / 2), int(btn_rect.center().y() - icn_s / 2), icn_s, icn_s))
        p.restore()

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
            if t.id == tid:
                return y
            y += t.height
        return y

    def track_at_y(self, y: int) -> TimelineTrack | None:
        cur = 0
        for t in self.tracks:
            if cur <= y < cur + t.height:
                return t
            cur += t.height
        return None

    def total_height(self) -> int:
        tracks_h = sum(t.height for t in self.tracks)
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
        self.duration_ms = max(0, int(ms))
        for clip in self.clips:
            if clip.kind == "video" and clip.extra.get("master"):
                clip.duration_ms = max(self.duration_ms, 1000)
                clip.label = self.media_name or "Footage"
        self._relayout()

    def set_playhead_ms(self, ms: int):
        self.playhead_ms = max(0, int(ms))
        now = self.gains()
        if now != self._last_gains:
            self._last_gains = now
            self.gains_changed.emit()
        self.update()

    def set_media(self, path: str, duration_ms: int = 0):
        """Load (or clear) master footage — replaces any previous source clip on the video track."""
        path = os.path.abspath(path) if path else ""
        old_path = self.media_path or ""
        replacing = bool(path) and path != old_path
        self.media_path = path
        self.media_name = os.path.basename(path) if path else ""
        self._frames = []
        self._wave = _as_envelope(None)
        if old_path and old_path in self._waves:
            self._waves.pop(old_path, None)
        if replacing or not path:
            # Stems belong to the previous film — drop them with the source.
            self.voice_path = ""
            self.bed_path = ""
        # Drop prior master/source footage + auto dialogue tied to the old film.
        kept: list[TimelineClip] = []
        for clip in self.clips:
            clip_path = str(clip.extra.get("path") or "")
            if clip.kind == "video":
                is_source = (
                    clip.id == "footage"
                    or bool(clip.extra.get("master"))
                    or bool(clip.extra.get("auto"))
                    or (old_path and clip_path == old_path)
                    or (path and clip_path == path)
                )
                if is_source:
                    continue
            elif clip.kind == "voice" and clip.extra.get("auto") and (replacing or not path):
                continue
            kept.append(clip)
        self.clips = kept
        if path:
            dur = duration_ms or int(probe_duration(path) * 1000)
            self.duration_ms = max(dur, 1000)
            video = self.ensure_track("video")
            self.clips.append(TimelineClip(
                id="footage",
                track_id=video.id,
                kind="video",
                start_ms=0,
                duration_ms=self.duration_ms,
                label=self.media_name,
                locked=video.locked,
                extra={"path": path, "master": True, "auto": True},
            ))
        else:
            self.duration_ms = 0
        self.playhead_ms = 0
        self.selected_ids.clear()
        self._relayout()
        self.clips_changed.emit()

    def set_dialogue(self, segments: list[dict]):
        self.clips = [c for c in self.clips if not (c.kind == "voice" and c.extra.get("auto"))]
        voice = self.ensure_track("voice")
        for i, seg in enumerate(segments or []):
            start = timestamp_to_sec(seg.get("start", ""))
            end = timestamp_to_sec(seg.get("end", ""))
            if end <= start:
                end = start + 1.2
            text = (seg.get("translated_text") or seg.get("text") or f"Line {i + 1}").strip()
            extra = {"auto": True, "row": i, "text": text}
            audio = str(seg.get("audio_path") or "")
            locked = True
            if audio and os.path.isfile(audio):
                extra["path"] = audio
                extra["file_ms"] = max(200, int((end - start) * 1000))
                locked = False
            self.clips.append(TimelineClip(
                id=f"dlg-{i}",
                track_id=voice.id,
                kind="voice",
                start_ms=int(seg.get("start_ms") or start * 1000),
                duration_ms=max(200, int((end - start) * 1000)),
                label=text[:48],
                locked=locked,
                extra=extra,
            ))
        last = max((c.end_ms for c in self.clips), default=self.duration_ms)
        if last > self.duration_ms:
            self.duration_ms = last
        self._relayout()

    def caption_cues(self) -> list[tuple[int, int, str]]:
        """Dubbed lines as (start, end, text) at wherever their voice clips sit now."""
        return [(start, end, text) for _vid, start, end, text in self.caption_segments()]

    def caption_segments(self) -> list[tuple[str, int, int, str]]:
        """Auto voice clips as (voice_id, start_ms, end_ms, text) for per-line caption tracks."""
        rows = [
            (c.id, c.start_ms, c.end_ms, str(c.extra.get("text") or c.label).strip())
            for c in self.clips if c.kind == "voice" and c.extra.get("auto")
        ]
        return sorted((row for row in rows if row[3]), key=lambda row: row[1])

    def gains(self) -> tuple[float, float, float]:
        return self._gain_at("video"), self._gain_at("voice"), self._bed_gain_at(self.playhead_ms)

    def _has_solo(self) -> bool:
        return any(getattr(t, "solo", False) for t in self.tracks if t.kind in {"video", "voice", "audio"})

    def _track_audible(self, track: TimelineTrack | None) -> bool:
        if not track or track.muted:
            return False
        if self._has_solo():
            return bool(getattr(track, "solo", False))
        return True

    def _bed_gain_at(self, ms: int) -> float:
        if not self.bed_path:
            return 0.0
        track = next((item for item in self.tracks if item.kind == "video"), None)
        if not self._track_audible(track):
            return 0.0
        clip = next(
            (c for c in self.clips if c.track_id == track.id and c.start_ms <= ms < c.end_ms and c.kind == "video"),
            None,
        )
        if not clip:
            return 0.0
        base = self.clip_volume(clip) / 100.0 * track.volume / 100.0
        return max(0.0, min(1.5, base * max(0.0, 1.0 - self.key_mult(clip, ms))))

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

    def set_wave(self, peaks, path: str = ""):
        """Store a WAVE_RATE peak envelope for `path` (the footage when empty)."""
        norm = _as_envelope(peaks)
        key = path or self.media_path
        if key:
            self._waves[key] = norm
        if not path or path == self.media_path:
            self._wave = norm
        self.update()

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

    def set_show_waveforms(self, show: bool):
        self.show_waveforms = show
        self.update()


    def _wave_source(self, clip: TimelineClip) -> tuple[np.ndarray, int] | None:
        """Envelope for the clip and the file time (ms) that sits under clip.start_ms."""
        path = str(clip.extra.get("path") or "")
        if not path and clip.kind == "voice" and self.voice_path:
            path = self.voice_path
        env = self._waves.get(path) if path else None
        own_file = env is not None and len(env) > 0 and path != self.media_path
        if own_file and path == self.voice_path:
            return env, clip.start_ms
        if not own_file:
            env = self._wave
        if env is None or not len(env):
            return None
        in_ms = int(clip.extra.get("in_ms") or 0)
        if clip.kind in {"voice", "audio"} and not own_file:
            in_ms = clip.start_ms
        return env, in_ms

    def set_frames(self, paths: list[str]):
        pix = []
        for p in paths or []:
            img = QPixmap(p)
            if not img.isNull():
                pix.append(img)
        self._frames = pix
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

    def delete_track(self, tid: str):
        track = self.track_by_id(tid)
        if not track:
            return
        self.push_history()
        self.clips = [c for c in self.clips if c.track_id != tid]
        self.tracks = [t for t in self.tracks if t.id != tid]
        if not self.tracks:
            self.tracks = [new_track("video")]
        self._relayout()

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
            if kind == "shape":
                ov["shape"] = ov.get("shape") if ov.get("shape") in SHAPE_LABELS else "rect"
                ov.setdefault("w", shape_size(ov["shape"])[0])
                ov.setdefault("h", shape_size(ov["shape"])[1])
                ov.setdefault("y", 0.5)
            ov.setdefault("x", 0.5 if kind != "logo" else 0.86)
            ov.setdefault("y", 0.84 if kind == "caption" else (0.10 if kind == "logo" else 0.42))
            ov.setdefault("w", 0.14 if kind in {"logo", "image"} else 0.62)
            ov.setdefault("h", 0.14 if kind in {"logo", "image"} else 0.12)
            ov.setdefault("color", "#f8fafc")
            ov.setdefault("font_size", 20)
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

    def paintEvent(self, event):
        self._exposed = QRectF(event.rect())
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(BG_TL))
        y = 0
        for i, track in enumerate(self.tracks):
            if track.hidden:
                bg = QColor("#070b10")
            else:
                bg = QColor("#0b1016") if i % 2 == 0 else QColor("#0d1320")
            p.fillRect(0, y, self.width(), track.height, bg)
            if track.locked:
                p.fillRect(0, y, self.width(), track.height, QColor(0, 0, 0, 50))
            if track.hidden:
                p.fillRect(0, y, self.width(), track.height, QColor(0, 0, 0, 40))
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            p.fillRect(0, y + track.height - 1, self.width(), 1, QColor(TRACK_DIVIDER))
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self._paint_sound_bed(p, track, y)
            y += track.height
        if y < self.height():
            p.fillRect(0, y, self.width(), self.height() - y, QColor(BG_TL))
        if not self.media_path:
            self._paint_empty(p)
        for clip in self.clips:
            self._paint_clip(p, clip)
            self._paint_trim_grips(p, clip)
        self._paint_split_seams(p)
        for clip in self.clips:
            self._paint_volume_line(p, clip)
        self._paint_recording(p)
        if self._marquee:
            p.setPen(QPen(QColor("#2ec4b6"), 1, Qt.PenStyle.DashLine))
            p.setBrush(QColor(46, 196, 182, 36))
            p.drawRect(self._marquee)
        hx = int(self.x_at(self.playhead_ms))
        p.setPen(QPen(QColor(PLAYHEAD), 1))
        p.drawLine(hx, 0, hx, self.height())
        p.setBrush(QColor(PLAYHEAD))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon([QPoint(hx - 5, 0), QPoint(hx + 5, 0), QPoint(hx, 9)])
        p.end()

    def _paint_recording(self, p: QPainter):
        track = self.track_by_id(self.rec_track) if self.rec_start >= 0 else None
        if track is None:
            return
        top = self.track_top(track.id)
        x0 = self.x_at(self.rec_start)
        width = max(2.0, self.x_at(self.rec_start + self.rec_ms) - x0)
        rect = QRectF(x0, top + 2, width, track.height - 4)
        rose = QColor(COLOR_ACCENT_ROSE)
        fill = QColor(rose)
        fill.setAlpha(70)
        p.save()
        p.setOpacity(self._view_opacity(track))
        p.setPen(QPen(rose, 1))
        p.setBrush(fill)
        p.drawRoundedRect(rect, 3, 3)
        if rect.width() > 40 and track.height >= 16:
            p.setPen(QColor(COLOR_TEXT_MAIN))
            p.drawText(rect.adjusted(6, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       f"● REC {fmt_tc(self.rec_ms)}")
        p.restore()

    def _paint_sound_bed(self, p: QPainter, track: TimelineTrack, top: int):
        """Ghost the speech-bed envelope on the primary Voice track only.

        Blank Audio/Voice tracks must stay empty — never paint the master
        footage wave onto a track that has no clips of its own.
        """
        if track.kind != "voice" or not self.duration_ms:
            return
        if any(clip.track_id == track.id for clip in self.clips):
            return
        # Only show when a real speech-bed stem exists (auto-mix / music bed).
        bed = str(getattr(self, "bed_path", "") or "")
        if not bed:
            return
        env = self._waves.get(bed)
        if env is None or not len(env):
            return
        # Only the first (primary) empty voice lane gets the reference bed.
        primary = next((t for t in self.tracks if t.kind == "voice"), None)
        if primary is None or primary.id != track.id:
            return
        width = max(8.0, self.x_at(self.duration_ms))
        band = QRectF(0, top + 3, width, max(8.0, track.height - 6))
        p.save()
        p.setOpacity(min(0.45, self._view_opacity(track)))
        self._paint_wave(p, band, env, 0, "#a5b4fc")
        p.restore()

    def _paint_empty(self, p: QPainter):
        video = next((t for t in self.tracks if t.kind == "video"), None)
        if not video:
            return
        top = self.track_top(video.id)
        p.setPen(QColor("#737373"))
        font = QFont()
        font.setPixelSize(11)
        p.setFont(font)
        p.drawText(
            QRectF(12, top + 6, self.width() - 24, video.height - 12),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "Drop footage here — or Dub movie to load automatically",
        )

    def _cover_tile(self, pix: QPixmap, cw: int, ch: int) -> QPixmap:
        if pix.isNull() or cw < 2 or ch < 2:
            return QPixmap()
        scaled = pix.scaled(
            cw + 2,
            ch + 2,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (scaled.width() - cw) // 2)
        y = max(0, (scaled.height() - ch) // 2)
        return scaled.copy(x, y, cw, ch)

    def _paint_clip(self, p: QPainter, clip: TimelineClip):
        track = self.track_by_id(clip.track_id)
        if not track:
            return
        rect = self.clip_rect(clip)
        selected = clip.id in self.selected_ids
        is_video = clip.kind == "video" and (clip.extra.get("master") or clip.extra.get("path"))
        if is_video and self._frames:
            self._paint_filmstrip(p, clip, rect, selected)
            return
        p.save()
        p.setOpacity(self._view_opacity(track))
        color = QColor(track.color)
        alpha = 90 if clip.kind in {"video", "voice", "audio"} else 220
        color.setAlpha(int(alpha * max(0.25, track.opacity / 100.0)))
        if selected:
            color = color.lighter(112)
        p.setPen(QPen(QColor("#f5f5f5") if selected else color.darker(140), 1))
        p.setBrush(color)
        p.drawRoundedRect(rect, 3, 3)
        if clip.kind in {"text", "caption", "shape"} | FX_KINDS:
            self._paint_text_clip(p, clip, rect)
            p.restore()
            return
        source = self._wave_source(clip) if clip.kind in {"video", "voice", "audio"} else None
        if source:
            self._paint_wave(p, rect.adjusted(2, 2, -2, -2), *source, "#e0f2fe")
        p.setPen(QColor("#0b1016") if clip.kind in {"text", "shape", "caption"} else QColor("#f8fafc"))
        font = QFont()
        font.setPixelSize(10)
        font.setBold(True)
        p.setFont(font)
        align = Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextSingleLine
        if clip.kind in {"voice", "audio"} and source:
            align |= Qt.AlignmentFlag.AlignTop
            box = rect.adjusted(6, 2, -6, 0)
        else:
            align |= Qt.AlignmentFlag.AlignVCenter
            box = rect.adjusted(8, 0, -8, 0)
        p.drawText(box, align, clip.label)
        if clip.locked or track.locked:
            if rect.width() >= 28 and rect.height() >= 14:
                lock_pix = icon("lock", color="#f59e0b", size=10).pixmap(10, 10)
                p.drawPixmap(int(rect.right() - 13), int(rect.top() + 3), lock_pix)
        p.restore()

    def _paint_text_clip(self, p: QPainter, clip: TimelineClip, rect: QRectF):
        """Text, shape and effect clips: kind glyph, a label, and lighter bands where the in / out animations run."""
        overlay = dict(clip.extra.get("overlay") or {})
        style = clean_text_style(overlay)
        anim_in, anim_out = anim_spans(style, clip.duration_ms) if clip.kind not in FX_KINDS else (0, 0)
        p.save()
        p.setClipRect(rect.adjusted(1, 1, -1, -1))
        p.setPen(Qt.PenStyle.NoPen)
        band = QColor(255, 255, 255, 70)
        if anim_in:
            p.fillRect(QRectF(rect.x(), rect.y(), self.x_at(anim_in), rect.height()), band)
        if anim_out:
            w = self.x_at(anim_out)
            p.fillRect(QRectF(rect.right() - w, rect.y(), w, rect.height()), band)
        if style["anim_loop"] != "none" and clip.kind not in FX_KINDS:
            p.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(rect.x() + 2, rect.bottom() - 3), QPointF(rect.right() - 2, rect.bottom() - 3))
        ink = QColor("#0b1016")
        x = rect.x() + 6
        side = min(12, int(rect.height()) - 6)
        if side >= 8 and rect.width() > 26:
            name = {
                "caption": "chat",
                "shape": "shapes",
                "effect": "sparkles",
                "filter": "filter",
            }.get(clip.kind, "type")
            glyph = icon(name, color=ink.name(), size=side)
            glyph.paint(p, QRect(int(x), int(rect.center().y() - side / 2), side, side))
            x += side + 4
        font = QFont()
        font.setPixelSize(10)
        font.setBold(True)
        p.setFont(font)
        p.setPen(ink)
        words = " ".join(str(overlay.get("text") or clip.label or "").split()) or clip.label
        if clip.kind in FX_KINDS:
            fx = clean_fx(clip.kind, clip.extra.get("fx"))
            words = f"{fx_label(clip.kind, fx)} · {fx['intensity']}%"
        elif clip.kind == "shape":
            words = SHAPE_LABELS.get(str(overlay.get("shape")), clip.label)
        if clip.kind == "caption" and overlay.get("auto_caption"):
            words = words or "Caption"
        elif overlay.get("live") and clip.kind == "caption":
            words = f"Live captions · {words}" if words else "Live captions"
        p.drawText(QRectF(x, rect.y(), rect.right() - x - 4, rect.height()),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextSingleLine,
                   p.fontMetrics().elidedText(words, Qt.TextElideMode.ElideRight, int(max(0, rect.right() - x - 4))))
        p.restore()

    def _paint_filmstrip(self, p: QPainter, clip: TimelineClip, rect: QRectF, selected: bool):
        wave_h = max(32, int(rect.height() * 0.42)) if rect.height() >= 52 else 0
        film = QRectF(rect.x(), rect.y(), rect.width(), max(8.0, rect.height() - wave_h))
        ch = max(8, int(film.height()))
        cw = max(36, int(ch * 16 / 9))
        n_cells = max(1, int(rect.width() / cw) + 1)
        n_frames = len(self._frames)
        track = self.track_by_id(clip.track_id)
        p.save()
        p.setClipRect(film)
        mute_fade = 0.4 if track and track.muted else 1.0
        view_fade = self._view_opacity(track)
        p.setOpacity(mute_fade * view_fade * max(0.35, (track.opacity if track else 100) / 100.0))
        for i in range(n_cells):
            fi = min(n_frames - 1, int(i / max(1, n_cells - 1) * (n_frames - 1))) if n_cells > 1 else 0
            tile = self._cover_tile(self._frames[fi], cw, ch)
            x = int(film.x() + i * cw)
            if not tile.isNull():
                p.drawPixmap(x, int(film.y()), tile)
        p.setOpacity(1.0)
        p.restore()
        if wave_h:
            band = QRectF(rect.x(), rect.bottom() - wave_h, rect.width(), wave_h)
            p.save()
            p.setOpacity(view_fade)
            source = self._wave_source(clip)
            if source:
                self._paint_wave(p, band, *source, "#7dd3fc")
            else:
                p.fillRect(band, QColor("#070b12"))
                p.setPen(QColor("#334155"))
                p.drawLine(int(band.left()), int(band.center().y()), int(band.right()), int(band.center().y()))
            p.restore()
        p.save()
        p.setOpacity(view_fade)
        border = QColor(CLIP_TEAL)
        p.setPen(QPen(border.lighter(130) if selected else border, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 2, 2)
        label = clip.label or "Footage"
        dur = fmt_tc(clip.duration_ms)
        font = QFont()
        font.setPixelSize(10)
        font.setBold(True)
        p.setFont(font)
        text = f"{label}   {dur}"
        p.setPen(QColor(0, 0, 0, 160))
        p.drawText(rect.adjusted(8, 4, -8, 0), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextSingleLine, text)
        p.setPen(QColor("#f5f5f5"))
        p.drawText(rect.adjusted(7, 3, -8, 0), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextSingleLine, text)
        p.restore()

    def _paint_wave(self, p: QPainter, rect: QRectF, env: np.ndarray, file_ms: int, color: str):
        """Fixed-size bars; each one summarises the audio under it, so zooming reveals detail instead of stretching."""
        if not self.show_waveforms or env is None or not len(env) or rect.width() < 4 or rect.height() < 4:
            return
        exposed = self._exposed if not self._exposed.isEmpty() else QRectF(self.rect())
        x0 = max(rect.left(), exposed.left())
        x1 = min(rect.right(), exposed.right())
        if x1 <= x0:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setClipRect(rect)
        p.setPen(Qt.PenStyle.NoPen)
        shade = QColor("#080c12")
        shade.setAlpha(90)
        p.fillRect(QRectF(x0, rect.top(), x1 - x0, rect.height()), shade)

        left = math.floor(rect.left())
        first = int((x0 - left) // WAVE_PITCH)
        last = int(math.ceil((x1 - left) / WAVE_PITCH))
        slots = np.arange(first, last + 1, dtype=np.float64)
        edges = ((file_ms + slots * WAVE_PITCH * 1000.0 / self.pps) * WAVE_RATE / 1000.0).astype(np.int64)
        count = len(env)
        inside = (edges[:-1] >= 0) & (edges[:-1] < count)
        starts = np.clip(edges, 0, count - 1)
        amps = np.maximum.reduceat(env, starts)[:-1]
        amps[~inside] = 0.0

        ink = QColor(color)
        ink.setAlpha(210)
        p.setBrush(ink)
        mid = rect.center().y()
        span = rect.height() * 0.86
        bar_w = WAVE_PITCH - 1
        bars = []
        for slot, amp in zip(range(first, last), amps.tolist()):
            if amp <= 0.0 and not inside[slot - first]:
                continue
            h = max(1.0, round(amp * span))
            bars.append(QRectF(left + slot * WAVE_PITCH, round(mid - h / 2.0), bar_w, h))
        if bars:
            p.drawRects(bars)
        p.restore()

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

    def footage_clips(self) -> list[TimelineClip]:
        return [c for c in self.clips if c.kind == "video" and (c.extra.get("master") or c.extra.get("path"))]

    def voice_spans(self) -> list[tuple[int, int]]:
        spans = []
        for track in self.tracks:
            if track.kind not in {"voice", "audio"} or track.muted or track.hidden:
                continue
            for clip in self.clips:
                if clip.track_id == track.id and self.clip_volume(clip) > 0:
                    spans.append((clip.start_ms, clip.end_ms))
        return sorted(spans)

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

    def _gain_at(self, kind: str) -> float:
        track = next((item for item in self.tracks if item.kind == kind), None)
        if not self._track_audible(track):
            return 0.0
        ms = self.playhead_ms
        clip = next(
            (c for c in self.clips if c.track_id == track.id and c.start_ms <= ms < c.end_ms),
            None,
        )
        level = self.level_at(clip, ms) if clip else 100
        return max(0.0, min(1.5, level / 100.0 * track.volume / 100.0))

    def voice_clip_at(self, ms: int, take: bool = False) -> TimelineClip | None:
        for track in self.tracks:
            if track.kind not in {"voice", "audio"}:
                continue
            for clip in self.clips:
                if clip.track_id != track.id or bool(clip.extra.get("take")) != take:
                    continue
                if clip.extra.get("path") and clip.start_ms <= ms < clip.end_ms:
                    return clip
        return None

    def clip_gain(self, clip: TimelineClip, ms: int, fades: bool = True) -> float:
        track = self.track_by_id(clip.track_id)
        if not self._track_audible(track):
            return 0.0
        return max(0.0, min(1.5, self.level_at(clip, ms, fades) / 100.0 * track.volume / 100.0))

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

    def _paint_trim_grips(self, p: QPainter, clip: TimelineClip):
        track = self.track_by_id(clip.track_id)
        if clip.id not in self.selected_ids or not track or track.locked or clip.locked:
            return
        rect = self.clip_rect(clip)
        if rect.width() < 14:
            return
        h = min(rect.height() - 6, 18.0)
        p.save()
        p.setOpacity(self._view_opacity(track))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#f8fafc"))
        for x in (rect.left() + 2, rect.right() - 5):
            p.drawRoundedRect(QRectF(x, rect.center().y() - h / 2, 3, h), 1.5, 1.5)
        p.restore()

    def _discard_history_if_same(self, before: dict | None):
        """Drop the last undo step when the edit did not change clips."""
        if not before or not self._undo:
            return
        after = self._snapshot()
        if after.get("clips") == before.get("clips") and after.get("tracks") == before.get("tracks"):
            self._undo.pop()
            self.history_changed.emit()

    def _edge_track(self, y: int) -> TimelineTrack | None:
        cur = 0
        for t in self.tracks:
            bottom = cur + t.height
            if abs(y - bottom) <= 4:
                return t
            cur = bottom
        return None

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
            self._scrub_to(pos.x())
            return
        if self._trim:
            self._drag_trim(pos.x())
            return
        if self._resize_tid:
            delta = int(event.globalPosition().y()) - self._resize_y
            self.height_changed.emit(self._resize_tid, self._resize_h + delta)
            return
        if self._drag_ids:
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

    def leaveEvent(self, event):
        if self._hover_seam_clip_id:
            self._hover_seam_clip_id = ""
            self._hover_seam_part = ""
            self.update()
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
            start = self.ms_at(int(event.position().x()))
            if self.duration_ms:
                start = min(start, max(0, self.duration_ms - 800))
            dur = 4000
            if self.duration_ms:
                dur = max(800, min(6000, self.duration_ms - start))
            busy = track is not None and any(
                c.track_id == track.id and c.start_ms < start + dur and start < c.end_ms for c in self.clips
            )
            if track is not None and (track.kind != kind or track.locked or busy):
                track = None
            if kind in FX_KINDS:
                label = fx_label(kind, style)
                extra = {"fx": style}
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

