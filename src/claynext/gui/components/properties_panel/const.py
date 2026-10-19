"""Track property kinds and the volume scale."""
from __future__ import annotations

import math

AUDIO_KINDS = {"video", "voice", "audio"}
VIDEO_TABS = ("video", "audio", "adjust")
DB_MIN, DB_MAX = -400, 60

def pct_to_db10(pct: float) -> int:
    if pct <= 0.5:
        return DB_MIN
    return max(DB_MIN, min(DB_MAX, round(200 * math.log10(pct / 100.0))))

def db10_to_pct(value: int) -> float:
    if value <= DB_MIN:
        return 0.0
    return min(200.0, 100.0 * 10 ** (value / 200.0))

def db_text(value: int) -> str:
    return "-∞ dB" if value <= DB_MIN else f"{value / 10:+.1f} dB"
