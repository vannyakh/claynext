"""Exact and near-duplicate detection over normalized text.

Exact: identical ``normalize_text`` output. Near: character-shingle Jaccard similarity at or
above a threshold. Candidate pairs come from MinHash LSH with fixed seeds (deterministic),
then every candidate pair is confirmed with the exact Jaccard score, so LSH only affects
recall, never precision. Near duplicates are reported, never dropped automatically.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any, Iterable

from claynext.models.datasets.normalize import jaccard, normalize_text, shingles
from claynext.models.datasets.schema import STATUS_RANK, DialogueRecord

_PRIME = (1 << 61) - 1
_MASK = (1 << 64) - 1
FIELDS = ("target", "source")
ORIGIN_RANK = {"synthetic": 0, "human_reviewed": 1, "human_authored": 2}


def record_text(rec: DialogueRecord, which: str = "target") -> str:
    if which == "source":
        return rec.source_text
    cand = rec.preferred_candidate()
    return cand.text if cand else ""


class _UnionFind:
    def __init__(self, items: Iterable[str]):
        self.parent = {i: i for i in items}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # Smaller id becomes root so clusters are stable across runs.
            lo, hi = sorted((ra, rb))
            self.parent[hi] = lo

    def clusters(self) -> list[list[str]]:
        groups: dict[str, list[str]] = {}
        for item in self.parent:
            groups.setdefault(self.find(item), []).append(item)
        return sorted((sorted(g) for g in groups.values() if len(g) > 1), key=lambda g: g[0])


def _shingle_hash(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big")


def minhash_signature(sh: frozenset[str], perms: list[tuple[int, int]]) -> tuple[int, ...]:
    if not sh:
        return tuple(_MASK for _ in perms)
    hashes = [_shingle_hash(s) for s in sh]
    return tuple(min((a * h + b) % _PRIME for h in hashes) for a, b in perms)


def _permutations(num_perm: int, seed: int) -> list[tuple[int, int]]:
    rng = random.Random(seed)
    return [(rng.randrange(1, _PRIME), rng.randrange(0, _PRIME)) for _ in range(num_perm)]


@dataclass
class DuplicateReport:
    field: str
    threshold: float
    exact_groups: list[list[str]] = field(default_factory=list)
    near_pairs: list[tuple[str, str, float]] = field(default_factory=list)
    near_clusters: list[list[str]] = field(default_factory=list)
    cross_group_near_pairs: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "threshold": self.threshold,
            "exact_groups": len(self.exact_groups),
            "exact_duplicate_records": sum(len(g) - 1 for g in self.exact_groups),
            "near_pairs": len(self.near_pairs),
            "near_clusters": len(self.near_clusters),
            "cross_group_near_pairs": self.cross_group_near_pairs,
        }

    def to_dict(self, *, limit: int = 200) -> dict[str, Any]:
        return {
            **self.summary(),
            "exact_examples": self.exact_groups[:limit],
            "near_examples": [{"a": a, "b": b, "jaccard": round(s, 4)} for a, b, s in self.near_pairs[:limit]],
        }


def find_duplicates(
    records: list[DialogueRecord],
    *,
    which: str = "target",
    threshold: float = 0.8,
    shingle_size: int = 3,
    num_perm: int = 64,
    bands: int = 16,
    seed: int = 1729,
) -> DuplicateReport:
    if which not in FIELDS:
        raise ValueError(f"field must be one of {FIELDS}")
    if num_perm % bands:
        raise ValueError("num_perm must be divisible by bands")
    report = DuplicateReport(field=which, threshold=threshold)
    by_id = {r.id: r for r in records}

    exact: dict[str, list[str]] = {}
    for rec in records:
        norm = normalize_text(record_text(rec, which))
        if norm:
            exact.setdefault(norm, []).append(rec.id)
    report.exact_groups = sorted((sorted(ids) for ids in exact.values() if len(ids) > 1), key=lambda g: g[0])

    sh = {r.id: shingles(record_text(r, which), shingle_size) for r in records}
    perms = _permutations(num_perm, seed)
    rows = num_perm // bands
    buckets: dict[tuple[int, tuple[int, ...]], list[str]] = {}
    # One representative per exact group; exact copies are already reported.
    reps = sorted(min(ids) for ids in exact.values())
    for rid in reps:
        sig = minhash_signature(sh[rid], perms)
        for band in range(bands):
            buckets.setdefault((band, sig[band * rows:(band + 1) * rows]), []).append(rid)

    seen: set[tuple[str, str]] = set()
    uf = _UnionFind(reps)
    for ids in buckets.values():
        if len(ids) < 2:
            continue
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = sorted((ids[i], ids[j]))
                if (a, b) in seen:
                    continue
                seen.add((a, b))
                score = jaccard(sh[a], sh[b])
                if score >= threshold:
                    report.near_pairs.append((a, b, score))
                    uf.union(a, b)
                    if by_id[a].group_key() != by_id[b].group_key():
                        report.cross_group_near_pairs += 1
    report.near_pairs.sort(key=lambda p: (-p[2], p[0], p[1]))
    report.near_clusters = uf.clusters()
    return report


def _keep_rank(rec: DialogueRecord) -> tuple:
    return (-STATUS_RANK.get(rec.status, 0), -ORIGIN_RANK.get(rec.origin, 0), rec.id)


def drop_exact_duplicates(
    records: list[DialogueRecord], *, which: str = "target"
) -> tuple[list[DialogueRecord], list[dict[str, str]]]:
    """Keep the best record of each exact group (highest review status, then human origin, then id)."""
    by_norm: dict[str, list[DialogueRecord]] = {}
    for rec in records:
        by_norm.setdefault(normalize_text(record_text(rec, which)) or f"\0{rec.id}", []).append(rec)
    kept_ids: set[str] = set()
    dropped: list[dict[str, str]] = []
    for group in by_norm.values():
        group = sorted(group, key=_keep_rank)
        kept_ids.add(group[0].id)
        dropped.extend({"id": r.id, "duplicate_of": group[0].id} for r in group[1:])
    return [r for r in records if r.id in kept_ids], sorted(dropped, key=lambda d: d["id"])
