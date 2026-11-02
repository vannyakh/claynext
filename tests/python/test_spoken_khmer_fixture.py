"""Spoken-Khmer fixture lookup. Not a fine-tune. No API keys.

Run:
  KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=src .venv/bin/python tests/python/test_spoken_khmer_fixture.py
"""
from __future__ import annotations

from pathlib import Path

from claynext.models.training.spoken_fixture import (
    DEFAULT_SFT_PATH,
    HOLDOUT_REFUSAL,
    NOT_IN_TEST_SET,
    FixtureDataError,
    SpokenKhmerFixture,
    is_holdout_id,
)

FIXTURE_ROWS = (
    {
        "id": "kp-010",
        "source": "Hello fixture.",
        "khmer": "សួស្តី ហ្វិកស្ទួរ",
        "licence": "unknown",
        "owner_training_approved": True,
        "split": "train",
    },
    {
        "id": "kp-011",
        "source": "Second fixture line.",
        "khmer": "បន្ទាត់ទីពីរ",
        "licence": "unknown",
        "owner_training_approved": True,
        "split": "train",
    },
)


def _row(**overrides):
    base = {
        "id": "kp-012",
        "source": "Third fixture line.",
        "khmer": "បន្ទាត់ទីបី",
        "licence": "unknown",
        "owner_training_approved": True,
        "split": "train",
    }
    base.update(overrides)
    return base


def test_lookup_by_id_and_source():
    model = SpokenKhmerFixture(rows=list(FIXTURE_ROWS))
    by_id = model.lookup(row_id="kp-010")
    assert by_id.ok is True
    assert by_id.status == "hit"
    assert by_id.text == "សួស្តី ហ្វិកស្ទួរ"
    assert by_id.trained is False
    assert by_id.generates is False
    assert by_id.promoted is False
    assert by_id.licence == "unknown"
    by_source = model.lookup(source="Second fixture line.")
    assert by_source.ok is True
    assert by_source.row_id == "kp-011"
    assert by_source.text == "បន្ទាត់ទីពីរ"
    both = model.lookup(row_id="KP-010", source="Hello fixture.")
    assert both.ok is True
    assert both.row_id == "kp-010"


def test_unknown_source_is_not_in_the_test_set():
    model = SpokenKhmerFixture(rows=list(FIXTURE_ROWS))
    miss = model.lookup(source="this line was never approved")
    assert miss.ok is False
    assert miss.status == "not_in_test_set"
    assert miss.text == ""
    assert miss.message == NOT_IN_TEST_SET
    assert miss.generates is False
    empty = model.lookup()
    assert empty.status == "not_in_test_set"
    assert empty.message == NOT_IN_TEST_SET
    unknown_id = model.lookup(row_id="kp-759")
    assert unknown_id.status == "not_in_test_set"
    assert unknown_id.text == ""
    mismatch = model.lookup(row_id="kp-010", source="Second fixture line.")
    assert mismatch.status == "not_in_test_set"
    assert mismatch.text == ""


def test_holdout_ids_are_refused():
    model = SpokenKhmerFixture(rows=list(FIXTURE_ROWS))
    for row_id in ("kp-1001", "kp-1500", "KP-2000"):
        assert is_holdout_id(row_id) is True
        refused = model.lookup(row_id=row_id, source="Hello fixture.")
        assert refused.ok is False
        assert refused.status == "refused_holdout"
        assert refused.text == ""
        assert refused.message == HOLDOUT_REFUSAL
        assert "សួស្តី" not in refused.text
    assert is_holdout_id("kp-1000") is False
    assert is_holdout_id("kp-2001") is False
    outside = model.lookup(row_id="kp-2001")
    assert outside.status == "not_in_test_set"


def test_bad_rows_are_not_indexed():
    model_rows = list(FIXTURE_ROWS)
    try:
        SpokenKhmerFixture(rows=model_rows + [_row(id="kp-1001", source="Holdout source.")])
    except FixtureDataError as exc:
        assert "holdout" in str(exc)
    else:
        raise AssertionError("holdout row was indexed")
    try:
        SpokenKhmerFixture(rows=model_rows + [_row(owner_training_approved=False)])
    except FixtureDataError as exc:
        assert "owner_training_approved" in str(exc)
    else:
        raise AssertionError("unapproved row was indexed")
    try:
        SpokenKhmerFixture(rows=model_rows + [_row(source="Hello fixture.")])
    except FixtureDataError as exc:
        assert "duplicate source" in str(exc)
    else:
        raise AssertionError("duplicate source was indexed")


def test_benchmark_row_uses_id_before_source():
    model = SpokenKhmerFixture(rows=list(FIXTURE_ROWS))
    hit = model.translate_row({"id": "kp-011", "source_text": "Second fixture line."})
    assert hit["ok"] is True
    assert hit["text"] == "បន្ទាត់ទីពីរ"
    assert hit["trained"] is False
    refused = model({"id": "kp-1001", "source_text": "Hello fixture."})
    assert refused["status"] == "refused_holdout"
    assert refused["text"] == ""


def test_default_export_is_the_approved_758():
    assert DEFAULT_SFT_PATH.is_file()
    model = SpokenKhmerFixture()
    assert model.row_count == 758
    assert "kp-001" in model._by_id
    assert "kp-758" in model._by_id
    assert all(row["licence"] == "unknown" for row in model._by_id.values())
    assert all(row["owner_training_approved"] is True for row in model._by_id.values())
    assert all(not is_holdout_id(row_id) for row_id in model._by_id)
    first = model.lookup(row_id="kp-001")
    assert first.ok is True
    assert first.text == model._by_id["kp-001"]["khmer"]
    assert first.text
    assert first.trained is False
    assert first.promoted is False
    missing = model.lookup(source="this source is not in the approved export")
    assert missing.status == "not_in_test_set"
    assert missing.message == NOT_IN_TEST_SET
    assert model.lookup(row_id="kp-1001").status == "refused_holdout"
    assert model.lookup(row_id="kp-2000").status == "refused_holdout"
    assert Path(DEFAULT_SFT_PATH).name == "sft-train-approved.jsonl"


if __name__ == "__main__":
    import sys
    import traceback

    failed = 0
    tests = [
        ("test_lookup_by_id_and_source", test_lookup_by_id_and_source),
        ("test_unknown_source_is_not_in_the_test_set", test_unknown_source_is_not_in_the_test_set),
        ("test_holdout_ids_are_refused", test_holdout_ids_are_refused),
        ("test_bad_rows_are_not_indexed", test_bad_rows_are_not_indexed),
        ("test_benchmark_row_uses_id_before_source", test_benchmark_row_uses_id_before_source),
        ("test_default_export_is_the_approved_758", test_default_export_is_the_approved_758),
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
