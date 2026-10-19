"""Draw tracks, clips, filmstrip, waveforms, and seams."""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import (
    Qt,
    QRect,
    QRectF,
    QPoint,
    QPointF,
)
from PySide6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QFont,
    QPixmap,
    QLinearGradient,
)

from claynext.constants.timeline_constants import (
    BG_TL,
    CLIP_TEAL,
    FX_KINDS,
    OVERLAY_KINDS,
    PLAYHEAD,
    TRACK_DIVIDER,
)
from claynext.constants.theme_constants import (
    COLOR_ACCENT_ROSE,
    COLOR_TEXT_MAIN,
)
from claynext.adapters.ffmpeg_service import WAVE_RATE
from claynext.gui.icons import icon
from claynext.models.text_style import (
    anim_spans,
    clean_text_style,
)
from claynext.models.fx import (
    clean_fx,
    fx_label,
)
from claynext.models.transitions import TRANSITION_LABELS
from claynext.gui.components.render.shape import SHAPE_LABELS
from claynext.gui.components.timeline.canvas_const import WAVE_PITCH
from claynext.gui.components.timeline.helpers import fmt_tc
from claynext.gui.components.timeline.models import (
    TimelineClip,
    TimelineTrack,
)


class CanvasPaint:
    """Draw tracks, clips, filmstrip, waveforms, and seams."""

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

    def paintEvent(self, event):
        self._exposed = QRectF(event.rect())
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(BG_TL))
        y = 0
        lane_i = 0
        for track in self.tracks:
            if not self.lane_visible(track):
                continue
            if track.hidden:
                bg = QColor("#070b10")
            else:
                bg = QColor("#0b1016") if lane_i % 2 == 0 else QColor("#0d1320")
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
            lane_i += 1
        if y < self.height():
            p.fillRect(0, y, self.width(), self.height() - y, QColor(BG_TL))
        if not self.media_path:
            self._paint_empty(p)
        for clip in self.clips:
            if not self.lane_visible(self.track_by_id(clip.track_id)):
                continue
            self._paint_clip(p, clip)
            self._paint_trim_grips(p, clip)
        self._paint_split_seams(p)
        for clip in self.clips:
            if not self.lane_visible(self.track_by_id(clip.track_id)):
                continue
            self._paint_volume_line(p, clip)
        self._paint_recording(p)
        if self._marquee:
            p.setPen(QPen(QColor("#2ec4b6"), 1, Qt.PenStyle.DashLine))
            p.setBrush(QColor(46, 196, 182, 36))
            p.drawRect(self._marquee)
        # CapCut-style hover guide (white line under scrub tip)
        if self._hover_tip_active and self._hover_guide_x >= 0:
            gx = int(self._hover_guide_x)
            p.setPen(QPen(QColor(255, 255, 255, 200), 1))
            p.drawLine(gx, 0, gx, self.height())
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
        strip_path = str(clip.extra.get("path") or "")
        own_strip = not strip_path or strip_path == self.media_path
        if is_video and self._frames and own_strip:
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
            self._paint_outside_master(p, clip, rect)
            return
        source = self._wave_source(clip) if clip.kind in {"video", "voice", "audio"} else None
        muted = bool(track.muted)
        wave_box = rect.adjusted(2, 2, -2, -2)
        if source:
            if muted:
                p.setOpacity(self._view_opacity(track) * 0.28)
            self._paint_wave(p, wave_box, *source, "#e0f2fe")
            if muted:
                p.setOpacity(self._view_opacity(track))
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
        if muted and clip.kind in {"voice", "audio"} and source:
            self._paint_mute_badge(p, wave_box)
        self._paint_outside_master(p, clip, rect)

    def _paint_outside_master(self, p: QPainter, clip: TimelineClip, rect: QRectF):
        """The part of an overlay past the current master stays on the timeline, drawn dark."""
        if clip.kind not in OVERLAY_KINDS:
            return
        span = self.master_span()
        if not span:
            return
        start, length = span
        end = start + length
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))

        def wash(a: int, b: int):
            if b <= a:
                return
            box = QRectF(self.x_at(a), rect.y(), max(0.0, self.x_at(b) - self.x_at(a)), rect.height())
            box = box.intersected(rect)
            if box.width() > 0.5:
                p.drawRect(box)

        wash(clip.start_ms, min(clip.end_ms, start))
        wash(max(clip.start_ms, end), clip.end_ms)
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
            fx = clean_fx(clip.kind, clip.extra.get("fx") or {})
            try:
                words = f"{fx_label(clip.kind, fx)} · {int(fx.get('intensity', 0))}%"
            except Exception:
                words = clip.label or "FX"
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

    def _paint_mute_badge(self, p: QPainter, band: QRectF):
        """Floating mute glyph on the audio band only (video filmstrip stays full opacity)."""
        if band.width() < 22 or band.height() < 14:
            return
        size = 14 if band.height() >= 28 else 12
        pix = icon("volume-off", color="#f87171", size=size).pixmap(size, size)
        if pix.isNull():
            return
        pad = 6
        x = int(band.left() + pad)
        y = int(band.center().y() - size / 2)
        # Soft chip behind the icon so it reads on dense waveforms
        chip = QRectF(x - 3, y - 2, size + 6, size + 4)
        p.save()
        p.setOpacity(1.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(8, 12, 18, 170))
        p.drawRoundedRect(chip, 4, 4)
        p.drawPixmap(x, y, pix)
        p.restore()

    def _paint_filmstrip(self, p: QPainter, clip: TimelineClip, rect: QRectF, selected: bool):
        wave_h = max(32, int(rect.height() * 0.42)) if rect.height() >= 52 else 0
        film = QRectF(rect.x(), rect.y(), rect.width(), max(8.0, rect.height() - wave_h))
        ch = max(8, int(film.height()))
        cw = max(36, int(ch * 16 / 9))
        n_cells = max(1, int(rect.width() / cw) + 1)
        n_frames = len(self._frames)
        track = self.track_by_id(clip.track_id)
        muted = bool(track and track.muted)
        p.save()
        p.setClipRect(film)
        # Mute must not dim video tiles — only the audio band below
        view_fade = self._view_opacity(track)
        p.setOpacity(view_fade * max(0.35, (track.opacity if track else 100) / 100.0))
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
            p.setOpacity(view_fade * (0.28 if muted else 1.0))
            source = self._wave_source(clip)
            if source:
                self._paint_wave(p, band, *source, "#7dd3fc")
            else:
                p.fillRect(band, QColor("#070b12"))
                p.setPen(QColor("#334155"))
                p.drawLine(int(band.left()), int(band.center().y()), int(band.right()), int(band.center().y()))
            p.restore()
            if muted:
                self._paint_mute_badge(p, band)
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
