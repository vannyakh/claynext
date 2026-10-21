"""Character Intelligence Engine + Dialogue Performance Planner. No network, no TTS."""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from claynext.models.character_intel import (
    CharacterRegistry,
    map_delivery,
    plan_performance,
    set_line_style,
    tempo_window,
)
from claynext.models.character_intel.performance_planner import build_request, plan_lines
from claynext.models.character_intel.prosody import prosody_fallback
from claynext.models.character_intel.stage import PLAN_FILE, REGISTRY_FILE, run_character_stage
from claynext.models.character_intel.voice_casting import estimate_presentation

_NO_RUST = "claynext.adapters.rust_bridge.ai._find_binary"


def _line(i: int, speaker: str, text: str, *, sid: str = "", **extra) -> dict:
    seg = {
        "id": i + 1,
        "start": f"00:00:{i * 3:02d},000",
        "end": f"00:00:{i * 3 + 2:02d},500",
        "speaker": speaker,
        "original_text": text,
        "translated_text": text,
        "text": text,
        "tts_voice_hint": "km-KH-PisethNeural",
    }
    if sid:
        seg.update(speaker_id=sid, speaker_source="diarization")
    seg.update(extra)
    return seg


def _scene() -> list[dict]:
    return [
        _line(0, "SPEAKER_00", "Where were you last night?", sid="SPEAKER_00"),
        _line(1, "SPEAKER_01", "GET OUT OF MY HOUSE!!", sid="SPEAKER_01"),
        _line(2, "SPEAKER_00", "I'm sorry.", sid="SPEAKER_00"),
    ]


def _tone(freq: float, seconds: float, sr: int = 8000, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    return (amp * np.sin(2 * math.pi * freq * t)).astype(np.float32)


# ── performance planner ───────────────────────────────────────────────────

def _styles(segments: list[dict]) -> list[str]:
    return [seg["performance"]["style"] for seg in segments]


def test_shouted_line_is_never_neutral_rust_and_python():
    for no_rust in (False, True):
        segs = _scene()
        if no_rust:
            with patch(_NO_RUST, return_value=None):
                plan = plan_performance(segs, lang="Khmer")
            assert plan["engine"] == "python"
        else:
            plan = plan_performance(segs, lang="Khmer")
        perf = segs[1]["performance"]
        assert perf["style"] == "shouting", (plan["engine"], perf)
        assert perf["intensity"] >= 0.65
        assert perf["delivery"] == "shouting"
        for key in ("emotion", "intensity", "timing", "overall"):
            assert 0.0 <= float(perf["confidence"][key]) <= 1.0


def test_angry_expression_is_not_neutral():
    segs = [_line(0, "A", "You lied to me.", expression="angry", expression_source="llm")]
    with patch(_NO_RUST, return_value=None):
        plan_performance(segs, lang="Khmer")
    assert segs[0]["performance"]["style"] in {"angry", "shouting"}
    assert segs[0]["performance"]["intensity"] >= 0.6


def test_rust_and_python_plans_agree():
    segs = _scene() + [_line(3, "A", "Help me, please don't!", expression="fearful", expression_source="llm")]
    request = build_request(segs, lang="Khmer", names=["Dara"])
    rust, engine = plan_lines(request)
    with patch(_NO_RUST, return_value=None):
        python, py_engine = plan_lines(request)
    assert py_engine == "python"
    if engine != "rust":
        return
    for a, b in zip(rust, python):
        assert a["style"] == b["style"]
        assert abs(a["intensity"] - b["intensity"]) < 0.02
        assert abs(a["target_duration_sec"] - b["target_duration_sec"]) < 0.02


def test_editor_style_wins_over_auto_plan():
    segs = _scene()
    set_line_style(segs[1], "whispering", 0.4)
    with patch(_NO_RUST, return_value=None):
        plan_performance(segs, lang="Khmer")
    perf = segs[1]["performance"]
    assert perf["style"] == "whispering"
    assert perf["manual"] is True
    assert perf["confidence"]["emotion"] == 1.0
    assert abs(perf["intensity"] - 0.4) < 1e-6


def test_planner_keeps_translated_words():
    segs = _scene()
    before = [seg["translated_text"] for seg in segs]
    plan = plan_performance(segs, lang="Khmer")
    assert [seg["translated_text"] for seg in segs] == before
    assert [row["text"] for row in plan["lines"]] == before


def test_tempo_window_never_widens_sync_range():
    seg = {"performance": {"tempo_max": 1.1}}
    lo, hi = tempo_window(seg, 0.9, 1.8)
    assert lo == 0.9 and 1.45 <= hi <= 1.8
    assert tempo_window({}, 0.9, 1.8) == (0.9, 1.8)


# ── expression mapper ─────────────────────────────────────────────────────

def test_expression_mapper_per_provider():
    shout = {"style": "shouting", "intensity": 0.8}
    edge = map_delivery("km-KH-PisethNeural", shout)
    assert edge["provider"] == "edge"
    assert edge["speed"] > 1.0 and edge["volume_pct"] > 0 and edge["pitch_hz"] > 0

    whisper = {"style": "whispering", "intensity": 0.6}
    assert map_delivery("km-KH-SreymomNeural", whisper)["volume_pct"] < 0

    vox = map_delivery("voxcpm-test", {"style": "sad", "intensity": 0.5})
    assert vox["provider"] == "voxcpm" and "sad" in vox["style_prompt"]

    omni = map_delivery("omnivoice-test", whisper)
    assert omni["instruct_extra"] == "whisper"
    assert map_delivery("omnivoice-test", whisper, has_reference=True)["instruct_extra"] == ""
    assert map_delivery("omnivoice-test", shout)["instruct_extra"] == ""

    eleven = map_delivery("eleven:abc", shout)
    assert eleven["eleven"]["style"] > 0 and 0.2 <= eleven["eleven"]["stability"] <= 0.45

    sglang = map_delivery("sglang:voice", shout)
    assert sglang["applied"] == [] and sglang["speed"] == 1.0 and sglang["style_prompt"] == ""

    neutral = map_delivery("km-KH-PisethNeural", {"style": "neutral", "intensity": 0.9})
    assert neutral["applied"] == [] and neutral["speed"] == 1.0
    assert map_delivery("km-KH-PisethNeural", None)["applied"] == []


def test_edge_receives_unchanged_text_with_prosody():
    from claynext.models.tts_service import TTSEngine

    calls = []

    def fake_edge(text, voice, out, **kw):
        calls.append((text, kw))
        return out

    text = "ចេញពីផ្ទះខ្ញុំ!"
    with patch.object(TTSEngine, "synthesize_edge", side_effect=fake_edge):
        TTSEngine._synthesize_plain(
            text, "km-KH-PisethNeural", "/tmp/never.mp3",
            performance={"style": "shouting", "intensity": 1.0},
        )
    assert calls and calls[0][0] == text
    kw = calls[0][1]
    assert kw["speed"] > 1.0 and kw["pitch"] > 0 and kw["volume"] > 0


# ── prosody ───────────────────────────────────────────────────────────────

def test_prosody_fallback_reads_pitch_and_loudness():
    sr = 8000
    pcm = np.concatenate([_tone(200, 1.0, sr, 0.05), np.zeros(sr // 2, np.float32), _tone(200, 1.0, sr, 0.6)])
    spans = [
        {"index": 0, "start_sec": 0.0, "end_sec": 1.0},
        {"index": 1, "start_sec": 1.5, "end_sec": 2.5},
    ]
    feats = prosody_fallback(pcm.tobytes(), sr, spans)
    assert len(feats) == 2
    assert abs(feats[1]["pitch_hz"] - 200) < 15 and feats[1]["voiced_ratio"] > 0.9
    assert feats[1]["rms_db"] > feats[0]["rms_db"] + 15
    assert feats[0]["loudness_rel_db"] < -9 and feats[0]["voiced_ratio"] < 0.35

    from claynext.adapters.ai import get_ai_adapter

    rust = get_ai_adapter().analyze_prosody_pcm(pcm.tobytes(), sr, spans)
    if rust:
        for a, b in zip(rust, feats):
            assert abs(a["pitch_hz"] - b["pitch_hz"]) < 5
            assert abs(a["rms_db"] - b["rms_db"]) < 1.0
            assert abs(a["loudness_rel_db"] - b["loudness_rel_db"]) < 1.0


# ── registry ──────────────────────────────────────────────────────────────

def test_presentation_is_uncertain_without_evidence():
    presentation, conf = estimate_presentation([{"gender": "Male"}])
    assert presentation == "uncertain" and conf < 0.45
    presentation, conf = estimate_presentation([{"gender": "Female", "gender_manual": True}])
    assert presentation == "feminine_sounding" and conf == 1.0


def test_name_stays_unknown_without_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        reg = CharacterRegistry(Path(tmp) / "r.json")
        segs = [
            _line(0, "SPEAKER_00", "Hello there.", sid="SPEAKER_00"),
            _line(1, "Sreymom", "Who are you?", sid="SPEAKER_01", speaker_label_source="voice"),
            _line(2, "Dara", "Dara, come here!", sid="SPEAKER_02"),
        ]
        reg.reconcile(segs, lang="Khmer", base_voice="km-KH-PisethNeural")
        by_label = {c["label"]: c for c in reg.characters}
        assert by_label["SPEAKER_00"]["name"] == "Unknown"
        assert by_label["Sreymom"]["name"] == "Unknown"
        assert by_label["Dara"]["name"] == "Dara"
        assert any(e["source"] == "dialogue" for e in by_label["Dara"]["name_evidence"])
        assert all(c["voice_profile"]["presentation"] in {"masculine_sounding", "feminine_sounding", "uncertain"}
                   for c in reg.characters)


def test_registry_persists_and_editor_override_wins_on_rerun():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "registry.json"
        reg = CharacterRegistry(path)
        first = _scene()
        reg.reconcile(first, lang="Khmer", base_voice="km-KH-PisethNeural")
        cid = first[1]["character_id"]
        reg.set_override(cid, name="Mother", voice_id="km-KH-SreymomNeural", presentation="feminine_sounding")
        reg.save()

        again = CharacterRegistry.load(path)
        rerun = _scene()
        again.reconcile(rerun, lang="Khmer", base_voice="km-KH-PisethNeural")
        assert rerun[1]["character_id"] == cid
        assert rerun[1]["speaker"] == "Mother"
        assert rerun[1]["tts_voice_hint"] == "km-KH-SreymomNeural"
        assert rerun[1]["gender"] == "Female"
        assert rerun[0]["character_id"] == first[0]["character_id"] == rerun[2]["character_id"]
        profile = again.get(cid)
        assert profile["name"] == "Mother" and profile["confidence"]["character_identity"] == 1.0


def test_registry_keeps_auto_voice_stable_across_reruns():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "registry.json"
        first = _scene()
        first[1]["tts_voice_hint"] = "km-KH-SreymomNeural"
        reg = CharacterRegistry(path)
        reg.reconcile(first, lang="Khmer", base_voice="km-KH-PisethNeural")
        reg.save()

        rerun = _scene()
        CharacterRegistry.load(path).reconcile(rerun, lang="Khmer", base_voice="km-KH-PisethNeural")
        assert rerun[1]["tts_voice_hint"] == "km-KH-SreymomNeural"

        other_lang = _scene()
        CharacterRegistry.load(path).reconcile(other_lang, lang="English", base_voice="en-US-GuyNeural")
        assert other_lang[1]["tts_voice_hint"] == "km-KH-PisethNeural"


def test_stage_writes_plan_and_registry_without_audio():
    with tempfile.TemporaryDirectory() as tmp:
        shared = {}
        with patch("claynext.utils.config.STUDIO_CACHE", Path(tmp) / "cache"):
            segs = _scene()
            result = run_character_stage(
                segs,
                media_path=str(Path(tmp) / "movie.mp4"),
                audio_path=str(Path(tmp) / "missing.wav"),
                job_dir=Path(tmp) / "job",
                target_lang="Khmer",
                share=lambda key, value: shared.__setitem__(key, value),
            )
        plan = json.loads((Path(tmp) / "job" / PLAN_FILE).read_text(encoding="utf-8"))
        assert len(plan["lines"]) == 3 and plan["lines"][1]["style"] == "shouting"
        registry = json.loads((Path(tmp) / "job" / REGISTRY_FILE).read_text(encoding="utf-8"))
        assert len(registry["characters"]) == 2
        assert result["registry_path"].startswith(str(Path(tmp) / "cache"))
        assert set(shared) == {"performance", "characters"}
        assert all(seg.get("character_id") for seg in segs)


if __name__ == "__main__":
    import sys

    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:
                failed += 1
                print(f"FAIL {name}: {exc!r}")
    sys.exit(1 if failed else 0)
