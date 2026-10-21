"""Speech turn segmentation via AI adapter VAD (Rust) or energy heuristic."""
from __future__ import annotations

import logging
import struct
import wave
from pathlib import Path
from typing import Any

logger = logging.getLogger("claynext.voice_training.speech_segmenter")


def _energy_vad(wav_path: Path, *, frame_ms: int = 30, thresh: float = 0.02) -> list[dict[str, Any]]:
    """Simple RMS energy VAD for fixtures / when Rust VAD is missing."""
    try:
        with wave.open(str(wav_path), "rb") as wf:
            rate = wf.getframerate()
            ch = wf.getnchannels()
            width = wf.getsampwidth()
            n = wf.getnframes()
            raw = wf.readframes(n)
    except Exception:
        return [{"start": 0.0, "end": 1.0, "confidence": 0.0}]

    if width != 2:
        duration = n / max(rate, 1)
        return [{"start": 0.0, "end": max(duration, 0.1), "confidence": 0.0}]

    frame = max(1, int(rate * frame_ms / 1000))
    samples = struct.unpack(f"<{len(raw) // 2}h", raw)
    if ch > 1:
        samples = samples[::ch]
    turns: list[dict[str, Any]] = []
    in_speech = False
    start = 0.0
    for i in range(0, len(samples), frame):
        chunk = samples[i : i + frame]
        if not chunk:
            break
        rms = (sum(s * s for s in chunk) / len(chunk)) ** 0.5 / 32768.0
        t = i / rate
        if rms >= thresh and not in_speech:
            in_speech = True
            start = t
        elif rms < thresh and in_speech:
            in_speech = False
            if t - start >= 0.15:
                turns.append({"start": round(start, 3), "end": round(t, 3), "confidence": 0.5})
    if in_speech:
        end = len(samples) / rate
        if end - start >= 0.15:
            turns.append({"start": round(start, 3), "end": round(end, 3), "confidence": 0.5})
    if not turns:
        duration = len(samples) / max(rate, 1)
        turns = [{"start": 0.0, "end": max(duration, 0.1), "confidence": 0.0}]
    return turns


def segment_speech(wav_path: str | Path, *, threshold: float = 0.5) -> list[dict[str, Any]]:
    """
    Return speech turns ``[{start, end, confidence}, …]``.

    Prefers ``get_ai_adapter().vad_chunk``; falls back to energy VAD.
    """
    path = Path(wav_path)
    try:
        from claynext.adapters.ai import get_ai_adapter

        turns = get_ai_adapter().vad_chunk(path, threshold=threshold)
        if turns:
            normalized = []
            for t in turns:
                start = float(t.get("start", t.get("start_sec", 0.0)) or 0.0)
                end = float(t.get("end", t.get("end_sec", start + 0.5)) or (start + 0.5))
                conf = float(t.get("confidence", t.get("score", 0.7)) or 0.7)
                normalized.append({"start": start, "end": end, "confidence": conf})
            if normalized:
                return normalized
    except Exception as exc:
        logger.debug("Rust VAD unavailable: %s", exc)
    return _energy_vad(path)
