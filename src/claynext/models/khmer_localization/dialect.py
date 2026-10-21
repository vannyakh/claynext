"""Regional Dialect Adapter: curated regional vocabulary, applied only with evidence.

Automatic replacement needs all of: the project enables regional vocabulary,
the character's region was set by the editor or project config, and the entry
is ``verified`` with at least one evidence row. Every other match is returned
as a suggestion for human review and the text is left unchanged.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from claynext.models.khmer_localization.lexicon import REGIONAL_FILE, find_forms, load_dictionary, normalize
from claynext.models.khmer_localization.speech_profile import LocalizationConfig, SpeechProfile

TRUSTED_REGION_SOURCES = ("editor", "project_config")


@dataclass
class DialectEntry:
    region: str
    standard: str
    regional: str
    verified: bool = False
    evidence: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""

    @property
    def applicable(self) -> bool:
        return bool(self.verified and self.evidence)


@dataclass
class DialectResult:
    text: str
    applied: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RegionalDialectAdapter:
    def __init__(self, entries: list[DialectEntry] | None = None):
        if entries is None:
            data = load_dictionary(REGIONAL_FILE)
            entries = [DialectEntry(**dict(row)) for row in data.get("entries") or []]
        self.entries = entries

    def apply(self, text: str, profile: SpeechProfile | None, config: LocalizationConfig) -> DialectResult:
        out = DialectResult(text=text)
        region = profile.region if profile else None
        if not region:
            out.reasons.append("no region set for this character")
            return out
        candidates = [e for e in self.entries if e.region == region]
        trusted = profile.region_source in TRUSTED_REGION_SOURCES
        work = normalize(text)
        for entry in candidates:
            if not find_forms(work, [entry.standard]):
                continue
            row = {"region": region, "standard": entry.standard, "regional": entry.regional,
                   "verified": entry.verified, "evidence": len(entry.evidence)}
            if config.allow_regional and trusted and entry.applicable:
                work = work.replace(normalize(entry.standard), normalize(entry.regional))
                out.applied.append(row)
            else:
                out.suggestions.append(row)
        if not config.allow_regional:
            out.reasons.append("regional vocabulary disabled for this project")
        if not trusted:
            out.reasons.append(f"region source {profile.region_source or 'none'} is not editor or project config")
        out.text = work if out.applied else text
        return out
