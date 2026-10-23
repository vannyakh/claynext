"""Experiment snapshots. Checkpoints are paths only; this registry does not write weights."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def register_snapshot(root: str | Path, snapshot: dict[str, Any]) -> Path:
    folder = Path(root)
    folder.mkdir(parents=True, exist_ok=True)
    digest = str(snapshot.get("config_sha256") or "snapshot")
    path = folder / f"{digest}.json"
    if path.exists():
        return path
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def snapshot_record(config: dict[str, Any], config_hash: str) -> dict[str, Any]:
    return {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": config.get("seed"),
        "config_sha256": config_hash,
        "config": config,
        "weights": None,
        "dry_run": True,
    }
