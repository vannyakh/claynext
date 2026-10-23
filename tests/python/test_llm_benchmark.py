"""Leakage, synthetic gold, promotion, runner shape, and training dry-run.

Run:
  KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=src .venv/bin/python tests/python/test_llm_benchmark.py
"""
from __future__ import annotations

import json
from pathlib import Path

from claynext.models.benchmarks.leakage import LeakageError, assert_no_leakage
from claynext.models.benchmarks.promotion import evaluate_promotion
from claynext.models.benchmarks.prompt import contains_model_id, judge_prompt, translation_prompt
from claynext.models.benchmarks.runner import run_benchmark
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
