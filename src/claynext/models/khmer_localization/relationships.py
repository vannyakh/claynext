"""Relationship Context Analyzer: directed speaker → listener relationships with evidence.

Relationships come from the editor or project config (trusted) or from
heuristics over the source line (vocatives like "Mom", "boss"), which are
recorded as evidence with low confidence and always reviewed.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Iterable

from claynext.models.khmer_localization.lexicon import PronounInventory, load_inventory

SOURCES = ("editor", "project_config", "heuristic", "dataset")
TRUSTED = ("editor", "project_config", "dataset")
HEURISTIC_CONFIDENCE = 0.5


@dataclass
class Relationship:
    speaker: str
    listener: str
    relation: str
    hostility: int = 0
    intimacy: int = 0
    source: str = "project_config"
    confidence: float = 1.0
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def validate(self, inventory: PronounInventory | None = None) -> "Relationship":
        if not self.speaker or not self.listener:
            raise ValueError("relationship needs speaker and listener")
        inv = inventory or load_inventory()
        key, rule = inv.relation(self.relation)
        if rule is None:
            raise ValueError(f"unknown relation {self.relation!r}")
        self.relation = key
        self.hostility = max(0, min(3, int(self.hostility or 0)))
        self.intimacy = max(0, min(3, int(self.intimacy or 0)))
        if self.source not in SOURCES:
            raise ValueError(f"relationship source {self.source!r} not in {SOURCES}")
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        return self

    @property
    def trusted(self) -> bool:
        return self.source in TRUSTED

    def inverse(self, inventory: PronounInventory | None = None) -> "Relationship | None":
        inv = inventory or load_inventory()
        _key, rule = inv.relation(self.relation)
        other = str((rule or {}).get("inverse") or "")
        if not other:
            return None
        return Relationship(
            speaker=self.listener, listener=self.speaker, relation=other,
            hostility=self.hostility, intimacy=self.intimacy, source=self.source,
            confidence=self.confidence, evidence=[{"source": "inverse_of", "relation": self.relation}],
        )


class RelationshipGraph:
    def __init__(self, inventory: PronounInventory | None = None):
        self._inv = inventory
        self._edges: dict[tuple[str, str], Relationship] = {}

    @property
    def inventory(self) -> PronounInventory:
        if self._inv is None:
            self._inv = load_inventory()
        return self._inv

    def set(self, rel: Relationship, *, with_inverse: bool = True) -> Relationship:
        rel.validate(self.inventory)
        current = self._edges.get((rel.speaker, rel.listener))
        if current is not None and current.trusted and not rel.trusted:
            return current
        self._edges[(rel.speaker, rel.listener)] = rel
        if with_inverse:
            inv = rel.inverse(self.inventory)
            existing = self._edges.get((rel.listener, rel.speaker))
            if inv is not None and (existing is None or not existing.trusted or rel.trusted):
                self._edges[(inv.speaker, inv.listener)] = inv.validate(self.inventory)
        return rel

    def get(self, speaker: str, listener: str) -> Relationship | None:
        return self._edges.get((speaker, listener))

    def to_list(self) -> list[dict[str, Any]]:
        return [asdict(r) for _k, r in sorted(self._edges.items())]

    @classmethod
    def from_list(cls, rows: Iterable[dict[str, Any]], inventory: PronounInventory | None = None) -> "RelationshipGraph":
        graph = cls(inventory)
        names = {f.name for f in fields(Relationship)}
        for row in rows or []:
            graph.set(Relationship(**{k: v for k, v in row.items() if k in names}), with_inverse=False)
        return graph


def analyze_line(
    text: str,
    speaker: str,
    listener: str,
    *,
    inventory: PronounInventory | None = None,
) -> Relationship | None:
    """Heuristic relationship hint from English vocatives in the source line."""
    inv = inventory or load_inventory()
    low = str(text or "").lower()
    for cue in inv.data.get("vocative_cues") or []:
        pattern = str(cue.get("pattern") or "")
        m = re.search(pattern, low) if pattern else None
        if not m:
            continue
        return Relationship(
            speaker=speaker, listener=listener, relation=str(cue["relation"]),
            source="heuristic", confidence=HEURISTIC_CONFIDENCE,
            evidence=[{"source": "vocative", "match": m.group(0), "text": str(text)[:80],
                       "listener_gender": str(cue.get("listener_gender") or "")}],
        ).validate(inv)
    return None
