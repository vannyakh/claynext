"""Text normalization and shingling for duplicate detection (Khmer-aware, deterministic)."""
from __future__ import annotations

import re
import unicodedata

KHMER_RANGE = ("\u1780", "\u17ff")
KHMER_SYMBOLS = ("\u19e0", "\u19ff")
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)
# Khmer sentence / section signs (not the repetition mark ៗ U+17D7) and common punctuation.
_PUNCT = re.compile(r"[\u17d4-\u17d6\u17d8-\u17da\s\.,!?;:'\"“”‘’…\-–—()\[\]{}«»/\\|~`*_]+")


def has_khmer(text: str) -> bool:
    return any(KHMER_RANGE[0] <= ch <= KHMER_RANGE[1] or KHMER_SYMBOLS[0] <= ch <= KHMER_SYMBOLS[1] for ch in text or "")


def normalize_text(text: str) -> str:
    """NFC, no zero-width marks, lowercase Latin, punctuation and whitespace removed.

    Khmer is written without spaces between words, so spacing is not meaningful for
    duplicate detection and is dropped along with punctuation.
    """
    value = unicodedata.normalize("NFC", str(text or "")).translate(_ZERO_WIDTH)
    return _PUNCT.sub("", value.casefold())


def shingles(text: str, size: int = 3) -> frozenset[str]:
    """Character n-grams of the normalized text. Short strings yield one shingle."""
    norm = normalize_text(text)
    if not norm:
        return frozenset()
    if len(norm) <= size:
        return frozenset({norm})
    return frozenset(norm[i:i + size] for i in range(len(norm) - size + 1))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
