"""Tests for cinematic movie-translate orchestration."""
from __future__ import annotations

from unittest.mock import patch

from claynext.models.movie_translate import (
    _merge_cast,
    pick_ollama_model,
    resolve_movie_engine_chain,
    translate_movie_dialogue,
)


def test_resolve_movie_chain_includes_fallbacks():
    with patch("claynext.models.movie_translate.get_key_pool") as pool_cls, patch(
        "claynext.models.translate_service.TranslateEngine.ollama_available",
        return_value=True,
    ), patch(
        "claynext.models.translate_service.TranslateEngine.is_nllb_downloaded",
        return_value=True,
    ), patch(
        "claynext.models.movie_translate.pick_ollama_model",
        return_value="qwen3:8b",
    ):
        pool = pool_cls.return_value
        pool.secrets.return_value = ["fake-key"]
        pool.ready_count.return_value = 1
        steps = resolve_movie_engine_chain("auto", target_lang="Khmer", ollama_model="")
        backends = [b for _l, b, _m in steps]
        assert backends[0] == "gemini"
        assert "ollama" in backends
        assert "nllb" in backends
        assert backends[-1] == "google"


def test_movie_engine_alias():
    with patch("claynext.models.movie_translate.get_key_pool") as pool_cls, patch(
        "claynext.models.translate_service.TranslateEngine.ollama_available",
        return_value=False,
    ), patch(
        "claynext.models.translate_service.TranslateEngine.is_nllb_downloaded",
        return_value=False,
    ):
        pool = pool_cls.return_value
        pool.secrets.return_value = []
        pool.ready_count.return_value = 0
        steps = resolve_movie_engine_chain("movie")
        assert steps[-1][1] == "google"


def test_merge_cast_keeps_speaker():
    originals = [
        {
            "id": 1,
            "text": "Hi",
            "speaker": "Hero",
            "gender": "Male",
            "duration_sec": 1.5,
            "recommended_syllables": {"min": 1, "target": 3, "max": 4},
        }
    ]
    translated = [{"id": 1, "translated_text": "សួស្តី", "original_text": "Hi"}]
    merged = _merge_cast(originals, translated)
    assert merged[0]["speaker"] == "Hero"
    assert merged[0]["gender"] == "Male"
    assert merged[0]["duration_sec"] == 1.5


def test_translate_movie_dialogue_google_path():
    segs = [
        {"id": 1, "text": "Hello", "start": "00:00:01", "end": "00:00:03", "speaker": "A"},
    ]
    with patch(
        "claynext.models.movie_translate.resolve_movie_engine_chain",
        return_value=[("Google", "google", "")],
    ), patch(
        "claynext.models.translate_service.TranslateEngine._translate_google_batched",
        return_value=[{"id": 1, "translated_text": "សួស្តី", "original_text": "Hello"}],
    ), patch(
        "claynext.models.translate_service.TranslateEngine._ensure_timing",
    ):
        out = translate_movie_dialogue(segs, "Khmer", translator="google")
        assert out[0]["translated_text"] == "សួស្តី"
        assert out[0]["speaker"] == "A"


def test_pick_ollama_prefers_installed():
    with patch(
        "claynext.models.movie_translate._installed_ollama",
        return_value={"aya-expanse:8b", "qwen3:8b"},
    ):
        assert pick_ollama_model("", target_lang="Khmer") == "aya-expanse:8b"
        assert pick_ollama_model("", target_lang="English") == "qwen3:8b"
