"""Timeline track and clip schema."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from claynext.constants.timeline_constants import PRESET


@dataclass
class TimelineTrack:
    id: str
    kind: str
    name: str
    height: int = 24
    color: str = "#64748b"
    icon: str = "copy"
    locked: bool = False
    muted: bool = False
    solo: bool = False
    hidden: bool = False
    opacity: int = 100
    volume: int = 100
    selected: bool = False


@dataclass
class TimelineClip:
    id: str
    track_id: str
    kind: str
    start_ms: int
    duration_ms: int
    label: str
    locked: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def end_ms(self) -> int:
        return self.start_ms + max(1, self.duration_ms)


def new_track(kind: str, index: int = 1) -> TimelineTrack:
    name, h, color, icn = PRESET.get(kind, (kind.title(), 24, "#64748b", "copy"))
    if kind == "video":
        # First video lane is the master source. Later ones are overlay video.
        label = "Source" if index <= 1 else ("Video" if index == 2 else f"Video {index - 1}")
    else:
        label = name if index <= 1 else f"{name} {index}"
    return TimelineTrack(
        id=uuid.uuid4().hex[:10],
        kind=kind,
        name=label,
        height=h,
        color=color,
        icon=icn,
    )

