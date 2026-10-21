"""Group-aware train / validation / test split with a fixed seed and a leakage check.

Every record belongs to one group (first present key of film / script / dialogue family /
speaker, else its own id). Near-duplicate clusters can merge groups so that paraphrases of
the same line never land in different splits. Whole groups are assigned, largest first,
to the split furthest below its target size; ties follow a seeded shuffle.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from claynext.models.datasets.dedupe import _UnionFind
from claynext.models.datasets.schema import GROUP_KEYS, DialogueRecord

SPLITS = ("train", "validation", "test")
DEFAULT_RATIOS = (0.8, 0.1, 0.1)
DEFAULT_SEED = 13


@dataclass
class SplitReport:
    seed: int
    ratios: tuple[float, ...]
    group_keys: tuple[str, ...]
    assignments: dict[str, str] = field(default_factory=dict)
    excluded: list[str] = field(default_factory=list)
    groups: dict[str, list[str]] = field(default_factory=dict)
    merged_by_near_duplicates: int = 0

    def counts(self) -> dict[str, dict[str, int]]:
        out = {s: {"records": 0, "groups": 0} for s in SPLITS}
        for split in self.assignments.values():
            out[split]["records"] += 1
        for members in self.groups.values():
            out[self.assignments[members[0]]]["groups"] += 1
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "ratios": dict(zip(SPLITS, self.ratios)),
            "group_keys": list(self.group_keys),
            "splits": self.counts(),
            "excluded": len(self.excluded),
            "groups": len(self.groups),
            "groups_merged_by_near_duplicates": self.merged_by_near_duplicates,
        }


def split_records(
    records: list[DialogueRecord],
    *,
    ratios: tuple[float, float, float] = DEFAULT_RATIOS,
    seed: int = DEFAULT_SEED,
    group_keys: tuple[str, ...] = GROUP_KEYS,
    near_clusters: list[list[str]] | None = None,
    exclude_statuses: tuple[str, ...] = ("rejected",),
) -> SplitReport:
    if len(ratios) != len(SPLITS) or any(r < 0 for r in ratios) or abs(sum(ratios) - 1.0) > 1e-6:
        raise ValueError("ratios must be three non-negative numbers that sum to 1")
    report = SplitReport(seed=seed, ratios=tuple(ratios), group_keys=tuple(group_keys))
    kept = [r for r in records if r.status not in exclude_statuses]
    report.excluded = sorted(r.id for r in records if r.status in exclude_statuses)

    base_group = {r.id: r.group_key(group_keys) for r in kept}
    uf = _UnionFind(sorted(set(base_group.values())))
    for cluster in near_clusters or []:
        gids = sorted({base_group[i] for i in cluster if i in base_group})
        for other in gids[1:]:
            if uf.find(gids[0]) != uf.find(other):
                report.merged_by_near_duplicates += 1
            uf.union(gids[0], other)
    for rid, gid in base_group.items():
        report.groups.setdefault(uf.find(gid), []).append(rid)
    for members in report.groups.values():
        members.sort()

    order = sorted(report.groups)
    random.Random(seed).shuffle(order)
    rank = {gid: i for i, gid in enumerate(order)}
    total = len(kept)
    targets = [ratio * total for ratio in ratios]
    sizes = [0] * len(SPLITS)
    for gid in sorted(order, key=lambda g: (-len(report.groups[g]), rank[g])):
        idx = max(range(len(SPLITS)), key=lambda i: (targets[i] - sizes[i], -i))
        sizes[idx] += len(report.groups[gid])
        for rid in report.groups[gid]:
            report.assignments[rid] = SPLITS[idx]
    return report


def apply_split(records: list[DialogueRecord], report: SplitReport) -> None:
    for rec in records:
        rec.split = report.assignments.get(rec.id)


def find_leaks(
    records: list[DialogueRecord],
    *,
    group_keys: tuple[str, ...] = GROUP_KEYS,
    near_clusters: list[list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Groups (or near-duplicate clusters) whose records sit in more than one split."""
    leaks = []
    by_group: dict[str, set[str]] = {}
    for rec in records:
        if rec.split:
            by_group.setdefault(rec.group_key(group_keys), set()).add(rec.split)
    leaks.extend({"group": g, "splits": sorted(s)} for g, s in sorted(by_group.items()) if len(s) > 1)
    split_of = {r.id: r.split for r in records}
    for cluster in near_clusters or []:
        splits = {split_of.get(i) for i in cluster} - {None}
        if len(splits) > 1:
            leaks.append({"near_duplicate_cluster": cluster, "splits": sorted(splits)})
    return leaks
