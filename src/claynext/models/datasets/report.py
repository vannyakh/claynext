"""Dataset quality report: distributions, missing fields, validation warnings, duplicates, splits."""
from __future__ import annotations

from collections import Counter
from typing import Any

from claynext.models.datasets.dedupe import DuplicateReport
from claynext.models.datasets.schema import QUALITY_DIMENSIONS, DialogueRecord, validate_record
from claynext.models.datasets.split import SPLITS, find_leaks


def _tally(values) -> dict[str, int]:
    return dict(Counter(v if v not in (None, "") else "(none)" for v in values).most_common())


def quality_report(
    records: list[DialogueRecord],
    *,
    duplicates: DuplicateReport | None = None,
    near_clusters: list[list[str]] | None = None,
) -> dict[str, Any]:
    issues = [(r.id, i) for r in records for i in validate_record(r)]
    missing = {
        "category": sum(1 for r in records if not r.category),
        "emotion": sum(1 for r in records if not r.emotion),
        "speaker_id": sum(1 for r in records if not r.speaker_id),
        "listener_id": sum(1 for r in records if not r.listener_id),
        "relationship": sum(1 for r in records if not r.relationship),
        "register": sum(1 for r in records if not r.register),
        "intensity": sum(1 for r in records if r.intensity is None),
        "license": sum(1 for r in records if not r.provenance.license),
        "group_key": sum(1 for r in records if r.group_key().startswith("id:")),
        "tts_text": sum(1 for r in records if not r.tts_text),
        "literal_candidate": sum(1 for r in records if not any(c.style == "literal" for c in r.candidates)),
        "natural_candidate": sum(1 for r in records if not any(c.style == "natural" for c in r.candidates)),
        "quality_scores": sum(1 for r in records if not r.quality.scores),
    }
    scored = {
        d: sum(1 for r in records if r.quality.scores.get(d) is not None) for d in QUALITY_DIMENSIONS
    }
    split_counts = {s: sum(1 for r in records if r.split == s) for s in SPLITS}
    split_counts["(none)"] = sum(1 for r in records if not r.split)
    report: dict[str, Any] = {
        "total": len(records),
        "training_eligible": sum(1 for r in records if r.status in ("reviewed", "gold")),
        "by_status": _tally(r.status for r in records),
        "by_origin": _tally(r.origin for r in records),
        "by_category": _tally(r.category for r in records),
        "by_emotion": _tally(r.emotion for r in records),
        "by_relationship": _tally(r.relationship for r in records),
        "by_register": _tally(r.register for r in records),
        "by_dataset": _tally(r.provenance.dataset for r in records),
        "groups": len({r.group_key() for r in records}),
        "missing": missing,
        "scored_dimensions": scored,
        "validation": {
            "errors": _tally(i.code for _, i in issues if i.severity == "error"),
            "warnings": _tally(i.code for _, i in issues if i.severity == "warning"),
        },
        "splits": split_counts,
        "leaks": find_leaks(records, near_clusters=near_clusters),
    }
    if duplicates is not None:
        report["duplicates"] = duplicates.summary()
    return report


def format_report(report: dict[str, Any]) -> str:
    lines = [f"records: {report['total']}   training-eligible (reviewed+gold): {report['training_eligible']}"
             f"   groups: {report['groups']}"]
    for key in ("by_status", "by_origin", "by_category", "by_emotion", "by_relationship", "by_register", "splits"):
        values = report.get(key) or {}
        lines.append(f"{key.replace('by_', ''):<13} " + ", ".join(f"{k}={v}" for k, v in values.items()))
    lines.append("missing       " + ", ".join(f"{k}={v}" for k, v in report["missing"].items() if v))
    for sev in ("errors", "warnings"):
        values = report["validation"][sev]
        lines.append(f"{sev:<13} " + (", ".join(f"{k}={v}" for k, v in values.items()) or "none"))
    if "duplicates" in report:
        d = report["duplicates"]
        lines.append(
            f"duplicates    exact_groups={d['exact_groups']} exact_records={d['exact_duplicate_records']} "
            f"near_pairs={d['near_pairs']} near_clusters={d['near_clusters']} "
            f"cross_group_near_pairs={d['cross_group_near_pairs']} (field={d['field']}, J>={d['threshold']})"
        )
    lines.append(f"leaks         {len(report['leaks'])}")
    return "\n".join(lines)
