"""Generate Khmer translation candidates with Gemini for pending KSLD rows.

Respects review gates:
- Only ``pending_native_review`` (and optionally needs_changes) rows get new
  synthetic candidates by default.
- Gold / approved rows are skipped unless ``force=True`` (still does not change
  review_status to gold).
"""
from __future__ import annotations

from typing import Callable

from claynext.models.khmer_spoken.providers.google_gemini_provider import GeminiTeacherProvider
from claynext.models.khmer_spoken.schema import (
    REVIEW_GOLD,
    REVIEW_NEEDS_CHANGES,
    REVIEW_PENDING,
    DialogueExample,
    TranslationCandidate,
)

ProgressCb = Callable[[int, str], None] | None

ELIGIBLE_FOR_TEACHER = frozenset({REVIEW_PENDING, REVIEW_NEEDS_CHANGES})


def generate_candidates_batch(
    examples: list[DialogueExample],
    *,
    provider: GeminiTeacherProvider | None = None,
    force: bool = False,
    limit: int | None = None,
    progress_callback: ProgressCb = None,
) -> dict:
    """Attach Gemini candidates to eligible examples. Mutates and returns a report.

    Offline / no-key: returns ``skipped`` without raising.
    """
    teacher = provider or GeminiTeacherProvider()
    if not teacher.available():
        return {
            "ok": False,
            "skipped": True,
            "reason": "missing_key",
            "updated": 0,
            "skipped_rows": len(examples),
            "error": "No Gemini API key — candidate generation skipped.",
            "examples": examples,
        }

    updated = 0
    skipped_rows = 0
    errors: list[str] = []
    work = examples if limit is None else examples[: max(0, limit)]
    total = max(1, len(work))

    for i, ex in enumerate(work):
        if progress_callback:
            pct = int(100 * i / total)
            progress_callback(pct, f"Generating candidates {i + 1}/{len(work)}…")

        if not force and ex.review_status not in ELIGIBLE_FOR_TEACHER:
            skipped_rows += 1
            continue
        if not force and ex.review_status == REVIEW_GOLD:
            skipped_rows += 1
            continue

        result = teacher.generate_khmer_candidates(
            ex.source_text,
            source_lang=ex.source_lang,
            emotion=ex.emotion,
            register=ex.register,
            speaker_id=ex.speaker_id,
            listener_id=ex.listener_id,
            progress_callback=progress_callback,
        )
        if result.skipped or not result.ok:
            errors.append(f"{ex.id}: {result.error or 'failed'}")
            skipped_rows += 1
            continue

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
        if new_cands:
            # Keep prior candidates; append teacher proposals.
            ex.candidates = list(ex.candidates) + new_cands
            if ex.origin == "synthetic":
                ex.origin = "gemini_teacher"
            # Never auto-promote — stay pending until human review.
            if ex.review_status not in ELIGIBLE_FOR_TEACHER:
                ex.review_status = REVIEW_PENDING
            updated += 1
        else:
            errors.append(f"{ex.id}: no candidates parsed")
            skipped_rows += 1

    if progress_callback:
        progress_callback(100, f"Candidates ready ({updated} updated)")

    return {
        "ok": True,
        "skipped": False,
        "updated": updated,
        "skipped_rows": skipped_rows,
        "errors": errors,
        "examples": examples,
    }
