"""TTS Pronunciation Normalizer: ``localized_text`` → ``tts_text``.

The subtitle line (``localized_text``) is never modified. This produces the
copy sent to a voice engine: Unicode NFC, zero-width characters removed,
the repetition mark ៗ expanded for listed words, standard abbreviations
spelled out, and (opt-in) unverified colloquial respellings.
"""
from __future__ import annotations

import re
from typing import Any

from claynext.models.khmer_localization.lexicon import TTS_FILE, find_forms, load_dictionary, normalize


def _lexicon(force_fallback: bool = False) -> dict[str, Any]:
    return load_dictionary(TTS_FILE, force_fallback=force_fallback)


def _expand_repeat(text: str, mark: str, words: list[str]) -> str:
    for word in sorted(words, key=len, reverse=True):
        text = re.sub(re.escape(word) + r"\s?" + re.escape(mark), f"{word}{word}", text)
    return text


def normalize_for_tts(
    localized_text: str,
    *,
    include_unverified: bool = False,
    lexicon: dict[str, Any] | None = None,
) -> str:
    lex = lexicon if lexicon is not None else _lexicon()
    text = normalize(localized_text)
    mark = str(lex.get("repeat_mark") or "ៗ")
    text = _expand_repeat(text, mark, [normalize(w) for w in lex.get("repeat_words") or []])
    for row in lex.get("abbreviations") or []:
        if row.get("standard") or include_unverified:
            text = text.replace(normalize(row["written"]), normalize(row["spoken"]))
    for row in lex.get("respellings") or []:
        if not (row.get("verified") or include_unverified):
            continue
        written, spoken = normalize(row["written"]), normalize(row["spoken"])
        for m in reversed(find_forms(text, [written])):
            text = text[:m.start] + spoken + text[m.end:]
    return re.sub(r"[ \t]+", " ", text).strip()


def tts_field(localized_text: str, **kwargs: Any) -> str | None:
    """``tts_text`` for the three-field line record: ``None`` when identical to the subtitle."""
    spoken = normalize_for_tts(localized_text, **kwargs)
    return None if spoken == str(localized_text or "").strip() else spoken
