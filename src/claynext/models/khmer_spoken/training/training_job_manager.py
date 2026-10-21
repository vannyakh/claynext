"""Async training job ledger — Vertex Gemini SFT vs local LoRA stay separate."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from claynext.models.khmer_spoken.paths import JOBS_DIR, ensure_khmer_spoken_dirs
from claynext.models.khmer_spoken.training.vertex_tuning_client import VertexTuningClient

JobKind = Literal["vertex_gemini_sft", "local_lora"]


@dataclass
class TrainingJob:
    job_id: str
    kind: JobKind
    status: str  # queued | running | succeeded | failed | refused
    created_at: str
    updated_at: str
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class TrainingJobManager:
    """Persist job records under ``data/khmer_spoken/jobs/``. UI polls; never blocks Qt."""

    def __init__(self, root: Path | None = None):
        ensure_khmer_spoken_dirs()
        self.root = Path(root) if root else JOBS_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def list_jobs(self) -> list[TrainingJob]:
        jobs: list[TrainingJob] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                jobs.append(TrainingJob(**{k: data[k] for k in TrainingJob.__dataclass_fields__ if k in data}))
            except Exception:
                continue
        return jobs

    def get(self, job_id: str) -> TrainingJob | None:
        path = self._path(job_id)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return TrainingJob(**{k: data[k] for k in TrainingJob.__dataclass_fields__ if k in data})

    def _save(self, job: TrainingJob) -> TrainingJob:
        job.updated_at = _now()
        self._path(job.job_id).write_text(
            json.dumps(job.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return job

    def enqueue_vertex_sft(
        self,
        *,
        train_uri: str,
        model: str = "gemini-2.5-flash",
        display_name: str = "ksld-gemini-sft",
        client: VertexTuningClient | None = None,
    ) -> TrainingJob:
        """Create a ledger entry; call Vertex stub (refuses without GCP creds)."""
        now = _now()
        job = TrainingJob(
            job_id=f"vtx-{uuid.uuid4().hex[:12]}",
            kind="vertex_gemini_sft",
            status="queued",
            created_at=now,
            updated_at=now,
            details={"train_uri": train_uri, "model": model, "display_name": display_name},
        )
        self._save(job)
        vtx = client or VertexTuningClient()
        ref = vtx.submit_supervised_tune(
            train_uri=train_uri, model=model, display_name=display_name
        )
        job.status = "refused" if not ref.ok else ref.status
        job.error = ref.error
        job.details.update(ref.details)
        job.details["vertex_job_id"] = ref.job_id
        return self._save(job)

    def enqueue_local_lora(
        self,
        *,
        dataset_path: str,
        base_model: str = "unspecified-open-weight",
    ) -> TrainingJob:
        """Separate stub entrypoint for local LoRA/QLoRA — does not call Vertex."""
        now = _now()
        job = TrainingJob(
            job_id=f"lora-{uuid.uuid4().hex[:12]}",
            kind="local_lora",
            status="refused",
            created_at=now,
            updated_at=now,
            error=(
                "Local LoRA/QLoRA trainer is a separate stub entrypoint in milestone 1. "
                "Not started."
            ),
            details={
                "dataset_path": dataset_path,
                "base_model": base_model,
                "platform": "local_open_weight",
                "separate_from_vertex": True,
            },
        )
        return self._save(job)
