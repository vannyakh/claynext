"""Tests for the dialogue localization dataset foundation. No network, no GPU.

Run: PYTHONPATH=src .venv/bin/python tests/python/test_datasets.py
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import tempfile
from pathlib import Path

from claynext.cli.app import main as cli_main
from claynext.models.datasets.dedupe import drop_exact_duplicates, find_duplicates
from claynext.models.datasets.export import export_sft
from claynext.models.datasets.io import import_file, import_rows, read_records, write_records
from claynext.models.datasets.normalize import normalize_text, shingles
from claynext.models.datasets.review import apply_review_rows
from claynext.models.datasets.schema import (
    Candidate,
    DialogueRecord,
    Provenance,
    Regional,
    Review,
    validate_record,
)
from claynext.models.datasets.split import apply_split, find_leaks, split_records
from claynext.models.datasets.store import DatasetStore

KSLD_DIR = Path("/Users/vannya/Documents/SourceCode/AiProject/khmer_spoken_language_dataset_v0.1")
TS = "2026-10-01T10:00:00+00:00"


def _rec(rid: str = "r1", text: str = "ខ្ញុំទៅផ្ទះហើយ។", **kw) -> DialogueRecord:
    base = dict(
        id=rid,
        source_text="I'm going home.",
        candidates=[Candidate(text=text, style="natural")],
        speaker_id="A",
        listener_id="B",
        relationship="friends",
        emotion="neutral",
        category="everyday",
        provenance=Provenance(dataset="unit", license="CC-BY-4.0"),
        groups={"dialogue_family": f"fam-{rid}"},
    )
    base.update(kw)
    return DialogueRecord(**base)


def _codes(rec: DialogueRecord, severity: str = "error") -> set[str]:
    return {i.code for i in validate_record(rec) if i.severity == severity}


def _flat_rows(n: int = 30) -> list[dict[str, str]]:
    rows = []
    phrases = ["ខ្ញុំទៅផ្ទះហើយ", "អរគុណច្រើន", "ចាំខ្ញុំបន្តិច", "ឯងទៅណា", "កុំខឹងអី", "ញ៉ាំបាយហើយឬនៅ"]
    for i in range(n):
        rows.append({
            "id": f"f{i:03d}",
            "source_text": f"line {i}",
            "khmer_natural": f"{phrases[i % len(phrases)]} {i}។",
            "khmer_literal": f"{phrases[i % len(phrases)]}។",
            "speaker_id": f"S{i % 3}",
            "relationship": "friends",
            "emotion": "neutral",
            "category": "everyday",
            "license": "CC-BY-4.0",
            "origin": "human_authored",
            "review_status": "draft",
            "film_id": f"film{i % 5}",
        })
    return rows


# ── Schema and validation ───────────────────────────────────────────────

def test_valid_draft_has_no_errors():
    assert _codes(_rec()) == set()


def test_synthetic_cannot_be_gold_without_human_review():
    rec = _rec(origin="synthetic", review=Review(status="gold"))
    codes = _codes(rec)
    assert "synthetic_gold_unreviewed" in codes
    assert {"review_missing_reviewer", "review_missing_timestamp"} <= codes
    model_reviewed = _rec(origin="synthetic", review=Review("gold", "judge-1", "model", TS))
    assert "synthetic_gold_unreviewed" in _codes(model_reviewed)
    human = _rec(origin="synthetic", review=Review("gold", "rv-07", "human", TS))
    assert _codes(human) == set()


def test_gold_needs_reviewer_timestamp_and_license():
    rec = _rec(origin="human_authored", review=Review("gold", "rv-07", "human", None))
    assert "review_missing_timestamp" in _codes(rec)
    rec = _rec(origin="human_authored", review=Review("gold", "rv-07", "human", "yesterday"))
    assert "bad_reviewed_at" in _codes(rec)
    rec = _rec(origin="human_authored", review=Review("gold", "rv-07", "human", TS),
               provenance=Provenance(dataset="unit"))
    assert "gold_requires_license" in _codes(rec)
    assert "review_missing_reviewer" in _codes(_rec(review=Review("reviewed", None, None, TS)))


def test_regional_claims_need_provenance_and_confidence():
    draft = _rec(regional=Regional(region="battambang"))
    assert "regional_unsupported" in _codes(draft, "warning")
    reviewed = _rec(regional=Regional(region="battambang"), review=Review("reviewed", "rv", "human", TS))
    assert "regional_unsupported" in _codes(reviewed)
    assert "regional_verified_without_provenance" in _codes(_rec(regional=Regional(region="x", verified=True)))
    ok = _rec(regional=Regional(region="battambang", provenance="native speaker interview #3", confidence=0.7))
    assert _codes(ok) == set()
    assert "regional_confidence_range" in _codes(_rec(regional=Regional(region="x", provenance="p", confidence=2)))


def test_ranges_and_vocabularies():
    rec = _rec(intensity=5, category="horror", register="royal")
    rec.quality.scores["naturalness"] = 6
    assert {"level_out_of_range", "bad_category", "bad_register", "score_out_of_range"} <= _codes(rec)
    assert "missing_candidates" in _codes(_rec(candidates=[]))
    assert "candidate_not_khmer" in _codes(_rec(text="hello"), "warning")


def test_record_round_trips_through_dict():
    rec = _rec(intensity=2, regional=Regional(region="r", provenance="p", confidence=0.5))
    rec.quality.scores["naturalness"] = 4.0
    rec.metadata["k"] = "v"
    assert DialogueRecord.from_dict(json.loads(json.dumps(rec.to_dict()))) == rec


# ── Normalization and duplicates ────────────────────────────────────────

def test_normalize_khmer_punctuation_zero_width_and_spacing():
    assert normalize_text("ខ្ញុំ\u200bទៅ ផ្ទះ ហើយ។") == normalize_text("ខ្ញុំទៅផ្ទះហើយ")
    assert normalize_text("Hello, World!") == "helloworld"
    assert "ៗ" in normalize_text("ឆាប់ៗ")
    assert shingles("ab") == frozenset({"ab"})


def test_exact_and_near_duplicates_are_deterministic():
    recs = [
        _rec("a", "ខ្ញុំទៅផ្ទះហើយ។"),
        _rec("b", "ខ្ញុំ ទៅផ្ទះហើយ"),            # exact after normalization
        _rec("c", "ខ្ញុំទៅផ្ទះហើយណា។"),         # near
        _rec("d", "ថ្ងៃនេះភ្លៀងខ្លាំងណាស់។"),     # unrelated
    ]
    rep = find_duplicates(recs, threshold=0.7)
    assert rep.exact_groups == [["a", "b"]]
    assert [(a, b) for a, b, _ in rep.near_pairs] == [("a", "c")]
    assert rep.near_clusters == [["a", "c"]]
    assert rep.cross_group_near_pairs == 1
    again = find_duplicates(list(reversed(recs)), threshold=0.7)
    assert again.summary() == rep.summary() and again.near_pairs == rep.near_pairs


def test_drop_exact_keeps_best_reviewed_record():
    recs = [_rec("a"), _rec("b", review=Review("reviewed", "rv", "human", TS)), _rec("c", "ផ្សេង។")]
    kept, dropped = drop_exact_duplicates(recs)
    assert sorted(r.id for r in kept) == ["b", "c"]
    assert dropped == [{"id": "a", "duplicate_of": "b"}]


# ── Splitting ───────────────────────────────────────────────────────────

def test_group_split_has_no_leakage_and_is_reproducible():
    recs = import_rows(_flat_rows(60), dataset="unit").records
    rep = split_records(recs, seed=7)
    apply_split(recs, rep)
    assert find_leaks(recs) == []
    by_film = {}
    for r in recs:
        by_film.setdefault(r.groups["film_id"], set()).add(r.split)
    assert all(len(s) == 1 for s in by_film.values())
    assert split_records(recs, seed=7).assignments == rep.assignments
    assert sum(c["records"] for c in rep.counts().values()) == 60


def test_split_ratios_and_near_duplicate_merge():
    recs = [_rec(f"r{i:02d}", f"ប្រយោគ {i} ណាស់។") for i in range(40)]
    rep = split_records(recs, seed=1)
    counts = rep.counts()
    assert (counts["train"]["records"], counts["validation"]["records"], counts["test"]["records"]) == (32, 4, 4)
    merged = split_records(recs, seed=1, near_clusters=[["r00", "r01", "r02"]])
    assert merged.merged_by_near_duplicates == 2
    assert len({merged.assignments[i] for i in ("r00", "r01", "r02")}) == 1


def test_rejected_records_are_excluded_from_splits():
    recs = [_rec("a"), _rec("b", review=Review("rejected", "rv", "human", TS))]
    rep = split_records(recs)
    assert rep.excluded == ["b"] and "b" not in rep.assignments


# ── Import formats ──────────────────────────────────────────────────────

def test_import_csv_json_jsonl_and_rejects():
    rows = _flat_rows(5)
    rows.append({"id": "f000", "source_text": "dup", "khmer": "ស្ទួន។"})
    rows.append({"id": "bad", "source_text": "", "khmer": ""})
    rows.append({"id": "lvl", "source_text": "x", "khmer": "ក។", "slang_level": "lots"})
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        fields = sorted({k for r in rows for k in r})
        with (tmp / "d.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        (tmp / "d.json").write_text(json.dumps({"records": rows}, ensure_ascii=False), encoding="utf-8")
        (tmp / "d.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n{oops\n",
                                     encoding="utf-8")
        results = {s: import_file(tmp / f"d.{s}") for s in ("csv", "json", "jsonl")}
    for suffix, res in results.items():
        assert len(res.records) == 5, suffix
        codes = res.summary()["reject_reasons"]
        assert codes.get("duplicate_id") == 1 and codes.get("parse_error", 0) >= 1, (suffix, codes)
        assert {"missing_source_text", "missing_candidates"} <= set(codes), suffix
        rec = next(r for r in res.records if r.id == "f001")
        assert [c.style for c in rec.candidates] == ["natural", "literal"]
        assert rec.groups == {"film_id": "film1", "speaker_id": "S1"} and rec.provenance.license == "CC-BY-4.0"
        assert rec.group_key() == "film_id:film1"
    assert results["jsonl"].summary()["reject_reasons"]["parse_error"] == 2


def test_canonical_jsonl_round_trip_is_byte_stable():
    recs = import_rows(_flat_rows(10), dataset="unit").records
    with tempfile.TemporaryDirectory() as tmp:
        a = write_records(Path(tmp) / "a.jsonl", recs)
        b = write_records(Path(tmp) / "b.jsonl", read_records(a))
        assert a.read_bytes() == b.read_bytes()
        res = import_file(a)
        assert res.shape_counts == {"canonical": 10} and len(res.records) == 10


# ── Store, versions, export, review ─────────────────────────────────────

def test_versions_are_immutable_and_chained():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.jsonl"
        src.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in _flat_rows(12)), encoding="utf-8")
        store = DatasetStore("unit", root=Path(tmp) / "ds")
        store.import_file(src)
        v1 = store.create_version(note="first")
        assert v1["version"] == "v0001" and v1["parent"] is None and v1["record_count"] == 12
        try:
            store.create_version()
            raise AssertionError("unchanged snapshot should fail")
        except ValueError:
            pass
        records = store.load_working()
        records[0].review = Review("reviewed", "rv-1", "human", TS)
        store.save_working(records)
        v2 = store.create_version()
        assert v2["parent"] == "v0001" and v2["sha256"] != v1["sha256"] and v2["training_eligible"] == 1
        assert store.list_versions() == ["v0001", "v0002"] and store.verify_version("v0001")
        frozen = store.versions_dir / "v0001" / "records.jsonl"
        assert not os.access(frozen, os.W_OK)
        assert len(store.load_version("v0001")) == 12
        res = store.import_file(src)
        assert len(res.records) == 0 and res.summary()["reject_reasons"] == {"duplicate_id": 12}


def test_sft_export_defaults_to_reviewed_records():
    recs = [_rec("a"), _rec("b", review=Review("reviewed", "rv", "human", TS)), _rec("c")]
    recs[1].split = "train"
    with tempfile.TemporaryDirectory() as tmp:
        m = export_sft(recs, tmp)
        assert m["examples"] == 1 and not m["contains_unreviewed"] and list(m["files"]) == ["train"]
        line = json.loads((Path(tmp) / "train.jsonl").read_text(encoding="utf-8"))
        assert [x["role"] for x in line["messages"]] == ["system", "user", "assistant"]
        assert line["messages"][2]["content"] == "ខ្ញុំទៅផ្ទះហើយ។"
        assert json.loads(line["messages"][1]["content"])["relationship"] == "friends"
        m2 = export_sft(recs, tmp, statuses=("draft", "reviewed", "gold"))
        assert m2["examples"] == 3 and m2["contains_unreviewed"] and "unsplit" in m2["files"]


def test_review_sheet_applies_human_review_but_never_gold():
    recs = [_rec("a", origin="synthetic"), _rec("b"), _rec("c")]
    rows = [
        {"id": "a", "reviewer_id": "rv-9", "decision": "approved", "corrected_khmer": "ខ្ញុំទៅផ្ទះសិនហើយ។",
         "meaning_accuracy_1_5": "5", "naturalness_1_5": "4", "relationship_fit_1_5": "4"},
        {"id": "b", "reviewer_id": "", "decision": "approved"},
        {"id": "c", "reviewer_id": "rv-9", "decision": "rejected"},
        {"id": "zz", "reviewer_id": "rv-9", "decision": "approved"},
        {"id": "a", "reviewer_id": "", "decision": ""},
    ]
    res = apply_review_rows(recs, rows, reviewed_at=TS)
    assert res.applied == {"reviewed": 1, "rejected": 1} and res.skipped_blank == 1 and len(res.errors) == 2
    a = recs[0]
    assert a.status == "reviewed" and a.origin == "human_reviewed" and a.review.reviewer_type == "human"
    assert a.preferred_candidate().text == "ខ្ញុំទៅផ្ទះសិនហើយ។" and len(a.candidates) == 2
    assert a.quality.scores == {"semantic_accuracy": 5.0, "naturalness": 4.0} and a.quality.scored_by == "human"
    assert a.quality.extra == {"relationship_fit": 4.0}
    assert _codes(a) == set() and recs[1].status == "draft" and recs[2].status == "rejected"


def test_cli_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.jsonl"
        src.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in _flat_rows(20)), encoding="utf-8")
        root = str(Path(tmp) / "ds")
        common = ["--name", "unit", "--root", root]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert cli_main(["dataset", "import", str(src), *common]) == 0
            assert cli_main(["dataset", "validate", *common]) == 0
            assert cli_main(["dataset", "dedupe", *common]) == 0
            assert cli_main(["dataset", "split", *common, "--seed", "3"]) == 0
            assert cli_main(["dataset", "report", *common, "--json"]) == 0
            assert cli_main(["dataset", "version", *common]) == 0
            assert cli_main(["dataset", "export", *common, "--format", "jsonl", "-o", str(Path(tmp) / "o.jsonl")]) == 0
            assert cli_main(["dataset", "export", *common, "--include-unreviewed", "-o", str(Path(tmp) / "sft")]) == 0
        store = DatasetStore("unit", root=root)
        assert store.list_versions() == ["v0001"]
        assert all(r.split for r in store.load_version("v0001"))
        assert len((Path(tmp) / "o.jsonl").read_text(encoding="utf-8").splitlines()) == 20
        manifest = json.loads((Path(tmp) / "sft" / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["examples"] == 20 and manifest["source"]["version"] == "v0001"


# ── Genre mapping, review sheets, promotion ─────────────────────────────

def _ksld_row(rid: str, genre: str) -> dict[str, str]:
    return {"id": rid, "scene_id": "SCENE-1", "source_language": "en", "target_language": "km",
            "source_text": "Are you okay?", "target_text": "មិនអីទេឬ?", "genre": genre, "emotion": "caring",
            "relationship": "sibling", "speech_register": "casual", "region": "unspecified",
            "regional_verified": "False", "slang_level": "0", "profanity_level": "0",
            "character_id": "CHAR-01", "listener_id": "CHAR-02", "tts_text": "មិនអីទេឬ?",
            "variation_method": "seed_translation", "review_status": "needs_native_review",
            "reviewer_id": "", "quality_score": "", "split": "train", "notes": ""}


def test_ksld_genre_mappings_for_care_surprise_excited():
    rows = [_ksld_row(f"k{i}", g) for i, g in enumerate(("care", "surprise", "excited", "mystery"))]
    res = import_rows(rows, dataset="ksld", file="x.jsonl")
    cats = {r.metadata["source_genre"]: r.category for r in res.records}
    assert cats == {"care": "family", "surprise": "everyday", "excited": "comedy_sarcasm", "mystery": None}
    assert res.warnings.get("missing_category") == 1


def _read_sheet(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def test_review_export_has_reviewed_at_and_prefilled_context():
    from claynext.models.datasets.review import REVIEWER_COLUMNS, export_review_sheet

    rec = _rec("a", speaker_id="CHAR-01")
    rec.quality.scores["naturalness"] = 3.0
    rec.quality.scored_by = "model"
    with tempfile.TemporaryDirectory() as tmp:
        rows = _read_sheet(export_review_sheet([rec, _rec("b")], Path(tmp) / "sheet.csv"))
    assert [r["id"] for r in rows] == ["a", "b"]
    row = rows[0]
    assert "reviewed_at" in row and "reviewer_id" in row and "decision" in row
    assert row["source_text"] == "I'm going home." and row["khmer_current"] == "ខ្ញុំទៅផ្ទះហើយ។"
    assert row["status"] == "draft" and row["current_naturalness"] == "3.0" and row["current_scored_by"] == "model"
    assert all(row[c] == "" for c in REVIEWER_COLUMNS)


def test_review_apply_prefers_sheet_timestamp_then_argument_then_clock():
    from claynext.models.datasets.review import export_review_sheet

    recs = [_rec("a"), _rec("b"), _rec("c")]
    with tempfile.TemporaryDirectory() as tmp:
        rows = _read_sheet(export_review_sheet(recs, Path(tmp) / "sheet.csv"))
    sheet_ts = "2026-09-30T08:15:00+07:00"
    for row in rows:
        row.update(reviewer_id="rv-1", decision="approved", naturalness="4")
    rows[0]["reviewed_at"] = sheet_ts
    res = apply_review_rows(recs, rows[:2], reviewed_at=TS)
    assert res.timestamp_source == {"sheet": 1, "argument": 1} and not res.errors
    assert recs[0].review.reviewed_at == sheet_ts and recs[1].review.reviewed_at == TS
    assert recs[0].quality.scores["naturalness"] == 4.0 and recs[0].quality.scored_by == "human"
    res = apply_review_rows(recs, rows[2:])
    assert res.timestamp_source == {"clock": 1} and recs[2].review.reviewed_at
    bad = apply_review_rows([_rec("d")], [{"id": "d", "reviewer_id": "rv", "decision": "approved",
                                          "reviewed_at": "last tuesday"}])
    assert "not ISO 8601" in bad.errors[0]["error"]


def test_review_sheet_cannot_promote_to_gold():
    recs = [_rec("a"), _rec("b")]
    res = apply_review_rows(recs, [{"id": "a", "reviewer_id": "", "decision": "gold"},
                                   {"id": "b", "reviewer_id": "rv", "decision": "promote"}])
    assert len(res.errors) == 2 and "reviewer_id is missing" in res.errors[0]["error"]
    assert {r.status for r in recs} == {"draft"}


def test_promote_blocks_gold_for_unreviewed_synthetic_and_missing_license():
    from claynext.models.datasets.promote import promote_records

    unreviewed = _rec("s1", origin="synthetic", review=Review("staging"))
    model_only = _rec("s2", origin="synthetic", review=Review("reviewed", "judge", "model", TS))
    no_license = _rec("h1", origin="human_authored", review=Review("reviewed", "rv", "human", TS),
                      provenance=Provenance(dataset="unit"))
    draft = _rec("d1", origin="human_authored", review=Review("draft", "rv", "human", TS))
    recs = [unreviewed, model_only, no_license, draft]
    res = promote_records(recs, "gold", ids=["s1", "s2", "h1", "d1", "nope"])
    blocked = {b["id"]: b["reasons"] for b in res.blocked}
    assert {"missing_reviewer_id", "missing_reviewed_at", "synthetic_without_human_review"} <= set(blocked["s1"])
    assert blocked["s2"] == ["synthetic_without_human_review"]
    assert blocked["h1"] == ["missing_license"]
    assert blocked["d1"] == ["transition_draft_to_gold_not_allowed"]
    assert res.promoted == [] and res.unknown_ids == ["nope"]
    assert [r.status for r in recs] == ["staging", "reviewed", "reviewed", "draft"]
    # Turning the licence check off does not make gold possible without a licence.
    assert promote_records([no_license], "gold", require_license=False).blocked


def test_promote_succeeds_for_reviewed_human_authored_with_license():
    from claynext.models.datasets.promote import promote_records

    rec = _rec("h1", origin="human_authored", review=Review("reviewed", "rv-3", "human", TS))
    dry = promote_records([rec], "gold", dry_run=True, by="lead-1")
    assert dry.promoted == ["h1"] and rec.status == "reviewed"
    res = promote_records([rec], "gold", by="lead-1")
    assert res.promoted == ["h1"] and rec.status == "gold" and _codes(rec) == set()
    assert rec.metadata["promotions"][0]["from"] == "reviewed" and rec.metadata["promotions"][0]["by"] == "lead-1"
    assert promote_records([rec], "gold").already == ["h1"]
    # Reviewed synthetic data that a human approved (origin human_reviewed) can also become gold.
    approved = _rec("s1", origin="synthetic")
    apply_review_rows([approved], [{"id": "s1", "reviewer_id": "rv-4", "decision": "approved"}], reviewed_at=TS)
    assert approved.origin == "human_reviewed"
    assert promote_records([approved], "gold").promoted == ["s1"]


def test_promote_transitions_and_bulk_mode():
    from claynext.models.datasets.promote import promote_records

    recs = [_rec("a"), _rec("b", review=Review("reviewed", "rv", "human", TS)), _rec("c")]
    res = promote_records(recs, "staging")
    assert res.promoted == ["a", "c"] and recs[1].status == "reviewed"
    res = promote_records(recs, "reviewed")
    assert sorted(b["id"] for b in res.blocked) == ["a", "c"]
    assert promote_records(recs, "reviewed", ids=["b"]).already == ["b"]


def test_cli_review_loop():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        rows = _flat_rows(4)
        src = tmp / "in.jsonl"
        src.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
        common = ["--name", "unit", "--root", str(tmp / "ds")]
        sheet = tmp / "sheet.csv"
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            assert cli_main(["dataset", "import", str(src), *common]) == 0
            assert cli_main(["dataset", "review-export", *common, "--out", str(sheet)]) == 0
            filled = _read_sheet(sheet)
            for row in filled[:2]:
                row.update(reviewer_id="rv-1", decision="approved", reviewed_at="2026-10-20T09:00:00+07:00")
            with sheet.open("w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(filled[0]))
                writer.writeheader()
                writer.writerows(filled)
            assert cli_main(["dataset", "review-apply", str(sheet), *common]) == 0
            assert cli_main(["dataset", "promote", *common, "--to", "gold", "--ids", "f000,f002"]) == 1
            assert cli_main(["dataset", "promote", *common, "--to", "gold", "--ids", "f000", "--by", "lead"]) == 0
        recs = {r.id: r for r in DatasetStore("unit", root=tmp / "ds").load_working()}
        assert recs["f000"].status == "gold" and recs["f000"].review.reviewed_at == "2026-10-20T09:00:00+07:00"
        assert recs["f001"].status == "reviewed" and recs["f002"].status == "draft"


# ── The user's Khmer Spoken Language Dataset ────────────────────────────

def test_import_real_ksld_dataset_if_present():
    jsonl = KSLD_DIR / "dialogues.jsonl"
    if not jsonl.is_file():
        print("  (skipped: KSLD dataset folder not found)")
        return
    res = import_file(jsonl)
    assert len(res.records) == 1000 and not res.rejects, res.summary()
    assert res.shape_counts == {"ksld": 1000}
    recs = res.records
    assert {r.status for r in recs} == {"draft"} and {r.origin for r in recs} == {"synthetic"}
    assert all(r.provenance.license is None for r in recs)
    assert all(r.regional.region is None and not r.regional.verified for r in recs)
    assert all(r.tts_text is None and r.metadata.get("tts_text_placeholder") for r in recs)
    assert len({r.group_key() for r in recs}) == 100
    assert all(r.category for r in recs) and "missing_category" not in res.warnings
    csv_res = import_file(KSLD_DIR / "dialogues.csv")
    for a, b in zip(csv_res.records, recs, strict=True):
        assert a.provenance.file == "dialogues.csv" and b.provenance.file == "dialogues.jsonl"
        a.provenance.file = b.provenance.file
        assert a == b, a.id

    dup = find_duplicates(recs)
    assert dup.exact_groups == []
    rep = split_records(recs, near_clusters=dup.near_clusters)
    apply_split(recs, rep)
    assert find_leaks(recs, near_clusters=dup.near_clusters) == []
    assert sum(c["records"] for c in rep.counts().values()) == 1000


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
