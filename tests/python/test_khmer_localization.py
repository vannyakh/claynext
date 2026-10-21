"""Tests for the Character-Aware Khmer Dialogue Localization engine (milestone 1). No live LLM calls."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from claynext.models.khmer_localization import evaluator, lexicon
from claynext.models.khmer_localization.dialect import DialectEntry, RegionalDialectAdapter
from claynext.models.khmer_localization.lexicon import find_forms, load_inventory
from claynext.models.khmer_localization.postcheck import check_line
from claynext.models.khmer_localization.pronouns import Party, PronounContext, PronounResolver
from claynext.models.khmer_localization.relationships import Relationship, RelationshipGraph, analyze_line
from claynext.models.khmer_localization.slang import select_levels, source_intensity
from claynext.models.khmer_localization.speech_profile import (
    LocalizationConfig,
    LocalizationStore,
    SpeechProfile,
)
from claynext.models.khmer_localization.tts_normalizer import normalize_for_tts, tts_field
from claynext.prompts import loader
from claynext.prompts.registry import SkillRegistry

SKILL_ID = "movie.khmer_natural_dialogue"
ROUGH = {"អញ", "ឯង", "ហ្អែង"}


def _resolve(relation: str = "", *, sp=("male", "adult"), ls=("female", "adult"), profile=None, config=None, **ctx):
    speaker = Party("a", gender=sp[0], age_group=sp[1], profile=profile)
    listener = Party("b", gender=ls[0], age_group=ls[1]) if ls else None
    return PronounResolver(config=config).resolve(PronounContext(speaker=speaker, listener=listener, relation=relation, **ctx))


# ── Dictionaries ────────────────────────────────────────────────────────

def test_dictionaries_parse_the_same_with_the_fallback_parser():
    files = sorted(lexicon.DICTIONARY_DIR.glob("*.yaml")) + [loader.SKILLS_DIR / "khmer_natural_dialogue" / "skill.yaml"]
    assert len(files) == 5
    for path in files:
        assert loader.load_yaml(path) == loader.load_yaml(path, force_fallback=True), path.name


def test_dictionaries_ship_unreviewed_and_regional_unverified():
    for path in lexicon.DICTIONARY_DIR.glob("*.yaml"):
        data = loader.load_yaml(path)
        assert data["version"] and data["review"]["status"] == "pending_native_review", path.name
        assert data["review"]["reviewer"] is None
    regional = loader.load_yaml(lexicon.REGIONAL_FILE)
    assert all(not e.get("verified") and not e.get("evidence") for e in regional["entries"])
    prof = loader.load_yaml(lexicon.PROFANITY_FILE)
    assert all(t["verified"] is False for t in prof["khmer_terms"])


def test_every_rule_form_is_in_the_inventory():
    inv = load_inventory()
    for name, rule in inv.relations.items():
        assert inv.relation(rule["inverse"])[1] is not None, name
        for slot in ("first", "second", "first_alt", "second_alt"):
            value = rule.get(slot) or {}
            forms = value if isinstance(value, list) else [f for v in value.values() for f in v]
            for form in forms:
                assert form in inv.forms, (name, slot, form)
        for form in rule.get("forbidden") or []:
            assert form in inv.forms, (name, form)


# ── Detection in unsegmented Khmer ──────────────────────────────────────

def test_detection_skips_compounds_and_glued_clusters():
    inv = load_inventory()
    for text, form in (("ខ្ញុំធ្វើខ្លួនឯង", "ឯង"), ("ទុកកូនម្នាក់ឯងទៅ", "ឯង"), ("សូមបង្ហាញ", "បង"),
                       ("អញ្ជើញមក", "អញ"), ("អញ្ចឹងទេ", "អញ"), ("បង់លុយ", "បង"), ("មើលអ្នកណាហ្នឹង", "អ្នក"),
                       ("ដូចកូនក្មេង", "កូន"), ("ផ្សារនៅឯណា", "ឯង"), ("បងប្អូន", "បង")):
        found = {m.form for m in inv.detect(text)}
        assert form not in found, (text, found)
    assert {m.form for m in inv.detect("ទុកកូនម្នាក់ឯងទៅ")} == {"កូន"}
    assert [m.form for m in inv.detect("ប្អូនស្រី")] == ["ប្អូន"]
    assert [m.form for m in inv.detect("ខ្ញុំព្រះករុណា។")] == ["ខ្ញុំព្រះករុណា"]


def test_detection_before_khmer_punctuation():
    inv = load_inventory()
    assert [m.form for m in inv.detect("អញនឹងសម្លាប់ឯង។")] == ["អញ", "ឯង"]
    assert [m.form for m in inv.detect("អរគុណបង!")] == ["បង"]


def test_short_kin_terms_need_word_boundaries():
    inv = load_inventory()
    assert "តា" not in {m.form for m in inv.detect("តាមខ្ញុំមក")}
    assert "ពូ" not in {m.form for m in inv.detect("គាត់ពូកែណាស់")}
    assert "តា" in {m.form for m in inv.detect("តា ចាំចៅលីឲ្យ។")}


def test_nyom_spelling_variant_does_not_match_inside_khnhom():
    assert find_forms("ខ្ញុំឃ្លាន", ["ញុំ"]) == []
    inv = load_inventory()
    assert [m.form for m in inv.detect("ញុំឃ្លាន")] == ["ញ៉ុំ"]


# ── Pronoun Resolver ────────────────────────────────────────────────────

def test_core_relationship_rules():
    d = _resolve("child_to_parent", sp=("male", "child"), ls=("female", "adult"))
    assert (d.first_person, d.second_person) == ("កូន", "ម៉ាក់") and not d.needs_review
    assert {"អញ", "ឯង"} <= set(d.forbidden)
    d = _resolve("romantic")
    assert (d.first_person, d.second_person) == ("បង", "អូន")
    d = _resolve("romantic", sp=("female", "adult"), ls=("male", "adult"))
    assert (d.first_person, d.second_person) == ("អូន", "បង")
    d = _resolve("younger_to_older_sibling", sp=("female", "teen"))
    assert (d.first_person, d.second_person) == ("អូន", "បង")
    d = _resolve("lay_to_monk", ls=("male", "elder"))
    assert (d.first_person, d.second_person) == ("ខ្ញុំព្រះករុណា", "ព្រះអង្គ") and "អ្នក" in d.forbidden


def test_inverse_relations_and_alias():
    d = _resolve("spouses")
    assert d.relation == "romantic"
    graph = RelationshipGraph()
    graph.set(Relationship("kid", "mom", "child_to_parent"))
    assert graph.get("mom", "kid").relation == "parent_to_child"


def test_nyom_is_never_a_blanket_swap():
    inv = load_inventory()
    for relation in inv.relations:
        for sp in (("male", "child"), ("female", "teen"), ("female", "adult")):
            d = _resolve(relation, sp=sp, register="casual")
            assert d.first_person != "ញ៉ុំ", relation
    habit = SpeechProfile(character_id="a", habitual_first_person=["ញ៉ុំ"], confidence=0.8)
    d = _resolve("younger_to_older_sibling", sp=("female", "teen"), profile=habit, register="casual")
    assert d.first_person == "ញ៉ុំ" and "អូន" in d.first_alternatives
    d = _resolve("strangers", sp=("female", "adult"), profile=habit, register="formal")
    assert d.first_person != "ញ៉ុំ" and d.needs_review
    d = _resolve("friends", profile=habit)
    assert d.first_person == "ខ្ញុំ"


def test_anger_alone_never_selects_rough_forms():
    inv = load_inventory()
    for relation, rule in inv.relations.items():
        if rule.get("allow_rough"):
            continue
        d = _resolve(relation, emotion="angry", sp=("male", "adult"), ls=("male", "adult"))
        assert d.first_person not in ROUGH and d.second_person not in ROUGH, relation


def test_hostility_evidence_unlocks_rough_forms_for_enemies():
    calm = _resolve("enemies", hostility=0)
    assert (calm.first_person, calm.second_person) == ("ខ្ញុំ", "អ្នក")
    hot = _resolve("enemies", hostility=2, emotion="angry")
    assert (hot.first_person, hot.second_person) == ("អញ", "ឯង") and hot.allow_rough and not hot.needs_review


def test_rough_habit_toward_stranger_is_reviewed_not_applied():
    prof = SpeechProfile(character_id="a", habitual_second_person=["ឯង"], register="street", slang_level=2)
    d = _resolve("strangers", profile=prof, register="street")
    assert d.second_person == "អ្នក" and d.needs_review
    assert any("ឯង" in r for r in d.review_reasons)


def test_unknown_relationship_and_listener_need_review():
    d = _resolve("", sp=("female", "adult"), ls=("male", "child"))
    assert d.source == "age_fallback" and d.second_person in ("អូន", "ប្អូន") and d.needs_review
    d = _resolve("friends", ls=None)
    assert d.needs_review and "listener unknown" in d.review_reasons
    d = _resolve("child_to_parent", relation_source="heuristic", relation_confidence=0.5)
    assert d.needs_review


def test_formal_register_and_register_lock():
    d = _resolve("boss_to_employee", ls=("male", "adult"), register="formal")
    assert d.second_person == "លោក"
    d = _resolve("master_to_servant", ls=("female", "adult"), scene_formality="formal")
    assert d.second_person == "អ្នក" and "ឯង" in d.second_alternatives
    d = _resolve("child_to_parent", sp=("male", "adult"), ls=("male", "adult"), register="formal")
    assert d.second_person == "ប៉ា"


def test_override_precedence_scene_over_character_over_rule():
    prof = SpeechProfile(character_id="a", pronoun_overrides=[{"listener": "b", "first": "ខ្ញុំ", "second": "ឯង"}])
    d = _resolve("friends", profile=prof)
    assert (d.first_person, d.second_person, d.source) == ("ខ្ញុំ", "ឯង", "character_override") and not d.needs_review
    cfg = LocalizationConfig(scene_overrides=[{"scene_id": "s1", "speaker": "a", "listener": "b", "first": "យើង", "second": "លោក"}])
    d = _resolve("friends", profile=prof, config=cfg, scene_id="s1")
    assert (d.first_person, d.second_person, d.source) == ("យើង", "លោក", "scene_override")
    assert d.confidence == 1.0 and "ឯង" in d.second_alternatives


# ── Speech profiles and store ───────────────────────────────────────────

def test_profile_validation():
    for bad in ({"slang_level": 5}, {"register": "royal"}, {"region": "battambang"}, {"overrides": {"voice": "x"}}):
        try:
            SpeechProfile.from_dict({"character_id": "a", **bad})
            raise AssertionError(f"should reject {bad}")
        except ValueError:
            pass
    p = SpeechProfile.from_dict({"character_id": "a", "gender": "Female", "age_group": "25-35"})
    assert (p.gender, p.age_group, p.region) == ("female", "adult", None)


def test_override_wins_and_project_cap_still_applies():
    store = LocalizationStore(project_key="p")
    store.config = LocalizationConfig(profanity_cap=1, slang_cap=2)
    store.upsert(SpeechProfile(character_id="c1", register="neutral", profanity_level=0, slang_level=1))
    store.set_override("c1", register="street", profanity_level=3, slang_level=3, region="battambang")
    eff = store.effective("c1")
    assert eff.register == "street" and eff.profanity_level == 1 and eff.slang_level == 2
    assert eff.region is None
    store.config.allow_regional = True
    eff = store.effective("c1")
    assert eff.region == "battambang" and eff.region_source == "editor"
    store.upsert(SpeechProfile(character_id="c1", register="formal"))
    assert store.effective("c1").register == "street"


def test_store_roundtrip_and_seed_from_character_registry():
    row = {
        "character_id": "CHAR_001", "name": "Dara", "role": "son",
        "voice_profile": {"presentation": "masculine_sounding", "age_range_estimate": "8-12"},
        "overrides": {},
    }
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalizationStore.for_project("proj", tmp)
        assert store.seed_from_characters([row, {"name": "no id"}]) == ["CHAR_001"]
        store.set_override("CHAR_001", habitual_first_person=["ញ៉ុំ"])
        store.relationships.set(Relationship("CHAR_001", "CHAR_002", "child_to_parent"))
        path = store.save()
        assert path == Path(tmp) / "khmer_localization.json"
        again = LocalizationStore.load(path)
    prof = again.profile("CHAR_001")
    assert (prof.name, prof.gender, prof.age_group, prof.social_role) == ("Dara", "male", "child", "son")
    assert again.effective("CHAR_001").habitual_first_person == ["ញ៉ុំ"]
    assert again.relationships.get("CHAR_002", "CHAR_001").relation == "parent_to_child"


def test_heuristic_relationship_never_replaces_a_trusted_one():
    graph = RelationshipGraph()
    graph.set(Relationship("a", "b", "friends_close"))
    hint = analyze_line("Mom, I'm home.", "a", "b")
    assert hint.relation == "child_to_parent" and hint.source == "heuristic" and hint.confidence < 1
    graph.set(hint)
    assert graph.get("a", "b").relation == "friends_close"
    assert analyze_line("See you tomorrow.", "a", "b") is None


# ── Slang / profanity, dialect, TTS ─────────────────────────────────────

def test_profanity_never_exceeds_source_or_caps():
    hot = SpeechProfile(character_id="a", profanity_level=3, slang_level=3)
    cfg = LocalizationConfig(profanity_cap=3, slang_cap=3)
    assert select_levels("I am so angry at you!", hot, cfg).allowed_profanity == 0
    assert source_intensity("Get out, you bastard!")[0] == 2
    assert select_levels("Get out, you bastard!", hot, cfg).allowed_profanity == 2
    mild = SpeechProfile(character_id="a", profanity_level=1)
    assert select_levels("Get out, you bastard!", mild, cfg).allowed_profanity == 1
    assert select_levels("What the fuck!", hot, LocalizationConfig(profanity_cap=0)).allowed_profanity == 0
    assert source_intensity("Hello there")[0] == 0 and source_intensity("shell")[0] == 0


def test_dialect_adapter_needs_verified_evidence_and_trusted_region():
    entries = [
        DialectEntry(region="r1", standard="ប៉ុន្មាន", regional="X", verified=False),
        DialectEntry(region="r1", standard="ឆ្ងាញ់", regional="Y", verified=True,
                     evidence=[{"source": "reviewer", "example": "..."}]),
    ]
    adapter = RegionalDialectAdapter(entries)
    text = "ឆ្ងាញ់ ប៉ុន្មាន"
    editor = SpeechProfile(character_id="a", region="r1", region_source="editor")
    res = adapter.apply(text, editor, LocalizationConfig(allow_regional=True))
    assert res.text == "Y ប៉ុន្មាន" and len(res.applied) == 1 and res.suggestions[0]["verified"] is False
    res = adapter.apply(text, editor, LocalizationConfig(allow_regional=False))
    assert res.text == text and not res.applied
    guessed = SpeechProfile(character_id="a", region="r1", region_source="evidence")
    res = adapter.apply(text, guessed, LocalizationConfig(allow_regional=True))
    assert res.text == text and not res.applied
    assert RegionalDialectAdapter().apply(text, editor, LocalizationConfig(allow_regional=True)).text == text


def test_tts_normalizer_is_separate_and_conservative():
    line = "ចាំបងណា បងមកវិញឆាប់ៗ។"
    assert normalize_for_tts(line) == "ចាំបងណា បងមកវិញឆាប់ឆាប់។"
    assert line == "ចាំបងណា បងមកវិញឆាប់ៗ។"
    assert normalize_for_tts("ឆ្នាំ ២០២៦ គ.ស.") == "ឆ្នាំ ២០២៦ គ្រិស្តសករាជ"
    assert tts_field("ខ្ញុំឃ្លានហើយ។") is None
    assert normalize_for_tts("ញុំឃ្លាន") == "ញុំឃ្លាន"
    assert normalize_for_tts("ញុំឃ្លាន", include_unverified=True) == "ញ៉ុំឃ្លាន"
    assert normalize_for_tts("ខ្ញុំឃ្លាន", include_unverified=True) == "ខ្ញុំឃ្លាន"
    assert normalize_for_tts("ខ្ញុំ\u200bទៅ") == "ខ្ញុំទៅ"


def test_postcheck_flags_without_rewriting():
    plan = _resolve("child_to_parent", sp=("male", "child")).plan()
    res = check_line("អញឃ្លានហើយ ម៉ាក់", plan, profanity_max=0)
    assert "forbidden_pronoun:អញ" in res.violations and not res.ok
    res = check_line("ម៉ាក់ កូនឃ្លានហើយ", plan, profanity_max=0)
    assert res.ok and res.detected == ["ម៉ាក់", "កូន"]
    res = check_line("ឈប់ទៅ អាឆ្កែ!", _resolve("enemies", hostility=2).plan(), profanity_max=1)
    assert any(v.startswith("profanity_above_limit") for v in res.violations)
    res = check_line("ញ៉ុំឃ្លាន", _resolve("younger_to_older_sibling").plan(), profanity_max=0)
    assert "habit_gated_form_unplanned:ញ៉ុំ" in res.warnings


# ── Dataset and evaluator ───────────────────────────────────────────────

def test_dataset_has_100_cases_all_pending_native_review():
    cases = evaluator.load_cases()
    assert len(cases) == 100
    assert len({c["id"] for c in cases}) == 100
    assert all(evaluator.validate_case(c) == [] for c in cases)
    assert all(c["review"] == {"status": "pending_native_review", "reviewer": None, "reviewed_at": None} for c in cases)
    cats = {c["category"] for c in cases}
    for must in ("child_to_parent", "younger_to_older_sibling", "romantic", "friends_close", "boss_to_employee",
                 "lay_to_monk", "strangers", "enemies_insult", "servant_to_master", "police", "comedy",
                 "anger_without_profanity", "affectionate_teasing", "nyom_habit", "unknown_relationship"):
        assert must in cats, must


def test_evaluator_suite_passes_with_both_parsers():
    for fallback in (False, True):
        lexicon.clear_cache()
        report = evaluator.run(force_fallback=fallback)
        assert report["evaluated"] == 100 and report["failed"] == [], [
            (r["id"], r["failures"]) for r in report["results"] if not r["passed"]
        ]
        assert report["by_review_status"] == {"pending_native_review": 100}
        assert "No case is native-speaker reviewed" in report["note"]
    lexicon.clear_cache()


def test_evaluator_reviewed_only_filter():
    report = evaluator.run(reviewed_only=True)
    assert report["evaluated"] == 0 and report["total_cases"] == 100
    cases = evaluator.load_cases()[:3]
    cases[0]["review"] = {"status": "reviewed", "reviewer": "tester", "reviewed_at": "2026-10-21"}
    cases[1]["review"] = {"status": "reviewed", "reviewer": None, "reviewed_at": None}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cases.jsonl"
        path.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), encoding="utf-8")
        report = evaluator.run(path, reviewed_only=True)
    assert report["evaluated"] == 2 and report["by_review_status"] == {"pending_native_review": 1, "reviewed": 2}
    assert report["failed"] == [cases[1]["id"]]


def test_evaluator_scores_model_outputs():
    report = evaluator.run(outputs={"kp-001": "ម៉ាក់ កូនឃ្លានបាយហើយ។", "kp-002": "ឯងឲ្យអញចេញទៅលេងបានទេ?"})
    assert report["outputs"]["failed"] == ["kp-002"]
    assert len(report["outputs"]["missing"]) == 98


# ── Skill registry and session ──────────────────────────────────────────

def _segments():
    return [
        {"id": 1, "text": "Mom, I'm home.", "speaker": "Dara", "gender": "Male", "duration_sec": 1.5,
         "recommended_syllables": {"min": 2, "target": 4, "max": 8}},
        {"id": 2, "text": "Where were you?", "speaker": "Mother", "gender": "Female", "expression": "angry",
         "duration_sec": 1.5, "recommended_syllables": {"min": 2, "target": 4, "max": 8}},
    ]


def _session(tmp: str, fallback: bool = False):
    from claynext.models.khmer_localization.skill import KhmerDialogueSession

    store = LocalizationStore.for_project("t", tmp)
    store.relationships.set(Relationship("Dara", "Mother", "child_to_parent"))
    skill = SkillRegistry(force_fallback=fallback).load().get(SKILL_ID, "^0.1")
    return KhmerDialogueSession(skill, segments=_segments(), source_lang="English", target_lang="Khmer",
                                run_dir=tmp, store=store)


def _reply(line2: str = "កូនទៅណាមក?"):
    return {"lines": [
        {"id": 1, "source_text": "Mom, I'm home.", "localized_text": "ម៉ាក់ កូនមកវិញហើយ។", "tts_text": None,
         "pronouns_used": {"first_person": ["កូន"], "second_person": ["ម៉ាក់"]}, "register": "neutral",
         "candidates": [{"text": "ម៉ាក់! កូនមកដល់ហើយ", "register": "neutral", "note": "more excited"}],
         "confidence": 0.9, "review_flags": []},
        {"id": 2, "source_text": "Where were you?", "localized_text": line2, "tts_text": None,
         "pronouns_used": {"first_person": [], "second_person": ["កូន"]}, "register": "neutral",
         "confidence": 0.8},
    ]}


def test_skill_registered_locked_and_renders_the_same_with_both_engines():
    reg = SkillRegistry().load()
    assert SKILL_ID in reg.ids()
    skill = reg.get(SKILL_ID, "^0.1")
    assert skill.version == "0.1.0" and skill.lock_status() == "locked"
    assert all(skill.supports_backend(b) for b in ("gemini", "ollama", "sglang-omni", "openai"))
    schema = loader.load_schema(skill.manifest.input_schema)
    assert set(schema["properties"]) == set(skill.manifest.inputs)
    from claynext.models.translate_service import TranslateEngine

    texts = []
    for fallback in (False, True):
        with tempfile.TemporaryDirectory() as tmp:
            s = _session(tmp, fallback)
            prompt, inputs = s.render(TranslateEngine._payload_for(_segments(), "Khmer"))
            texts.append(prompt.text)
    assert texts[0] == texts[1]
    plan = inputs["dialogue"][0]["pronoun_plan"]
    assert (plan["first_person"], plan["second_person"]) == ("កូន", "ម៉ាក់")
    assert inputs["dialogue"][1]["pronoun_plan"]["first_person"] == "ម៉ាក់"
    assert inputs["dialogue"][1]["style"]["profanity_max"] == 0
    assert "Never swap ខ្ញុំ for ញ៉ុំ" in texts[0]


def test_session_check_keeps_three_fields_and_flags_violations():
    from claynext.models.translate_service import TranslateEngine

    with tempfile.TemporaryDirectory() as tmp:
        s = _session(tmp)
        _prompt, inputs = s.render(TranslateEngine._payload_for(_segments(), "Khmer"))
        res = s.check(_reply("ហ្អែងទៅណាមក?"), inputs)
        assert res.ok
        assert s.rows(res) == [{"id": 1, "translated_text": "ម៉ាក់ កូនមកវិញហើយ។"},
                               {"id": 2, "translated_text": "ហ្អែងទៅណាមក?"}]
        lines = s.lines()
        assert lines["1"]["source_text"] == "Mom, I'm home." and lines["1"]["tts_text"] is None
        assert lines["1"]["candidates"][0]["note"] == "more excited" and not lines["1"]["violations"]
        assert lines["2"]["localized_text"] == "ហ្អែងទៅណាមក?"
        assert "forbidden_pronoun:ហ្អែង" in lines["2"]["violations"] and lines["2"]["needs_review"]
        assert any("forbidden_pronoun" in w for w in res.warnings)
        s.save()
        log = json.loads((Path(tmp) / "skill_runs" / f"{SKILL_ID}.json").read_text(encoding="utf-8"))
        assert (Path(tmp) / "khmer_localization.json").is_file()
    kl = log["runs"][-1]["khmer_localization"]
    assert kl["summary"]["violations"] == 1 and kl["lines"][1]["pronoun_decision"]["relation"] == "parent_to_child"


def test_session_invalid_reply_falls_back_through_translate_engine():
    from claynext.models.translate_service import TranslateEngine

    bad = {"lines": [_reply()["lines"][0]]}
    with tempfile.TemporaryDirectory() as tmp:
        s = _session(tmp)
        with patch.object(TranslateEngine, "_gemini_batch", return_value=bad):
            rows = TranslateEngine._skill_batch(
                _segments(), "Khmer", "gemini", "", None, source_lang="English", skill=s,
                legacy=lambda chunk: {c["id"]: {"id": c["id"], "translated_text": "LEGACY"} for c in chunk},
            )
    assert [r["translated_text"] for r in rows.values()] == ["LEGACY", "LEGACY"]
    assert "omitted id(s): 2" in s.report()["calls"][0]["validation"]["errors"][0]


def test_session_valid_reply_through_translate_engine():
    from claynext.models.translate_service import TranslateEngine

    with tempfile.TemporaryDirectory() as tmp:
        s = _session(tmp)
        with patch.object(TranslateEngine, "_gemini_batch", return_value=_reply()) as call:
            rows = TranslateEngine._skill_batch(
                _segments(), "Khmer", "gemini", "", None, source_lang="English", skill=s,
                legacy=lambda chunk: {},
            )
    assert [rows[i]["translated_text"] for i in (1, 2)] == ["ម៉ាក់ កូនមកវិញហើយ។", "កូនទៅណាមក?"]
    assert call.call_args.kwargs["generation"] == {"temperature": 0.3, "maxOutputTokens": 4096}


def test_setting_defaults_off_and_only_for_khmer():
    from claynext.models.features import FEATURE_SETTING_KEYS
    from claynext.models.khmer_localization.skill import SETTING_KEY, KhmerDialogueSession, session_if_enabled
    from claynext.models.movie_translate import MovieTranslateOptions, _open_translation_skill
    from claynext.prompts.translation import TranslationSkillSession
    from claynext.utils.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG[SETTING_KEY] == "0" and SETTING_KEY in FEATURE_SETTING_KEYS
    segs = _segments()
    with patch("claynext.models.features.get_feature_setting", return_value="0"):
        assert session_if_enabled(segs, source_lang="English", target_lang="Khmer") is None
        assert _open_translation_skill(MovieTranslateOptions(), segs, "English", "Khmer") is None
    with patch("claynext.models.features.get_feature_setting", return_value="1"):
        assert session_if_enabled(segs, source_lang="English", target_lang="Vietnamese") is None
        s = _open_translation_skill(MovieTranslateOptions(), segs, "English", "Khmer")
        assert isinstance(s, KhmerDialogueSession) and s.path.name.endswith(f".{SKILL_ID}.json")
        other = _open_translation_skill(MovieTranslateOptions(), segs, "English", "English")
        assert type(other) is TranslationSkillSession
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
