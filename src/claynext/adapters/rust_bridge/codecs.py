"""Bridge to backends/hardware-codecs (claynext-codecs)."""
from __future__ import annotations

import json
import logging

from claynext.adapters.rust_bridge.process import _find_binary, _run_rust
from claynext.models.hardware import GpuCapability, GpuVendor

logger = logging.getLogger("claynext.adapters.rust")


class RustHardwareCodecsAdapter:
    """Interfaces with `backends/hardware-codecs` (claynext-codecs)."""

    @classmethod
    def is_available(cls) -> bool:
        return _find_binary("claynext-codecs") is not None

    @classmethod
    def detect_gpus(cls) -> list[GpuCapability]:
        binary = _find_binary("claynext-codecs")
        if not binary:
            return []
        try:
            res = _run_rust(binary, ["detect"], check=True)
            raw_list = json.loads(res.stdout)
            gpus = []
            for item in raw_list:
                vendor_str = str(item.get("vendor") or "unknown").lower()
                vendor = GpuVendor.UNKNOWN
                for v in GpuVendor:
                    if v.value == vendor_str:
                        vendor = v
                        break
                gpus.append(
                    GpuCapability(
                        name=str(item.get("name") or "Unknown GPU"),
                        vendor=vendor,
                        driver_version=item.get("driver_version"),
                        supports_nvenc=bool(item.get("supports_nvenc")),
                        supports_nvdec=bool(item.get("supports_nvdec")),
                        supports_qsv=bool(item.get("supports_qsv")),
                        supports_amf=bool(item.get("supports_amf")),
                        supports_d3d11va=bool(item.get("supports_d3d11va")),
                        supports_videotoolbox=bool(item.get("supports_videotoolbox")),
                    )
                )
            return gpus
        except Exception as e:
            logger.warning(f"Rust GPU detection failed: {e}")
            return []

    @classmethod
    def get_optimal_encoder_args(cls, prefer_hevc: bool = False) -> list[str]:
        binary = _find_binary("claynext-codecs")
        if binary:
            try:
                flag = "--hevc" if prefer_hevc else "--h264"
                res = _run_rust(binary, ["ffmpeg-args", flag], check=True)
                args = res.stdout.strip().split()
                # Skip hevc_mf — Windows often has no HEVC Media Foundation encoder.
                if args and "hevc_mf" not in args:
                    return args
            except Exception as e:
                logger.warning(f"Rust optimal encoder query failed: {e}")

        # Software fallback (H.264 by default — widest Windows playback support)
        codec = "libx265" if prefer_hevc else "libx264"
        return ["-c:v", codec, "-crf", "20", "-preset", "faster"]


