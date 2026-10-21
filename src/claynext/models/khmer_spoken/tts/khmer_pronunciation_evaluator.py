"""Lightweight text-side pronunciation / TTS-suitability checks for Khmer lines.

Does not score audio waveforms (that belongs to voice_training evaluation).
Flags issues that often break TTS: empty text, missing Khmer script, extreme length.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

_KHMER_RE = re.compile(r"[\u1780-\u17FF]")


@dataclass
class PronunciationCheck:
    ok: bool
    score: float  # 0..1 heuristic
    issues: list[str]
    char_count: int
    khmer_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_pronunciation_text(text: str, *, max_chars: int = 280) -> PronunciationCheck:
    text = (text or "").strip()
    issues: list[str] = []
    if not text:
        return PronunciationCheck(False, 0.0, ["empty_text"], 0, 0.0)
    khmer = sum(1 for ch in text if _KHMER_RE.match(ch))
    ratio = khmer / max(1, len(text))
    if ratio < 0.3:
        issues.append("low_khmer_script_ratio")
    if len(text) > max_chars:
        issues.append("too_long_for_preview")
    # Heuristic score
    score = min(1.0, ratio) * (0.7 if len(text) <= max_chars else 0.4)
    if not issues:
        score = max(score, 0.75)
    return PronunciationCheck(
        ok=not issues,
        score=round(score, 3),
        issues=issues,
        char_count=len(text),
        khmer_ratio=round(ratio, 3),
    )
