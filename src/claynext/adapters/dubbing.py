"""
Dubbing Adapter: High-performance audio ducking and multi-track audio operations.
"""
from __future__ import annotations

import logging
from typing import Any

from claynext.adapters.rust_engine import get_rust_engine

logger = logging.getLogger("claynext.adapters.dubbing")


class DubbingAdapter:
    """Manages audio ducking, vocal alignment, and track gain parameters via Rust engine."""

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


_dubbing_adapter: DubbingAdapter | None = None


def get_dubbing_adapter() -> DubbingAdapter:
    global _dubbing_adapter
    if _dubbing_adapter is None:
        _dubbing_adapter = DubbingAdapter()
    return _dubbing_adapter
