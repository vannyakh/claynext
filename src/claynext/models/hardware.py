"""Hardware and codec capability domain models."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GpuVendor(str, Enum):
    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    APPLE = "apple"
    UNKNOWN = "unknown"


@dataclass
class GpuCapability:
    name: str
    vendor: GpuVendor
    driver_version: str | None = None
    supports_nvenc: bool = False
    supports_nvdec: bool = False
    supports_qsv: bool = False
    supports_amf: bool = False
    supports_d3d11va: bool = False


@dataclass
class CodecProfile:
    codec_name: str
    is_hardware: bool
    encoder_args: list[str]
    preset: str = "medium"
    quality_crf: int | None = None
    bitrate_kbps: int | None = None
