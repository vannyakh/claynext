"""Dry-run trainer for SFT, LoRA, QLoRA, and DPO.

``start`` refuses a real GPU job unless ``approval`` is true, and still refuses
7B/8B/14B on a 16 GB machine. No training stack is imported. No weights are written.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from claynext.models.training.config import config_sha256, load_config, validate_config
from claynext.models.training.registry import register_snapshot, snapshot_record


@dataclass
class CancelHandle:
    cancelled: bool = False
    at_step: int | None = None

    def cancel(self) -> None:
        self.cancelled = True


@dataclass
class ResumeState:
    step: int
    config_sha256: str
    seed: int
    checkpoint_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def training_implementation_available() -> bool:
    """True only if a local trainer library is already installed. Does not install one."""
    for name in ("peft", "mlx_lm"):
        try:
            __import__(name)
            return True
        except ImportError:
            continue
    return False


def prepare(
    path: str | Path,
    *,
    registry_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Validate a config and snapshot the seed. Does not start training."""
    config = load_config(path)
    check = validate_config(config)
    digest = config_sha256(config)
    record = snapshot_record(config, digest)
    result = {
        "status": "dry_run" if check["ok"] else "invalid",
        "started": False,
        "approval_seen": False,
        "validation": check,
        "snapshot": {"seed": config.get("seed"), "config_sha256": digest},
        "cancel": {"supported": True, "cancelled": False},
        "resume": {"supported": True, "checkpoint_path": None},
        "implementation_available": training_implementation_available(),
        "weights": None,
    }
    if registry_dir is not None and check["ok"]:
        result["registry_path"] = str(register_snapshot(registry_dir, record))
    return result


def start(
    path: str | Path,
    *,
    approval: bool = False,
    cancel: CancelHandle | None = None,
    resume: ResumeState | None = None,
    registry_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Refuse a real run by default. Approval does not override a blocked size class."""
    result = prepare(path, registry_dir=registry_dir)
    result["approval_seen"] = bool(approval)
    if cancel is not None and cancel.cancelled:
        result["status"] = "cancelled"
        result["started"] = False
        result["cancel"] = {"supported": True, "cancelled": True, "at_step": cancel.at_step}
        return result
    if resume is not None:
        expected = result["snapshot"]["config_sha256"]
        matches = resume.config_sha256 == expected and resume.seed == result["snapshot"]["seed"]
        result["resume"] = {
            "supported": True,
            "accepted": matches,
            "step": resume.step,
            "checkpoint_path": resume.checkpoint_path,
        }
        if not matches:
            result["status"] = "refused"
            result["reason"] = "resume config hash does not match the snapshot"
            result["started"] = False
            return result
    if not result["validation"]["ok"]:
        result["status"] = "invalid"
        result["started"] = False
        return result
    if not approval:
        result["status"] = "dry_run"
        result["reason"] = "approval flag is false; config was validated only"
        result["started"] = False
        return result
    if result["validation"]["machine_blocked"]:
        result["status"] = "refused"
        result["reason"] = (
            "this M4 has 16 GB RAM; 3B/7B/8B/14B fine-tunes are not started "
            "(7B/8B/14B do not fit; 3B is not a tiny adapter)"
        )
        result["started"] = False
        return result
    if not training_implementation_available():
        result["status"] = "refused"
        result["reason"] = "no tiny-adapter trainer is installed; dry-run only"
        result["started"] = False
        return result
    result["status"] = "refused"
    result["reason"] = "tiny-adapter path is installed but this milestone does not launch it"
    result["started"] = False
    return result
