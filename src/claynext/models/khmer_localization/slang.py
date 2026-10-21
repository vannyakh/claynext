"""Slang and Profanity Selector: how casual and how strong a localized line may be.

``allowed profanity = min(source level, character level, project cap, scene cap)``.
The source level comes from markers in the source line, so a character who is
angry but does not swear gets level 0. Slang is capped the same way but is
not bound to the source, since register is a character trait.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from claynext.models.khmer_localization.lexicon import PROFANITY_FILE, find_forms, load_dictionary
from claynext.models.khmer_localization.speech_profile import LocalizationConfig, SceneStyle, SpeechProfile


@dataclass
class LevelDecision:
    source_profanity: int
    allowed_profanity: int
    allowed_slang: int
    markers: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _lexicon(force_fallback: bool = False) -> dict[str, Any]:
    return load_dictionary(PROFANITY_FILE, force_fallback=force_fallback)


def source_intensity(text: str, language: str = "english", *, force_fallback: bool = False) -> tuple[int, list[str]]:
    """Highest profanity / insult level found in a source line, with the matched markers."""
    markers = ((_lexicon(force_fallback).get("source_markers") or {}).get(language.lower()) or [])
    low = str(text or "").lower()
    level, hits = 0, []
    for row in markers:
        term = str(row.get("term") or "").lower()
        if term and re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", low):
            hits.append(term)
            level = max(level, int(row.get("level") or 0))
    return level, hits


def khmer_intensity(text: str, *, force_fallback: bool = False) -> tuple[int, list[str]]:
    """Highest level of listed Khmer insult / swear terms in a localized line (detection only)."""
    rows = _lexicon(force_fallback).get("khmer_terms") or []
    levels = {str(r["term"]): int(r.get("level") or 0) for r in rows if r.get("term")}
    hits = [m.form for m in find_forms(text, levels)]
    return max((levels[h] for h in hits), default=0), hits


def select_levels(
    source_text: str,
    profile: SpeechProfile | None,
    config: LocalizationConfig,
    scene: SceneStyle | None = None,
    *,
    source_language: str = "english",
) -> LevelDecision:
    src, markers = source_intensity(source_text, source_language)
    caps = {"source": src, "project": config.profanity_cap}
    slang_caps = {"project": config.slang_cap}
    if profile is not None:
        caps["character"] = profile.profanity_level
        slang_caps["character"] = profile.slang_level
    else:
        slang_caps["character"] = 0
    if scene is not None and scene.profanity_cap is not None:
        caps["scene"] = scene.profanity_cap
    if scene is not None and scene.slang_cap is not None:
        slang_caps["scene"] = scene.slang_cap
    allowed = min(caps.values())
    slang = min(slang_caps.values())
    reasons = [f"profanity capped by {k}={v}" for k, v in caps.items() if v == allowed]
    reasons += [f"slang capped by {k}={v}" for k, v in slang_caps.items() if v == slang]
    return LevelDecision(source_profanity=src, allowed_profanity=allowed, allowed_slang=slang,
                         markers=markers, reasons=reasons)
