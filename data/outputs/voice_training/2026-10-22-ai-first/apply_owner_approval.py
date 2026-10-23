"""Record project-owner approval on kp-001..kp-055. Does not call Gemini."""
from __future__ import annotations

import json
from pathlib import Path

from claynext.models.khmer_spoken.datasets.io_store import (
    export_gold_version,
    load_examples,
    save_examples,
)
from claynext.models.khmer_spoken.datasets.khmer_human_review import apply_review_decision
from claynext.models.khmer_spoken.paths import WORKSPACE_CANDIDATES
from claynext.models.khmer_spoken.schema import REVIEW_APPROVED, REVIEW_PENDING, utc_now_iso
from claynext.models.khmer_spoken.training.local_lora_stub import plan_local_lora

APPROVED_IDS = {f"kp-{i:03d}" for i in range(1, 56)}
REVIEWER = "project-owner"
WHEN = utc_now_iso()


def main() -> int:
    rows = load_examples(WORKSPACE_CANDIDATES)
    if len(rows) != 100:
        raise SystemExit(f"expected 100 workspace rows, got {len(rows)}")

    approved = 0
    skipped = []
    for ex in rows:
        if ex.id not in APPROVED_IDS:
            continue
        if ex.review_status != REVIEW_PENDING:
            skipped.append({"id": ex.id, "reason": f"status {ex.review_status}"})
            continue
        if len(ex.candidates) < 1 or ex.origin != "gemini_teacher":
            skipped.append({"id": ex.id, "reason": "missing gemini candidates"})
            continue
        history = list(ex.metadata.get("review_history") or [])
        history.append({
            "at": WHEN,
            "by": REVIEWER,
            "decision": "approve",
            "from_status": ex.review_status,
            "quote": "pls approve all",
        })
        ex.metadata["review_history"] = history
        ex.metadata["owner_approval"] = {
            "by": REVIEWER,
            "decision": "approve",
            "at": WHEN,
            "scope": "kp-001 through kp-055",
        }
        prior_notes = ex.reviewer_notes
        updated, issues = apply_review_decision(
            ex,
            decision="approve",
            verified_by=REVIEWER,
            verified_at=WHEN,
        )
        errors = [i for i in issues if i.severity == "error"]
        if errors or updated.review_status != REVIEW_APPROVED:
            skipped.append({
                "id": ex.id,
                "reason": ",".join(i.code for i in errors) or updated.review_status,
            })
            continue
        if prior_notes and prior_notes not in (updated.reviewer_notes or ""):
            updated.reviewer_notes = prior_notes
        note = " Owner approved the Khmer text; licence remains unknown."
        if note.strip() not in (updated.license_notes or ""):
            updated.license_notes = (updated.license_notes or "") + note
        if updated.license_type != "unknown":
            raise SystemExit(f"{ex.id} licence changed to {updated.license_type}")
        if len(updated.candidates) != 3:
            raise SystemExit(f"{ex.id} candidate count changed")
        approved += 1

    untouched = [ex.id for ex in rows if ex.id not in APPROVED_IDS]
    pending_tail = [
        ex.id for ex in rows
        if ex.id not in APPROVED_IDS and ex.review_status == REVIEW_PENDING and not ex.candidates
    ]
    save_examples(WORKSPACE_CANDIDATES, rows)

    gold = export_gold_version(rows, version="owner-approved-20261022")
    exported = load_examples(gold["path"])
    lora = plan_local_lora(dataset_path=str(WORKSPACE_CANDIDATES))
    summary = {
        "approved": approved,
        "skipped": skipped,
        "workspace_approved": sum(1 for ex in rows if ex.review_status == REVIEW_APPROVED),
        "workspace_pending": sum(1 for ex in rows if ex.review_status == REVIEW_PENDING),
        "workspace_gold": sum(1 for ex in rows if ex.review_status == "gold"),
        "license_types": sorted({ex.license_type for ex in rows}),
        "verified_by": sorted({ex.verified_by for ex in rows if ex.id in APPROVED_IDS}),
        "tail_still_pending": pending_tail,
        "untouched_ids": len(untouched),
        "gold_export_count": gold["count"],
        "gold_export_rejected": len(gold["rejected"]),
        "gold_export_path": gold["path"],
        "gold_export_ids": [ex.id for ex in exported],
        "gold_export_statuses": sorted({ex.review_status for ex in exported}),
        "gold_export_licenses": sorted({ex.license_type for ex in exported}),
        "lora_status": lora.status,
        "lora_error": lora.error,
        "lora_ok": lora.ok,
    }
    out = Path("data/outputs/voice_training/2026-10-22-ai-first/approval_run.json")
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "approved": summary["approved"],
        "workspace_pending": summary["workspace_pending"],
        "gold_export_count": summary["gold_export_count"],
        "gold_export_rejected": summary["gold_export_rejected"],
        "lora_status": summary["lora_status"],
        "skipped": summary["skipped"],
    }, ensure_ascii=False))
    return 0 if approved == 55 and not skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
