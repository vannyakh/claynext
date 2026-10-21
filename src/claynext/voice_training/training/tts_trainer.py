"""
Khmer TTS fine-tuning entrypoint — dry-run capable for Intel Mac.

Torch is pinned 2.2.2 / numpy 1.26.4 here; newer TTS trainers often will not
install. This module always supports ``dry_run=True`` (default when deps missing)
and writes a checkpoint/experiment manifest without GPU training.
"""
from __future__ import annotations

import importlib.util
import logging
import platform
from pathlib import Path
from typing import Any, Callable

from claynext.voice_training.datasets.dataset_builder import load_dataset
from claynext.voice_training.datasets.dataset_validator import validate_dataset
from claynext.voice_training.ingestion.rights_validator import assert_training_allowed
from claynext.voice_training.training.checkpoints import new_experiment_id, write_manifest

logger = logging.getLogger("claynext.voice_training.tts_trainer")

Ping = Callable[[int, str], None] | None


def _pkg_present(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def trainer_capability() -> dict[str, Any]:
    """What this environment can actually run."""
    intel_mac = platform.system() == "Darwin" and platform.machine().lower() in {
        "x86_64", "amd64", "i386",
    }
    has_torch = _pkg_present("torch")
    # Conservative: do not claim Coqui / Matcha / etc. without an explicit detect.
    has_coqui = _pkg_present("TTS")
    can_gpu_train = bool(has_torch and has_coqui and not intel_mac)
    return {
        "platform": f"{platform.system()}-{platform.machine()}",
        "intel_mac": intel_mac,
        "torch": has_torch,
        "coqui_tts": has_coqui,
        "can_gpu_train": can_gpu_train,
        "recommended_mode": "dry_run" if not can_gpu_train else "train",
        "note": (
            "Intel Mac: prefer dry-run. Newer TTS trainers typically need newer torch "
            "wheels that are unavailable on x86_64 macOS."
            if intel_mac
            else "GPU training only when a compatible TTS trainer package is installed."
        ),
    }


def run_finetune(
    dataset_path: str | Path,
    *,
    model_name: str = "khmer-tts-baseline",
    dry_run: bool | None = None,
    gate: str = "voice_model_training",
    progress_callback: Ping = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Rights-gated fine-tune entrypoint.

    When ``dry_run`` is True (default if GPU training is unavailable), writes an
    experiment manifest and skips weight updates.
    """
    caps = trainer_capability()
    if dry_run is None:
        dry_run = not caps["can_gpu_train"]

    if progress_callback:
        progress_callback(5, "Loading dataset…")
    dataset = load_dataset(dataset_path)

    if progress_callback:
        progress_callback(15, "Validating schema…")
    report = validate_dataset(dataset)
    if not report.ok:
        msgs = "; ".join(i.message for i in report.errors[:5])
        raise ValueError(f"Dataset schema invalid: {msgs}")

    if progress_callback:
        progress_callback(25, "Checking rights / consent…")
    assert_training_allowed(dataset, gate=gate)  # type: ignore[arg-type]

    experiment_id = new_experiment_id("khmer_tts")
    train_n = sum(1 for s in dataset.segments if s.train_split == "train")
    val_n = sum(1 for s in dataset.segments if s.train_split == "val")
    test_n = sum(1 for s in dataset.segments if s.train_split == "test")

    manifest: dict[str, Any] = {
        "status": "dry_run_complete" if dry_run else "queued",
        "mode": "dry_run" if dry_run else "train",
        "model_name": model_name,
        "dataset_path": str(Path(dataset_path).resolve()),
        "dataset_id": dataset.dataset_id,
        "gate": gate,
        "segment_counts": {"train": train_n, "val": val_n, "test": test_n},
        "capability": caps,
        "checkpoint": None,
        "extra": dict(extra or {}),
        "rights_policy": (
            "Voice-identity training requires documented license + performer consent "
            "with permitted_uses including voice_model_training or tts_synthesis."
        ),
    }

    if dry_run:
        if progress_callback:
            progress_callback(80, "Writing dry-run checkpoint manifest…")
        manifest["checkpoint"] = {
            "type": "manifest_only",
            "weights": None,
            "reason": "Dry-run: GPU trainer unavailable or dry_run=True",
        }
        path = write_manifest(experiment_id, manifest)
        if progress_callback:
            progress_callback(100, "Dry-run complete")
        return {
            "ok": True,
            "dry_run": True,
            "experiment_id": experiment_id,
            "manifest_path": str(path),
            "manifest": manifest,
        }

    # Real training path — only when a compatible trainer exists.
    if progress_callback:
        progress_callback(40, f"Starting fine-tune ({model_name})…")
    try:
        # Placeholder hook for a future Coqui / in-house trainer.
        raise RuntimeError(
            "No compatible TTS fine-tuner is wired in this environment. "
            "Re-run with dry_run=True."
        )
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        path = write_manifest(experiment_id, manifest)
        raise RuntimeError(str(exc)) from exc
