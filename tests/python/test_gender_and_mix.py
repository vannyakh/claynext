"""Tests for AI gender detection, character naming, and 0-volume dialogue isolation."""
from __future__ import annotations

import tempfile
import wave
import numpy as np
import pytest

from claynext.models.gender_voices import (
    infer_gender_from_text,
    apply_character_cast,
    assign_gender_and_voices,
)
from claynext.adapters.ffmpeg_service import dynamic_duck_audio


def test_chinese_official_male_detection():
    line = "下官秦州通判莫宗明，率本州属官，恭迎圣上任"
    assert infer_gender_from_text(line) == "Male"

    segs = [{"speaker": "Character 1", "text": line}]
    apply_character_cast(segs)
    assert segs[0]["speaker"] == "莫宗明"

    assign_gender_and_voices(
        segs,
        primary_voice="km-KH-SreymomNeural",
        secondary_voice="km-KH-PisethNeural",
        lang="km-KH",
    )
    assert segs[0]["gender"] == "Male"
    assert segs[0]["tts_voice_hint"] == "km-KH-PisethNeural"


def test_chinese_female_greeting_detection():
    line = "臣妾给皇上请安，愿皇上万岁万福。"
    assert infer_gender_from_text(line) == "Female"

    segs = [{"speaker": "Character 2", "text": line}]
    assign_gender_and_voices(
        segs,
        primary_voice="km-KH-PisethNeural",
        secondary_voice="km-KH-SreymomNeural",
        lang="km-KH",
    )
    assert segs[0]["gender"] == "Female"
    assert segs[0]["tts_voice_hint"] == "km-KH-SreymomNeural"


def test_spoken_source_ducking_volume_zero():
    """Verify that duck_vol=0.0 completely silences the spoken dialogue segments."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f_in, tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f_out:
        in_path = f_in.name
        out_path = f_out.name

    try:
        wf = wave.open(in_path, "wb")
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        # 2 seconds of sound at amplitude 12000
        samples = (np.ones((44100 * 2, 2)) * 12000).astype(np.int16)
        wf.writeframes(samples.tobytes())
        wf.close()

        # Duck dialogue from 0.4s to 1.6s down to 0.0
        dynamic_duck_audio(in_path, [(0.4, 1.6)], out_path, duck_vol=0.0)

        wf_out = wave.open(out_path, "rb")
        raw = wf_out.readframes(wf_out.getnframes())
        wf_out.close()
        out_samples = np.frombuffer(raw, dtype=np.int16).reshape(-1, 2)

        # In the middle of the spoken segment (0.8s to 1.2s), volume must be exactly 0
        mid_start = int(0.8 * 44100)
        mid_end = int(1.2 * 44100)
        max_spoken_vol = int(np.max(np.abs(out_samples[mid_start:mid_end])))
        assert max_spoken_vol == 0

        # Outside the spoken segment (at start), cinema audio remains at full volume
        max_outside_vol = int(np.max(np.abs(out_samples[0:500])))
        assert max_outside_vol > 5000
    finally:
        import os
        for p in (in_path, out_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


def test_ffmpeg_adapter_run_ffmpeg_compatibility():
    from claynext.adapters.ffmpeg_adapter import run_ffmpeg, FFmpegResult

    # Test with keyword argument 'timeout'
    res = run_ffmpeg(["-version"], timeout=30)
    assert isinstance(res, FFmpegResult)
    assert res.returncode == 0
    # Test bool behavior
    assert bool(res) is True

    # Test failure return
    bad_res = run_ffmpeg(["-invalid_option_xyz"], timeout=10)
    assert bad_res.returncode != 0
    assert bool(bad_res) is False


def test_meaningful_speech_and_merge_segments():
    from claynext.models.asr_service import is_meaningful_speech, merge_dialogue_segments

    # 1. Punctuation & phantom Whisper hallucinations
    assert not is_meaningful_speech("...")
    assert not is_meaningful_speech("……")
    assert not is_meaningful_speech("口 ...")
    assert not is_meaningful_speech("♪♫")
    assert not is_meaningful_speech("   ")
    assert is_meaningful_speech("下官秦州通判莫宗明")
    assert is_meaningful_speech("Hello world")

    # 2. Merge chopped segments from the same speech turn
    raw_segments = [
        {"id": 1, "start": "00:01:00,000", "end": "00:01:00,300", "text": "..."},
        {"id": 2, "start": "00:01:00,400", "end": "00:01:01,200", "text": "下官秦州通判"},
        {"id": 3, "start": "00:01:01,350", "end": "00:01:02,500", "text": "莫宗明"},
        {"id": 4, "start": "00:01:02,600", "end": "00:01:04,000", "text": "恭迎圣上"},
        {"id": 5, "start": "00:01:04,100", "end": "00:01:04,400", "text": "口"},
    ]
    merged = merge_dialogue_segments(raw_segments)
    # The dummy "..." and "口" must be stripped out, and the 3 speech parts merged into 1 coherent sentence
    assert len(merged) == 1
    assert merged[0]["start"] == "00:01:00,400"
    assert merged[0]["end"] == "00:01:04,000"
    assert merged[0]["text"] == "下官秦州通判莫宗明恭迎圣上"


