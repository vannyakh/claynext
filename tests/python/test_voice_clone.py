"""Tests for movie voice cloning, pitch/tone detection, and runtime tone matching."""
from __future__ import annotations

import os
import tempfile
import wave
import numpy as np
import pytest

from claynext.models.voice_clone import (
    analyze_voice_tone,
    clone_character_voices_from_movie,
)
from claynext.models.tts_service import TTSEngine


def _generate_tone_wav(freq: float, duration: float = 1.0, sr: int = 16000) -> str:
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Fundamental + harmonics to simulate vocal tone
    sig = 0.7 * np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * 2 * freq * t)
    samples = (sig * 32767).astype(np.int16)

    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.tobytes())
    return path


def test_analyze_voice_tone_male():
    """Verify detection of deep male vocal tone (~110 Hz)."""
    wav_path = _generate_tone_wav(110.0, duration=1.2)
    try:
        tone = analyze_voice_tone(wav_path)
        assert abs(tone["median_f0"] - 110.0) < 5.0
        assert tone["gender"] == "Male"
        # Base male std is 125, so offset ~ -15 Hz
        assert -20.0 <= tone["pitch_offset_hz"] <= -10.0
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)


def test_analyze_voice_tone_female():
    """Verify detection of female vocal tone (~220 Hz)."""
    wav_path = _generate_tone_wav(220.0, duration=1.2)
    try:
        tone = analyze_voice_tone(wav_path)
        assert abs(tone["median_f0"] - 220.0) < 5.0
        assert tone["gender"] == "Female"
        # Base female std is 210, so offset ~ +10 Hz
        assert 5.0 <= tone["pitch_offset_hz"] <= 15.0
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)


def test_clone_voices_catalog_integration():
    """Verify clone:movie is in catalog and properly labeled."""
    voices = TTSEngine.list_voices("Khmer")
    clone_entry = next((v for v in voices if v["id"] == "clone:movie"), None)
    assert clone_entry is not None
    assert clone_entry["tag"] == "Voice Clone"

    label = TTSEngine.voice_label("clone:Mo Zongming")
    assert "Actor Clone (Mo Zongming)" in label


def test_clone_character_voices_from_movie():
    """Verify voice clone extraction and metadata attachment to script segments."""
    wav_path = _generate_tone_wav(115.0, duration=3.0)
    try:
        segments = [
            {
                "id": 1,
                "speaker": "Commander",
                "start": "00:00:00,100",
                "end": "00:00:02,500",
                "start_sec": 0.1,
                "end_sec": 2.5,
                "text": "Open the city gates immediately!",
            }
        ]
        profiles = clone_character_voices_from_movie(wav_path, segments)
        assert "Commander" in profiles
        assert segments[0]["voice_id"] == "clone:Commander"
        assert "reference_wav" in segments[0]
        assert "pitch_offset" in segments[0]
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)
