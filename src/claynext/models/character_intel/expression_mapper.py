"""Planner style + intensity → the controls each TTS engine really has.

The spoken words are never changed here. An engine without an emotion control
gets the line unchanged and ``applied`` stays empty.
"""
from __future__ import annotations

from typing import Any

STYLES = (
    "neutral", "happy", "sad", "angry", "fearful",
    "whispering", "shouting", "crying", "laughing",
)

# rate %, pitch Hz, volume % at intensity 1.0 (Edge TTS prosody controls).
_EDGE_PROSODY: dict[str, tuple[float, float, float]] = {
    "neutral": (0.0, 0.0, 0.0),
    "happy": (8.0, 6.0, 5.0),
    "sad": (-10.0, -6.0, -10.0),
    "angry": (6.0, -2.0, 15.0),
    "fearful": (10.0, 8.0, 0.0),
    "whispering": (-8.0, -4.0, -35.0),
    "shouting": (10.0, 12.0, 25.0),
    "crying": (-14.0, 4.0, -10.0),
    "laughing": (6.0, 8.0, 5.0),
}

_STYLE_PHRASE = {
    "happy": "cheerful and bright",
    "sad": "sad and subdued",
    "angry": "angry, tense and forceful",
    "fearful": "frightened, breathless and urgent",
    "whispering": "whispering softly",
    "shouting": "shouting with a raised voice",
    "crying": "crying, voice breaking",
    "laughing": "laughing while speaking",
}


def normalize_style(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in STYLES else "neutral"


def provider_for_voice(voice_id: str) -> str:
    vid = str(voice_id or "")
    try:
        from claynext.models.tts_service import TTSEngine

        if TTSEngine._is_clone_voice(vid):
            return "clone"
        if TTSEngine._is_voxcpm_voice(vid):
            return "voxcpm"
        if TTSEngine._is_omnivoice_voice(vid):
            return "omnivoice"
        if TTSEngine._is_sglang_voice(vid):
            return "sglang"
        if TTSEngine._is_eleven_voice(vid):
            return "elevenlabs"
        if TTSEngine._is_kitten_voice(vid):
            return "kitten"
        if TTSEngine._is_edge_voice(vid):
            return "edge"
    except Exception:
        pass
    low = vid.lower()
    for prefix in ("clone", "voxcpm", "omnivoice", "sglang", "eleven", "kitten"):
        if low.startswith(prefix):
            return "elevenlabs" if prefix == "eleven" else prefix
    return "edge" if "neural" in low else "unknown"


def style_phrase(style: str, intensity: float) -> str:
    phrase = _STYLE_PHRASE.get(style, "")
    if not phrase:
        return ""
    if intensity >= 0.75:
        return f"very {phrase}" if "," not in phrase else f"intensely {phrase}"
    if intensity < 0.4:
        return f"slightly {phrase}"
    return phrase


def map_delivery(
    voice_id: str,
    performance: dict[str, Any] | None,
    *,
    has_reference: bool = False,
) -> dict[str, Any]:
    """Engine controls for one line. Neutral (no-op) when ``performance`` is empty."""
    provider = provider_for_voice(voice_id)
    perf = performance or {}
    style = normalize_style(perf.get("style"))
    try:
        intensity = max(0.0, min(1.0, float(perf.get("intensity", 0.5))))
    except (TypeError, ValueError):
        intensity = 0.5
    out: dict[str, Any] = {
        "provider": provider,
        "style": style,
        "intensity": round(intensity, 3),
        "speed": 1.0,
        "pitch_hz": 0.0,
        "volume_pct": 0.0,
        "style_prompt": "",
        "instruct_extra": "",
        "eleven": {},
        "applied": [],
    }
    if not perf or style == "neutral":
        return out

    rate, pitch, volume = _EDGE_PROSODY.get(style, (0.0, 0.0, 0.0))
    speed = round(1.0 + rate * intensity / 100.0, 3)

    if provider in {"edge", "clone"}:
        out["speed"] = speed
        out["pitch_hz"] = round(pitch * intensity, 1)
        out["volume_pct"] = round(volume * intensity, 1)
        out["applied"] = ["rate", "pitch", "volume"]
    if provider in {"voxcpm", "clone"}:
        out["style_prompt"] = style_phrase(style, intensity)
        out["applied"] = out["applied"] + ["style_prompt"]
    elif provider == "omnivoice":
        out["speed"] = speed
        out["applied"] = ["speed"]
        if style == "whispering" and not has_reference:
            out["instruct_extra"] = "whisper"
            out["applied"].append("instruct")
    elif provider == "elevenlabs":
        out["speed"] = speed
        if style == "whispering":
            eleven = {"stability": 0.5, "style": round(0.3 * intensity, 3)}
        else:
            eleven = {
                "stability": round(max(0.2, 0.45 - 0.25 * intensity), 3),
                "style": round(0.5 * intensity, 3),
            }
        out["eleven"] = eleven
        out["applied"] = ["speed", "stability", "style"]
    elif provider == "kitten":
        out["speed"] = speed
        out["applied"] = ["speed"]
    return out
