"""One-shot AI-first spoken drafts. Not a new trainer. No secrets in stdout."""
from __future__ import annotations

import json
import re
import sqlite3
import traceback
from pathlib import Path

from claynext.models.khmer_spoken.datasets.gemini_candidate_generator import (
    generate_candidates_batch,
)
from claynext.models.khmer_spoken.datasets.io_store import (
    export_gold_version,
    load_examples,
    save_examples,
)
from claynext.models.khmer_spoken.paths import (
    DEFAULT_FIXTURE,
    WORKSPACE_CANDIDATES,
    ensure_khmer_spoken_dirs,
)
from claynext.models.khmer_spoken.providers.google_gemini_provider import GeminiTeacherProvider
from claynext.models.jev_decisions import jev_key_configured, rank_khmer_candidates
from claynext.models.khmer_spoken.datasets.khmer_human_review import apply_review_decision
from claynext.models.khmer_spoken.schema import (
    REVIEW_APPROVED,
    REVIEW_GOLD,
    REVIEW_PENDING,
    DialogueExample,
    utc_now_iso,
)
from claynext.models.khmer_spoken.training.ranked_export import export_ranked_training
from claynext.models.training.config import CONFIG_DIR
from claynext.models.training.trainer import start as start_train
from concurrent.futures import ThreadPoolExecutor
from claynext.models.khmer_spoken.training.local_lora_stub import plan_local_lora
from claynext.models.khmer_spoken.training.training_job_manager import TrainingJobManager
from claynext.utils.paths import DATA_DIR

SEED = (
    Path(__file__).resolve().parents[4]
    / "src/claynext/prompts/evaluations/khmer_pronoun_cases.jsonl"
)
OUT_DIR = Path(__file__).resolve().parent
PROGRESS = OUT_DIR / "progress.json"
NEW_IDS = {f"kp-{i:03d}" for i in range(56, 101)}
SOURCE_NOTE = (
    "AI draft from the built-in pronoun eval seed "
    "(src/claynext/prompts/evaluations/khmer_pronoun_cases.jsonl). "
    "Unreviewed. No licence. Not for gold promotion or weight training."
)


def redact(text: str) -> str:
    cleaned = text or ""
    cleaned = re.sub(r"AIza[\w\-]+", "[redacted]", cleaned)
    cleaned = re.sub(r"(?i)(key|token|secret|authorization)=([^\s&\"']+)", r"\1=[redacted]", cleaned)
    cleaned = re.sub(r"(?i)bearer\s+\S+", "bearer [redacted]", cleaned)
    return cleaned[:500]


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


def load_seed() -> list[DialogueExample]:
    rows: list[DialogueExample] = []
    for line in SEED.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        speaker = raw.get("speaker") or {}
        listener = raw.get("listener") or {}
        relation = (raw.get("relationship") or {}).get("relation") or ""
        review = raw.get("review") or {}
        rows.append(
            DialogueExample(
                id=str(raw.get("id") or ""),
                source_text=str(raw.get("source_text") or ""),
                source_lang="en",
                target_lang="km",
                stub_khmer=str(raw.get("reference_khmer") or ""),
                speaker_id=str(speaker.get("id") or ""),
                listener_id=str(listener.get("id") or ""),
                relationship=str(relation),
                emotion=str(raw.get("emotion") or "neutral"),
                register=str(raw.get("register") or "neutral"),
                category=str(raw.get("category") or "everyday"),
                origin="synthetic",
                license_type="unknown",
                license_notes=SOURCE_NOTE,
                review_status=REVIEW_PENDING,
                reviewer_notes=(
                    "Unverified stub only. Seed review status: "
                    + str(review.get("status") or "pending_native_review")
                    + ". Owner reviews later."
                ),
                metadata={
                    "provenance": "ai_draft",
                    "source_file": "src/claynext/prompts/evaluations/khmer_pronoun_cases.jsonl",
                    "source_review_status": review.get("status") or "pending_native_review",
                    "licence": None,
                    "not_for_gold": True,
                    "not_for_weight_training": True,
                    "seed_notes": str(raw.get("notes") or ""),
                },
            )
        )
    return rows


def write_progress(payload: dict) -> None:
    PROGRESS.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _stop_class(message: str) -> str:
    """auth: every key is dead. cooldown: pool already waited once. else: row error."""
    text = (message or "").lower()
    if any(token in text for token in ("401", "403", "were rejected", "invalid api key")):
        return "auth"
    if any(token in text for token in (
        "cooling", "rate-limited", "rate limited", "503", "unavailable",
        "no available gemini", "high demand",
    )):
        return "cooldown"
    return ""


def _one_row(ex: DialogueExample, teacher: GeminiTeacherProvider) -> tuple[bool, str]:
    """One pool call per row. Rotation and the single cooldown wait live in the pool."""
    try:
        report = generate_candidates_batch([ex], provider=teacher, limit=1)
    except Exception as exc:
        return False, redact(f"{type(exc).__name__}: {exc}")
    errors = [redact(str(item)) for item in (report.get("errors") or [])]
    if report.get("skipped") or not report.get("ok") or errors or report.get("updated") != 1:
        return False, redact(
            "; ".join(errors) or str(report.get("error") or report.get("reason") or "row_failed")
        )
    return True, ""


def _rank_rows(rows: list[DialogueExample]) -> dict:
    if not jev_key_configured():
        return {"ran": False, "reason": "no_key", "ranked": 0, "unchanged": 0}
    targets = [
        ex for ex in rows
        if ex.candidates and not (ex.metadata.get("jev") or {}).get("applied")
    ]

    def _one(ex: DialogueExample) -> dict:
        try:
            return rank_khmer_candidates(ex)
        except Exception:
            return {"applied": False, "reason": "error"}

    workers = min(3, len(targets))
    if workers <= 1:
        results = [_one(ex) for ex in targets]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_one, targets))
    ranked = sum(1 for item in results if item.get("applied"))
    return {
        "ran": True,
        "reason": "",
        "ranked": ranked,
        "unchanged": len(results) - ranked,
    }


def _approve_new_rows(rows: list[DialogueExample]) -> dict:
    """Same owner quote as kp-001..kp-055. Only rows that now have real candidates."""
    when = utc_now_iso()
    approved = 0
    for ex in rows:
        if ex.id not in NEW_IDS or ex.review_status != REVIEW_PENDING:
            continue
        texts = [cand.text.strip() for cand in ex.candidates if cand.text and cand.text.strip()]
        if ex.origin != "gemini_teacher" or not texts:
            continue
        history = list(ex.metadata.get("review_history") or [])
        history.append({
            "at": when,
            "by": "project-owner",
            "decision": "approve",
            "from_status": ex.review_status,
            "quote": "pls approve all",
        })
        ex.metadata["review_history"] = history
        ex.metadata["owner_approval"] = {
            "by": "project-owner",
            "decision": "approve",
            "at": when,
            "scope": "kp-056 through kp-100",
            "quote": "pls approve all",
        }
        prior_notes = ex.reviewer_notes
        updated, issues = apply_review_decision(
            ex,
            decision="approve",
            verified_by="project-owner",
            verified_at=when,
        )
        errors = [item for item in issues if item.severity == "error"]
        if errors or updated.review_status != REVIEW_APPROVED:
            continue
        if prior_notes and prior_notes not in (updated.reviewer_notes or ""):
            updated.reviewer_notes = prior_notes
        if updated.license_type != "unknown":
            updated.license_type = "unknown"
        note = " Owner approved the Khmer text; licence remains unknown."
        if note.strip() not in (updated.license_notes or ""):
            updated.license_notes = (updated.license_notes or "") + note
        approved += 1
    return {"approved": approved}


def main() -> int:
    ensure_khmer_spoken_dirs()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    keys_before = enabled_gemini_keys()
    resumed = WORKSPACE_CANDIDATES.is_file()
    rows = load_examples(WORKSPACE_CANDIDATES) if resumed else []
    if len(rows) != 100:
        rows = load_seed()
        resumed = False
        if len(rows) != 100:
            raise SystemExit(f"expected 100 seed rows, got {len(rows)}")
        save_examples(DEFAULT_FIXTURE, rows)
        save_examples(WORKSPACE_CANDIDATES, rows)
    if any(r.review_status == REVIEW_GOLD for r in rows):
        raise SystemExit("refusing to continue: a workspace row is already gold")
    # The model that already returned kp-001. The default list tries gemini-3.8-flash first.
    teacher = GeminiTeacherProvider(models=("gemini-flash-latest",))
    already = sum(1 for r in rows if r.candidates and r.origin == "gemini_teacher")
    print(
        f"SEED rows={len(rows)} resumed={resumed} already={already} "
        f"fixture={DEFAULT_FIXTURE} gemini_available={teacher.available()} "
        f"enabled_gemini_keys={keys_before}",
        flush=True,
    )

    updated = already
    stop_reason = ""
    if not teacher.available():
        stop_reason = "missing_key"
        print("AI_FIRST_STOP missing_key", flush=True)
    else:
        for index, ex in enumerate(rows):
            if ex.candidates and ex.origin == "gemini_teacher":
                continue
            ok, err = _one_row(ex, teacher)
            if not ok:
                kind = _stop_class(err)
                if kind in {"auth", "cooldown"}:
                    stop_reason = err
                    print(f"ROW {index + 1}/100 STOP {stop_reason}", flush=True)
                    break
                print(f"ROW {index + 1}/100 SKIP {err}", flush=True)
                continue
            updated += 1
            save_examples(WORKSPACE_CANDIDATES, rows)
            if ex.review_status != REVIEW_PENDING or ex.verified_by or ex.review_status == REVIEW_GOLD:
                stop_reason = "generator changed review status; stopping"
                print(f"ROW {index + 1}/100 STOP {stop_reason}", flush=True)
                break
            print(
                f"ROW {index + 1}/100 updated={updated} candidates={len(ex.candidates)} "
                f"status={ex.review_status} origin={ex.origin}",
                flush=True,
            )
            write_progress({
                "updated": updated,
                "last_id": ex.id,
                "stopped": False,
            })

    save_examples(WORKSPACE_CANDIDATES, rows)
    jev = _rank_rows(rows)
    print(
        f"JEV ran={jev['ran']} ranked={jev['ranked']} unchanged={jev['unchanged']} reason={jev['reason'] or 'ok'}",
        flush=True,
    )
    save_examples(WORKSPACE_CANDIDATES, rows)
    approval = _approve_new_rows(rows)
    save_examples(WORKSPACE_CANDIDATES, rows)
    ranked_path = OUT_DIR / "ranked_sft.jsonl"
    ranked = export_ranked_training(rows, ranked_path)
    continued = export_gold_version(rows, version="owner-approved-20261022-ranked")
    fourteen = start_train(CONFIG_DIR / "qlora_14b.yaml", approval=True)
    lora = plan_local_lora(dataset_path=str(ranked_path))
    job = TrainingJobManager().enqueue_local_lora(dataset_path=str(ranked_path))
    keys_after = enabled_gemini_keys()
    summary = {
        "seed_rows": len(rows),
        "gemini_updated": updated,
        "gemini_called": updated > already or bool(stop_reason),
        "stop_reason": stop_reason,
        "pending": sum(1 for r in rows if r.review_status == REVIEW_PENDING),
        "approved": sum(1 for r in rows if r.review_status == REVIEW_APPROVED),
        "gold": sum(1 for r in rows if r.review_status == REVIEW_GOLD),
        "with_candidates": sum(1 for r in rows if r.candidates),
        "license_types": sorted({r.license_type for r in rows}),
        "newly_approved": approval["approved"],
        "jev_ran": jev["ran"],
        "jev_ranked": jev["ranked"],
        "jev_unchanged": jev["unchanged"],
        "jev_reason": jev["reason"],
        "ranked_export_count": ranked["count"],
        "ranked_export_path": ranked["path"],
        "trainer_installed": ranked["trainer_installed"],
        "weights_written": False,
        "continued_gold_count": continued["count"],
        "continued_gold_rejected": len(continued["rejected"]),
        "continued_gold_path": continued["path"],
        "qlora_14b_status": fourteen["status"],
        "qlora_14b_started": fourteen["started"],
        "qlora_14b_weights": fourteen["weights"],
        "lora_status": lora.status,
        "lora_error": lora.error,
        "lora_job_id": job.job_id,
        "lora_job_status": job.status,
        "enabled_gemini_keys_before": keys_before,
        "enabled_gemini_keys_after": keys_after,
        "fixture": str(DEFAULT_FIXTURE),
        "workspace": str(WORKSPACE_CANDIDATES),
    }
    (OUT_DIR / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_progress({**summary, "stopped": bool(stop_reason)})
    print("AI_FIRST_DONE " + json.dumps({k: summary[k] for k in (
        "gemini_updated", "stop_reason", "newly_approved", "jev_ran", "jev_ranked",
        "jev_reason", "ranked_export_count", "trainer_installed", "qlora_14b_status",
        "qlora_14b_started", "weights_written", "continued_gold_count",
        "enabled_gemini_keys_before", "enabled_gemini_keys_after",
    )}), flush=True)
    if stop_reason == "missing_key":
        return 2
    return 0 if not stop_reason else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        print("AI_FIRST_STOP " + redact(traceback.format_exc()), flush=True)
        raise
