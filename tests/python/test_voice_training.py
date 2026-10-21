"""Voice training milestone 1 — rights gate, schema, validator, dry-run trainer.

Run:
  KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=src .venv/bin/python tests/python/test_voice_training.py
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

from claynext.voice_training.datasets.dataset_builder import (
    assign_splits,
    load_dataset,
    save_dataset,
)
from claynext.voice_training.datasets.dataset_validator import validate_dataset
from claynext.voice_training.datasets.speech_schema import (
    PerformerConsent,
    RecordingSession,
    SpeechDataset,
    SpeechSegment,
)
from claynext.voice_training.evaluation.harness import run_evaluation
from claynext.voice_training.ingestion.rights_validator import (
    assert_training_allowed,
    validate_dataset_for_training,
    validate_session,
)
from claynext.voice_training.training.tts_trainer import run_finetune, trainer_capability

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "khmer_speech" / "dataset.json"
DEMO = Path(__file__).resolve().parents[2] / "data" / "voice_datasets" / "demo_consented" / "dataset.json"


def _consent(**kw) -> PerformerConsent:
    base = dict(
        name="Actor A",
        consent_id="c1",
        permitted_uses=["voice_model_training", "tts_synthesis"],
        restrictions=[],
        expires_at=(datetime.now(timezone.utc) + timedelta(days=30)).replace(microsecond=0).isoformat(),
        revocable=True,
    )
    base.update(kw)
    return PerformerConsent(**base)


def _session(**kw) -> RecordingSession:
    base = dict(
        source_id="src1",
        title="Booth",
        owner="Studio",
        license_type="actor_recording",
        license_doc_path="/tmp/license.txt",
        performers=[_consent()],
        session_id="sess1",
        catalog_role="training_source",
    )
    base.update(kw)
    return RecordingSession(**base)


def _dataset(sessions=None, segments=None) -> SpeechDataset:
    return SpeechDataset(
        dataset_id="ds_test",
        name="test",
        sessions=sessions or [_session()],
        segments=segments or [
            SpeechSegment(
                segment_id="seg1",
                audio_path="/tmp/a.wav",
                start_sec=0.0,
                end_sec=1.0,
                speaker_id="spk1",
                transcript_display="សួស្តី",
                session_id="sess1",
                source_id="src1",
                train_split="train",
            )
        ],
    )


# ── Rights gate ─────────────────────────────────────────────────────────

def test_rights_allows_consented_training():
    verdict = validate_session(_session(), gate="voice_model_training")
    assert verdict.allowed, [i.message for i in verdict.errors]


def test_rights_blocks_missing_consent_id():
    sess = _session(performers=[_consent(consent_id="")])
    verdict = validate_session(sess, gate="voice_model_training")
    assert not verdict.allowed
    assert any(i.code == "missing_consent_id" for i in verdict.errors)


def test_rights_blocks_expired_consent():
    past = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0).isoformat()
    sess = _session(performers=[_consent(expires_at=past)])
    verdict = validate_session(sess, gate="voice_model_training")
    assert not verdict.allowed
    assert any(i.code == "consent_expired" for i in verdict.errors)


def test_rights_blocks_missing_permitted_uses():
    sess = _session(performers=[_consent(permitted_uses=["research_only"])])
    verdict = validate_session(sess, gate="voice_model_training")
    assert not verdict.allowed
    assert any(i.code == "permitted_uses_missing" for i in verdict.errors)


def test_rights_blocks_catalog_candidate():
    sess = _session(catalog_role="catalog_candidate")
    verdict = validate_session(sess, gate="voice_model_training")
    assert not verdict.allowed
    assert any(i.code == "catalog_candidate_only" for i in verdict.errors)


def test_rights_blocks_voice_cloning_without_explicit_grant():
    sess = _session(performers=[_consent(permitted_uses=["voice_model_training", "tts_synthesis"])])
    verdict = validate_session(sess, gate="voice_cloning")
    assert not verdict.allowed
    assert any(i.code == "cloning_not_permitted" for i in verdict.errors)


def test_assert_training_allowed_raises():
    ds = _dataset(sessions=[_session(performers=[_consent(permitted_uses=[])])])
    try:
        assert_training_allowed(ds)
        raise AssertionError("expected PermissionError")
    except PermissionError:
        pass


# ── Schema / validator / splits ─────────────────────────────────────────

def test_schema_roundtrip():
    ds = _dataset()
    raw = ds.to_dict()
    back = SpeechDataset.from_dict(raw)
    assert back.dataset_id == ds.dataset_id
    assert back.segments[0].transcript_display == "សួស្តី"
    assert back.sessions[0].performers[0].consent_id == "c1"


def test_validator_ok_and_split_leak():
    ds = _dataset()
    report = validate_dataset(ds)
    assert report.ok, [i.message for i in report.errors]

    # Same session in train + test → leak
    ds.segments.append(
        SpeechSegment(
            segment_id="seg2",
            audio_path="/tmp/b.wav",
            start_sec=0.0,
            end_sec=1.0,
            session_id="sess1",
            source_id="src1",
            train_split="test",
        )
    )
    report2 = validate_dataset(ds)
    assert any(i.code == "split_leak_session" for i in report2.errors)


def test_assign_splits_by_session():
    segs = []
    for i in range(6):
        segs.append(
            SpeechSegment(
                segment_id=f"s{i}",
                audio_path="/tmp/x.wav",
                start_sec=0.0,
                end_sec=1.0,
                session_id=f"sess{i}",
                source_id=f"src{i}",
                train_split="train",
            )
        )
    ds = SpeechDataset(dataset_id="d", name="n", sessions=[], segments=segs)
    assign_splits(ds, val_ratio=0.2, test_ratio=0.2, seed=7)
    by_sess: dict[str, set[str]] = {}
    for seg in ds.segments:
        by_sess.setdefault(seg.session_id, set()).add(seg.train_split)
    assert all(len(v) == 1 for v in by_sess.values())


# ── Fixture + evaluation + dry-run ──────────────────────────────────────

def test_fixture_dataset_loads():
    path = FIXTURE if FIXTURE.is_file() else DEMO
    assert path.is_file(), f"missing fixture at {FIXTURE} or {DEMO}"
    ds = load_dataset(path)
    assert ds.segments
    assert ds.sessions
    report = validate_dataset(ds)
    assert report.ok, [i.to_dict() for i in report.errors]
    rights = validate_dataset_for_training(ds, gate="voice_model_training")
    assert rights.allowed, [i.message for i in rights.errors]


def test_evaluation_harness_on_fixture():
    path = FIXTURE if FIXTURE.is_file() else DEMO
    summary = run_evaluation(path)
    assert summary["segments"] >= 1
    assert 0.0 <= summary["intelligibility_mean"] <= 1.0
    assert 0.0 <= summary["naturalness_mean"] <= 1.0
    assert "speaker_consistency" in summary


def test_dry_run_trainer_writes_manifest():
    path = FIXTURE if FIXTURE.is_file() else DEMO
    caps = trainer_capability()
    assert "recommended_mode" in caps
    result = run_finetune(path, dry_run=True, model_name="khmer-tts-baseline")
    assert result["ok"] is True
    assert result["dry_run"] is True
    manifest_path = Path(result["manifest_path"])
    assert manifest_path.is_file()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["status"] == "dry_run_complete"
    assert data["checkpoint"]["weights"] is None


def test_dry_run_blocked_without_consent():
    with tempfile.TemporaryDirectory() as tmp:
        bad = _dataset(sessions=[_session(performers=[_consent(permitted_uses=["display_only"])])])
        path = Path(tmp) / "dataset.json"
        save_dataset(bad, path)
        try:
            run_finetune(path, dry_run=True)
            raise AssertionError("expected PermissionError")
        except PermissionError:
            pass


def main() -> None:
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
