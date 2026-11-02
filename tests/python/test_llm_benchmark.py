"""Leakage, synthetic gold, promotion, runner shape, and training dry-run.

Run:
  KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=src .venv/bin/python tests/python/test_llm_benchmark.py
"""
from __future__ import annotations

import json
from pathlib import Path

from claynext.models.benchmarks.comparison import (
    build_comparison_judge_prompt,
    comparison_report,
)
from claynext.models.benchmarks.leakage import LeakageError, assert_no_leakage
from claynext.models.benchmarks.promotion import evaluate_promotion
from claynext.models.benchmarks.prompt import contains_model_id, judge_prompt, translation_prompt
from claynext.models.benchmarks.runner import run_benchmark
from claynext.models.benchmarks.spoken_split import (
    INCOMPLETE_NOTE,
    SPEC_RELATIVE,
    LockedPoolError,
    OverlapError,
    SplitPlanError,
    apply_spoken_split,
    assert_assignment_disjoint,
    assert_scale_not_locked,
    assert_trainable,
    incomplete_split_spec,
    plan_scale_holdout,
    plan_spoken_split,
)
from claynext.models.benchmarks.schema import (
    BenchmarkRow,
    SplitLockError,
    SyntheticGoldError,
    assign_split,
    assert_not_synthetic_gold,
)
from claynext.models.llm_gateway.base import Pricing


def _row(**kwargs) -> BenchmarkRow:
    data = dict(
        id="line-1",
        scene_id="scene-1",
        dialogue_family_id="family-a",
        source_language="en",
        source_text="Go home.",
        reference_khmer="ទៅផ្ទះហើយ",
        split="test",
        licence="unknown",
        review_status="pending_native_review",
        origin="gemini_teacher",
        dataset_version="fixture-pending",
        locked=True,
        synthetic_only=True,
    )
    data.update(kwargs)
    return BenchmarkRow(**data)


def _score(reviewer: str, dimension: str, *, passed: bool | None = None, rating: int | None = None) -> dict:
    return {
        "reviewer_id": reviewer,
        "dimension": dimension,
        "passed": passed,
        "rating": rating,
    }


def _complete_review() -> dict:
    scores = []
    for reviewer in ("reviewer-a", "reviewer-b"):
        for dimension in ("meaning", "pronoun", "emotion_register", "terminology", "structured_output"):
            scores.append(_score(reviewer, dimension, passed=True))
        scores.append(_score(reviewer, "natural_khmer", rating=5))
    return {"item_id": "line-1", "scores": scores, "adjudication": {}}


def test_leakage_same_family_refused():
    calls = {"n": 0}

    def translate(_row):
        calls["n"] += 1
        return "ទៅផ្ទះហើយ"

    train = _row(id="train-1", split="train", locked=False)
    held = _row(id="test-1")
    try:
        run_benchmark([held], translate, train_rows=[train], synthetic_fixture=True)
    except LeakageError as exc:
        assert exc.families == ["family-a"]
    else:
        raise AssertionError("leakage was scored")
    assert calls["n"] == 0
    assert_no_leakage([_row(dialogue_family_id="family-b")], train_rows=[train])


def test_synthetic_and_pending_are_not_gold():
    pending = _row()
    assert pending.is_gold_reference() is False
    synthetic_gold = _row(
        review_status="gold",
        origin="synthetic",
        synthetic_only=True,
        reviewer_id="model",
        reviewed_at="2026-10-22T00:00:00+00:00",
        licence="CC-BY-4.0",
    )
    assert synthetic_gold.is_gold_reference() is False
    try:
        assert_not_synthetic_gold(synthetic_gold)
    except SyntheticGoldError:
        pass
    else:
        raise AssertionError("synthetic gold was accepted")
    human = _row(
        review_status="gold",
        origin="human_authored",
        synthetic_only=False,
        reviewer_id="native-1",
        reviewed_at="2026-10-22T00:00:00+00:00",
        licence="CC-BY-4.0",
    )
    assert human.is_gold_reference() is True


def test_locked_test_split_cannot_move():
    row = _row()
    try:
        assign_split(row, "train")
    except SplitLockError:
        pass
    else:
        raise AssertionError("locked test row moved")
    assert row.split == "test"


def test_promotion_refuses_without_human_gates():
    refused = evaluate_promotion(None, candidate_id="fixture-not-a-model")
    assert refused["promoted"] is False
    assert refused["decision"] == "not_promoted"
    assert refused["uncertainty"]["n"] is None
    assert refused["uncertainty"]["agreement"] is None
    assert "no human review record" in refused["reasons"]
    partial = evaluate_promotion(
        [_complete_review()],
        baseline_improved=True,
        critical_semantic_regressions=0,
        licence_allows_deployment=True,
        cto_approved=False,
        qa_approved=True,
        candidate_id="fixture-not-a-model",
    )
    assert partial["promoted"] is False
    assert "CTO approval flag is false" in partial["reasons"]


def test_promotion_accepts_only_a_complete_human_record():
    accepted = evaluate_promotion(
        [_complete_review()],
        baseline_improved=True,
        critical_semantic_regressions=0,
        licence_allows_deployment=True,
        cto_approved=True,
        qa_approved=True,
        synthetic_fixture=False,
        candidate_id="fixture-not-a-model",
    )
    assert accepted["promoted"] is True
    assert accepted["decision"] == "promoted"
    assert accepted["model_evaluated"] is False
    assert accepted["uncertainty"]["n"] == 1
    assert accepted["uncertainty"]["agreement"] == 1.0
    fixture = evaluate_promotion(
        [_complete_review()],
        baseline_improved=True,
        critical_semantic_regressions=0,
        licence_allows_deployment=True,
        cto_approved=True,
        qa_approved=True,
        synthetic_fixture=True,
        candidate_id="fixture-not-a-model",
    )
    assert fixture["promoted"] is False


def test_disagreement_blocks_promotion():
    item = _complete_review()
    item["scores"].append(_score("reviewer-b", "meaning", passed=False))
    # The second meaning score from reviewer-b disagrees with the first.
    # Keep a single conflicting pair: drop the unanimous meaning scores and set both.
    item["scores"] = [
        score for score in item["scores"]
        if not (score["dimension"] == "meaning")
    ]
    item["scores"].extend([
        _score("reviewer-a", "meaning", passed=True),
        _score("reviewer-b", "meaning", passed=False),
    ])
    decision = evaluate_promotion(
        [item],
        baseline_improved=True,
        critical_semantic_regressions=0,
        licence_allows_deployment=True,
        cto_approved=True,
        qa_approved=True,
    )
    assert decision["promoted"] is False
    assert "unresolved reviewer disagreement" in decision["reasons"]


def test_runner_report_shape_with_fake_translator(tmp: Path):
    seen: list[str] = []

    def translate(row: BenchmarkRow) -> dict:
        prompt = translation_prompt(row)
        seen.append(prompt)
        blinded = judge_prompt(
            source_text=row.source_text,
            reference_khmer=row.reference_khmer,
            hypothesis="ទៅផ្ទះហើយ",
        )
        assert contains_model_id(prompt, "aya-expanse:8b") is False
        assert contains_model_id(blinded, "gpt-4o-mini") is False
        return {"text": "ទៅផ្ទះហើយ", "latency_ms": 12, "tokens_in": 10, "tokens_out": 4}

    report = run_benchmark(
        [_row()],
        translate,
        model_id="aya-expanse:8b",
        provider_label="fake-translator",
        pricing=None,
        synthetic_fixture=True,
        judge=lambda prompt: prompt,
        out_dir=tmp,
    )
    assert report["synthetic_fixture"] is True
    assert report["not_a_gold_benchmark"] is True
    assert report["quality_score"] is None
    assert report["prompt_version"] == "khmer-movie-benchmark-1"
    assert report["decoding"]["temperature"] == 0
    assert report["prompt_includes_model_id"] is False
    assert "aya-expanse" not in seen[0]
    assert report["metrics"]["meaning"]["value"] is None
    assert report["metrics"]["naturalness"]["value"] is None
    assert report["metrics"]["emotion_register"]["value"] is None
    assert report["metrics"]["cost"]["value"] is None
    assert report["uncertainty"]["agreement"] is None
    assert report["promotion"]["promoted"] is False
    assert report["promotion"]["decision"] == "not_promoted"
    assert report["leaderboard"]["ranked"] is False
    assert report["judge_raw"][0]["used_as_score"] is False
    assert "aya-expanse" not in report["judge_raw"][0]["text"]
    saved = json.loads(Path(report["path"]).read_text(encoding="utf-8"))
    blob = json.dumps(saved).lower()
    assert saved["synthetic_fixture"] is True
    assert "chrf" not in blob
    assert "comet" not in blob
    assert "beats gpt" not in blob
    priced = run_benchmark(
        [_row(id="line-2")],
        translate,
        pricing=Pricing(input_per_million=1.0, output_per_million=2.0),
        synthetic_fixture=True,
        provider_label="fake-priced",
    )
    assert priced["metrics"]["cost"]["method"] == "user_supplied_pricing"
    assert priced["metrics"]["cost"]["value"] == (10 * 1.0 + 4 * 2.0) / 1_000_000


def _spoken(row_id: str, family: str, **extra) -> dict:
    row = {
        "id": row_id,
        "dialogue_family_id": family,
        "split": "train",
        "locked": False,
        "origin": "gemini_teacher",
        "licence": "unknown",
        "review_status": "pending_native_review",
        "reference_khmer": "",
    }
    row.update(extra)
    return row


def test_spoken_split_refuses_leakage_and_caps_train():
    try:
        assert_assignment_disjoint(["a"], ["b"], {"a": "family-a", "b": "family-a"})
    except LeakageError as exc:
        assert exc.families == ["family-a"]
    else:
        raise AssertionError("shared dialogue family was accepted")
    try:
        assert_assignment_disjoint(["a"], ["a"], {"a": "family-a"})
    except OverlapError:
        pass
    else:
        raise AssertionError("duplicate id was accepted")

    locked_pair = [
        _spoken("a", "family-a", split="test", locked=True, reference_khmer="ក"),
        _spoken("b", "family-a", reference_khmer="ខ"),
        _spoken("c", "family-b", reference_khmer="គ"),
    ]
    plan = plan_spoken_split(locked_pair)
    assert plan["train_count"] <= 100
    assert "a" in plan["locked_ids"] and "b" in plan["locked_ids"]
    assert "a" not in plan["train_ids"] and "b" not in plan["train_ids"]
    try:
        assert_trainable(plan, "a")
    except LockedPoolError:
        pass
    else:
        raise AssertionError("locked row was trainable")

    wide = [_spoken(f"row-{index}", f"family-{index}") for index in range(120)]
    capped = plan_spoken_split(wide, train_size=250)
    assert capped["train_count"] == 100
    assert capped["locked_count"] == 20
    assert capped["train_cap"] == 100
    assert set(capped["train_ids"]).isdisjoint(capped["locked_ids"])
    again = plan_spoken_split(list(reversed(wide)), train_size=250)
    assert again["train_ids"] == capped["train_ids"]

    one_family = [_spoken(f"kp-{index:03d}", "same-scene") for index in range(1, 501)]
    try:
        plan_spoken_split(one_family)
    except SplitPlanError:
        pass
    else:
        raise AssertionError("one dialogue family was split to fill 100 train rows")

    held = _row(id="kp-050", dialogue_family_id="family-050")
    try:
        apply_spoken_split([held], {"train_ids": ["kp-050"], "locked_ids": [], "train_count": 1})
    except SplitLockError:
        pass
    else:
        raise AssertionError("locked test row moved into train")
    assert held.split == "test"


def test_spoken_split_500_locks_the_rest_and_spec_is_incomplete():
    rows = []
    for index in range(1, 501):
        rows.append(_spoken(
            f"kp-{index:03d}",
            f"family-{index}",
            reference_khmer="ទៅផ្ទះហើយ",
        ))
    plan = plan_spoken_split(rows)
    assert plan["train_count"] == 100
    assert plan["locked_count"] == 400
    assert plan["matches_owner_500"] is True
    assert plan["locked_pool_complete"] is True
    assert plan["native_gold_benchmark"] is False
    assert plan["not_the_1000_to_2000_native_gold_benchmark"] is True
    assert plan["promotion"] == "not_promoted"
    assert set(plan["train_ids"]).isdisjoint(plan["locked_ids"])
    families = {row_id: f"family-{int(row_id[3:]):d}" for row_id in plan["train_ids"] + plan["locked_ids"]}
    assert_assignment_disjoint(plan["train_ids"], plan["locked_ids"], families)
    same = plan_spoken_split(rows, seed=13)
    assert same["train_ids"] == plan["train_ids"]

    spec = incomplete_split_spec()
    assert spec["locked_pool_complete"] is False
    assert spec["train_cap"] == 100
    assert spec["target_total"] == 500
    assert spec["locked_when_complete"] == 400
    assert spec["assignment"] is None
    assert spec["native_gold_benchmark"] is False
    assert spec["current_jev_ranked_rows"]["count"] == 100
    assert spec["current_jev_ranked_rows"]["is_gold"] is False
    assert spec["prior_plan"]["deleted"] is False
    assert spec["prior_plan"]["train"] == 80
    assert spec["note"] == INCOMPLETE_NOTE
    path = Path(__file__).resolve().parents[2] / SPEC_RELATIVE
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["locked_pool_complete"] is False
    assert saved["note"] == INCOMPLETE_NOTE
    assert saved["promotion"] == "not_promoted"


def test_scale_holdout_locks_the_last_thousand_and_does_not_train():
    ids = [f"kp-{index:03d}" for index in range(1, 2001)]
    plan = plan_scale_holdout(ids)
    assert plan["train_count"] == 1000
    assert plan["locked_count"] == 1000
    assert plan["train_id_first"] == "kp-001"
    assert plan["train_id_last"] == "kp-1000"
    assert plan["locked_id_first"] == "kp-1001"
    assert plan["locked_id_last"] == "kp-2000"
    assert plan["promotion"] == "not_promoted"
    assert plan["native_gold_benchmark"] is False
    assert plan["not_the_1000_to_2000_native_gold_benchmark"] is True
    assert plan["weights_written"] is False
    assert plan["weight_update"] is False
    assert plan["train_on_locked"] is False
    assert set(plan["train_ids"]).isdisjoint(plan["locked_ids"])
    assert plan["dataset_rows_target"]["status"] == "target_not_current"
    assert plan["native_benchmark_rows_target"]["min"] == 1000
    try:
        assert_scale_not_locked(plan, "kp-1001")
    except LockedPoolError:
        pass
    else:
        raise AssertionError("locked scale id was trainable")
    assert_scale_not_locked(plan, "kp-1000")
    small = plan_scale_holdout([f"kp-{index:03d}" for index in range(1, 501)])
    assert small["rule"] == "until_1000_locked_rows_exist_lock_every_id_outside_the_train_pool"
    assert small["train_count"] == 100
    assert small["locked_count"] == 400
    assert small["train_id_last"] == "kp-100"
    assert small["locked_id_first"] == "kp-101"
    assert small["promotion"] == "not_promoted"


def test_comparison_report_does_not_promote_synthetic_reference():
    report = comparison_report(
        native_reviewed=False,
        reference_origin="gemini_teacher",
        model_ids=["gpt-4o-mini", "gemini-flash-latest"],
        pricing=Pricing(input_per_million=1.0, output_per_million=2.0),
        measurements={
            "C": {"quality": 0.99, "latency_ms": 12, "vram_gb": 80},
            "E": {"quality": 1.0, "beats_gpt": False},
        },
    )
    assert report["not_a_gold_benchmark"] is True
    assert report["synthetic_reference"] is True
    assert report["promotion"]["promoted"] is False
    assert report["promotion"]["decision"] == "not_promoted"
    assert report["winner"] is None
    assert report["quality_score"] is None
    assert report["leaderboard"]["ranked"] is False
    assert report["leaderboard"]["promoted_model_id"] is None
    assert report["judge_prompt_includes_model_name"] is False
    assert "gpt-4o-mini" not in report["judge_prompt"].lower()
    assert "gemini" not in report["judge_prompt"].lower()
    by_role = {slot["role"]: slot for slot in report["models"]}
    assert list(by_role) == ["A", "B", "C", "D", "E"]
    assert by_role["D"]["present"] is False
    assert by_role["E"]["label"] == "hosted GPT/Gemini"
    for slot in report["models"]:
        assert slot["quality"] is None
        assert slot["regression_risk"] is None
        assert slot["cost_usd"] is None
        assert slot["promotion"] == "not_promoted"
    assert by_role["C"]["latency_ms"] == 12
    assert by_role["C"]["vram_gb"] == 80
    assert by_role["A"]["latency_ms"] is None
    blob = json.dumps(report).lower()
    assert "beats gpt" not in blob
    assert "beat gpt" not in blob
    assert "chrf" not in blob
    assert "comet" not in blob
    priced = comparison_report(
        measurements={"E": {"trace_cost": 0.25, "tokens_in": 10, "tokens_out": 4}},
        pricing=Pricing(input_per_million=9.0, output_per_million=9.0),
    )
    hosted = {slot["role"]: slot for slot in priced["models"]}["E"]
    assert hosted["cost_usd"] == 0.25
    assert hosted["cost"]["method"] == "provider_trace"
    assert priced["promotion"]["promoted"] is False
    assert priced["winner"] is None
    try:
        build_comparison_judge_prompt(
            source_text="Go home.",
            reference_khmer="ទៅផ្ទះហើយ",
            hypothesis="written by gpt-4o-mini",
            model_ids=["gpt-4o-mini"],
        )
    except ValueError:
        pass
    else:
        raise AssertionError("judge prompt kept the model name")
    try:
        comparison_report(measurements={"A": {"beats_gpt": True}})
    except ValueError:
        pass
    else:
        raise AssertionError("a win claim was written into the report")


if __name__ == "__main__":
    import sys
    import tempfile
    import traceback

    failed = 0
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        tests = [
            ("test_leakage_same_family_refused", test_leakage_same_family_refused),
            ("test_synthetic_and_pending_are_not_gold", test_synthetic_and_pending_are_not_gold),
            ("test_locked_test_split_cannot_move", test_locked_test_split_cannot_move),
            ("test_promotion_refuses_without_human_gates", test_promotion_refuses_without_human_gates),
            ("test_promotion_accepts_only_a_complete_human_record", test_promotion_accepts_only_a_complete_human_record),
            ("test_disagreement_blocks_promotion", test_disagreement_blocks_promotion),
            ("test_runner_report_shape_with_fake_translator", lambda: test_runner_report_shape_with_fake_translator(tmp)),
            ("test_spoken_split_refuses_leakage_and_caps_train", test_spoken_split_refuses_leakage_and_caps_train),
            ("test_spoken_split_500_locks_the_rest_and_spec_is_incomplete", test_spoken_split_500_locks_the_rest_and_spec_is_incomplete),
            ("test_scale_holdout_locks_the_last_thousand_and_does_not_train", test_scale_holdout_locks_the_last_thousand_and_does_not_train),
            ("test_comparison_report_does_not_promote_synthetic_reference", test_comparison_report_does_not_promote_synthetic_reference),
        ]
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
