"""Load, seek, and mix the preview player and stem buses."""
from __future__ import annotations

import os

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import (
    QUrl,
    Slot,
    QSize,
    QThreadPool,
)
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from claynext.adapters.ffmpeg_service import probe_media
from claynext.adapters.media import ensure_playback_file, ready_playback_path
from claynext.gui.worker import Worker
from claynext.models.thumbnails import ensure_thumbnail, pixmap_for, VIDEO_EXTS

class PreviewPlayer:
    def set_dock_host(self, host: QWidget, index: int = 0):
        self._dock_host = host
        self._dock_index = index

    def set_fullscreen_target(self, target: QWidget, host: QWidget, index: int = 0):
        """Take `target` (e.g. stage + overlays) fullscreen instead of the bare player, docking back into host."""
        self._fs_target = (target, host, index)

    def _setup_player(self):
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video.videoSink())
        self._source_gain = 1.0
        self._voice_gain = 1.0
        self._bed_gain = 0.0
        self._master_mute = False
        self._bed_path = ""
        self._voice_path = ""
        self.bed_out = QAudioOutput(self)
        self.voice_out = QAudioOutput(self)
        self.bed_player = QMediaPlayer(self)
        self.voice_player = QMediaPlayer(self)
        self.bed_player.setAudioOutput(self.bed_out)
        self.voice_player.setAudioOutput(self.voice_out)

        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.errorOccurred.connect(self._on_error)
        self.video.frame_image.connect(self._on_video_frame)
        self.stage.setCurrentIndex(0)

    @staticmethod
    def _probe_video_size(path: str) -> tuple[int, int]:
        """Return (width, height) from probe_media; never raises."""
        try:
            info = probe_media(path)
        except Exception:
            return 0, 0
        if isinstance(info, dict):
            return int(info.get("width") or 0), int(info.get("height") or 0)
        stream = getattr(info, "video_stream", None)
        if stream is None:
            return 0, 0
        return int(getattr(stream, "width", 0) or 0), int(getattr(stream, "height", 0) or 0)

    def load(self, path: str) -> bool:
        if not path or not os.path.isfile(path):
            self.clear()
            return False

        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.stop()
        self.player.setSource(QUrl())

        self._load_gen += 1
        gen = self._load_gen
        self._path = path
        self._play_path = ""
        self._source_ready = False
        self._pending_play = False
        self._pending_seek = -1
        self._title = os.path.basename(path)
        ext = os.path.splitext(path)[1].lower()
        self._is_video = ext in VIDEO_EXTS

        self.stage.show()
        self._update_stage_bounds()

        if self._is_video:
            # Placeholder first — poster/probe run async so Play is not blocked
            self.poster.clear()
            self.poster.setText(self._title)
            self.stage.setCurrentWidget(self.poster)
            self._queue_poster(path, gen)
        else:
            self.placeholder.setText(self._title)
            self.stage.setCurrentWidget(self.placeholder)

        self.media_changed.emit(path)

        abs_path = os.path.abspath(path)
        # Instant path: cached convert OR original MP4/MOV (no blocking re-encode)
        cached = ready_playback_path(abs_path)
        if cached:
            self.loading_changed.emit(False)
            self._apply_play_source(gen, cached)
            return True

        # Exotic formats only — convert in background; allow pending play when ready
        self.loading_changed.emit(True)
        worker = Worker(ensure_playback_file, abs_path)
        worker.signals.result.connect(lambda play_path, g=gen: self._apply_play_source(g, play_path))
        worker.signals.error.connect(lambda err, _tb, g=gen: self._on_compat_fail(g, err))
        self._compat_worker = worker
        QThreadPool.globalInstance().start(worker)
        return True

    def _queue_poster(self, path: str, gen: int):
        """Probe size + cache poster thumb off the UI thread (QPixmap stays on UI)."""

        def _job(media_path: str, progress_callback=None):
            w, h = self._probe_video_size(media_path)
            thumb = ensure_thumbnail(media_path, width=480)
            return w, h, thumb or ""

        worker = Worker(_job, path)
        worker.signals.result.connect(lambda res, g=gen: self._on_poster_ready(g, res))
        QThreadPool.globalInstance().start(worker)

    def _on_poster_ready(self, gen: int, res):
        if gen != self._load_gen or not self._is_video:
            return
        try:
            w, h, thumb = res
        except Exception:
            return
        if w > 0 and h > 0:
            self._video_natural_ratio = float(w) / float(h)
            self._update_stage_bounds()
        # Don't clobber live video while playing
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            return
        pix = pixmap_for(self._path, QSize(480, 270)) if self._path else QPixmap()
        if pix.isNull() and thumb and os.path.isfile(thumb):
            pix = QPixmap(thumb)
        if pix.isNull():
            return
        if pix.width() > 0 and pix.height() > 0:
            new_ratio = float(pix.width()) / float(pix.height())
            if (
                self._video_natural_ratio is None
                or abs(self._video_natural_ratio - new_ratio) > 0.001
            ):
                self._video_natural_ratio = new_ratio
                self._update_stage_bounds()
        self._paint_poster(pix)
        if self.stage.currentWidget() is not self.video:
            self.stage.setCurrentWidget(self.poster)
        if self._canvas["bg"] == "blur":
            self._set_blur_source(pix.toImage())

    def _on_compat_fail(self, gen: int, err):
        if gen != self._load_gen:
            return
        self._source_ready = False
        self.loading_changed.emit(False)
        self.placeholder.setText(f"Playback convert failed · {err}")
        self.stage.setCurrentWidget(self.placeholder)

    def _apply_play_source(self, gen: int, play_path: str):
        if gen != self._load_gen or not self._path:
            return
        if not play_path or not os.path.isfile(play_path):
            self._on_compat_fail(gen, "missing playback file")
            return
        self._play_path = play_path
        self.player.setSource(QUrl.fromLocalFile(os.path.abspath(play_path)))
        self._source_ready = True
        self.loading_changed.emit(False)
        self._apply_buses()
        if self._pending_seek >= 0:
            self.seek_ms(self._pending_seek)
        if self._pending_play:
            self._pending_play = False
            self.toggle_play()

    def clear(self):
        if self._fullscreen:
            self.exit_fullscreen()
        self.stop()
        self._load_gen += 1
        self._path = ""
        self._play_path = ""
        self._title = ""
        self._is_video = False
        self.loading_changed.emit(False)
        self._source_ready = False
        self._pending_play = False
        self._video_natural_ratio = None
        self._custom_ratio = self.ASPECT_PRESETS.get(self._aspect_key, (None, None))[0]
        self._blur_src = QImage()
        self.player.setSource(QUrl())
        self.placeholder.setText("Select media to play")
        self.poster.clear()
        self.stage.setCurrentWidget(self.placeholder)
        self.stage.hide()
        self.playing_changed.emit(False)
        self.duration_changed.emit(0)
        self.position_changed.emit(0)
        self.media_cleared.emit()

    def toggle_play(self):
        if not self._path:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            return
        if not self._source_ready:
            self._pending_play = True
            return
        if self._is_video:
            self.stage.setCurrentWidget(self.video)
        self.player.play()

    def stop(self):
        self._pending_play = False
        self.player.stop()
        if self._path and self._is_video:
            self._show_poster(self._path)

    def stop_playback(self):
        """Halt audio/video when leaving the tool window."""
        self._pending_play = False
        if self._fullscreen:
            self.exit_fullscreen()
        self.player.stop()
        if self._path and self._is_video:
            self._show_poster(self._path)

    def seek_ms(self, ms: int):
        pos = max(0, int(ms))
        if self._path and not self._source_ready:
            self._pending_seek = pos
            return
        self._pending_seek = -1
        self.player.setPosition(pos)
        self._seek_stems(pos)

    def set_muted(self, muted: bool):
        self._master_mute = bool(muted)
        self._apply_buses()

    def set_source_gain(self, gain: float):
        self._source_gain = max(0.0, min(1.5, float(gain)))
        self._apply_buses()

    def set_voice_gain(self, gain: float):
        self._voice_gain = max(0.0, min(1.5, float(gain)))
        self._apply_buses()

    def set_bed_gain(self, gain: float):
        self._bed_gain = max(0.0, min(1.5, float(gain)))
        self._apply_buses()

    def set_stems(self, bed: str, voice: str):
        self._bed_path = bed if bed and os.path.isfile(bed) else ""
        self._voice_path = voice if voice and os.path.isfile(voice) else ""
        self._load_stem(self.bed_player, self._bed_path)
        self._load_stem(self.voice_player, self._voice_path)
        self._apply_buses()
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._sync_stems(True)

    def _load_stem(self, player: QMediaPlayer, path: str):
        player.stop()
        if path:
            player.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
            player.setPosition(self.player.position())
        else:
            player.setSource(QUrl())

    def _apply_buses(self):
        if not hasattr(self, "audio"):
            return
        source = 0.0 if self._master_mute else self._source_gain
        voice = 0.0 if self._master_mute else self._voice_gain
        bed = 0.0 if self._master_mute or not self._bed_path else self._bed_gain
        self.audio.setMuted(source <= 0.001)
        self.audio.setVolume(min(1.0, source))
        self.bed_out.setVolume(min(1.0, bed))
        self.bed_out.setMuted(bed <= 0.001)
        self.voice_out.setVolume(voice)
        self.voice_out.setMuted(voice <= 0.001 or not self._voice_path)

    def _seek_stems(self, pos: int):
        for player, path in ((self.bed_player, self._bed_path), (self.voice_player, self._voice_path)):
            if path:
                player.setPosition(pos)

    def _sync_stems(self, playing: bool):
        pos = self.player.position()
        for player, path in ((self.bed_player, self._bed_path), (self.voice_player, self._voice_path)):
            if not path:
                if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                    player.pause()
                continue
            if abs(player.position() - pos) > 180:
                player.setPosition(pos)
            if playing and player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                player.play()
            elif not playing and player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                player.pause()

    @Slot(int)
    def _on_position(self, pos: int):
        self.position_changed.emit(pos)
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._sync_stems(True)

    @Slot(int)
    def _on_duration(self, dur: int):
        self.duration_changed.emit(dur)

    @Slot(QMediaPlayer.PlaybackState)
    def _on_state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.playing_changed.emit(playing)
        self._sync_stems(playing)
        if state == QMediaPlayer.PlaybackState.StoppedState and self._path and self._is_video:
            self._show_poster(self._path)

    def _on_error(self, error, message=""):
        # Auto-recover using proxy processor if playback stream errors out
        if self._path and not getattr(self, "_proxy_recovering", False):
            self._proxy_recovering = True
            # pyrefly: ignore [missing-import]
            from claynext.adapters.media import ensure_proxy_render
            gen = self._load_gen
            worker = Worker(ensure_proxy_render, self._path)
            worker.signals.result.connect(lambda proxy_path, g=gen: self._on_proxy_recovered(g, proxy_path))
            worker.signals.error.connect(lambda _err, _tb: self._reset_proxy_recovering())
            QThreadPool.globalInstance().start(worker)
            return

        if self._path and self._is_video and self.poster.pixmap() and not self.poster.pixmap().isNull():
            self.stage.setCurrentWidget(self.poster)
        else:
            self.placeholder.setText(f"Preview error · {message or error}")
            self.stage.setCurrentWidget(self.placeholder)

    def _reset_proxy_recovering(self):
        self._proxy_recovering = False

    def _on_proxy_recovered(self, gen: int, proxy_path: str):
        self._proxy_recovering = False
        if gen == self._load_gen and proxy_path and os.path.isfile(proxy_path):
            self._apply_play_source(gen, proxy_path)
