"""Media domain models."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MediaType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    UNKNOWN = "unknown"


@dataclass
class VideoStreamInfo:
    width: u32 = 0
    height: u32 = 0
    codec: str = ""
    pixel_format: str = "yuv420p"
    frame_rate: float = 30.0
    bit_rate: int = 0
    duration: float = 0.0
    rotation: int = 0
    is_vfr: bool = False


@dataclass
class AudioStreamInfo:
    sample_rate: int = 44100
    channels: int = 2
    codec: str = ""
    bit_rate: int = 0
    duration: float = 0.0
    channel_layout: str = "stereo"


@dataclass
class MediaMetadata:
    path: str
    media_type: MediaType
    format_name: str = ""
    duration: float = 0.0
    file_size_bytes: int = 0
    bit_rate: int = 0
    video_stream: VideoStreamInfo | None = None
    audio_stream: AudioStreamInfo | None = None
    extra_streams: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DecodedVideoFrame:
    width: int
    height: int
    pts: float
    format: str  # "rgba", "rgb24"
    data: bytes


@dataclass
class DecodedAudioChunk:
    sample_rate: int
    channels: int
    pts: float
    samples: list[float]  # Float32 normalized [-1.0, 1.0]
