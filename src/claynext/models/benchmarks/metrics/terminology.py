"""Glossary presence checks. Absence of a glossary leaves the metric unscored."""
from __future__ import annotations

from typing import Any

from claynext.models.benchmarks.metrics.common import metric, not_scored
from claynext.models.benchmarks.schema import BenchmarkRow


def terminology_metric(
    rows: list[BenchmarkRow],
    outputs: dict[str, str],
    glossary: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if not glossary:
        return not_scored(
            "terminology",
            "no glossary supplied; terminology consistency is not scored",
        )
    checks: list[dict[str, Any]] = []
    for row in rows:
        text = outputs.get(row.id, "")
        for term in glossary:
            source = str(term.get("source") or "")
            khmer = str(term.get("khmer") or "")
            if source and source in row.source_text:
                checks.append({
                    "id": row.id,
                    "source": source,
                    "khmer_present": bool(khmer) and khmer in text,
                })
    return metric(
        "terminology",
        method="glossary_presence",
        reason="presence checks are not a terminology accuracy score",
        details={"checks": checks},
    )
