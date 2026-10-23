"""Record project-owner approval of every row in the 2026-10-22 rejected file.

Does not call Gemini or Jev. Does not start training. Does not invent candidates.
Licence stays unknown. The original rejected.json snapshot is left unchanged.
"""
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
from claynext.models.khmer_spoken.schema import REVIEW_APPROVED, utc_now_iso
from claynext.models.khmer_spoken.training.ranked_export import export_ranked_training

REJECTED_PATH = Path(
    "data/khmer_spoken/versions/owner-approved-20261022/rejected.json"
)
VERSION = "owner-approved-20261022-rejected-cleared"
REVIEWER = "project-owner"
QUOTE = (
    "x/Users/server2/Documents/Project/claynext/data/khmer_spoken/versions/"
    "owner-approved-20261022/rejected.json approve all"
)
NOTE = " Owner approved the Khmer text; licence remains unknown."
WHEN = utc_now_iso()


def _candidate_fingerprint(ex) -> list[tuple[str, str, str, str]]:
    return [(c.style, c.text, c.provider, c.model) for c in ex.candidates]


def _has_gemini_text(ex) -> bool:
    return any((c.text or "").strip() for c in ex.candidates)


def main() -> int:
    rejected_rows = json.loads(REJECTED_PATH.read_text(encoding="utf-8"))
    rejected_by_id = {row["id"]: row for row in rejected_rows}
    rows = load_examples(WORKSPACE_CANDIDATES)
    if len(rows) != 100:
        raise SystemExit(f"expected 100 workspace rows, got {len(rows)}")

    by_id = {ex.id: ex for ex in rows}
    missing = sorted(set(rejected_by_id) - set(by_id))
    if missing:
        raise SystemExit(f"rejected ids missing from workspace: {missing}")

    approved_now = 0
    already = 0
    reasons: dict[str, dict] = {}
    for ex_id, rejection in rejected_by_id.items():
        ex = by_id[ex_id]
        fingerprint = _candidate_fingerprint(ex)
        gemini = _has_gemini_text(ex)
        jev = ex.metadata.get("jev") or {}
        reasons[ex_id] = {
            "export_issues": list(rejection.get("issues") or []),
            "status_at_rejection": rejection.get("review_status"),
            "status_before": ex.review_status,
            "origin": ex.origin,
            "license_type": ex.license_type,
            "gemini_text": gemini,
            "candidate_count": len(ex.candidates),
            "stub_text": bool((ex.stub_khmer or "").strip()),
            "jev_applied": bool(jev.get("applied")) if isinstance(jev, dict) else False,
            "jev_stored": bool(jev),
        }
        history = list(ex.metadata.get("review_history") or [])
        history.append({
            "at": WHEN,
            "by": REVIEWER,
            "decision": "approve",
            "from_status": ex.review_status,
            "quote": QUOTE,
            "prior_rejection": {
                "file": str(REJECTED_PATH),
                "review_status": rejection.get("review_status"),
                "issues": list(rejection.get("issues") or []),
            },
        })
        ex.metadata["review_history"] = history
        approval = {
            "by": REVIEWER,
            "decision": "approve",
            "at": WHEN,
            "scope": "rejected.json kp-056 through kp-100",
            "quote": QUOTE,
            "prior_rejection_issues": list(rejection.get("issues") or []),
        }
        if ex.review_status == REVIEW_APPROVED:
            # Keep the earlier approval fields. This wave is an extra history entry.
            prior = dict(ex.metadata.get("owner_approval") or {})
            prior["rejected_file_confirmed_at"] = WHEN
            prior["rejected_file_quote"] = QUOTE
            ex.metadata["owner_approval"] = prior
            already += 1
        else:
            ex.metadata["owner_approval"] = approval
            prior_notes = ex.reviewer_notes
            # Do not pass approved_text. The review helper copies preferred text,
            # which is the stored stub when no candidate exists. It does not
            # create candidate sentences.
            updated, issues = apply_review_decision(
                ex,
                decision="approve",
                verified_by=REVIEWER,
                verified_at=WHEN,
            )
            errors = [i for i in issues if i.severity == "error"]
            text_errors = [i for i in errors if i.code == "missing_approved_text"]
            other_errors = [i for i in errors if i.code != "missing_approved_text"]
            if other_errors or updated.review_status != REVIEW_APPROVED:
                raise SystemExit(
                    f"{ex.id} approval failed: "
                    + ",".join(i.code for i in other_errors or errors)
                    + f" status={updated.review_status}"
                )
            if text_errors and (updated.approved_text or "").strip():
                raise SystemExit(f"{ex.id} reported missing text but approved_text is set")
            if prior_notes and prior_notes not in (updated.reviewer_notes or ""):
                updated.reviewer_notes = prior_notes
            if NOTE.strip() not in (updated.license_notes or ""):
                updated.license_notes = (updated.license_notes or "") + NOTE
            approved_now += 1
        if ex.license_type != "unknown":
            raise SystemExit(f"{ex.id} licence changed to {ex.license_type}")
        if _candidate_fingerprint(ex) != fingerprint:
            raise SystemExit(f"{ex.id} candidates changed")

    save_examples(WORKSPACE_CANDIDATES, rows)

    gold = export_gold_version(rows, version=VERSION)
    exported = load_examples(gold["path"])
    exported_ids = {ex.id for ex in exported}
    rejected_ids = set(rejected_by_id)
    approved_but_not_exported = sorted(
        ex.id for ex in rows
        if ex.id in rejected_ids and ex.id not in exported_ids
    )
    no_text = sorted(
        ex.id for ex in rows
        if ex.id in rejected_ids and not (ex.approved_text or ex.preferred_khmer() or "").strip()
    )
    no_gemini = sorted(ex.id for ex in rows if ex.id in rejected_ids and not _has_gemini_text(ex))
    ranked_path = Path(gold["path"]).parent / "ranked.jsonl"
    ranked = export_ranked_training(rows, ranked_path)

    summary = {
        "rejected_file_count": len(rejected_rows),
        "rejected_issue_codes": sorted({
            code
            for row in rejected_rows
            for code in (row.get("issues") or [])
        }),
        "empty_gemini_candidates": sum(1 for item in reasons.values() if not item["gemini_text"]),
        "licence_unknown": sum(1 for item in reasons.values() if item["license_type"] == "unknown"),
        "jev_applied_among_rejected_ids": sum(1 for item in reasons.values() if item["jev_applied"]),
        "jev_missing_among_rejected_ids": sum(1 for item in reasons.values() if not item["jev_stored"]),
        "schema_export_issues_other_than_not_approved": [
            item["export_issues"] for item in reasons.values()
            if item["export_issues"] != ["not_approved_or_gold"]
        ],
        "newly_approved": approved_now,
        "already_approved_confirmed": already,
        "owner_approved_in_rejected_file": approved_now + already,
        "workspace_approved": sum(1 for ex in rows if ex.review_status == REVIEW_APPROVED),
        "workspace_pending": sum(1 for ex in rows if ex.review_status == "pending_native_review"),
        "license_types": sorted({ex.license_type for ex in rows}),
        "gold_export_count": gold["count"],
        "gold_export_rejected": len(gold["rejected"]),
        "gold_export_path": gold["path"],
        "gold_export_ids": [ex.id for ex in exported],
        "gold_includes_previous_55": all(f"kp-{i:03d}" in exported_ids for i in range(1, 56)),
        "gold_includes_previous_58": all(
            ex_id in exported_ids
            for ex_id in ("kp-056", "kp-058", "kp-059")
        ),
        "approved_but_not_exported": approved_but_not_exported,
        "rows_still_without_text": no_text,
        "rows_without_gemini_text": no_gemini,
        "ranked_export_count": ranked["count"],
        "ranked_export_path": ranked["path"],
        "weights_written": ranked["weights_written"],
        "trainer_installed": ranked["trainer_installed"],
        "original_rejected_json_unchanged": True,
    }
    out = Path("data/outputs/voice_training/2026-10-22-ai-first/rejected_cleared_run.json")
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "rejected_file_count": summary["rejected_file_count"],
        "newly_approved": summary["newly_approved"],
        "already_approved_confirmed": summary["already_approved_confirmed"],
        "owner_approved_in_rejected_file": summary["owner_approved_in_rejected_file"],
        "workspace_approved": summary["workspace_approved"],
        "workspace_pending": summary["workspace_pending"],
        "gold_export_count": summary["gold_export_count"],
        "gold_export_rejected": summary["gold_export_rejected"],
        "gold_export_path": summary["gold_export_path"],
        "approved_but_not_exported": summary["approved_but_not_exported"],
        "rows_still_without_text": summary["rows_still_without_text"],
        "rows_without_gemini_text_count": len(summary["rows_without_gemini_text"]),
        "ranked_export_count": summary["ranked_export_count"],
        "ranked_export_path": summary["ranked_export_path"],
        "license_types": summary["license_types"],
        "weights_written": summary["weights_written"],
    }, ensure_ascii=False))
    ok = (
        summary["owner_approved_in_rejected_file"] == len(rejected_rows)
        and summary["workspace_approved"] == 100
        and summary["workspace_pending"] == 0
        and summary["license_types"] == ["unknown"]
        and summary["gold_includes_previous_55"]
        and summary["gold_includes_previous_58"]
        and not summary["rows_still_without_text"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
