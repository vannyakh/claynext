"""Lightweight audio quality scoring for segment keep/drop decisions."""
from __future__ import annotations

import struct
import wave
from pathlib import Path
from typing import Any


def score_wav(wav_path: str | Path) -> dict[str, Any]:
    """
    Return ``{quality_score (0-1), duration_sec, peak, rms, keep}``.

    Heuristic only — no ML. Drops near-silent or extremely short clips.
    """
    path = Path(wav_path)
    if not path.is_file():
        return {"quality_score": 0.0, "duration_sec": 0.0, "peak": 0.0, "rms": 0.0, "keep": False}

    try:
        with wave.open(str(path), "rb") as wf:
            rate = wf.getframerate()
            ch = wf.getnchannels()
            width = wf.getsampwidth()
            n = wf.getnframes()
            raw = wf.readframes(n)
            duration = n / max(rate, 1)
    except Exception:
        return {"quality_score": 0.3, "duration_sec": 0.0, "peak": 0.0, "rms": 0.0, "keep": True}

    peak = 0.0
    rms = 0.0
    if width == 2 and raw:
        samples = struct.unpack(f"<{len(raw) // 2}h", raw)
        if ch > 1:
            samples = samples[::ch]
        if samples:
            peak = max(abs(s) for s in samples) / 32768.0
            rms = (sum(s * s for s in samples) / len(samples)) ** 0.5 / 32768.0

    score = 0.5
    if duration >= 0.4:
        score += 0.15
    if 0.02 <= rms <= 0.35:
        score += 0.2
    if peak >= 0.05:
        score += 0.1
    if duration < 0.2 or rms < 0.005:
        score = min(score, 0.2)

    score = max(0.0, min(1.0, score))
    keep = score >= 0.35 and duration >= 0.2
    return {
        "quality_score": round(score, 3),
        "duration_sec": round(duration, 3),
        "peak": round(peak, 4),
        "rms": round(rms, 4),
        "keep": keep,
    }
