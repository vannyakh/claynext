"""Native Khmer human review gates for KSLD gold promotion.

Synthetic / Gemini candidates remain ``pending_native_review`` until a human
sets ``verified_by`` + ``verified_at`` and approves text.
"""
from __future__ import annotations

from claynext.models.khmer_spoken.schema import (
    REVIEW_APPROVED,
    REVIEW_GOLD,
    REVIEW_NEEDS_CHANGES,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    DialogueExample,
    ValidationIssue,
    can_promote_to_gold,
    utc_now_iso,
    validate_example,
)

_DECISION_MAP = {
    "approve": REVIEW_APPROVED,
    "approved": REVIEW_APPROVED,
    "reject": REVIEW_REJECTED,
    "rejected": REVIEW_REJECTED,
    "needs_changes": REVIEW_NEEDS_CHANGES,
    "gold": REVIEW_GOLD,
    "pending": REVIEW_PENDING,
    REVIEW_PENDING: REVIEW_PENDING,
}


def apply_review_decision(
    ex: DialogueExample,
    *,
    decision: str,
    verified_by: str = "",
    approved_text: str = "",
    notes: str = "",
    verified_at: str | None = None,
) -> tuple[DialogueExample, list[ValidationIssue]]:
    """Apply approve / reject / needs_changes / gold. Returns (example, issues)."""
    key = (decision or "").strip().lower()
    if key not in _DECISION_MAP:
        raise ValueError(f"Unknown review decision: {decision!r}")

    status = _DECISION_MAP[key]
    if notes:
        ex.reviewer_notes = notes
    if approved_text.strip():
        ex.approved_text = approved_text.strip()
    elif status in {REVIEW_APPROVED, REVIEW_GOLD} and not ex.approved_text:
        ex.approved_text = ex.preferred_khmer()

    if status in {REVIEW_APPROVED, REVIEW_GOLD}:
        if not verified_by.strip() and not ex.verified_by:
            issues = [
                ValidationIssue(
                    "error",
                    "missing_verified_by",
                    "verified_by",
                    "Native reviewer id is required to approve/gold.",
                )
            ]
            return ex, issues
        ex.verified_by = verified_by.strip() or ex.verified_by
        ex.verified_at = verified_at or ex.verified_at or utc_now_iso()
        ex.review_status = status
        if status == REVIEW_GOLD:
            ok, issues = can_promote_to_gold(ex)
            if not ok:
                ex.review_status = REVIEW_APPROVED
                return ex, [i for i in issues if i.severity == "error"]
            return ex, issues
        return ex, validate_example(ex)

    # reject / needs_changes / pending — reviewer fields optional but recorded when given
    ex.review_status = status
    if verified_by.strip():
        ex.verified_by = verified_by.strip()
        ex.verified_at = verified_at or utc_now_iso()
    return ex, validate_example(ex)


def promote_to_gold(
    ex: DialogueExample,
    *,
    verified_by: str,
    approved_text: str = "",
    notes: str = "",
    verified_at: str | None = None,
) -> tuple[DialogueExample, list[ValidationIssue]]:
    """Promote one example to gold; requires native reviewer fields."""
    return apply_review_decision(
        ex,
        decision="gold",
        verified_by=verified_by,
        approved_text=approved_text,
        notes=notes,
        verified_at=verified_at,
    )
