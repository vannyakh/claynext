"""
Rust Engine Bridge: Communicates with native claynext-engine.exe for core timeline and project management.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from claynext.utils.paths import APP_DIR

logger = logging.getLogger("claynext.adapters.rust_engine")


def _resolve_engine_exe() -> Path | None:
    # 1. Environment variable override
    env_path = os.environ.get("CLAYNEXT_ENGINE_BIN")
    if env_path and Path(env_path).is_file():
        return Path(env_path)

    # 2. Local workspace target debug / release
    candidates = [
        APP_DIR / "target" / "release" / "claynext-engine.exe",
        APP_DIR / "target" / "debug" / "claynext-engine.exe",
        APP_DIR / "target" / "release" / "claynext-engine",
        APP_DIR / "target" / "debug" / "claynext-engine",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


class RustEngineAdapter:
    """Dispatches strongly-typed JSON commands to the native Rust editor-core engine."""

    def __init__(self, engine_path: Path | None = None) -> None:
        self.engine_path = engine_path or _resolve_engine_exe()

    def is_available(self) -> bool:
        return self.engine_path is not None and self.engine_path.is_file()

    def execute_command(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a single engine command via CLI exec mode."""
        if not self.is_available():
            raise RuntimeError(f"Native Rust engine binary not found at {self.engine_path}")

        req_body = json.dumps({"command": command, "payload": payload})
        cmd = [str(self.engine_path), "exec", req_body]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if res.returncode != 0:
                logger.error("Engine execution failed with code %d: %s", res.returncode, res.stderr)
                return {"status": "error", "message": res.stderr}

            return json.loads(res.stdout.strip())
        except Exception as e:
            logger.exception("Failed to execute command on Rust engine: %s", e)
            return {"status": "error", "message": str(e)}

    def create_project(self, name: str, width: int = 1920, height: int = 1080, fps_num: int = 30, fps_den: int = 1) -> dict[str, Any]:
        return self.execute_command(
            "create_project",
            {"name": name, "width": width, "height": height, "fps_num": fps_num, "fps_den": fps_den},
        )

    def open_project(self, path: str) -> dict[str, Any]:
        return self.execute_command("open_project", {"path": path})

    def save_project(self, path: str) -> dict[str, Any]:
        return self.execute_command("save_project", {"path": path})


# Global singleton instance
_engine_instance: RustEngineAdapter | None = None


def get_rust_engine() -> RustEngineAdapter:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = RustEngineAdapter()
    return _engine_instance
