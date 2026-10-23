"""Fill Gemini candidates for already-approved rows that still have none.

Does not re-approve, does not change licence, and does not start training.
run_ai_first.py skips these rows: the teacher generator refuses approved
status, and that script would rewrite owner-approved-20261022-ranked.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from claynext.models.jev_decisions import jev_key_configured, rank_khmer_candidates
from claynext.models.khmer_spoken.datasets.io_store import export_gold_version, load_examples, save_examples
from claynext.models.khmer_spoken.paths import WORKSPACE_CANDIDATES
from claynext.models.khmer_spoken.providers.google_gemini_provider import GeminiTeacherProvider
from claynext.models.khmer_spoken.schema import REVIEW_APPROVED, REVIEW_GOLD, TranslationCandidate
from claynext.models.khmer_spoken.training.ranked_export import export_ranked_training
from claynext.utils.paths import DATA_DIR

OUT_DIR = Path(__file__).resolve().parent
PROGRESS = OUT_DIR / "remainder_progress.json"
SUMMARY = OUT_DIR / "remainder_run.json"
VERSION = "owner-approved-20261023-remainder"
TARGET_IDS = ["kp-057", *[f"kp-{i:03d}" for i in range(60, 101)]]
PROTECTED = (
    Path("data/khmer_spoken/versions/owner-approved-20261022/dialogue.jsonl"),
    Path("data/khmer_spoken/versions/owner-approved-20261022-rejected-cleared/dialogue.jsonl"),
    Path("data/khmer_spoken/versions/owner-approved-20261022-ranked/dialogue.jsonl"),
)


def redact(text: str) -> str:
    cleaned = text or ""
    cleaned = re.sub(r"AIza[\w\-]+", "[redacted]", cleaned)
    cleaned = re.sub(r"(?i)(key|token|secret|authorization)=([^\s&\"']+)", r"\1=[redacted]", cleaned)
    cleaned = re.sub(r"(?i)bearer\s+\S+", "bearer [redacted]", cleaned)
    return cleaned[:500]


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def enabled_gemini_keys() -> int:
    db = DATA_DIR / "claynext.db"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = con.execute(
            "SELECT COUNT(*) FROM api_keys WHERE provider = 'gemini' AND enabled = 1"
        ).fetchone()
    finally:
        con.close()
    return int(row[0] if row else 0)


def _stop_class(message: str) -> str:
    text = (message or "").lower()
    if any(token in text for token in ("401", "403", "were rejected", "invalid api key")):
        return "auth"
    if any(token in text for token in (
        "cooling", "rate-limited", "rate limited", "503", "unavailable",
        "no available gemini", "high demand",
    )):
        return "cooldown"
    return ""


def _freeze(ex) -> tuple:
    return (
        ex.review_status,
        ex.verified_by,
        ex.verified_at,
        ex.approved_text,
        ex.license_type,
        ex.license_notes,
        ex.reviewer_notes,
        ex.stub_khmer,
    )


def _restore(ex, frozen: tuple) -> None:
    (
        ex.review_status,
        ex.verified_by,
        ex.verified_at,
        ex.approved_text,
        ex.license_type,
        ex.license_notes,
        ex.reviewer_notes,
        ex.stub_khmer,
    ) = frozen


def _attach(ex, teacher: GeminiTeacherProvider) -> tuple[bool, str]:
    """One teacher call. The pool rotates on timeout/503 and waits once."""
    frozen = _freeze(ex)
    prior = list(ex.candidates)
    try:
        result = teacher.generate_khmer_candidates(
            ex.source_text,
            source_lang=ex.source_lang,
            emotion=ex.emotion,
            register=ex.register,
            speaker_id=ex.speaker_id,
            listener_id=ex.listener_id,
        )
    except Exception as exc:
        _restore(ex, frozen)
        ex.candidates = prior
        return False, redact(f"{type(exc).__name__}: {exc}")
    if result.skipped or not result.ok:
        _restore(ex, frozen)
        ex.candidates = prior
        return False, redact(result.error or "row_failed")
    new_cands: list[TranslationCandidate] = []
    for row in result.candidates:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        new_cands.append(
            TranslationCandidate(
                text=text,
                style=str(row.get("style") or "natural"),
                provider="gemini_teacher",
                model=result.model,
                notes=str(row.get("notes") or ""),
                emotion=str(row.get("emotion") or ex.emotion),
                register=str(row.get("register") or ex.register),
            )
        )
    if not new_cands and result.text:
        new_cands.append(
            TranslationCandidate(
                text=result.text[:2000],
                style="natural",
                provider="gemini_teacher",
                model=result.model,
                notes="raw_fallback",
            )
        )
    _restore(ex, frozen)
    if not new_cands:
        ex.candidates = prior
        return False, "no candidates parsed"
    ex.candidates = prior + new_cands
    if ex.origin == "synthetic":
        ex.origin = "gemini_teacher"
    if _freeze(ex) != frozen:
        _restore(ex, frozen)
        ex.candidates = prior
        return False, "review fields changed; row reverted"
    return True, ""


def _rank_new(rows: list) -> dict:
    if not jev_key_configured():
        return {"ran": False, "reason": "no_key", "ranked": 0, "unchanged": 0, "ids": []}
    targets = [
        ex for ex in rows
        if ex.id in set(TARGET_IDS)
        and ex.candidates
        and not (ex.metadata.get("jev") or {}).get("applied")
    ]

    def _one(ex) -> tuple[str, dict]:
        before = list(ex.candidates)
        try:
            result = rank_khmer_candidates(ex)
        except Exception:
            ex.candidates = before
            return ex.id, {"applied": False, "reason": "error"}
        if not result.get("applied"):
            ex.candidates = before
            jev = ex.metadata.get("jev") or {}
            if not jev.get("applied"):
                ex.metadata.pop("jev", None)
        return ex.id, result

    workers = min(3, len(targets))
    if workers <= 1:
        results = [_one(ex) for ex in targets]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_one, targets))
    ranked_ids = [item_id for item_id, item in results if item.get("applied")]
    return {
        "ran": True,
        "reason": "",
        "ranked": len(ranked_ids),
        "unchanged": len(results) - len(ranked_ids),
        "ids": ranked_ids,
        "reasons": {
            item_id: str(item.get("reason") or "applied")
            for item_id, item in results
        },
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    protected_before = {str(path): file_sha(path) for path in PROTECTED}
    keys_before = enabled_gemini_keys()
    rows = load_examples(WORKSPACE_CANDIDATES)
    if len(rows) != 100:
        raise SystemExit(f"expected 100 workspace rows, got {len(rows)}")
    if any(ex.review_status == REVIEW_GOLD for ex in rows):
        raise SystemExit("refusing to continue: a workspace row is already gold")
    if any(ex.review_status != REVIEW_APPROVED for ex in rows):
        raise SystemExit("refusing to continue: workspace is not fully approved")
    by_id = {ex.id: ex for ex in rows}
    missing = [item for item in TARGET_IDS if item not in by_id]
    if missing:
        raise SystemExit(f"missing target ids: {missing}")
    todo = [
        by_id[item] for item in TARGET_IDS
        if not any((cand.text or "").strip() for cand in by_id[item].candidates)
    ]
    teacher = GeminiTeacherProvider(models=("gemini-flash-latest",))
    print(
        f"REMAINDER targets={len(TARGET_IDS)} empty={len(todo)} "
        f"gemini_available={teacher.available()} enabled_gemini_keys={keys_before}",
        flush=True,
    )
    filled: list[str] = []
    still_empty: dict[str, str] = {}
    stop_reason = ""
    if not teacher.available():
        stop_reason = "missing_key"
        for ex in todo:
            still_empty[ex.id] = "missing_key"
        print("REMAINDER_STOP missing_key", flush=True)
    else:
        for index, ex in enumerate(todo, start=1):
            ok, err = _attach(ex, teacher)
            if not ok:
                kind = _stop_class(err)
                still_empty[ex.id] = err or "row_failed"
                if kind in {"auth", "cooldown"}:
                    stop_reason = err
                    for rest in todo[index:]:
                        if rest.id not in still_empty and rest.id not in filled:
                            still_empty[rest.id] = "not_attempted_after_stop"
                    print(f"ROW {ex.id} {index}/{len(todo)} STOP {stop_reason}", flush=True)
                    break
                print(f"ROW {ex.id} {index}/{len(todo)} SKIP {err}", flush=True)
                save_examples(WORKSPACE_CANDIDATES, rows)
                continue
            filled.append(ex.id)
            save_examples(WORKSPACE_CANDIDATES, rows)
            PROGRESS.write_text(json.dumps({
                "filled": len(filled),
                "last_id": ex.id,
                "candidates": len(ex.candidates),
                "stopped": False,
            }, ensure_ascii=False) + "\n", encoding="utf-8")
            print(
                f"ROW {ex.id} {index}/{len(todo)} candidates={len(ex.candidates)} "
                f"status={ex.review_status} origin={ex.origin} license={ex.license_type}",
                flush=True,
            )

    save_examples(WORKSPACE_CANDIDATES, rows)
    jev = _rank_new(rows) if filled else {
        "ran": False, "reason": "no_new_candidates", "ranked": 0, "unchanged": 0, "ids": [],
    }
    print(
        f"JEV ran={jev['ran']} ranked={jev['ranked']} unchanged={jev['unchanged']} "
        f"reason={jev['reason'] or 'ok'}",
        flush=True,
    )
    save_examples(WORKSPACE_CANDIDATES, rows)

    ranked_path = OUT_DIR / "ranked_sft.jsonl"
    ranked = export_ranked_training(rows, ranked_path)
    version_path = ""
    version_count = 0
    version_rejected = 0
    if filled:
        exported = export_gold_version(rows, version=VERSION)
        version_path = exported["path"]
        version_count = exported["count"]
        version_rejected = len(exported["rejected"])
        export_ranked_training(rows, Path(version_path).parent / "ranked.jsonl")

    empty_now = [
        ex.id for ex in rows
        if ex.id in set(TARGET_IDS)
        and not any((cand.text or "").strip() for cand in ex.candidates)
    ]
    protected_after = {str(path): file_sha(path) for path in PROTECTED}
    summary = {
        "target_rows": len(TARGET_IDS),
        "empty_at_start": len(todo),
        "filled": len(filled),
        "filled_ids": filled,
        "still_empty": empty_now,
        "still_empty_reasons": {item: still_empty.get(item, "") for item in empty_now},
        "stop_reason": stop_reason,
        "review_status": sorted({ex.review_status for ex in rows}),
        "license_types": sorted({ex.license_type for ex in rows}),
        "newly_approved": 0,
        "already_approved": sum(1 for ex in rows if ex.review_status == REVIEW_APPROVED),
        "with_candidates": sum(1 for ex in rows if ex.candidates),
        "target_with_candidates": sum(
            1 for ex in rows
            if ex.id in set(TARGET_IDS) and any((c.text or "").strip() for c in ex.candidates)
        ),
        "jev_ran": jev["ran"],
        "jev_ranked": jev["ranked"],
        "jev_unchanged": jev["unchanged"],
        "jev_reason": jev["reason"],
        "jev_ranked_ids": jev.get("ids") or [],
        "jev_reasons": jev.get("reasons") or {},
        "ranked_export_count": ranked["count"],
        "ranked_export_path": ranked["path"],
        "trainer_installed": ranked["trainer_installed"],
        "weights_written": False,
        "training_started": False,
        "qlora_14b_started": False,
        "new_version": VERSION if filled else "",
        "new_version_count": version_count,
        "new_version_rejected": version_rejected,
        "new_version_path": version_path,
        "protected_unchanged": protected_before == protected_after,
        "enabled_gemini_keys_before": keys_before,
        "enabled_gemini_keys_after": enabled_gemini_keys(),
        "workspace": str(WORKSPACE_CANDIDATES),
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PROGRESS.write_text(json.dumps({**summary, "stopped": bool(stop_reason)}, ensure_ascii=False) + "\n", encoding="utf-8")
    print("REMAINDER_DONE " + json.dumps({
        "filled": summary["filled"],
        "still_empty": summary["still_empty"],
        "stop_reason": summary["stop_reason"],
        "jev_ran": summary["jev_ran"],
        "jev_ranked": summary["jev_ranked"],
        "jev_unchanged": summary["jev_unchanged"],
        "ranked_export_count": summary["ranked_export_count"],
        "ranked_export_path": summary["ranked_export_path"],
        "new_version_path": summary["new_version_path"],
        "new_version_count": summary["new_version_count"],
        "weights_written": summary["weights_written"],
        "training_started": summary["training_started"],
        "qlora_14b_started": summary["qlora_14b_started"],
        "protected_unchanged": summary["protected_unchanged"],
        "license_types": summary["license_types"],
        "newly_approved": summary["newly_approved"],
    }, ensure_ascii=False), flush=True)
    if not summary["protected_unchanged"]:
        return 3
    if stop_reason == "missing_key":
        return 2
    return 0 if not stop_reason else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        print("REMAINDER_STOP " + redact(traceback.format_exc()), flush=True)
        raise
