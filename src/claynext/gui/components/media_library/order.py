"""Sort library files by the episode number in the filename."""
from __future__ import annotations

import os
import re

_DIGIT_MAP = str.maketrans("０１２３４５６７８９", "0123456789")
_SEASON_EP = re.compile(r"[Ss](\d{1,3})\s*[._\- ]?[Ee](\d{1,4})")
_CN_EP = re.compile(r"第\s*(\d+)\s*[集话回]")
_EP_WORD = re.compile(r"(?:episodes?|eps?|e)\s*[._\- ]?\s*(\d{1,5})", re.IGNORECASE)
_TRAILING = re.compile(r"(\d{1,5})\s*$")


def episode_sort_key(path: str) -> tuple:
    """Order 第005集 before 第013集, and S01E02 before S01E10."""
    name = os.path.splitext(os.path.basename(path))[0].translate(_DIGIT_MAP)
    folded = name.casefold()
    season = _SEASON_EP.search(name)
    if season:
        return (0, int(season.group(1)), int(season.group(2)), folded)
    numbered = _CN_EP.search(name) or _EP_WORD.search(name) or _TRAILING.search(name)
    if numbered:
        return (0, 0, int(numbered.group(1)), folded)
    return (1, 0, 0, folded)
