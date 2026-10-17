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
    width: int = 0
    height: int = 0
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

    @property
    def duration_seconds(self) -> float:
        return float(self.duration or 0.0)

    @property
    def width(self) -> int:
        return int(self.video_stream.width) if self.video_stream else 0

    @property
    def height(self) -> int:
        return int(self.video_stream.height) if self.video_stream else 0

    @property
    def fps(self) -> float:
        return float(self.video_stream.frame_rate) if self.video_stream else 0.0

    @property
    def video_codec(self) -> str:
        return str(self.video_stream.codec) if self.video_stream else ""

    @property
    def audio_codec(self) -> str:
        return str(self.audio_stream.codec) if self.audio_stream else ""


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

