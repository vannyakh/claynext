"""Tests for the versioned prompt skill registry and movie.dialogue_translation."""
from __future__ import annotations

import dataclasses
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from claynext.prompts import loader, renderer, versioning
from claynext.prompts.evaluation import TRANSLATION_CASES, run_suite
from claynext.prompts.registry import SkillRegistry, SkillResolutionError
from claynext.prompts.translation import SETTING_KEY, TranslationSkillSession

SKILL_ID = "movie.dialogue_translation"


def _skill(fallback: bool = False):
    return SkillRegistry(force_fallback=fallback).load().get(SKILL_ID, "^1.0")


def _units(text: str, lang: str = "") -> int:
    from claynext.models.translate_service import TranslateEngine

    return TranslateEngine._spoken_units_py(text, lang)


def _segments(n: int = 2) -> list[dict]:
    texts = ["Mom, I'm home.", "Where were you?", "Out.", "Out where?"]
    return [
        {
            "id": i + 1,
            "text": texts[i % len(texts)],
            "speaker": "Dara" if i % 2 == 0 else "Srey",
            "gender": "Male" if i % 2 == 0 else "Female",
            "start_sec": float(i * 2),
            "end_sec": float(i * 2 + 1.5),
            "duration_sec": 1.5,
            "recommended_syllables": {"min": 2, "target": 4, "max": 8},
            "speed_tolerance": {"min_rate": 0.65, "max_rate": 1.85},
        }
        for i in range(n)
    ]


# ── Registry, manifest, versioning ──────────────────────────────────────

def test_manifest_matches_milestone_contract():
    skill = _skill()
    m = skill.manifest
    assert m.id == SKILL_ID and m.version == "1.0.0"
    assert m.name == "Cinematic Dialogue Translator"
    assert m.model_capability == "text_generation"
    assert list(m.inputs) == [
        "source_language", "target_language", "dialogue",
        "scene_context", "character_profile", "glossary",
    ]
    assert m.output_schema == "translation"
    assert skill.settings["temperature"] == 0.2
    assert skill.settings["max_output_tokens"] == 2048
    schema = loader.load_schema(m.input_schema)
    assert set(schema["properties"]) == set(m.inputs)


def test_registry_catalog_and_lock():
    reg = SkillRegistry().load()
    assert SKILL_ID in reg.ids()
    row = next(r for r in reg.catalog() if r["id"] == SKILL_ID)
    assert row["fingerprint"].startswith("sha256:")
    assert row["lock"] == "locked", "prompt files changed: bump the skill version and re-pin versions.lock.json"


def test_semver_specs():
    assert versioning.matches("1.0.0", "^1.0")
    assert versioning.matches("1.4.2", "^1")
    assert not versioning.matches("2.0.0", "^1.0")
    assert versioning.matches("1.2.9", "~1.2")
    assert not versioning.matches("1.3.0", "~1.2")
    assert versioning.matches("1.5.0", ">=1.0.0,<2")
    assert not versioning.matches("1.0.0-rc1", "")
    assert versioning.best_match(["1.0.0", "1.2.0", "2.0.0"], "^1") == "1.2.0"
    assert versioning.best_match(["1.0.0"], "^2") is None


def test_resolve_dependencies_and_capabilities():
    reg = SkillRegistry().load()
    base = reg.get(SKILL_ID).manifest
    reg.register(dataclasses.replace(
        base, id="movie.quality_review", version="0.1.0",
        requires=({"id": SKILL_ID, "version": "^1.0"},),
    ))
    order = [s.id for s in reg.resolve("movie.quality_review", capabilities={"text_generation"})]
    assert order == [SKILL_ID, "movie.quality_review"]

    reg.register(dataclasses.replace(base, id="x.missing", version="1.0.0", requires=({"id": "nope", "version": ""},)))
    try:
        reg.resolve("x.missing")
        raise AssertionError("missing dependency should fail")
    except SkillResolutionError as exc:
        assert "nope" in str(exc)

    reg.register(dataclasses.replace(base, id="x.a", version="1.0.0", requires=({"id": "x.b", "version": ""},)))
    reg.register(dataclasses.replace(base, id="x.b", version="1.0.0", requires=({"id": "x.a", "version": ""},)))
    try:
        reg.resolve("x.a")
        raise AssertionError("cycle should fail")
    except SkillResolutionError as exc:
        assert "cycle" in str(exc)

    try:
        reg.resolve(SKILL_ID, capabilities={"speech"})
        raise AssertionError("capability mismatch should fail")
    except SkillResolutionError as exc:
        assert "text_generation" in str(exc)


def test_backend_support():
    skill = _skill()
    for backend in ("gemini", "ollama", "sglang-omni", "openai", "deepseek"):
        assert skill.supports_backend(backend), backend
    for backend in ("nllb", "google"):
        assert not skill.supports_backend(backend), backend


# ── Loader / renderer / validator fallbacks ─────────────────────────────

def test_yaml_fallback_matches_pyyaml():
    files = list(loader.LANGUAGES_DIR.glob("*.yaml")) + list(loader.SKILLS_DIR.glob("*/skill.yaml"))
    assert len(files) >= 3
    for path in files:
        assert loader.load_yaml(path) == loader.load_yaml(path, force_fallback=True), path.name


def test_language_profiles_and_glossary():
    km = loader.load_language("Khmer")
    assert km and km["id"] == "khmer" and km["spoken_unit"] == "syllable"
    assert loader.load_language("km")["id"] == "khmer"
    assert loader.load_language("Khmer (ភាសាខ្មែរ)")["id"] == "khmer"
    assert any(g["source"] == "Mom" and g["target"] == "ម៉ាក់" for g in km["glossary"])
    en = loader.load_language("English")
    assert en and en["glossary"] and en["instructions"]
    assert loader.load_language("Vietnamese") is None


def test_renderer_fallback_matches_jinja_for_every_case():
    jinja, mini = _skill(False), _skill(True)
    for case in loader.load_jsonl(TRANSLATION_CASES):
        assert jinja.render(case["inputs"]).text == mini.render(case["inputs"]).text, case["id"]


def test_renderer_rejects_undefined_and_unsupported():
    for fallback in (False, True):
        try:
            renderer.render_template("{{ missing }}", {}, force_fallback=fallback)
            raise AssertionError("undefined should fail")
        except renderer.RenderError:
            pass
    try:
        renderer.render_template("{{ x | upper }}", {"x": "a"}, force_fallback=True)
        raise AssertionError("unsupported filter should fail")
    except renderer.RenderError:
        pass


def test_render_rejects_invalid_inputs():
    skill = _skill()
    try:
        skill.render({"source_language": "English", "target_language": "Khmer", "dialogue": []})
        raise AssertionError("empty dialogue should fail")
    except renderer.RenderError as exc:
        assert "dialogue" in str(exc)


def test_validators_agree_on_every_case():
    full, bare = _skill(False), _skill(True)
    for case in loader.load_jsonl(TRANSLATION_CASES):
        a = full.validate_output(case["output"], case["inputs"])
        b = bare.validate_output(case["output"], case["inputs"])
        assert a.ok == b.ok, (case["id"], a.errors, b.errors)


# ── Evaluations ─────────────────────────────────────────────────────────

def test_translation_eval_suite_passes():
    for fallback in (False, True):
        report = run_suite(registry=SkillRegistry(force_fallback=fallback), count_units=_units)
        assert report["total"] >= 15
        assert report["failed"] == [], [r for r in report["results"] if not r["passed"]]


# ── Session ─────────────────────────────────────────────────────────────

def test_session_inputs_keep_quota_and_filter_glossary():
    segs = _segments(4)
    session = TranslationSkillSession(
        _skill(), segments=segs, source_lang="English", target_lang="Khmer",
        glossary=[{"source": "home", "target": "ផ្ទះ"}],
    )
    from claynext.models.translate_service import TranslateEngine

    inputs = session.build_inputs(TranslateEngine._payload_for(segs[2:], "Khmer"))
    assert inputs["dialogue"][0]["recommended_syllables"] == {"min": 2, "target": 4, "max": 8}
    assert inputs["scene_context"] == "Dara: Mom, I'm home.\nSrey: Where were you?"
    assert set(inputs["character_profile"]) == {"Dara", "Srey"}
    assert inputs["glossary"] == []
    first = session.build_inputs(TranslateEngine._payload_for(segs[:1], "Khmer"))
    sources = {g["source"] for g in first["glossary"]}
    assert sources == {"Mom", "home"}


def test_session_chunks_by_manifest_limit():
    session = TranslationSkillSession(_skill(), segments=_segments(20), source_lang="English", target_lang="Khmer")
    assert [len(c) for c in session.chunks(_segments(20))] == [16, 4]


# ── Translate path integration ──────────────────────────────────────────

def _translate(segs, *, prompt_skill, run_dir="", gemini=None, dub_prompt="LEGACY PROMPT"):
    from claynext.models.movie_translate import MovieTranslateOptions, translate_movie_dialogue

    with patch(
        "claynext.models.movie_translate.resolve_movie_engine_chain",
        return_value=[("Gemini", "gemini", "")],
    ), patch(
        "claynext.models.translate_service.TranslateEngine._ensure_timing",
    ), patch(
        "claynext.models.translate_service.TranslateEngine._tighten_to_slot",
    ), patch(
        "claynext.models.translate_service.TranslateEngine._dub_prompt",
        return_value=dub_prompt,
    ) as legacy_prompt, patch(
        "claynext.models.translate_service.TranslateEngine._gemini_batch",
        side_effect=gemini,
    ) as batch, patch(
        "claynext.models.llm_keys.ApiKeyPool.ready_count", return_value=1,
    ):
        out = translate_movie_dialogue(
            segs, "Khmer", source_lang="English",
            options=MovieTranslateOptions(translator="gemini", prompt_skill=prompt_skill, skill_run_dir=run_dir),
        )
    return out, legacy_prompt, batch


def test_skill_off_uses_legacy_prompt_unchanged():
    def gemini(prompt, progress=None, **kw):
        assert prompt == "LEGACY PROMPT" and not kw
        return [{"id": 1, "khmer_text": "ម៉ាក់ កូនមកវិញហើយ"}, {"id": 2, "khmer_text": "ឯងទៅណាមក?"}]

    from claynext.models.translate_service import TranslateEngine

    with patch.object(TranslateEngine, "_translate_llm", wraps=TranslateEngine._translate_llm) as llm:
        out, legacy_prompt, _batch = _translate(_segments(2), prompt_skill=False, gemini=gemini)
    assert "skill" not in llm.call_args.kwargs
    assert legacy_prompt.called
    assert [r["translated_text"] for r in out] == ["ម៉ាក់ កូនមកវិញហើយ", "ឯងទៅណាមក?"]


def test_skill_on_validates_and_persists_run():
    seen = {}

    def gemini(prompt, progress=None, *, generation=None):
        seen["prompt"], seen["generation"] = prompt, generation
        return [{"id": 1, "translation": "ម៉ាក់ កូនមកវិញហើយ", "confidence": 0.9},
                {"id": 2, "translation": "ឯងទៅណាមក?", "confidence": 0.5, "notes": "tone unclear"}]

    with tempfile.TemporaryDirectory() as tmp:
        out, legacy_prompt, _batch = _translate(_segments(2), prompt_skill=True, run_dir=tmp, gemini=gemini)
        assert not legacy_prompt.called
        assert "NO ADDITIONS OR OMISSIONS" in seen["prompt"] and "- Mom → ម៉ាក់" in seen["prompt"]
        assert seen["generation"] == {"temperature": 0.2, "maxOutputTokens": 2048}
        assert [r["translated_text"] for r in out] == ["ម៉ាក់ កូនមកវិញហើយ", "ឯងទៅណាមក?"]
        assert out[0]["speaker"] == "Dara" and out[0]["recommended_syllables"]["max"] == 8
        log = json.loads((Path(tmp) / "skill_runs" / f"{SKILL_ID}.json").read_text(encoding="utf-8"))
    run = log["runs"][-1]
    assert run["skill_id"] == SKILL_ID and run["version"] == "1.0.0" and run["lock"] == "locked"
    assert run["settings"]["temperature"] == 0.2
    assert run["summary"] == {"calls": 1, "validated": 1, "fallbacks": 0, "lines_from_skill": 2, "lines_from_legacy": 0}
    call = run["calls"][0]
    assert call["backend"] == "gemini" and call["validation"]["ok"] is True
    assert call["settings_applied"] == {"temperature": 0.2, "maxOutputTokens": 2048}
    assert run["review"] == [{"id": "2", "confidence": 0.5, "notes": "tone unclear"}]


def test_skill_invalid_reply_falls_back_to_legacy_prompt():
    prompts = []

    def gemini(prompt, progress=None, **kw):
        prompts.append(prompt)
        if kw:
            return [{"id": 1, "translation": "ម៉ាក់ កូនមកវិញហើយ"}]  # omits id 2
        return [{"id": 1, "khmer_text": "ម៉ាក់"}, {"id": 2, "khmer_text": "ឯងទៅណា?"}]

    with tempfile.TemporaryDirectory() as tmp:
        out, legacy_prompt, _batch = _translate(_segments(2), prompt_skill=True, run_dir=tmp, gemini=gemini)
        log = json.loads((Path(tmp) / "skill_runs" / f"{SKILL_ID}.json").read_text(encoding="utf-8"))
    assert legacy_prompt.called and prompts[-1] == "LEGACY PROMPT"
    assert [r["translated_text"] for r in out] == ["ម៉ាក់", "ឯងទៅណា?"]
    run = log["runs"][-1]
    assert run["summary"]["fallbacks"] == 1 and run["summary"]["lines_from_legacy"] == 2
    assert "omitted id(s): 2" in run["calls"][0]["validation"]["errors"][0]


def test_skill_rate_limit_is_not_retried_with_legacy():
    from claynext.models.llm_keys import RateLimitError
    from claynext.models.translate_service import TranslateEngine

    session = TranslationSkillSession(_skill(), segments=_segments(2), source_lang="English", target_lang="Khmer")
    calls = []
    with patch.object(TranslateEngine, "_gemini_batch", side_effect=RateLimitError("busy")):
        try:
            TranslateEngine._skill_batch(
                _segments(2), "Khmer", "gemini", "", None,
                source_lang="English", skill=session, legacy=lambda chunk: calls.append(chunk) or {},
            )
            raise AssertionError("rate limit should propagate")
        except RateLimitError:
            pass
    assert calls == []
    assert session.report()["calls"][0]["error"] == "busy"


def test_gemini_and_ollama_bodies_unchanged_without_settings():
    from claynext.models.translate_service import TranslateEngine

    bodies = []

    class _Resp:
        status = 200

        def __init__(self, payload):
            self._payload = payload

        def read(self):
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    gemini_reply = {"candidates": [{"content": {"parts": [{"text": "[]"}]}}]}

    def urlopen(req, timeout=0):
        bodies.append(json.loads(req.data.decode("utf-8")))
        if "generateContent" in req.full_url:
            return _Resp(gemini_reply)
        return _Resp({"response": "[]"})

    with patch("claynext.models.translate_service.urllib.request.urlopen", side_effect=urlopen), patch(
        "claynext.models.translate_service.get_key_pool",
    ) as pool, patch.object(TranslateEngine, "_pace_gemini"), patch(
        "claynext.models.translate_service.note_llm_usage",
    ):
        pool.return_value.call_with_rotation.side_effect = lambda _p, fn, **kw: fn("k")
        TranslateEngine._gemini_generate("m", "P")
        TranslateEngine._gemini_generate("m", "P", generation={"temperature": 0.2, "maxOutputTokens": 2048})
        TranslateEngine._ollama_generate("P", "qwen3:8b")
        TranslateEngine._ollama_generate("P", "qwen3:8b", options={"temperature": 0.2, "num_predict": 2048})
    assert bodies[0]["generationConfig"] == {"temperature": 0.4, "responseMimeType": "application/json"}
    assert bodies[1]["generationConfig"] == {
        "temperature": 0.2, "responseMimeType": "application/json", "maxOutputTokens": 2048,
    }
    assert bodies[2] == {"model": "qwen3:8b", "prompt": "P", "format": "json", "stream": False}
    assert bodies[3]["options"] == {"temperature": 0.2, "num_predict": 2048}


def test_setting_defaults_off_and_gates_session():
    from claynext.models.features import FEATURE_SETTING_KEYS
    from claynext.models.movie_translate import MovieTranslateOptions, _open_translation_skill
    from claynext.utils.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG[SETTING_KEY] == "0"
    assert SETTING_KEY in FEATURE_SETTING_KEYS
    segs = _segments(1)
    with patch("claynext.models.features.get_feature_setting", return_value="0"):
        assert _open_translation_skill(MovieTranslateOptions(), segs, "English", "Khmer") is None
    with patch("claynext.models.features.get_feature_setting", return_value="1"):
        session = _open_translation_skill(MovieTranslateOptions(), segs, "English", "Khmer")
        assert isinstance(session, TranslationSkillSession)
        assert session.path.parent.name == "runs"
    assert _open_translation_skill(MovieTranslateOptions(prompt_skill=False), segs, "English", "Khmer") is None


if __name__ == "__main__":
    import sys
    import traceback

    failed = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
