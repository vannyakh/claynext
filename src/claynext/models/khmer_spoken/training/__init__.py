"""Training entrypoints: Vertex Gemini SFT (stub) vs local LoRA (separate stub)."""
from __future__ import annotations

from claynext.models.khmer_spoken.training.training_job_manager import TrainingJobManager
from claynext.models.khmer_spoken.training.vertex_tuning_client import VertexTuningClient

__all__ = ["TrainingJobManager", "VertexTuningClient"]
