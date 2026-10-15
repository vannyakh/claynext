"""
Adapters Layer: Bridges Python PySide6 application to native Rust multimedia core and operating system.
"""
from __future__ import annotations

from claynext.adapters.dubbing import DubbingAdapter, get_dubbing_adapter
from claynext.adapters.events import EngineEventAdapter, get_event_adapter
from claynext.adapters.ffmpeg_adapter import FFmpegAdapter, get_ffmpeg_adapter
from claynext.adapters.hardware_codecs_adapter import HardwareCodecsAdapter, get_hardware_codecs
from claynext.adapters.media import MediaAdapter, get_media_adapter
from claynext.adapters.rendering import RenderingAdapter, get_rendering_adapter
from claynext.adapters.rust_core_adapter import RustCoreAdapter, get_rust_core
from claynext.adapters.rust_engine import RustEngineAdapter, get_rust_engine
from claynext.adapters.sysinfo_adapter import SysInfoAdapter, get_sysinfo
from claynext.adapters.timeline import TimelineAdapter, get_timeline_adapter

__all__ = [
    "DubbingAdapter",
    "EngineEventAdapter",
    "FFmpegAdapter",
    "HardwareCodecsAdapter",
    "MediaAdapter",
    "RenderingAdapter",
    "RustCoreAdapter",
    "RustEngineAdapter",
    "SysInfoAdapter",
    "TimelineAdapter",
    "get_dubbing_adapter",
    "get_event_adapter",
    "get_ffmpeg_adapter",
    "get_hardware_codecs",
    "get_media_adapter",
    "get_rendering_adapter",
    "get_rust_core",
    "get_rust_engine",
    "get_sysinfo",
    "get_timeline_adapter",
]
