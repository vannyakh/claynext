"""Versioned Khmer dictionaries and pronoun / term detection in unsegmented Khmer text.

Khmer is written without spaces between words, so detection works on
orthographic clusters: a form only matches when it is not glued to a
subscript (coeng) or dependent vowel / sign on either side, and known
compounds (ខ្លួនឯង, ម្នាក់ឯង, បងប្អូន, ...) are masked first. Forms marked
``boundary: word`` (short kin terms such as តា, ពូ) also need whitespace or
punctuation on both sides, trading misses for fewer false hits.
"""
from __future__ import annotations

import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from claynext.prompts import loader

DICTIONARY_DIR = loader.PROMPTS_DIR / "dictionaries" / "khmer"
PRONOUNS_FILE = DICTIONARY_DIR / "pronouns.yaml"
PROFANITY_FILE = DICTIONARY_DIR / "profanity.yaml"
REGIONAL_FILE = DICTIONARY_DIR / "regional.yaml"
TTS_FILE = DICTIONARY_DIR / "tts_pronunciation.yaml"

_COENG = "\u17d2"
_ZERO_WIDTH = "\u200b\u200c\u200d\ufeff"
_MASK = "\x00"

_cache: dict[tuple[str, bool], Any] = {}
_cache_lock = threading.Lock()


def load_dictionary(path: Path, *, force_fallback: bool = False) -> dict[str, Any]:
    key = (str(path), force_fallback)
    with _cache_lock:
        if key not in _cache:
            data = loader.load_yaml(path, force_fallback=force_fallback) or {}
            if not isinstance(data, dict):
                raise loader.ManifestError(f"{path.name}: dictionary must be a mapping")
            _cache[key] = data
        return _cache[key]


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", str(text or ""))
    return "".join(ch for ch in text if ch not in _ZERO_WIDTH)


def _is_khmer_mark(ch: str) -> bool:
    # Dependent vowels, signs, and coeng; U+17D4-U+17DA are punctuation (។ ៕ ...).
    return "\u17b6" <= ch <= "\u17d3" or ch == "\u17dd"


def _is_word_gap(ch: str) -> bool:
    if not ch:
        return True
    return ch.isspace() or unicodedata.category(ch)[0] in ("P", "Z", "S") or ch in "។៕៖!?,.\"'"


@dataclass(frozen=True)
class Match:
    form: str
    start: int
    end: int


def _mask_compounds(text: str, compounds: Iterable[str]) -> str:
    chars = list(text)
    for comp in sorted({normalize(c) for c in compounds if c}, key=len, reverse=True):
        start = 0
        while True:
            i = text.find(comp, start)
            if i < 0:
                break
            for k in range(i, i + len(comp)):
                chars[k] = _MASK
            start = i + len(comp)
    return "".join(chars)


def find_forms(
    text: str,
    forms: Iterable[str],
    *,
    compounds: Iterable[str] = (),
    word_bounded: Iterable[str] = (),
) -> list[Match]:
    """Non-overlapping matches of ``forms`` in ``text``, longest form first."""
    text = normalize(text)
    work = _mask_compounds(text, compounds)
    strict = {normalize(f) for f in word_bounded}
    found: list[Match] = []
    for form in sorted({normalize(f) for f in forms if f}, key=len, reverse=True):
        start = 0
        while True:
            i = work.find(form, start)
            if i < 0:
                break
            end = i + len(form)
            prev = work[i - 1] if i else ""
            nxt = work[end] if end < len(work) else ""
            ok = prev != _COENG and not (nxt and (_is_khmer_mark(nxt) or nxt == _COENG))
            if ok and form in strict:
                ok = _is_word_gap(prev) and _is_word_gap(nxt)
            if ok:
                found.append(Match(form, i, end))
                work = work[:i] + _MASK * len(form) + work[end:]
                start = end
            else:
                start = i + 1
    return sorted(found, key=lambda m: m.start)


class PronounInventory:
    """Forms, compounds, and relation rules from ``pronouns.yaml``."""

    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.version = str(data.get("version") or "")
        self.forms: dict[str, dict[str, Any]] = {}
        self.variant_of: dict[str, str] = {}
        for row in data.get("forms") or []:
            form = normalize(row.get("form") or "")
            if not form:
                continue
            self.forms[form] = dict(row)
            for alt in row.get("variants") or []:
                self.variant_of[normalize(alt)] = form
        self.compounds = [normalize(c) for c in data.get("compounds_not_pronoun") or []]
        self.relations: dict[str, dict[str, Any]] = dict(data.get("relations") or {})
        self.aliases: dict[str, str] = {str(k): str(v) for k, v in (data.get("aliases") or {}).items()}

    @classmethod
    def load(cls, path: Path = PRONOUNS_FILE, *, force_fallback: bool = False) -> "PronounInventory":
        return cls(load_dictionary(path, force_fallback=force_fallback))

    @property
    def rough_forms(self) -> set[str]:
        return {f for f, row in self.forms.items() if row.get("rough")}

    @property
    def habit_gated(self) -> set[str]:
        return {f for f, row in self.forms.items() if row.get("habit_gated")}

    def person(self, form: str) -> str:
        return str((self.forms.get(self.canonical(form)) or {}).get("person") or "")

    def canonical(self, form: str) -> str:
        form = normalize(form)
        return self.variant_of.get(form, form)

    def relation(self, name: str) -> tuple[str, dict[str, Any] | None]:
        key = str(name or "").strip().lower()
        key = self.aliases.get(key, key)
        return key, self.relations.get(key)

    def detect(self, text: str) -> list[Match]:
        all_forms = list(self.forms) + list(self.variant_of)
        bounded = [f for f, row in self.forms.items() if row.get("boundary") == "word"]
        return [
            Match(self.canonical(m.form), m.start, m.end)
            for m in find_forms(text, all_forms, compounds=self.compounds, word_bounded=bounded)
        ]


def load_inventory(*, force_fallback: bool = False) -> PronounInventory:
    return PronounInventory.load(force_fallback=force_fallback)
