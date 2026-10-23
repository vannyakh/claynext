"""Held-out Khmer movie benchmark rows.

A row can be scored as gold only when a human reviewed it, a licence is recorded,
and it is not synthetic-only. ``pending_native_review`` is not gold. Locked
``test`` rows stay in the test split.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = "1.0.0"
SPLITS = ("train", "validation", "test")
ORIGINS = ("human_authored", "human_reviewed", "synthetic", "gemini_teacher")
REVIEW_STATUSES = (
    "draft",
    "pending_native_review",
    "reviewed",
    "gold",
    "rejected",
)
# Licences that may ship in a product. Unknown and fixtures may not.
DEPLOYABLE_LICENCES = frozenset({"CC-BY-4.0", "CC-BY-SA-4.0", "proprietary_licensed"})


class BenchmarkSchemaError(ValueError):
    pass


class SyntheticGoldError(BenchmarkSchemaError):
    """Synthetic-only or unreviewed model text was presented as gold."""


class SplitLockError(BenchmarkSchemaError):
    """A locked test row was moved out of the test split."""


class GoldSetError(BenchmarkSchemaError):
    """A gold benchmark was requested for a row that is not human-reviewed gold."""


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


@dataclass
class BenchmarkRow:
    id: str
    scene_id: str
    dialogue_family_id: str
    source_language: str
    source_text: str
    reference_khmer: str
    split: str
    licence: str
    review_status: str
    origin: str
    dataset_version: str
    schema_version: str = SCHEMA_VERSION
    locked: bool = False
    synthetic_only: bool = False
    reviewer_id: str | None = None
    reviewed_at: str | None = None
    speaker_id: str = ""
    listener_id: str = ""
    relationship: str = ""
    emotion: str = "neutral"
    register: str = "neutral"
    category: str = "everyday"
    prompt_version: str = ""

    def is_gold_reference(self) -> bool:
        """True only for human-reviewed gold with a licence. Never synthetic-only."""
        if self.synthetic_only:
            return False
        if self.review_status != "gold":
            return False
        if self.origin not in {"human_authored", "human_reviewed"}:
            return False
        if self.origin == "human_reviewed" or self.review_status == "gold":
            if not self.reviewer_id or not self.reviewed_at:
                return False
        if not self.licence or self.licence not in DEPLOYABLE_LICENCES:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_row(row: BenchmarkRow) -> list[str]:
    """Return error codes. Does not invent a review."""
    errors: list[str] = []
    if not row.id:
        errors.append("missing_id")
    if not row.dialogue_family_id:
        errors.append("missing_dialogue_family")
    if not row.source_text:
        errors.append("missing_source_text")
    if row.split not in SPLITS:
        errors.append("bad_split")
    if row.origin not in ORIGINS:
        errors.append("bad_origin")
    if row.review_status not in REVIEW_STATUSES:
        errors.append("bad_review_status")
    if row.schema_version != SCHEMA_VERSION:
        errors.append("bad_schema_version")
    if row.synthetic_only and row.review_status == "gold":
        errors.append("synthetic_not_gold")
    if row.origin in {"synthetic", "gemini_teacher"} and row.review_status == "gold":
        errors.append("synthetic_not_gold")
    if row.review_status == "gold" and row.origin in {"human_authored", "human_reviewed"}:
        if not row.reviewer_id or not row.reviewed_at:
            errors.append("gold_missing_reviewer")
        if not row.licence:
            errors.append("gold_missing_licence")
    if row.split == "test" and not row.locked:
        errors.append("test_split_unlocked")
    return errors


def assert_not_synthetic_gold(row: BenchmarkRow) -> None:
    if "synthetic_not_gold" in validate_row(row) or (
        row.synthetic_only and row.review_status in {"gold", "reviewed"}
    ):
        raise SyntheticGoldError(
            f"{row.id} is synthetic-only or model-drafted and cannot be gold"
        )
    if row.review_status == "gold" and not row.is_gold_reference():
        raise SyntheticGoldError(f"{row.id} is not a human-reviewed gold reference")


def assign_split(row: BenchmarkRow, new_split: str) -> BenchmarkRow:
    """Move a row. Locked test rows cannot leave the test split."""
    if new_split not in SPLITS:
        raise BenchmarkSchemaError(f"split must be one of {SPLITS}")
    if row.split == "test" and row.locked and new_split != "test":
        raise SplitLockError(f"{row.id} is locked in the test split")
    row.split = new_split
    if new_split == "test":
        row.locked = True
    return row


def lock_test_rows(rows: list[BenchmarkRow]) -> list[BenchmarkRow]:
    for row in rows:
        if row.split == "test":
            row.locked = True
    return rows


def licence_allows_deployment(licence: str) -> bool:
    return licence in DEPLOYABLE_LICENCES
