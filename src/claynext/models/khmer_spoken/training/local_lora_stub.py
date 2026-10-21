"""Local LoRA / QLoRA trainer stub — separate from Vertex Gemini SFT.

Does not start training in milestone 1. Use ``TrainingJobManager.enqueue_local_lora``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LocalLoraPlan:
    ok: bool
    status: str
    error: str
    details: dict[str, Any]


def plan_local_lora(*, dataset_path: str, base_model: str = "unspecified-open-weight") -> LocalLoraPlan:
    return LocalLoraPlan(
        ok=False,
        status="refused",
        error="Local LoRA/QLoRA trainer is stubbed; Vertex SFT is a different client.",
        details={
            "dataset_path": dataset_path,
            "base_model": base_model,
            "platform": "local_open_weight",
            "separate_from_vertex": True,
            "separate_from_ai_studio": True,
        },
    )
