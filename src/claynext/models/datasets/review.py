"""Export native-speaker review sheets and apply filled ones to records.

Accepts the KSLD ``review_template.csv`` columns (``decision``, ``corrected_khmer``,
``meaning_accuracy_1_5``, ``naturalness_1_5``, ``relationship_fit_1_5``, ``emotion_fit_1_5``)
and the canonical dimension names. Rows with an empty decision are skipped. A review never
promotes a record to ``gold``; that stays a separate, explicit step.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claynext.models.datasets.io import read_rows
from claynext.models.datasets.schema import (
    QUALITY_DIMENSIONS,
    SCORE_MAX,
    SCORE_MIN,
    Candidate,
    DialogueRecord,
    parse_iso,
)
from claynext.models.datasets.store import now_iso

DECISIONS = {
    "approved": "reviewed",
    "approve": "reviewed",
    "accepted": "reviewed",
    "rejected": "rejected",
    "reject": "rejected",
    "needs_changes": "staging",
    "revise": "staging",
}
SCORE_COLUMNS = {
    "meaning_accuracy_1_5": "semantic_accuracy",
    "naturalness_1_5": "naturalness",
    "emotion_fit_1_5": "emotion_fit",
    **{d: d for d in QUALITY_DIMENSIONS},
}
EXTRA_SCORE_COLUMNS = {"relationship_fit_1_5": "relationship_fit"}


GOLD_DECISIONS = frozenset({"gold", "promote", "promote_gold"})


@dataclass
class ReviewResult:
    applied: dict[str, int] = field(default_factory=dict)
    skipped_blank: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    # Where each applied row's reviewed_at came from: sheet, argument, or clock.
    timestamp_source: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"applied": self.applied, "skipped_blank": self.skipped_blank,
                "timestamp_source": self.timestamp_source, "errors": self.errors}


def _score(raw: str, column: str) -> float:
    value = float(raw)
    if not SCORE_MIN <= value <= SCORE_MAX:
        raise ValueError(f"{column}={raw} is outside {SCORE_MIN:g}-{SCORE_MAX:g}")
    return value


def apply_review_rows(
    records: list[DialogueRecord], rows: list[dict[str, Any]], *, reviewed_at: str | None = None
) -> ReviewResult:
    """Mutates matching records in place.

    ``reviewed_at`` precedence: the row's ``reviewed_at`` column, then the ``reviewed_at``
    argument, then the wall clock at apply time.
    """
    result = ReviewResult()
    by_id = {r.id: r for r in records}
    for n, row in enumerate(rows, 1):
        decision = str(row.get("decision") or "").strip().lower()
        if not decision:
            result.skipped_blank += 1
            continue
        rid = str(row.get("id") or "").strip()
        rec = by_id.get(rid)
        reviewer = str(row.get("reviewer_id") or "").strip()
        sheet_when = str(row.get("reviewed_at") or "").strip()
        if sheet_when:
            when, when_source = sheet_when, "sheet"
        elif reviewed_at:
            when, when_source = reviewed_at, "argument"
        else:
            when, when_source = now_iso(), "clock"
        problem = None
        if rec is None:
            problem = f"unknown id {rid!r}"
        elif decision in GOLD_DECISIONS:
            problem = ("a review sheet cannot promote to gold; apply the review, then run "
                       "'claynext dataset promote --to gold'"
                       + ("" if reviewer else " (and reviewer_id is missing)"))
        elif rec.status == "gold":
            problem = "record is gold; sheet reviews do not change gold records"
        elif decision not in DECISIONS:
            problem = f"unknown decision {decision!r}; use one of {sorted(DECISIONS)}"
        elif not reviewer:
            problem = "reviewer_id is required"
        elif parse_iso(when) is None:
            problem = f"reviewed_at {when!r} is not ISO 8601"
        scores: dict[str, float] = {}
        extra: dict[str, float] = {}
        if problem is None:
            try:
                for column, dim in SCORE_COLUMNS.items():
                    if str(row.get(column) or "").strip():
                        scores[dim] = _score(str(row[column]).strip(), column)
                for column, name in EXTRA_SCORE_COLUMNS.items():
                    if str(row.get(column) or "").strip():
                        extra[name] = _score(str(row[column]).strip(), column)
            except ValueError as exc:
                problem = str(exc)
        if problem is not None:
            result.errors.append({"row": n, "id": rid or None, "error": problem})
            continue

        status = DECISIONS[decision]
        rec.review.status = status
        rec.review.reviewer_id = reviewer
        rec.review.reviewer_type = "human"
        rec.review.reviewed_at = when
        if str(row.get("notes") or "").strip():
            rec.review.notes = str(row["notes"]).strip()
        if scores or extra:
            rec.quality.scores.update(scores)
            rec.quality.extra.update(extra)
            rec.quality.scored_by = "human"
        corrected = str(row.get("corrected_khmer") or "").strip()
        current = rec.preferred_candidate()
        if corrected and (current is None or corrected != current.text):
            style = current.style if current else "unspecified"
            rec.candidates.insert(0, Candidate(text=corrected, style=style, origin="human_reviewed",
                                               notes=f"correction by {reviewer}"))
        if status == "reviewed" and rec.origin == "synthetic":
            rec.metadata["original_origin"] = rec.origin
            rec.origin = "human_reviewed"
        result.applied[status] = result.applied.get(status, 0) + 1
        result.timestamp_source[when_source] = result.timestamp_source.get(when_source, 0) + 1
    return result


def apply_review_file(
    records: list[DialogueRecord], path: str | Path, *, reviewed_at: str | None = None
) -> ReviewResult:
    return apply_review_rows(records, read_rows(Path(path)), reviewed_at=reviewed_at)


# ── Review sheet export ─────────────────────────────────────────────────

# Read-only context for the reviewer. Current scores are prefixed ``current_`` so that a model
# score shown for reference is never read back as a human score.
CONTEXT_COLUMNS = (
    "id", "status", "origin", "split", "category", "source_lang", "source_text", "khmer_current",
    "khmer_style", "khmer_alternatives", "speaker_id", "listener_id", "relationship", "emotion",
    "intensity", "register", "slang_level", "profanity_level", "region", "license",
    "current_reviewer_id", "current_reviewed_at", "current_scored_by",
    *(f"current_{d}" for d in QUALITY_DIMENSIONS),
    "context_notes",
)
# Filled in by the reviewer. ``decision``: approved | rejected | needs_changes.
# ``reviewed_at`` is ISO 8601 (e.g. 2026-10-21T14:30:00+07:00); left empty, apply time is used.
REVIEWER_COLUMNS = (
    "reviewer_id", "reviewed_at", "decision", "corrected_khmer",
    *QUALITY_DIMENSIONS, "relationship_fit_1_5", "notes",
)
SHEET_COLUMNS = CONTEXT_COLUMNS + REVIEWER_COLUMNS


def _cell(value: Any) -> str:
    return "" if value is None else str(value)


def review_sheet_row(rec: DialogueRecord) -> dict[str, str]:
    current = rec.preferred_candidate()
    others = [c.text for c in rec.candidates if c is not current and c.text]
    row = {
        "id": rec.id,
        "status": rec.status,
        "origin": rec.origin,
        "split": rec.split,
        "category": rec.category,
        "source_lang": rec.source_lang,
        "source_text": rec.source_text,
        "khmer_current": current.text if current else "",
        "khmer_style": current.style if current else "",
        "khmer_alternatives": " || ".join(others),
        "speaker_id": rec.speaker_id,
        "listener_id": rec.listener_id,
        "relationship": rec.relationship,
        "emotion": rec.emotion,
        "intensity": rec.intensity,
        "register": rec.register,
        "slang_level": rec.slang_level,
        "profanity_level": rec.profanity_level,
        "region": rec.regional.region,
        "license": rec.provenance.license,
        "current_reviewer_id": rec.review.reviewer_id,
        "current_reviewed_at": rec.review.reviewed_at,
        "current_scored_by": rec.quality.scored_by,
        "context_notes": rec.metadata.get("notes") or rec.review.notes,
        **{f"current_{d}": rec.quality.scores.get(d) for d in QUALITY_DIMENSIONS},
    }
    out = {col: _cell(row.get(col)) for col in CONTEXT_COLUMNS}
    out.update({col: "" for col in REVIEWER_COLUMNS})
    return out


def export_review_sheet(records: list[DialogueRecord], path: str | Path) -> Path:
    """CSV (UTF-8 with BOM so spreadsheet apps show Khmer correctly), one row per record, sorted by id."""
    import csv

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(SHEET_COLUMNS))
        writer.writeheader()
        for rec in sorted(records, key=lambda r: r.id):
            writer.writerow(review_sheet_row(rec))
    tmp.replace(p)
    return p
