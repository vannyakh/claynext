"""Tests for translate service refactoring, models, and latency optimizations."""
from __future__ import annotations

from unittest.mock import patch
import pytest

from claynext.models.translate_service import TranslateEngine, BATCH_SIZE, GEMINI_MIN_INTERVAL


def test_translate_constants_and_models():
    """Verify API batch packing + per-key pacing constants, and valid models."""
    assert BATCH_SIZE >= 40
    assert 2.0 <= GEMINI_MIN_INTERVAL <= 6.0

    # Ensure gemini-2.5-flash is NOT used since it generates 404 on Google AI Studio
    import inspect
    lines = inspect.getsource(TranslateEngine._gemini_batch)
    assert "gemini-2.5-flash" not in lines
    assert "gemini-2.0-flash" in lines


def test_pack_batches_respects_char_budget():
    # ~500 chars/line × 30 lines exceeds BATCH_MAX_CHARS
    segs = [{"id": i, "text": ("hello word " * 45)} for i in range(30)]
    batches = TranslateEngine._pack_batches(segs)
    assert len(batches) >= 2
    assert sum(len(b) for b in batches) == 30


def test_spoken_units_fast():
    """Verify fast in-memory beat calculation for GUI."""
    khmer_text = "សួស្តីបងប្អូនទាំងអស់គ្នា"
    beats = TranslateEngine.spoken_units_fast(khmer_text, "Khmer")
    assert beats > 0

    chinese_text = "下官秦州通判莫宗明"
    beats_zh = TranslateEngine.spoken_units_fast(chinese_text, "Chinese")
    assert beats_zh == 9


def test_translate_google_parallel():
    """Test parallel google translation returns correct packed rows."""
    segments = [
        {"id": 1, "text": "Hello world", "start": "00:00:01", "end": "00:00:03"},
        {"id": 2, "text": "Good morning", "start": "00:00:04", "end": "00:00:06"},
    ]

    with patch.object(TranslateEngine, "translate_text", side_effect=lambda text, target, source_lang="auto": f"translated_{text}"):
        result = TranslateEngine._translate_google_batched(segments, "Khmer")
        assert len(result) == 2
        assert result[0]["translated_text"] == "translated_Hello world"
        assert result[1]["translated_text"] == "translated_Good morning"
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2


def test_translate_subtitles_auto_fallback():
    """Test translate_subtitles runs cleanly through fallback."""
    segments = [
        {"id": 1, "text": "Hello world", "start": "00:00:01", "end": "00:00:03"},
    ]

    with patch.object(TranslateEngine, "translate_text", return_value="សួស្តីពិភពលោក"):
        res = TranslateEngine.translate_subtitles(
            segments,
            target_lang="Khmer",
            translator="google",
        )
        assert len(res) == 1
        assert res[0]["translated_text"] == "សួស្តីពិភពលោក"
