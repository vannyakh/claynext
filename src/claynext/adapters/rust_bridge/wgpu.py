"""Bridge to backends/wgpu (claynext-wgpu)."""
from __future__ import annotations

import json
import logging
from typing import Any

from claynext.adapters.rust_bridge.process import _find_binary, _run_rust

logger = logging.getLogger("claynext.adapters.rust")


class RustWgpuAdapter:
    """Interfaces with `backends/wgpu` (claynext-wgpu)."""

    @classmethod
    def get_device_info(cls) -> dict[str, Any]:
        binary = _find_binary("claynext-wgpu")
        if binary:
            try:
                res = _run_rust(binary, ["info"], check=True)
                return json.loads(res.stdout)
            except Exception as e:
                logger.warning(f"Rust WGPU info failed: {e}")
        return {"backend": "Primary", "preferred_format": "Rgba8Unorm"}


