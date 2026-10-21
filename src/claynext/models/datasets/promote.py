"""Explicit status promotion with transition and eligibility checks.

Allowed transitions::

    draft    -> staging | reviewed
    staging  -> reviewed | gold
    reviewed -> gold

Promotion never creates review metadata. ``reviewed`` and ``gold`` need the record to already
carry a reviewer id and an ISO ``reviewed_at`` (from ``review-apply`` or the source data).
``gold`` additionally needs ``reviewer_type=human`` (so synthetic data is never gold on its own)
and a licence. The result is re-validated with ``validate_record``; any error blocks the change.
Each promotion is appended to ``metadata["promotions"]``.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from claynext.models.datasets.schema import DialogueRecord, parse_iso, validate_record
from claynext.models.datasets.store import now_iso

TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"staging", "reviewed"}),
    "staging": frozenset({"reviewed", "gold"}),
    "reviewed": frozenset({"gold"}),
}
TARGETS = ("staging", "reviewed", "gold")


@dataclass
class PromoteResult:
    target: str
    promoted: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    blocked: list[dict[str, Any]] = field(default_factory=list)
    unknown_ids: list[str] = field(default_factory=list)

    def to_dict(self, *, limit: int = 50) -> dict[str, Any]:
        reasons: dict[str, int] = {}
        for b in self.blocked:
            for code in b["reasons"]:
                reasons[code] = reasons.get(code, 0) + 1
        return {
            "target": self.target,
            "promoted": len(self.promoted),
            "already": len(self.already),
            "blocked": len(self.blocked),
            "blocked_reasons": dict(sorted(reasons.items())),
            "blocked_examples": self.blocked[:limit],
            "unknown_ids": self.unknown_ids,
        }


def eligibility(rec: DialogueRecord, target: str, *, require_license: bool) -> list[str]:
    """Reason codes that block ``rec`` from moving to ``target``; empty means eligible."""
    reasons: list[str] = []
    if target not in TRANSITIONS.get(rec.status, frozenset()):
        reasons.append(f"transition_{rec.status}_to_{target}_not_allowed")
        return reasons
    review = rec.review
    if target in ("reviewed", "gold"):
        if not review.reviewer_id:
            reasons.append("missing_reviewer_id")
        if not review.reviewed_at or parse_iso(review.reviewed_at) is None:
            reasons.append("missing_reviewed_at")
    if target == "gold":
        if review.reviewer_type != "human":
            reasons.append("synthetic_without_human_review" if rec.origin == "synthetic"
                           else "gold_requires_human_review")
    if require_license and not rec.provenance.license:
        reasons.append("missing_license")
    return reasons


def promote_records(
    records: list[DialogueRecord],
    target: str,
    *,
    ids: list[str] | None = None,
    require_license: bool | None = None,
    by: str | None = None,
    dry_run: bool = False,
) -> PromoteResult:
    """Promote ``ids`` (or every record) to ``target``. Mutates records unless ``dry_run``.

    ``require_license`` defaults to True for gold and False otherwise. Gold always needs a licence
    because the schema requires it, so turning the flag off for gold has no effect.
    """
    if target not in TARGETS:
        raise ValueError(f"target must be one of {TARGETS}")
    need_license = (target == "gold") if require_license is None else bool(require_license)
    need_license = need_license or target == "gold"
    result = PromoteResult(target=target)
    by_id = {r.id: r for r in records}
    if ids:
        wanted = []
        for rid in ids:
            if rid in by_id:
                wanted.append(by_id[rid])
            else:
                result.unknown_ids.append(rid)
    else:
        wanted = sorted(records, key=lambda r: r.id)

    for rec in wanted:
        if rec.status == target:
            result.already.append(rec.id)
            continue
        if not ids and target not in TRANSITIONS.get(rec.status, frozenset()):
            # Bulk mode only considers records that could move to the target at all.
            continue
        reasons = eligibility(rec, target, require_license=need_license)
        if not reasons:
            trial = copy.deepcopy(rec)
            trial.review.status = target
            reasons = [f"schema:{i.code}" for i in validate_record(trial) if i.severity == "error"]
        if reasons:
            result.blocked.append({"id": rec.id, "status": rec.status, "reasons": reasons})
            continue
        if not dry_run:
            history = rec.metadata.setdefault("promotions", [])
            history.append({"from": rec.status, "to": target, "at": now_iso(), "by": by})
            rec.review.status = target
        result.promoted.append(rec.id)
    return result
