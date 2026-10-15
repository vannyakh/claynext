"""
Timeline Adapter: Dispatches timeline mutations and calculations to the Rust editor-timeline engine.
"""
from __future__ import annotations

import logging
from typing import Any

from claynext.adapters.rust_engine import get_rust_engine

logger = logging.getLogger("claynext.adapters.timeline")


class TimelineAdapter:
    """Dispatches non-linear timeline operations to the Rust engine."""

    def __init__(self) -> None:
        self._engine = get_rust_engine()

    def add_track(self, kind: str, name: str) -> str | None:
        """Add a new track (video, audio, or subtitle) via Rust engine."""
        res = self._engine.execute_command("add_track", {"kind": kind.lower(), "name": name})
        if res.get("status") == "ok":
            return res.get("data")
        return None

    def remove_track(self, track_id: str) -> bool:
        """Remove a track by its UUID."""
        res = self._engine.execute_command("remove_track", {"track_id": track_id})
        return res.get("status") == "ok"

    def add_clip(
        self,
        track_id: str,
        media_path: str,
        media_type: str,
        start_seconds: float,
        duration_seconds: float,
        source_in_seconds: float = 0.0,
    ) -> str | None:
        """Place a media clip onto a track via Rust engine."""
        payload = {
            "track_id": track_id,
            "media_path": media_path,
            "media_type": media_type.lower(),
            "start_seconds": start_seconds,
            "duration_seconds": duration_seconds,
            "source_in_seconds": source_in_seconds,
        }
        res = self._engine.execute_command("add_clip", payload)
        if res.get("status") == "ok":
            return res.get("data")
        return None

    def split_clip(self, clip_id: str, split_seconds: float) -> tuple[str, str] | None:
        """Split a clip into two distinct clips at a given timecode point via Rust engine."""
        payload = {"clip_id": clip_id, "split_seconds": split_seconds}
        res = self._engine.execute_command("split_clip", payload)
        if res.get("status") == "ok":
            data = res.get("data")
            if isinstance(data, list) and len(data) == 2:
                return data[0], data[1]
        return None

    def remove_clip(self, clip_id: str) -> bool:
        """Remove a clip by its UUID."""
        res = self._engine.execute_command("remove_clip", {"clip_id": clip_id})
        return res.get("status") == "ok"


_timeline_adapter: TimelineAdapter | None = None


def get_timeline_adapter() -> TimelineAdapter:
    global _timeline_adapter
    if _timeline_adapter is None:
        _timeline_adapter = TimelineAdapter()
    return _timeline_adapter
