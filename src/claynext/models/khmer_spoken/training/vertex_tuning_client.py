"""Google Cloud Vertex AI supervised fine-tuning client (STUB).

Platform distinction (enforced):
- **AI Studio / Gemini API keys** cannot submit Vertex tuning jobs.
- **Vertex** needs a GCP project, Application Default Credentials (or service
  account), and an eligible Gemini model in an allowed region.
- This stub checks eligibility dynamically and **refuses** without credentials.
  It never reports a fake successful tune.

Official docs: Vertex AI supervised fine-tuning for Gemini models.
Text SFT does **not** train Gemini TTS voice models.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Documented candidates — verify via discovery when credentials exist.
ELIGIBLE_MODEL_CANDIDATES = (
    "gemini-2.5-flash",
    "gemini-2.5-pro",
)
REGIONS_DOCUMENTED = ("us-central1",)  # unverified until live probe


@dataclass
class EligibilityReport:
    eligible: bool
    reasons: list[str] = field(default_factory=list)
    project: str = ""
    location: str = ""
    credentials_present: bool = False
    models: list[str] = field(default_factory=list)
    models_status: str = "unverified"
    platform: str = "vertex_ai"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "reasons": list(self.reasons),
            "project": self.project,
            "location": self.location,
            "credentials_present": self.credentials_present,
            "models": list(self.models),
            "models_status": self.models_status,
            "platform": self.platform,
            "notes": self.notes,
        }


@dataclass
class TuningJobRef:
    ok: bool
    job_id: str = ""
    status: str = "refused"
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class VertexTuningClient:
    """Stub client: eligibility checks only; no fake successful tunes."""

    provider_id = "google_cloud_vertex_sft"

    def __init__(
        self,
        *,
        project: str | None = None,
        location: str = "us-central1",
    ):
        self.project = (project or os.environ.get("GOOGLE_CLOUD_PROJECT")
                        or os.environ.get("GCLOUD_PROJECT") or "").strip()
        self.location = location

    def credentials_present(self) -> bool:
        # ADC path or explicit service-account JSON. AI Studio keys alone are insufficient.
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip():
            path = Path(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
            if path.is_file():
                return True
        # Common ADC locations (presence only — do not read secrets into logs).
        home = Path.home()
        adc = home / ".config" / "gcloud" / "application_default_credentials.json"
        if adc.is_file():
            return True
        return False

    def check_eligibility(self, *, model: str | None = None) -> EligibilityReport:
        reasons: list[str] = []
        creds = self.credentials_present()
        if not self.project:
            reasons.append("missing_gcp_project (set GOOGLE_CLOUD_PROJECT)")
        if not creds:
            reasons.append(
                "missing_gcp_credentials (ADC or GOOGLE_APPLICATION_CREDENTIALS); "
                "AI Studio / GEMINI_API_KEY cannot submit Vertex tuning jobs"
            )
        models = list(ELIGIBLE_MODEL_CANDIDATES)
        models_status = "documented_unverified"
        if model and model not in models:
            reasons.append(f"model {model!r} not in documented eligible candidates (unverified)")
            models_status = "requested_model_unverified"

        # Dynamic discovery placeholder — only when creds+project exist.
        if creds and self.project:
            discovered = self._try_discover_models()
            if discovered:
                models = discovered
                models_status = "discovered"
            else:
                reasons.append("model_discovery_unavailable_or_failed (using documented table)")

        eligible = not reasons and creds and bool(self.project)
        return EligibilityReport(
            eligible=eligible,
            reasons=reasons,
            project=self.project,
            location=self.location,
            credentials_present=creds,
            models=models,
            models_status=models_status,
            notes=(
                "Vertex supervised fine-tuning is separate from AI Studio teacher calls. "
                "Text SFT does not train TTS voices."
            ),
        )

    def submit_supervised_tune(
        self,
        *,
        train_uri: str,
        model: str = "gemini-2.5-flash",
        display_name: str = "ksld-gemini-sft",
    ) -> TuningJobRef:
        """Refuse without eligibility. Never invent a successful job id."""
        report = self.check_eligibility(model=model)
        if not report.eligible:
            return TuningJobRef(
                ok=False,
                status="refused",
                error="; ".join(report.reasons) or "not eligible",
                details=report.to_dict(),
            )
        # Live Vertex API submission is intentionally not implemented in milestone 1.
        return TuningJobRef(
            ok=False,
            status="refused",
            error=(
                "Vertex SFT submission is stubbed in milestone 1. "
                "Eligibility passed, but live tune jobs are not enabled yet. "
                f"train_uri={train_uri!r} model={model!r} name={display_name!r}"
            ),
            details=report.to_dict(),
        )

    def _try_discover_models(self) -> list[str]:
        """Best-effort HTTP discovery; returns empty on failure (no secrets logged)."""
        # Avoid importing heavy google-cloud SDKs. Optional urllib probe can be added later.
        _ = json.dumps({"project": self.project, "location": self.location})
        return []
