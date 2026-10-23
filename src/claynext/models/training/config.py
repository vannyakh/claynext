"""Load LoRA / SFT / QLoRA / DPO configs. Validation does not start training."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parent / "configs"
SIZE_CLASSES = ("tiny", "3b", "7b", "8b", "7b/8b", "14b")
# This M4 has 16 GB. These classes cannot be fine-tuned here.
MACHINE_BLOCKED_SIZES = frozenset({"7b", "8b", "7b/8b", "14b"})
METHODS = ("sft_lora", "qlora", "dpo")
REQUIRED = (
    "schema_version",
    "method",
    "base_model_size_class",
    "base_model_id",
    "seed",
    "dry_run_default",
    "approval_required",
    "tune_on_test",
    "train_split",
    "held_out_split",
    "hardware",
)


def load_config(path: str | Path) -> dict[str, Any]:
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config must be a mapping")
    return data


def config_sha256(config: dict[str, Any]) -> str:
    blob = json.dumps(config, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return errors and whether this machine may attempt a real start."""
    errors: list[str] = []
    for key in REQUIRED:
        if key not in config:
            errors.append(f"missing:{key}")
    method = str(config.get("method") or "")
    if method and method not in METHODS:
        errors.append("bad_method")
    size = str(config.get("base_model_size_class") or "")
    if size and size not in SIZE_CLASSES:
        errors.append("bad_size_class")
    if config.get("tune_on_test") is True:
        errors.append("tune_on_test")
    if config.get("train_split") == "test" or config.get("held_out_split") != "test":
        errors.append("test_split_misuse")
    hardware = config.get("hardware") or {}
    ram = hardware.get("ram_gb")
    if ram is None:
        errors.append("missing_ram")
    if method == "dpo" and (config.get("dpo") or {}).get("preference_path"):
        errors.append("dpo_preference_path_must_stay_empty_until_human_pairs_exist")
    machine_blocked = size in MACHINE_BLOCKED_SIZES or (isinstance(ram, (int, float)) and ram <= 16 and size != "tiny")
    return {
        "ok": not errors,
        "errors": errors,
        "machine_blocked": machine_blocked,
        "size_class": size,
        "dry_run": True,
    }
