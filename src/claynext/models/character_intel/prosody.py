"""Per-line acoustic features (energy, pitch, voicing) from the source vocals.

Rust ``claynext-ai analyze-prosody`` does the work. The numpy version below is
the fallback for a Studio without built binaries and mirrors the same rules.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("claynext.character_intel.prosody")

SAMPLE_RATE = 8000
_FRAME_SEC = 0.04
_MAX_PITCH_FRAMES = 32
_F0_MIN, _F0_MAX = 70.0, 420.0


def line_spans(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from claynext.models.dubbing_service import timestamp_to_sec

    spans = []
    for index, seg in enumerate(segments):
        start = float(seg.get("start_sec") or timestamp_to_sec(str(seg.get("start", ""))))
        end = float(seg.get("end_sec") or timestamp_to_sec(str(seg.get("end", ""))))
        if end > start:
            spans.append({"index": index, "start_sec": start, "end_sec": end})
    return spans


def analyze_segments_prosody(audio_path: str, segments: list[dict[str, Any]]) -> list[dict[str, Any] | None]:
    """One feature dict (or None) per segment. Never raises."""
    out: list[dict[str, Any] | None] = [None] * len(segments)
    if not audio_path or not os.path.isfile(audio_path) or not segments:
        return out
    spans = line_spans(segments)
    if not spans:
        return out
    try:
        from claynext.adapters.ai import get_ai_adapter

        ai = get_ai_adapter()
        pcm = ai.decode_mono_pcm(audio_path, SAMPLE_RATE)
        if not pcm:
            return out
        feats = ai.analyze_prosody_pcm(pcm, SAMPLE_RATE, spans)
        if feats is None:
            feats = prosody_fallback(pcm, SAMPLE_RATE, spans)
    except Exception as exc:
        logger.debug("prosody analysis failed: %s", exc)
        return out
    for row in feats or []:
        idx = int(row.get("index", -1))
        if 0 <= idx < len(out):
            out[idx] = row
    return out


def prosody_fallback(pcm: bytes, sample_rate: int, spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    import numpy as np

    samples = np.frombuffer(pcm, dtype="<f4").astype(np.float32)
    frame = max(16, int(sample_rate * _FRAME_SEC))
    track = _frame_rms(samples, frame)
    floor, median_voiced = _track_levels(track)
    rows = []
    for span in spans:
        start = min(len(samples), int(max(0.0, float(span["start_sec"])) * sample_rate))
        end = min(len(samples), int(max(float(span["start_sec"]), float(span["end_sec"])) * sample_rate))
        rows.append(_features(samples[start:end], sample_rate, frame, floor, median_voiced, span))
    return rows


def _frame_rms(x, frame: int):
    import numpy as np

    n = len(x) // frame
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    return np.sqrt(np.mean(x[: n * frame].reshape(n, frame) ** 2, axis=1))


def _track_levels(rms) -> tuple[float, float]:
    import numpy as np

    if len(rms) == 0:
        return 0.008, 0.05
    s = np.sort(rms)
    noise = float(s[(len(s) - 1) * 20 // 100])
    peak = max(float(s[(len(s) - 1) * 95 // 100]), noise + 1e-4)
    floor = max(noise + (peak - noise) * 0.08, 0.004)
    voiced = s[s >= floor]
    median = float(voiced[len(voiced) // 2]) if len(voiced) else peak
    return floor, max(median, 1e-4)


def _db(v: float) -> float:
    import math

    return 20.0 * math.log10(max(v, 1e-5))


def _pitch(frame, sample_rate: int) -> float | None:
    import numpy as np

    n = len(frame)
    min_lag = int(sample_rate / _F0_MAX)
    max_lag = min(int(np.ceil(sample_rate / _F0_MIN)), n - n // 4)
    if min_lag < 2 or max_lag <= min_lag:
        return None
    x = frame - frame.mean()
    if float(np.sum(x * x)) <= 1e-6:
        return None
    scores = []
    for lag in range(min_lag, max_lag + 1):
        a, b = x[: n - lag], x[lag:]
        denom = float(np.sqrt(np.sum(a * a) * np.sum(b * b)))
        scores.append(float(np.sum(a * b)) / denom if denom > 1e-9 else 0.0)
    best = max(scores) if scores else 0.0
    if best < 0.5:
        return None
    for k, r in enumerate(scores):
        left = scores[k - 1] if k > 0 else float("-inf")
        right = scores[k + 1] if k + 1 < len(scores) else float("-inf")
        if r >= best * 0.9 and r >= left and r >= right:
            return sample_rate / float(min_lag + k)
    return None


def _features(chunk, sample_rate: int, frame: int, floor: float, median_voiced: float, span: dict) -> dict:
    import math

    import numpy as np

    start, end = float(span["start_sec"]), float(span["end_sec"])
    row = {
        "index": int(span.get("index", 0)),
        "start_sec": start,
        "end_sec": end,
        "duration_sec": max(0.0, end - start),
        "rms_db": -90.0,
        "peak_db": -90.0,
        "loudness_rel_db": 0.0,
        "pitch_hz": 0.0,
        "pitch_range_st": 0.0,
        "voiced_ratio": 0.0,
        "pause_ratio": 0.0,
        "confidence": 0.0,
    }
    if len(chunk) < frame:
        return row
    rms = _frame_rms(chunk, frame)
    row["rms_db"] = _db(float(np.sqrt(np.mean(rms ** 2))))
    row["peak_db"] = _db(float(np.max(np.abs(chunk))))
    row["loudness_rel_db"] = row["rms_db"] - _db(median_voiced)
    row["pause_ratio"] = float(np.mean(rms < floor))
    loud = [i for i in range(len(rms)) if rms[i] >= floor]
    step = max(1, len(loud) // _MAX_PITCH_FRAMES)
    pitches: list[float] = []
    tried = 0
    for i in loud[::step]:
        tried += 1
        f0 = _pitch(chunk[i * frame:(i + 1) * frame], sample_rate)
        if f0:
            pitches.append(f0)
    voiced_share = len(pitches) / tried if tried else 0.0
    row["voiced_ratio"] = voiced_share * (len(loud) / len(rms))
    if pitches:
        pitches.sort()
        row["pitch_hz"] = pitches[len(pitches) // 2]
        lo = pitches[(len(pitches) - 1) * 10 // 100]
        hi = pitches[(len(pitches) - 1) * 90 // 100]
        row["pitch_range_st"] = 12.0 * math.log2(hi / lo) if lo > 0 else 0.0
    frames_ok = min(1.0, len(rms) / 8.0)
    voiced_ok = min(1.0, len(pitches) / 6.0)
    row["confidence"] = 0.35 + 0.35 * frames_ok + 0.30 * voiced_ok
    for key in ("rms_db", "peak_db", "loudness_rel_db", "pitch_hz", "pitch_range_st",
                "voiced_ratio", "pause_ratio", "confidence"):
        row[key] = round(float(row[key]), 3)
    return row
