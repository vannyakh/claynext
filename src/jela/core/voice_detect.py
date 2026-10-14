"""Find where people speak in a movie so the mix can swap only those spans to the music bed."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

import numpy as np
from PySide6 import QtMultimedia  # noqa: F401

from jela.core.ffmpeg_tools import ffmpeg_exe, probe_duration
from jela.utils.config import CACHE_DIR

RATE = 16000
CHUNK_S = 600
_SPEECH_FILTER = "pan=mono|c0=0.5*c0+0.5*c1,highpass=f=90,lowpass=f=7500"


def _cache_path(media_path: str, sensitivity: float) -> str:
    stat = os.stat(media_path)
    key = f"{os.path.abspath(media_path)}|{stat.st_size}|{int(stat.st_mtime)}|{sensitivity:.2f}|v1"
    folder = CACHE_DIR / "voice_spans"
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder / f"{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}.json")


def _read_chunks(media_path: str):
    """Yield (offset_s, float32 mono 16 kHz) blocks of the dialogue-weighted mid channel."""
    proc = subprocess.Popen(
        [
            ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin",
            "-i", media_path, "-vn", "-af", _SPEECH_FILTER,
            "-ac", "1", "-ar", str(RATE), "-f", "f32le", "pipe:1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    block = CHUNK_S * RATE * 4
    offset = 0.0
    try:
        while True:
            raw = proc.stdout.read(block)
            if not raw:
                break
            audio = np.frombuffer(raw[: len(raw) // 4 * 4], dtype=np.float32)
            yield offset, audio
            offset += len(audio) / RATE
    finally:
        proc.stdout.close()
        proc.wait()


def _silero_spans(audio: np.ndarray, sensitivity: float) -> list[tuple[float, float]]:
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    options = VadOptions(
        threshold=max(0.2, min(0.8, 0.65 - 0.3 * sensitivity)),
        min_speech_duration_ms=160,
        min_silence_duration_ms=220,
        speech_pad_ms=90,
    )
    return [
        (item["start"] / RATE, item["end"] / RATE)
        for item in get_speech_timestamps(audio, options, sampling_rate=RATE)
    ]


def _energy_spans(audio: np.ndarray, sensitivity: float) -> list[tuple[float, float]]:
    frame = int(RATE * 0.03)
    count = len(audio) // frame
    if count < 4:
        return []
    rms = np.sqrt(np.mean(audio[: count * frame].reshape(count, frame) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    floor, peak = np.percentile(db, 20), np.percentile(db, 97)
    gate = floor + (peak - floor) * (0.55 - 0.25 * sensitivity)
    active = db > gate
    spans, start = [], None
    for i, on in enumerate(active):
        if on and start is None:
            start = i
        elif not on and start is not None:
            spans.append((start * 0.03, i * 0.03))
            start = None
    if start is not None:
        spans.append((start * 0.03, count * 0.03))
    return spans


def merge_spans(spans: list[list[int]], gap_ms: int = 250, min_ms: int = 200) -> list[list[int]]:
    merged: list[list[int]] = []
    for start, end in sorted([int(a), int(b)] for a, b in spans if b > a):
        if merged and start - merged[-1][1] <= gap_ms:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [span for span in merged if span[1] - span[0] >= min_ms]


def detect_voice_spans(media_path: str, sensitivity: float = 0.5, progress_callback=None) -> list[list[int]]:
    """Speech spans in ms. Silero VAD when available, an energy gate otherwise. Cached per file."""
    if not media_path or not os.path.isfile(media_path):
        return []
    cache = _cache_path(media_path, sensitivity)
    if os.path.isfile(cache):
        try:
            with open(cache, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            pass
    try:
        import faster_whisper.vad  # noqa: F401
        detect = _silero_spans
    except Exception:
        detect = _energy_spans
    total = max(1.0, probe_duration(media_path))
    spans: list[list[int]] = []
    for offset, audio in _read_chunks(media_path):
        for start, end in detect(audio, sensitivity):
            spans.append([int((offset + start) * 1000), int((offset + end) * 1000)])
        if progress_callback:
            done = min(99, int((offset + len(audio) / RATE) * 100 / total))
            progress_callback(done, f"Detecting voices… {done}%")
    spans = merge_spans(spans)
    with open(cache, "w", encoding="utf-8") as handle:
        json.dump(spans, handle)
    return spans
