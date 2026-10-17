"""
Rust core bridge package — Python GUI/features → native Claynext backends.

Import from here (or ``claynext.adapters``). Modules map 1:1 to binaries:
``ffmpeg``, ``codecs``, ``cpu``, ``ai`` (claynext-ai), ``wgpu``.
"""
from __future__ import annotations

from claynext.adapters.rust_bridge.ai import RustAiAdapter
from claynext.adapters.rust_bridge.codecs import RustHardwareCodecsAdapter
from claynext.adapters.rust_bridge.core import RustCoreAdapter, get_rust_core
from claynext.adapters.rust_bridge.cpu import RustCpuAdapter
from claynext.adapters.rust_bridge.ffmpeg import RustFfmpegAdapter
from claynext.adapters.rust_bridge.wgpu import RustWgpuAdapter

__all__ = [
    "RustAiAdapter",
    "RustCoreAdapter",
    "RustCpuAdapter",
    "RustFfmpegAdapter",
    "RustHardwareCodecsAdapter",
    "RustWgpuAdapter",
    "get_rust_core",
]
