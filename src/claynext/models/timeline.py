"""Timeline track, clip, and overlay domain models."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TrackKind(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    DUB = "dub"
    OVERLAY = "overlay"
    SUBTITLE = "subtitle"


@dataclass
class ClipModel:
    id: str
    track_id: str
    name: str
    start_sec: float
    end_sec: float
    source_in: float = 0.0
    source_out: float = 0.0
    source_path: str = ""
    volume: float = 1.0
    muted: bool = False
    speed: float = 1.0


@dataclass
class TrackModel:
    id: str
    name: str
    kind: TrackKind
    volume: float = 1.0
    pan: float = 0.0
    muted: bool = False
    solo: bool = False
    locked: bool = False
    clips: list[ClipModel] = field(default_factory=list)


TimelineClip = ClipModel
TimelineTrack = TrackModel


