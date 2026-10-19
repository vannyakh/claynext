"""Footage, dialogue, captions, waveforms, and the master window."""
from __future__ import annotations

import os

import numpy as np
from PySide6.QtGui import QPixmap

from claynext.constants.timeline_constants import OVERLAY_KINDS
from claynext.models.dubbing_service import timestamp_to_sec
from claynext.adapters.ffmpeg_adapter import probe_duration
from claynext.gui.components.timeline.canvas_const import _as_envelope
from claynext.gui.components.timeline.models import (
    TimelineClip,
    TimelineTrack,
)


class CanvasMedia:
    """Footage, dialogue, captions, waveforms, and the master window."""

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

    def set_wave(self, peaks, path: str = ""):
        """Store a WAVE_RATE peak envelope for `path` (the footage when empty)."""
        norm = _as_envelope(peaks)
        key = path or self.media_path
        if key:
            self._waves[key] = norm
        if not path or path == self.media_path:
            self._wave = norm
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

    def source_track(self) -> TimelineTrack | None:
        """Master footage lane — the first video track."""
        return next((t for t in self.tracks if t.kind == "video"), None)

    def master_span(self) -> tuple[int, int] | None:
        """Start and length of the master footage, in milliseconds."""
        source = self.source_track()
        masters: list[TimelineClip] = []
        if source is not None:
            masters = [
                c for c in self.clips
                if c.track_id == source.id and (c.extra.get("master") or c.id == "footage")
            ]
            if not masters:
                masters = [c for c in self.clips if c.track_id == source.id and c.kind == "video"]
        if masters:
            start = min(c.start_ms for c in masters)
            end = max(c.end_ms for c in masters)
            if end > start:
                return start, end - start
        if self.duration_ms > 0:
            return 0, self.duration_ms
        return None

    def master_clip(self) -> TimelineClip | None:
        """The footage clip preview and export follow."""
        source = self.source_track()
        masters: list[TimelineClip] = []
        if source is not None:
            masters = [
                c for c in self.clips
                if c.track_id == source.id and (c.extra.get("master") or c.id == "footage")
            ]
            if not masters:
                masters = [c for c in self.clips if c.track_id == source.id and c.kind == "video"]
        if not masters:
            return None
        return min(masters, key=lambda c: (c.start_ms, c.id != "footage"))

    def master_window(self) -> tuple[int, int, int] | None:
        """Timeline start, file in-point, and length of the current master. None when it is the whole file."""
        clip = self.master_clip()
        if clip is None or clip.duration_ms <= 0:
            return None
        start = int(clip.start_ms)
        inn = int(clip.extra.get("in_ms") or 0)
        dur = int(clip.duration_ms)
        file_ms = int(clip.extra.get("file_ms") or 0)
        if start == 0 and inn == 0 and file_ms and dur >= file_ms - 200:
            return None
        return start, inn, dur

    def fit_master_placement(self, kind: str) -> tuple[int, int] | None:
        """On-screen overlays cover the whole master clip. Effects stay timed."""
        if kind not in OVERLAY_KINDS:
            return None
        return self.master_span()

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
