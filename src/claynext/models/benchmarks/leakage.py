"""Dialogue-family leakage checks for the held-out benchmark.

A test row is refused when its ``dialogue_family_id`` also appears in train.
That covers paraphrases that share a family id. Character-level near-duplicate
hashing is a separate, unscheduled job.
"""
from __future__ import annotations

from claynext.models.benchmarks.schema import BenchmarkRow


class LeakageError(ValueError):
    def __init__(self, families: list[str]):
        self.families = list(families)
        joined = ", ".join(self.families)
        super().__init__(
            "refusing to score: dialogue family also appears in train: " + joined
        )


def train_families(
    rows: list[BenchmarkRow],
    train_rows: list[BenchmarkRow] | None = None,
) -> set[str]:
    families: set[str] = set()
    for row in train_rows or []:
        if row.dialogue_family_id:
            families.add(row.dialogue_family_id)
    for row in rows:
        if row.split == "train" and row.dialogue_family_id:
            families.add(row.dialogue_family_id)
    return families


def leaked_families(
    rows: list[BenchmarkRow],
    train_rows: list[BenchmarkRow] | None = None,
) -> list[str]:
    """Family ids that would leak into the rows being scored."""
    families = train_families(rows, train_rows)
    found: list[str] = []
    if train_rows is not None:
        scored = rows
    else:
        scored = [row for row in rows if row.split == "test"]
    for row in scored:
        if row.dialogue_family_id and row.dialogue_family_id in families:
            found.append(row.dialogue_family_id)
    return sorted(set(found))


def assert_no_leakage(
    rows: list[BenchmarkRow],
    train_rows: list[BenchmarkRow] | None = None,
) -> None:
    leaked = leaked_families(rows, train_rows)
    if leaked:
        raise LeakageError(leaked)
