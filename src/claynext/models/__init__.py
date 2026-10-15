"""Claynext domain models."""
from __future__ import annotations

from claynext.models.dubbing import DubbingSegmentModel, SpeakerVoiceModel
from claynext.models.hardware import CodecProfile, GpuCapability, GpuVendor
from claynext.models.media import (
    AudioStreamInfo,
    DecodedAudioChunk,
    DecodedVideoFrame,
    MediaMetadata,
    MediaType,
    VideoStreamInfo,
)
from claynext.models.project import ProjectDocument, ProjectSettings
from claynext.models.timeline import ClipModel, TrackKind, TrackModel

__all__ = [
    "AudioStreamInfo",
    "ClipModel",
    "CodecProfile",
    "DecodedAudioChunk",
    "DecodedVideoFrame",
    "DubbingSegmentModel",
    "GpuCapability",
    "GpuVendor",
    "MediaMetadata",
    "MediaType",
    "ProjectDocument",
    "ProjectSettings",
    "SpeakerVoiceModel",
    "TrackKind",
    "TrackModel",
    "VideoStreamInfo",
]

