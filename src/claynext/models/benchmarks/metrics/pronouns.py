"""Pronoun structure via the existing evaluation runner. Not a human accuracy score."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from claynext.models.benchmarks.metrics.common import metric
from claynext.models.benchmarks.schema import BenchmarkRow
from claynext.models.datasets.schema import Candidate, DialogueRecord, Provenance, Review


def to_dialogue_record(row: BenchmarkRow) -> DialogueRecord:
    """Map a benchmark row into the dataset record the existing runner already scores."""
    gold = row.is_gold_reference()
    if gold:
        status, reviewer_type, origin = "gold", "human", row.origin
    elif row.review_status == "reviewed" and row.reviewer_id and row.reviewed_at:
        status, reviewer_type, origin = "reviewed", "human", "human_reviewed"
    else:
        status, reviewer_type = "draft", None
        origin = "synthetic" if row.origin not in {"human_authored", "human_reviewed", "synthetic"} else row.origin
    return DialogueRecord(
        id=row.id,
        source_text=row.source_text,
        source_lang=row.source_language or "en",
        candidates=[Candidate(text=row.reference_khmer, style="natural")] if row.reference_khmer else [],
        speaker_id=row.speaker_id or "speaker",
        listener_id=row.listener_id or None,
        relationship=row.relationship or None,
        emotion=row.emotion or "neutral",
        register=row.register or "neutral",
        category=row.category or "everyday",
        origin=origin,
        review=Review(
            status=status,
            reviewer_id=row.reviewer_id,
            reviewer_type=reviewer_type,
            reviewed_at=row.reviewed_at,
        ),
        provenance=Provenance(license=row.licence or None, dataset=row.dataset_version),
        groups={"dialogue_family": row.dialogue_family_id, "film_id": row.scene_id},
        split="test",
    )


def pronoun_metric(
    rows: list[BenchmarkRow],
    outputs: dict[str, str],
    *,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Reuse ``run_evaluation``. The rate is an automatic check, not the 97% human gate."""
    scored = [row for row in rows if row.reference_khmer and row.id in outputs]
    if not scored:
        return metric(
            "pronoun_accuracy",
            reason="no reference line to pass through the pronoun post-check",
        )
    records = [to_dialogue_record(row) for row in scored]

    def translate(record: DialogueRecord) -> str:
        return outputs.get(record.id, "")

    from claynext.models.evaluation.runner import run_evaluation

    if out_dir is None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_evaluation(
                records,
                translate=translate,
                provider_id="benchmark-automatic-check",
                prompt_version="khmer-movie-benchmark-1",
                dataset_version=scored[0].dataset_version,
                out_dir=tmp,
            )
    else:
        report = run_evaluation(
            records,
            translate=translate,
            provider_id="benchmark-automatic-check",
            prompt_version="khmer-movie-benchmark-1",
            dataset_version=scored[0].dataset_version,
            out_dir=out_dir,
        )
    pronoun = report.get("pronoun") or {}
    return metric(
        "pronoun_accuracy",
        reason=(
            "automatic pronoun resolver and post-check via evaluation.runner; "
            "not a human pronoun-accuracy percentage"
        ),
        method="evaluation_runner",
        automatic_check={
            "passed": pronoun.get("passed"),
            "failed": pronoun.get("failed") or [],
            "evaluated": report.get("evaluated"),
            "postcheck_violations": (report.get("postcheck") or {}).get("violations"),
            "gold": all(row.is_gold_reference() for row in scored),
        },
        details={"evaluation_runner_split": report.get("split")},
    )
