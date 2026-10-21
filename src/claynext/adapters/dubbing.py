"""
Dubbing Adapter: ducking + translate/timing helpers → Rust core (claynext-ai / engine).
"""
from __future__ import annotations

import logging
from typing import Any

from claynext.adapters.rust_bridge import RustAiAdapter
from claynext.adapters.rust_engine import get_rust_engine

logger = logging.getLogger("claynext.adapters.dubbing")

_PACE_FALLBACK = 3.5


class DubbingAdapter:
    """Domain facade for dubbing models — Rust first, Python fallback."""

    def __init__(self) -> None:
        self._engine = get_rust_engine()

    def set_ducking(
        self,
        music_track_id: str,
        voice_track_id: str,
        ducking_db: float = -14.0,
        attack_ms: float = 150.0,
        release_ms: float = 400.0,
    ) -> bool:
        """Configure automated background ducking under speech."""
        payload = {
            "music_track_id": music_track_id,
            "voice_track_id": voice_track_id,
            "ducking_db": ducking_db,
            "attack_ms": attack_ms,
            "release_ms": release_ms,
        }
        res = self._engine.execute_command("set_audio_ducking", payload)
        return res.get("status") == "ok"

    def estimate_speech_quota(
        self, duration_sec: float, target_lang: str = ""
    ) -> dict[str, int]:
        """Speech unit budget (min/target/max). Always returns a dict."""
        rust = RustAiAdapter.estimate_speech_quota(duration_sec, target_lang)
        if rust:
            return rust
        dur = max(0.0, float(duration_sec or 0.0))
        beats = dur * _PACE_FALLBACK
        target = max(1, int(round(beats * 0.90)))
        return {
            "min": max(1, int(round(beats * 0.60))),
            "target": target,
            "max": max(target, int(round(beats))),
        }

    def spoken_units(self, text: str, target_lang: str = "") -> int | None:
        return RustAiAdapter.spoken_units(text, target_lang)

    def spoken_units_many(self, texts: list[str], target_lang: str = "") -> list[int] | None:
        return RustAiAdapter.spoken_units_many(texts, target_lang)

    def build_fit_prompt(self, lines: list[dict[str, Any]], target_lang: str) -> str | None:
        prompt = RustAiAdapter.build_fit_prompt(lines, target_lang)
        if prompt and "max_units" in prompt and "Do not polish it polite" in prompt:
            return prompt
        return None

    def build_dub_prompt(
        self,
        payload: list[dict[str, Any]],
        target_lang: str,
        source_lang: str = "auto",
        *,
        style: dict[str, Any] | None = None,
    ) -> str | None:
        """Cinematic dubbing LLM prompt from Rust (None if binary missing)."""
        return RustAiAdapter.build_dub_prompt(
            payload, target_lang, source_lang, style=style
        )

    def plan_performance(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Per-line delivery plan from Rust ``plan-performance``. None if the binary is missing."""
        return RustAiAdapter.plan_performance(request)

    def ducked_volume(self, base_volume: float = 1.0, attenuation_db: float = -12.0) -> float:
        """Linear bed volume after dB duck (Rust core, Python fallback)."""
        rust = RustAiAdapter.ducked_volume(base_volume, attenuation_db)
        if rust is not None:
            return rust
        factor = 10.0 ** (float(attenuation_db) / 20.0)
        return max(0.0, min(1.0, float(base_volume) * factor))

    def align_speech_speed(
        self,
        audio_dur: float,
        slot_dur: float,
        *,
        min_speed: float = 0.65,
        max_speed: float = 1.85,
    ) -> float:
        """Tempo to fit TTS into slot (Rust core, Python fallback)."""
        rust = RustAiAdapter.align_speech_speed(
            audio_dur, slot_dur, min_speed=min_speed, max_speed=max_speed
        )
        if rust is not None:
            return rust
        if audio_dur > 0 and slot_dur > 0:
            return max(min_speed, min(max_speed, float(audio_dur) / float(slot_dur)))
        return 1.0


_dubbing_adapter: DubbingAdapter | None = None


def get_dubbing_adapter() -> DubbingAdapter:
    global _dubbing_adapter
    if _dubbing_adapter is None:
        _dubbing_adapter = DubbingAdapter()
    return _dubbing_adapter
