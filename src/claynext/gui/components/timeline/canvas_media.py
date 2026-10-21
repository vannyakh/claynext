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

def audio_stem_role(stem: bool, track_name: str, label: str) -> str:
    """Which soundtrack a laid stem is: effects, the full source mix, or the original vocals."""
    if not stem:
        return ""
    name = f"{track_name} {label}".lower()
    if "effect" in name:
        return "effects"
    if "vocal" in name:
        return "vocals"
    if "source" in name:
        return "source"
    return "stem"


# Clips that belong to one dub sequence. A new source must not inherit them.
_OTHER_SEQUENCE_KINDS = frozenset({
    "caption", "text", "image", "logo", "shape", "mask", "effect", "filter", "transition",
})


class CanvasMedia:
    """Footage, dialogue, captions, waveforms, and the master window."""

    def set_media(self, path: str, duration_ms: int = 0):
        """Load (or clear) master footage — replaces any previous source clip on the video track."""
        path = os.path.abspath(path) if path else ""
        old_path = os.path.abspath(self.media_path) if self.media_path else ""
        # First source keeps dialogue already placed. A different movie replaces it.
        replacing = bool(path) and bool(old_path) and path != old_path
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
            elif replacing and clip.kind in _OTHER_SEQUENCE_KINDS:
                # The previous film's sequence stays in its composition, not on this source.
                continue
            kept.append(clip)
        self.clips = kept
        if path:
            if duration_ms:
                dur = duration_ms
            elif int(getattr(self, "_quiet", 0)):
                dur = max(int(self.duration_ms or 0), 1000)
            else:
                dur = int(probe_duration(path) * 1000)
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
        if int(getattr(self, "_quiet", 0)):
            return
        self._relayout()
        self.clips_changed.emit()

    def drop_other_sequence(self, keep_path: str = "") -> None:
        """Take the open sequence off the timeline before a new source dub starts."""
        keep = os.path.abspath(keep_path) if keep_path else ""
        current = os.path.abspath(self.media_path) if self.media_path else ""
        other_film = bool(keep) and current != keep
        if other_film or not keep:
            self.voice_path = ""
            self.bed_path = ""
        kept: list[TimelineClip] = []
        for clip in self.clips:
            if clip.kind in _OTHER_SEQUENCE_KINDS or clip.kind == "voice":
                continue
            if other_film and clip.kind in {"video", "audio"}:
                clip_path = os.path.abspath(str(clip.extra.get("path") or "")) if clip.extra.get("path") else ""
                is_source = (
                    clip.id == "footage"
                    or bool(clip.extra.get("master"))
                    or bool(clip.extra.get("auto"))
                    or (current and clip_path == current)
                )
                if is_source or clip.kind == "audio":
                    continue
            kept.append(clip)
        self.clips = kept
        if other_film:
            self.media_path = ""
            self.media_name = ""
            self.duration_ms = 0
            self._frames = []
            self._wave = _as_envelope(None)
        self.playhead_ms = 0
        self.selected_ids.clear()
        self._relayout()
        self.clips_changed.emit()

    def _dialogue_clip(self, index: int, seg: dict, track_id: str) -> TimelineClip:
        start = timestamp_to_sec(seg.get("start", ""))
        end = timestamp_to_sec(seg.get("end", ""))
        if end <= start:
            end = start + 1.2
        text = (seg.get("translated_text") or seg.get("text") or f"Line {index + 1}").strip()
        extra = {"auto": True, "row": index, "text": text}
        audio = str(seg.get("audio_path") or "")
        locked = True
        if audio and os.path.isfile(audio):
            extra["path"] = audio
            extra["file_ms"] = max(200, int((end - start) * 1000))
            locked = False
        return TimelineClip(
            id=f"dlg-{index}",
            track_id=track_id,
            kind="voice",
            start_ms=int(seg.get("start_ms") or start * 1000),
            duration_ms=max(200, int((end - start) * 1000)),
            label=text[:48],
            locked=locked,
            extra=extra,
        )

    def set_dialogue(self, segments: list[dict]):
        self.clips = [c for c in self.clips if not (c.kind == "voice" and c.extra.get("auto"))]
        voice = self.ensure_track("voice")
        for i, seg in enumerate(segments or []):
            if isinstance(seg, dict):
                self.clips.append(self._dialogue_clip(i, seg, voice.id))
        self._extend_duration()
        self._relayout()

    def sync_dialogue(self, segments: list[dict]) -> bool:
        """Patch voice clips in place. Rebuild only when the line count changes."""
        segs = [seg for seg in (segments or []) if isinstance(seg, dict)]
        autos = [c for c in self.clips if c.kind == "voice" and c.extra.get("auto")]
        if len(autos) != len(segs):
            self.set_dialogue(segs)
            return True
        voice = self.ensure_track("voice")
        by_id = {clip.id: clip for clip in autos}
        changed = False
        for index, seg in enumerate(segs):
            fresh = self._dialogue_clip(index, seg, voice.id)
            clip = by_id.get(fresh.id)
            if clip is None:
                self.set_dialogue(segs)
                return True
            same = (
                clip.start_ms == fresh.start_ms
                and clip.duration_ms == fresh.duration_ms
                and clip.label == fresh.label
                and clip.locked == fresh.locked
                and clip.extra.get("text") == fresh.extra.get("text")
                and clip.extra.get("path") == fresh.extra.get("path")
            )
            if same:
                continue
            clip.start_ms = fresh.start_ms
            clip.duration_ms = fresh.duration_ms
            clip.label = fresh.label
            clip.locked = fresh.locked
            clip.track_id = voice.id
            clip.extra = fresh.extra
            changed = True
        if changed:
            self._extend_duration()
            self._relayout(notify=False)
        return changed

    def _extend_duration(self) -> None:
        last = max((c.end_ms for c in self.clips), default=self.duration_ms)
        if last > self.duration_ms:
            self.duration_ms = last

    def caption_cues(self) -> list[tuple[int, int, str]]:
        """Dubbed lines as (start, end, text) at wherever their voice clips sit now."""
        return [(start, end, text) for _vid, start, end, text in self.caption_segments()]

    def caption_segments(self) -> list[tuple[str, int, int, str]]:
        """Auto voice clips as (voice_id, start_ms, end_ms, text) for per-line caption tracks."""
        from claynext.models.tts_expression import strip_expression_tags

        rows = [
            (
                c.id,
                c.start_ms,
                c.end_ms,
                strip_expression_tags(str(c.extra.get("text") or c.label)),
            )
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

    def append_master(self, path: str, duration_ms: int = 0, start_ms: int | None = None) -> int:
        """Add another movie on the master track without replacing the ones already there."""
        path = os.path.abspath(path) if path else ""
        if not path:
            return 0
        video = self.ensure_track("video")
        for clip in self.master_clips():
            if os.path.abspath(str(clip.extra.get("path") or "")) == path:
                return int(clip.start_ms)
        if start_ms is None:
            span = self.master_span()
            start_ms = (span[0] + span[1]) if span else 0
        start_ms = max(0, int(start_ms))
        if duration_ms <= 0:
            duration_ms = 1000 if int(getattr(self, "_quiet", 0)) else int(probe_duration(path) * 1000) or 1000
        duration_ms = max(1000, int(duration_ms))
        clip_id = "footage" if not self.master_clips() else f"footage-{start_ms}"
        self.clips.append(TimelineClip(
            id=clip_id,
            track_id=video.id,
            kind="video",
            start_ms=start_ms,
            duration_ms=duration_ms,
            label=os.path.basename(path),
            locked=video.locked,
            extra={"path": path, "master": True, "auto": True, "file_ms": duration_ms},
        ))
        if not self.media_path:
            self.media_path = path
            self.media_name = os.path.basename(path)
        self.duration_ms = max(int(self.duration_ms or 0), start_ms + duration_ms)
        if int(getattr(self, "_quiet", 0)):
            return start_ms
        self._relayout()
        self.clips_changed.emit()
        return start_ms

    def drop_master(self, path: str) -> None:
        """Take one movie off the master track after its dub fails. Later movies close the gap."""
        path = os.path.abspath(path) if path else ""
        if not path:
            return
        self.clips = [
            clip for clip in self.clips
            if not (
                clip.kind == "video"
                and (clip.extra.get("master") or clip.id == "footage")
                and os.path.abspath(str(clip.extra.get("path") or "")) == path
            )
            and not (clip.kind == "voice" and clip.extra.get("merge_source") == path)
        ]
        remaining = self.master_clips()
        if remaining:
            first = remaining[0]
            self.media_path = str(first.extra.get("path") or "")
            self.media_name = os.path.basename(self.media_path) if self.media_path else first.label
            self.duration_ms = max(clip.end_ms for clip in self.clips)
        else:
            self.media_path = ""
            self.media_name = ""
            self.duration_ms = max((clip.end_ms for clip in self.clips), default=0)
        self._relayout()
        self.clips_changed.emit()

    def repack_masters(self) -> dict[str, int]:
        """Pull master movies together and return how many milliseconds each one moved."""
        cursor = 0
        deltas: dict[str, int] = {}
        for clip in self.master_clips():
            path = os.path.abspath(str(clip.extra.get("path") or ""))
            delta = cursor - int(clip.start_ms)
            if path:
                deltas[path] = delta
            clip.start_ms = cursor
            if path and delta:
                for voice in self.clips:
                    if voice.kind == "voice" and voice.extra.get("merge_source") == path:
                        voice.start_ms = max(0, int(voice.start_ms) + delta)
            cursor += int(clip.duration_ms)
        self.duration_ms = max(cursor, max((clip.end_ms for clip in self.clips), default=0))
        if int(getattr(self, "_quiet", 0)):
            return deltas
        self._relayout()
        self.clips_changed.emit()
        return deltas

    def replace_masters(self, rows: list[dict]) -> None:
        """Rebuild the master track from saved movie clips, in order."""
        video = self.ensure_track("video")
        self.clips = [
            clip for clip in self.clips
            if not (
                clip.track_id == video.id
                and clip.kind == "video"
                and (clip.extra.get("master") or clip.id == "footage")
            )
        ]
        self.media_path = ""
        self.media_name = ""
        self.duration_ms = 0
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            path = str(row.get("path") or "")
            if not path or not os.path.isfile(path):
                continue
            self.append_master(
                path,
                int(row.get("duration_ms") or 0),
                int(row.get("start_ms") or 0),
            )

    def place_source_dialogue(self, segments: list[dict], source: str) -> bool:
        """Replace only this movie's voice lines. Other movies on the sequence stay."""
        source = os.path.abspath(source) if source else ""
        segs = [seg for seg in (segments or []) if isinstance(seg, dict)]
        voice = self.ensure_track("voice")
        owned = [
            clip for clip in self.clips
            if clip.kind == "voice" and clip.extra.get("auto") and clip.extra.get("merge_source") == source
        ]
        if len(owned) != len(segs):
            drop = {clip.id for clip in owned}
            self.clips = [clip for clip in self.clips if clip.id not in drop]
            for index, seg in enumerate(segs):
                clip = self._dialogue_clip(index, seg, voice.id)
                clip.id = f"dlg-{abs(hash(source)) % 1_000_000:06d}-{index}"
                clip.extra["merge_source"] = source
                self.clips.append(clip)
            self._extend_duration()
            self._relayout()
            return True
        by_id = {clip.id: clip for clip in owned}
        changed = False
        for index, seg in enumerate(segs):
            fresh = self._dialogue_clip(index, seg, voice.id)
            clip_id = f"dlg-{abs(hash(source)) % 1_000_000:06d}-{index}"
            clip = by_id.get(clip_id)
            if clip is None:
                continue
            fresh.extra["merge_source"] = source
            same = (
                clip.start_ms == fresh.start_ms
                and clip.duration_ms == fresh.duration_ms
                and clip.label == fresh.label
                and clip.extra.get("path") == fresh.extra.get("path")
                and clip.extra.get("text") == fresh.extra.get("text")
            )
            if same:
                continue
            clip.start_ms = fresh.start_ms
            clip.duration_ms = fresh.duration_ms
            clip.label = fresh.label
            clip.locked = fresh.locked
            clip.track_id = voice.id
            clip.extra = fresh.extra
            changed = True
        if changed:
            self._extend_duration()
            self._relayout(notify=False)
        return changed

    def source_track(self) -> TimelineTrack | None:
        """Master footage lane — the first video track."""
        return next((t for t in self.tracks if t.kind == "video"), None)

    def master_clips(self) -> list[TimelineClip]:
        """Master movies on the source track, in timeline order."""
        source = self.source_track()
        if source is None:
            return []
        masters = [
            clip for clip in self.clips
            if clip.track_id == source.id and clip.kind == "video"
            and (clip.extra.get("master") or clip.id == "footage")
        ]
        if not masters:
            masters = [
                clip for clip in self.clips
                if clip.track_id == source.id and clip.kind == "video"
            ]
        return sorted(masters, key=lambda clip: (clip.start_ms, clip.id != "footage"))

    def master_at(self, ms: int) -> TimelineClip | None:
        """The master movie under this timeline time."""
        masters = self.master_clips()
        if not masters:
            return None
        for clip in masters:
            if clip.start_ms <= int(ms) < clip.end_ms:
                return clip
        if int(ms) >= masters[-1].end_ms:
            return masters[-1]
        return masters[0]

    def master_span(self) -> tuple[int, int] | None:
        """Start and length of the master footage, in milliseconds."""
        masters = self.master_clips()
        if masters:
            start = masters[0].start_ms
            end = max(clip.end_ms for clip in masters)
            if end > start:
                return start, end - start
        if self.duration_ms > 0:
            return 0, self.duration_ms
        return None

    def master_clip(self) -> TimelineClip | None:
        """The footage clip preview and export follow."""
        masters = self.master_clips()
        return masters[0] if masters else None

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
                if clip.extra.get("stem"):
                    continue
                if clip.track_id == track.id and self.clip_volume(clip) > 0:
                    spans.append((clip.start_ms, clip.end_ms))
        return sorted(spans)

    def stem_role(self, clip: TimelineClip) -> str:
        track = self.track_by_id(clip.track_id)
        return audio_stem_role(
            bool(clip.extra.get("stem")),
            getattr(track, "name", "") or "",
            clip.label or "",
        )

    def effects_bed_active(self) -> bool:
        """An audible Effects stem is the soundtrack, so the full movie mix stays out."""
        for clip in self.clips:
            if self.stem_role(clip) != "effects" or not clip.extra.get("path"):
                continue
            track = self.track_by_id(clip.track_id)
            if track is not None and not track.muted and not track.hidden:
                return True
        return False

    def effects_clip_at(self, ms: int) -> TimelineClip | None:
        if not self.effects_bed_active():
            return None
        for track in self.tracks:
            if track.kind != "audio" or track.muted or track.hidden:
                continue
            for clip in self.clips:
                if clip.track_id != track.id or self.stem_role(clip) != "effects":
                    continue
                if clip.extra.get("path") and clip.start_ms <= ms < clip.end_ms:
                    return clip
        return None

    def voice_clip_at(self, ms: int, take: bool = False) -> TimelineClip | None:
        replaced = self.effects_bed_active()
        for track in self.tracks:
            if track.kind not in {"voice", "audio"}:
                continue
            for clip in self.clips:
                if clip.track_id != track.id or bool(clip.extra.get("take")) != take:
                    continue
                role = self.stem_role(clip)
                if role == "effects" or (replaced and role in {"source", "vocals"}):
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
