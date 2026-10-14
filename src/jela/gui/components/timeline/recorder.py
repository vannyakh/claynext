"""Microphone voice-over capture for the timeline (Qt Multimedia)."""
from __future__ import annotations

import os
import time

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import (
    QAudioInput, QMediaCaptureSession, QMediaDevices, QMediaFormat, QMediaRecorder,
)

from jela.utils.paths import VOICEOVER_DIR


class VoiceRecorder(QObject):
    started = Signal(int)
    elapsed = Signal(int)
    finished = Signal(str, int, int)
    failed = Signal(str)
    devices_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._devices = QMediaDevices(self)
        self._devices.audioInputsChanged.connect(self.devices_changed.emit)
        self._device_id = b""
        self._input: QAudioInput | None = None
        self._session = QMediaCaptureSession(self)
        self._recorder = QMediaRecorder(self)
        self._session.setRecorder(self._recorder)
        fmt = QMediaFormat(QMediaFormat.FileFormat.Mpeg4Audio)
        fmt.setAudioCodec(QMediaFormat.AudioCodec.AAC)
        self._recorder.setMediaFormat(fmt)
        self._recorder.setQuality(QMediaRecorder.Quality.HighQuality)
        self._recorder.setAudioSampleRate(48000)
        self._recorder.setAudioChannelCount(1)
        self._recorder.durationChanged.connect(lambda ms: self.elapsed.emit(int(ms)))
        self._recorder.recorderStateChanged.connect(self._on_state)
        self._recorder.errorOccurred.connect(self._on_error)
        self._start_ms = 0
        self._path = ""
        self._active = False

    @staticmethod
    def inputs() -> list[tuple[bytes, str, bool]]:
        return [(bytes(d.id()), d.description(), d.isDefault()) for d in QMediaDevices.audioInputs()]

    @property
    def device_id(self) -> bytes:
        return self._device_id

    def set_device(self, device_id: bytes):
        self._device_id = bytes(device_id or b"")

    def is_recording(self) -> bool:
        return self._active

    def _device(self):
        devices = QMediaDevices.audioInputs()
        match = next((d for d in devices if bytes(d.id()) == self._device_id), None)
        return match or QMediaDevices.defaultAudioInput()

    def start(self, start_ms: int) -> bool:
        if self._active:
            return False
        device = self._device()
        if device.isNull():
            self.failed.emit("No microphone found")
            return False
        self._input = QAudioInput(device, self)
        self._session.setAudioInput(self._input)
        VOICEOVER_DIR.mkdir(parents=True, exist_ok=True)
        self._path = str(VOICEOVER_DIR / f"take_{time.strftime('%Y%m%d_%H%M%S')}.m4a")
        self._recorder.setOutputLocation(QUrl.fromLocalFile(self._path))
        self._start_ms = max(0, int(start_ms))
        self._active = True
        self._recorder.record()
        self.started.emit(self._start_ms)
        return True

    def stop(self):
        if self._active:
            self._recorder.stop()

    def _on_state(self, state):
        if state != QMediaRecorder.RecorderState.StoppedState or not self._active:
            return
        self._active = False
        duration = int(self._recorder.duration())
        actual = self._recorder.actualLocation().toLocalFile() or self._path
        self._session.setAudioInput(None)
        if not actual or not os.path.isfile(actual) or os.path.getsize(actual) == 0:
            self.failed.emit("Recording produced no audio file")
            return
        self.finished.emit(actual, self._start_ms, duration)

    def _on_error(self, _error, message: str):
        was_active = self._active
        self._active = False
        self._session.setAudioInput(None)
        if was_active:
            self.failed.emit(message or "Recording failed")
