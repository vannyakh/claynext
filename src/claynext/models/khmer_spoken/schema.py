"""KSLD dialogue example schema and gold-promotion validators.

Hard rules
----------
- Synthetic / Gemini candidates are **never** gold without native Khmer human review.
- Gold / approved promotion requires ``verified_by``, ``verified_at``, and
  ``review_status`` in an allowed verified set.
- Every example tracks ``license_type`` / license metadata (source rights).
- Text fine-tuning (Vertex Gemini SFT or local LoRA) ≠ TTS voice training.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "0.1.0"

# Align with khmer_localization evaluator vocabulary for native review.
REVIEW_PENDING = "pending_native_review"
REVIEW_APPROVED = "approved"
REVIEW_REJECTED = "rejected"
REVIEW_GOLD = "gold"
REVIEW_NEEDS_CHANGES = "needs_changes"

REVIEW_STATUSES = (
    REVIEW_PENDING,
    REVIEW_APPROVED,
    REVIEW_REJECTED,
    REVIEW_GOLD,
    REVIEW_NEEDS_CHANGES,
)
VERIFIED_STATUSES = frozenset({REVIEW_APPROVED, REVIEW_GOLD})
ORIGINS = ("human_authored", "human_reviewed", "synthetic", "gemini_teacher")
LICENSE_DEMO = "demo_fixture"
LICENSE_TYPES = (
    LICENSE_DEMO,
    "CC-BY-4.0",
    "CC-BY-SA-4.0",
    "proprietary_licensed",
    "unknown",
)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _opt(value: Any) -> str | None:
    text = _text(value)
    return text or None


def parse_iso(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class TranslationCandidate:
    """One Khmer rendering proposed by a teacher model or human."""

    text: str
    style: str = "natural"  # natural | literal | slang | character
    provider: str = "unknown"
    model: str = ""
    notes: str = ""
    emotion: str = ""
    register: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranslationCandidate":
        return cls(
            text=_text(data.get("text")),
            style=_text(data.get("style")) or "natural",
            provider=_text(data.get("provider")) or "unknown",
            model=_text(data.get("model")),
            notes=_text(data.get("notes")),
            emotion=_text(data.get("emotion")),
            register=_text(data.get("register")),
        )


@dataclass
class DialogueExample:
    """One dialogue line in the KSLD workspace (source + candidates + review)."""

    id: str
    source_text: str
    source_lang: str = "en"
    target_lang: str = "km"
    # Optional stub Khmer (fixture / prior draft) — not gold unless reviewed.
    stub_khmer: str = ""
    candidates: list[TranslationCandidate] = field(default_factory=list)
    approved_text: str = ""
    speaker_id: str = ""
    listener_id: str = ""
    relationship: str = ""
    emotion: str = "neutral"
    register: str = "neutral"
    category: str = "everyday"
    origin: str = "synthetic"
    license_type: str = LICENSE_DEMO
    license_notes: str = ""
    review_status: str = REVIEW_PENDING
    verified_by: str = ""
    verified_at: str = ""
    reviewer_notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["candidates"] = [asdict(c) for c in self.candidates]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DialogueExample":
        return cls(
            id=_text(data.get("id")),
            source_text=_text(data.get("source_text")),
            source_lang=_text(data.get("source_lang")) or "en",
            target_lang=_text(data.get("target_lang")) or "km",
            stub_khmer=_text(data.get("stub_khmer") or data.get("khmer_stub")),
            candidates=[
                TranslationCandidate.from_dict(c) for c in (data.get("candidates") or [])
            ],
            approved_text=_text(data.get("approved_text")),
            speaker_id=_text(data.get("speaker_id")),
            listener_id=_text(data.get("listener_id")),
            relationship=_text(data.get("relationship")),
            emotion=_text(data.get("emotion")) or "neutral",
            register=_text(data.get("register")) or "neutral",
            category=_text(data.get("category")) or "everyday",
            origin=_text(data.get("origin")) or "synthetic",
            license_type=_text(data.get("license_type") or data.get("license")) or LICENSE_DEMO,
            license_notes=_text(data.get("license_notes")),
            review_status=_text(data.get("review_status")) or REVIEW_PENDING,
            verified_by=_text(data.get("verified_by")),
            verified_at=_text(data.get("verified_at")),
            reviewer_notes=_text(data.get("reviewer_notes") or data.get("notes")),
            metadata=dict(data.get("metadata") or {}),
            schema_version=_text(data.get("schema_version")) or SCHEMA_VERSION,
        )

    @property
    def is_pending(self) -> bool:
        return self.review_status == REVIEW_PENDING

    @property
    def is_gold(self) -> bool:
        return self.review_status == REVIEW_GOLD

    def preferred_khmer(self) -> str:
        if self.approved_text:
            return self.approved_text
        for style in ("natural", "character", "slang", "literal"):
            for cand in self.candidates:
                if cand.style == style and cand.text:
                    return cand.text
        if self.candidates and self.candidates[0].text:
            return self.candidates[0].text
        return self.stub_khmer


@dataclass(frozen=True)
class ValidationIssue:
    severity: str  # error | warning
    code: str
    field: str
    message: str


def validate_example(ex: DialogueExample, *, for_gold: bool = False) -> list[ValidationIssue]:
    """Validate a dialogue example. Gold promotion is stricter."""
    issues: list[ValidationIssue] = []
    if not ex.id:
        issues.append(ValidationIssue("error", "missing_id", "id", "Example id is required."))
    if not ex.source_text:
        issues.append(
            ValidationIssue("error", "missing_source", "source_text", "Source text is required.")
        )
    if ex.review_status not in REVIEW_STATUSES:
        issues.append(
            ValidationIssue(
                "error",
                "bad_review_status",
                "review_status",
                f"Unknown review_status {ex.review_status!r}.",
            )
        )
    if ex.origin and ex.origin not in ORIGINS:
        issues.append(
            ValidationIssue(
                "warning",
                "unknown_origin",
                "origin",
                f"Origin {ex.origin!r} is not in the known set.",
            )
        )
    if not ex.license_type:
        issues.append(
            ValidationIssue(
                "error",
                "missing_license",
                "license_type",
                "license_type is required for training eligibility.",
            )
        )

    want_verified = for_gold or ex.review_status in VERIFIED_STATUSES
    if want_verified:
        if not ex.verified_by:
            issues.append(
                ValidationIssue(
                    "error",
                    "missing_verified_by",
                    "verified_by",
                    "Native reviewer id (verified_by) is required for approved/gold.",
                )
            )
        if not parse_iso(ex.verified_at):
            issues.append(
                ValidationIssue(
                    "error",
                    "missing_verified_at",
                    "verified_at",
                    "ISO verified_at timestamp is required for approved/gold.",
                )
            )
        if not (ex.approved_text or ex.preferred_khmer()):
            issues.append(
                ValidationIssue(
                    "error",
                    "missing_approved_text",
                    "approved_text",
                    "Approved Khmer text is required for gold/approved export.",
                )
            )

    if ex.review_status == REVIEW_GOLD:
        # Synthetic / Gemini candidates cannot be gold without human verification fields
        # (already checked) — still flag if origin claims model-only verification.
        if ex.origin in {"synthetic", "gemini_teacher"} and not ex.verified_by:
            issues.append(
                ValidationIssue(
                    "error",
                    "synthetic_gold_unreviewed",
                    "review_status",
                    "Synthetic/Gemini candidates cannot be gold without native human review.",
                )
            )
        if ex.license_type == LICENSE_DEMO:
            issues.append(
                ValidationIssue(
                    "warning",
                    "demo_license_gold",
                    "license_type",
                    "demo_fixture license is not suitable for production gold datasets.",
                )
            )

    return issues


def can_promote_to_gold(ex: DialogueExample) -> tuple[bool, list[ValidationIssue]]:
    issues = validate_example(ex, for_gold=True)
    errors = [i for i in issues if i.severity == "error"]
    return (not errors), issues
