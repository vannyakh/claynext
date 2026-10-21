"""KSLD / Gemini teacher milestone tests. No network, no GPU.

Run:
  KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=src .venv/bin/python tests/python/test_khmer_spoken.py
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from claynext.models.khmer_spoken.datasets.gemini_candidate_generator import (
    generate_candidates_batch,
)
from claynext.models.khmer_spoken.datasets.io_store import export_gold_version, import_jsonl, save_examples
from claynext.models.khmer_spoken.datasets.khmer_human_review import (
    apply_review_decision,
    promote_to_gold,
)
from claynext.models.khmer_spoken.evaluation.khmer_translation_benchmark import run_benchmark
from claynext.models.khmer_spoken.paths import DEFAULT_FIXTURE
from claynext.models.khmer_spoken.providers.google_tts_provider import GeminiTtsProvider
from claynext.models.khmer_spoken.schema import (
    REVIEW_GOLD,
    REVIEW_PENDING,
    DialogueExample,
    TranslationCandidate,
    can_promote_to_gold,
    validate_example,
)
from claynext.models.khmer_spoken.training.training_job_manager import TrainingJobManager
from claynext.models.khmer_spoken.training.vertex_tuning_client import VertexTuningClient


def _ex(**kw) -> DialogueExample:
    base = dict(
        id="t1",
        source_text="I'm going home.",
        stub_khmer="ខ្ញុំទៅផ្ទះហើយ។",
        candidates=[
            TranslationCandidate(text="ខ្ញុំទៅផ្ទះហើយ។", style="natural", provider="gemini_teacher")
        ],
        origin="gemini_teacher",
        license_type="demo_fixture",
        review_status=REVIEW_PENDING,
    )
    base.update(kw)
    return DialogueExample(**base)


def test_fixture_exists_and_pending():
    assert DEFAULT_FIXTURE.is_file(), f"missing fixture {DEFAULT_FIXTURE}"
    rows = import_jsonl(DEFAULT_FIXTURE)
    assert len(rows) >= 100
    assert all(r.review_status == REVIEW_PENDING for r in rows[:10])
    assert all(r.license_type == "demo_fixture" for r in rows[:10])
    assert all(not r.is_gold for r in rows)


def test_candidate_generator_skips_gold_and_respects_pending():
    pending = _ex(id="p1", review_status=REVIEW_PENDING)
    gold = _ex(
        id="g1",
        review_status=REVIEW_GOLD,
        verified_by="rv-1",
        verified_at="2026-10-01T10:00:00+00:00",
        approved_text="ខ្ញុំទៅផ្ទះហើយ។",
        license_type="CC-BY-4.0",
        origin="human_reviewed",
    )
    before = len(gold.candidates)

    class FakeTeacher:
        def available(self):
            return True

        def generate_khmer_candidates(self, *a, **k):
            from claynext.models.khmer_spoken.providers.google_gemini_provider import (
                GeminiTeacherResult,
            )

            return GeminiTeacherResult(
                ok=True,
                model="fake",
                candidates=[{"text": "សួស្តី។", "style": "natural"}],
            )

    report = generate_candidates_batch(
        [pending, gold], provider=FakeTeacher(), force=False  # type: ignore[arg-type]
    )
    assert report["ok"]
    assert report["updated"] == 1
    assert any(c.text == "សួស្តី។" for c in pending.candidates)
    assert len(gold.candidates) == before
    assert pending.review_status == REVIEW_PENDING


def test_human_review_promotion_requires_reviewer_fields():
    ex = _ex()
    updated, issues = promote_to_gold(ex, verified_by="")
    assert updated.review_status != REVIEW_GOLD
    assert any(i.code == "missing_verified_by" for i in issues)

    updated, issues = promote_to_gold(
        ex,
        verified_by="native-01",
        approved_text="ខ្ញុំទៅផ្ទះហើយ។",
        verified_at="2026-10-01T10:00:00+00:00",
    )
    # demo_fixture still allows gold with warning; errors should be empty
    errors = [i for i in issues if i.severity == "error"]
    assert not errors
    assert updated.review_status == REVIEW_GOLD
    assert updated.verified_by == "native-01"
    assert updated.verified_at


def test_approve_without_reviewer_fails():
    ex = _ex()
    updated, issues = apply_review_decision(ex, decision="approve", verified_by="")
    assert updated.review_status == REVIEW_PENDING
    assert any(i.code == "missing_verified_by" for i in issues)


def test_export_versioning(tmp_path: Path | None = None):
    root = Path(tempfile.mkdtemp()) if tmp_path is None else Path(tmp_path)
    gold = _ex(
        id="g1",
        review_status=REVIEW_GOLD,
        verified_by="rv-1",
        verified_at="2026-10-01T10:00:00+00:00",
        approved_text="ខ្ញុំទៅផ្ទះហើយ។",
        license_type="CC-BY-4.0",
        origin="human_reviewed",
    )
    pending = _ex(id="p1")
    result = export_gold_version(
        [gold, pending], version="ksld-test-v1", out_dir=root / "ksld-test-v1"
    )
    assert result["count"] == 1
    assert len(result["rejected"]) == 1
    data_path = Path(result["path"])
    assert data_path.is_file()
    manifest = json.loads((root / "ksld-test-v1" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "ksld-test-v1"
    assert manifest["count"] == 1
    rows = import_jsonl(data_path)
    assert rows[0].review_status == REVIEW_GOLD


def test_vertex_client_refuses_without_credentials(monkeypatch=None):
    client = VertexTuningClient(project="")
    # Force no credentials regardless of machine ADC.
    client.credentials_present = lambda: False  # type: ignore[method-assign]
    report = client.check_eligibility()
    assert not report.eligible
    assert any("credentials" in r for r in report.reasons)
    assert any("project" in r for r in report.reasons)

    ref = client.submit_supervised_tune(train_uri="gs://bucket/train.jsonl")
    assert not ref.ok
    assert ref.status == "refused"
    assert "AI Studio" in ref.error or "credentials" in ref.error or "project" in ref.error


def test_training_job_manager_separates_kinds(tmp_path: Path | None = None):
    root = Path(tempfile.mkdtemp()) if tmp_path is None else Path(tmp_path)
    mgr = TrainingJobManager(root=root)
    client = VertexTuningClient(project="")
    client.credentials_present = lambda: False  # type: ignore[method-assign]
    vtx = mgr.enqueue_vertex_sft(train_uri="gs://x", client=client)
    assert vtx.kind == "vertex_gemini_sft"
    assert vtx.status == "refused"
    lora = mgr.enqueue_local_lora(dataset_path="/tmp/ds.jsonl")
    assert lora.kind == "local_lora"
    assert lora.status == "refused"
    assert lora.details.get("separate_from_vertex") is True


def test_gemini_tts_missing_key_graceful():
    provider = GeminiTtsProvider()
    provider.available = lambda: False  # type: ignore[method-assign]
    with tempfile.TemporaryDirectory() as td:
        result = provider.synthesize_preview("សួស្តី", Path(td) / "out.wav")
    assert result.skipped
    assert not result.ok
    assert result.reason == "missing_key"


def test_benchmark_offline_on_fixture():
    rows = import_jsonl(DEFAULT_FIXTURE)[:15]
    with tempfile.TemporaryDirectory() as td:
        report = run_benchmark(rows, use_gemini_judge=False, out_dir=td)
        assert report.n_examples == 15
        assert report.offline
        assert Path(report.path).is_file()
        assert "gemini_teacher" in report.summary
        assert report.summary["gemini_teacher"]["n"] == 15


def test_validate_synthetic_gold_needs_human():
    ex = _ex(review_status=REVIEW_GOLD, origin="synthetic")
    codes = {i.code for i in validate_example(ex, for_gold=True) if i.severity == "error"}
    assert "missing_verified_by" in codes or "missing_verified_at" in codes
    ok, _ = can_promote_to_gold(ex)
    assert not ok


def test_save_roundtrip(tmp_path: Path | None = None):
    root = Path(tempfile.mkdtemp()) if tmp_path is None else Path(tmp_path)
    path = root / "ws.jsonl"
    save_examples(path, [_ex(), _ex(id="t2")])
    loaded = import_jsonl(path)
    assert len(loaded) == 2
    assert loaded[0].source_text


def main() -> None:
    tests = [
        test_fixture_exists_and_pending,
        test_candidate_generator_skips_gold_and_respects_pending,
        test_human_review_promotion_requires_reviewer_fields,
        test_approve_without_reviewer_fails,
        test_export_versioning,
        test_vertex_client_refuses_without_credentials,
        test_training_job_manager_separates_kinds,
        test_gemini_tts_missing_key_graceful,
        test_benchmark_offline_on_fixture,
        test_validate_synthetic_gold_needs_human,
        test_save_roundtrip,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"OK  {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    if failed:
        raise SystemExit(f"{failed} test(s) failed")
    print(f"All {len(tests)} tests passed.")


if __name__ == "__main__":
    main()
