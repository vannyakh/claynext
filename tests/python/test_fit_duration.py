"""Tests for fit_duration: full speech preservation without truncation, and dynamic speed-up."""
from __future__ import annotations

import os
import tempfile
import wave
import numpy as np
import pytest

from claynext.adapters.ffmpeg_service import fit_duration, probe_duration


def _generate_wav(duration: float, freq: float = 300.0, sr: int = 16000) -> str:
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    sig = np.sin(2 * np.pi * freq * t)
    samples = (sig * 32767).astype(np.int16)

    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.tobytes())
    return path


def test_fit_duration_up_speed_and_never_trim():
    """Verify that a 3.0s audio clip for a 1.5s slot speeds up without being hard-trimmed."""
    src = _generate_wav(3.0)
    fd, dst = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    try:
        # Request 1.5s target slot
        fit_duration(src, dst, target_sec=1.5, min_tempo=0.65, max_tempo=2.80, pad_or_trim=False, never_trim=True)
        res_dur = probe_duration(dst)

        # 3.0s at 2.0x speed should be approximately 1.5s (within ±0.15s)
        assert 1.35 <= res_dur <= 1.65
        assert os.path.getsize(dst) > 1000
    finally:
        for p in (src, dst):
            if os.path.exists(p):
                os.remove(p)


def test_fit_duration_high_tempo_chaining():
    """Verify that an audio clip requiring >2.0x tempo (e.g. 2.4x) speeds up cleanly via atempo chaining."""
    src = _generate_wav(4.8)
    fd, dst = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    try:
        # 4.8s into 2.0s slot requires 2.4x speed
        fit_duration(src, dst, target_sec=2.0, min_tempo=0.65, max_tempo=2.80, pad_or_trim=False, never_trim=True)
        res_dur = probe_duration(dst)

        # 4.8s / 2.4 = ~2.0s
        assert 1.80 <= res_dur <= 2.20
    finally:
        for p in (src, dst):
            if os.path.exists(p):
                os.remove(p)
