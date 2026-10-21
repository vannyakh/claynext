"""
Rights / consent gate for voice-identity training and cloning.

Buying or accessing a movie does NOT grant AI training or voice-cloning rights.
Commercial catalogs (TVB Khmer, KhDiamon, etc.) are catalog candidates only
until licensing + performer consent are documented.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from claynext.voice_training.datasets.speech_schema import (
    TTS_SYNTHESIS_USES,
    VOICE_IDENTITY_USES,
    PerformerConsent,
    RecordingSession,
    SpeechDataset,
)

GateKind = Literal[
    "voice_model_training",
    "tts_synthesis",
    "voice_cloning",
    "ingest_annotate",
]


@dataclass
class RightsIssue:
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"
    performer: str = ""
    source_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "performer": self.performer,
            "source_id": self.source_id,
        }


@dataclass
class RightsVerdict:
    allowed: bool
    issues: list[RightsIssue] = field(default_factory=list)
    gate: GateKind = "voice_model_training"

    @property
    def errors(self) -> list[RightsIssue]:
        return [i for i in self.issues if i.severity == "error"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "gate": self.gate,
            "issues": [i.to_dict() for i in self.issues],
        }


def _parse_expiry(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _consent_expired(consent: PerformerConsent, *, now: datetime | None = None) -> bool:
    exp = _parse_expiry(consent.expires_at)
    if exp is None:
        return False
    ref = now or datetime.now(timezone.utc)
    return exp <= ref


def _consent_revoked(consent: PerformerConsent) -> bool:
    return bool(consent.revoked_at)


def _uses_ok(consent: PerformerConsent, required: frozenset[str]) -> bool:
    uses = {str(u).strip().lower() for u in (consent.permitted_uses or [])}
    return bool(uses & {u.lower() for u in required})


def validate_performer_consent(
    consent: PerformerConsent,
    *,
    gate: GateKind = "voice_model_training",
    source_id: str = "",
    now: datetime | None = None,
) -> list[RightsIssue]:
    """Validate one performer consent record for the requested gate."""
    issues: list[RightsIssue] = []
    name = consent.name or "(unnamed)"
    sid = source_id

    if not (consent.consent_id or "").strip():
        issues.append(RightsIssue(
            code="missing_consent_id",
            message=f"Performer '{name}' has no consent_id.",
            performer=name,
            source_id=sid,
        ))
    if not (consent.name or "").strip():
        issues.append(RightsIssue(
            code="missing_performer_name",
            message="Performer name is required.",
            source_id=sid,
        ))
    if _consent_revoked(consent):
        issues.append(RightsIssue(
            code="consent_revoked",
            message=f"Consent for '{name}' was revoked at {consent.revoked_at}.",
            performer=name,
            source_id=sid,
        ))
    if _consent_expired(consent, now=now):
        issues.append(RightsIssue(
            code="consent_expired",
            message=f"Consent for '{name}' expired at {consent.expires_at}.",
            performer=name,
            source_id=sid,
        ))

    if gate in ("voice_model_training", "voice_cloning"):
        required = VOICE_IDENTITY_USES
        label = "voice_model_training / tts_synthesis / voice_cloning"
    elif gate == "tts_synthesis":
        required = TTS_SYNTHESIS_USES
        label = "tts_synthesis / voice_model_training"
    else:
        # ingest_annotate: consent preferred but not hard-required for annotation-only.
        return issues

    if not _uses_ok(consent, required):
        issues.append(RightsIssue(
            code="permitted_uses_missing",
            message=(
                f"Performer '{name}' permitted_uses must include one of "
                f"{sorted(required)} for {gate} (need {label})."
            ),
            performer=name,
            source_id=sid,
        ))

    if gate == "voice_cloning" and "voice_cloning" not in {
        str(u).strip().lower() for u in (consent.permitted_uses or [])
    }:
        # Voice cloning needs an explicit cloning grant (not just training).
        issues.append(RightsIssue(
            code="cloning_not_permitted",
            message=(
                f"Performer '{name}' lacks explicit 'voice_cloning' in permitted_uses. "
                "Recognizable voice cloning requires documented authorization."
            ),
            performer=name,
            source_id=sid,
        ))

    return issues


def validate_session(
    session: RecordingSession,
    *,
    gate: GateKind = "voice_model_training",
    now: datetime | None = None,
) -> RightsVerdict:
    """Gate a recording session for training / cloning / synthesis."""
    issues: list[RightsIssue] = []
    sid = session.source_id or session.session_id

    if session.catalog_role == "catalog_candidate":
        issues.append(RightsIssue(
            code="catalog_candidate_only",
            message=(
                f"Source '{sid}' is marked catalog_candidate. Commercial movie/TV "
                "catalogs cannot train voice identity without documented rights."
            ),
            source_id=sid,
        ))

    if gate != "ingest_annotate":
        if not (session.license_type or "").strip():
            issues.append(RightsIssue(
                code="missing_license_type",
                message=f"Source '{sid}' is missing license_type.",
                source_id=sid,
            ))
        if not (session.owner or "").strip():
            issues.append(RightsIssue(
                code="missing_owner",
                message=f"Source '{sid}' is missing owner.",
                source_id=sid,
            ))
        if not session.performers:
            issues.append(RightsIssue(
                code="no_performers",
                message=f"Source '{sid}' has no performers with consent records.",
                source_id=sid,
            ))

    for performer in session.performers:
        issues.extend(
            validate_performer_consent(performer, gate=gate, source_id=sid, now=now)
        )

    # For identity training, at least one performer must fully pass.
    if gate in ("voice_model_training", "voice_cloning", "tts_synthesis") and session.performers:
        ok_any = False
        for performer in session.performers:
            per_issues = validate_performer_consent(
                performer, gate=gate, source_id=sid, now=now
            )
            if not any(i.severity == "error" for i in per_issues):
                ok_any = True
                break
        if not ok_any and not any(i.code == "no_performers" for i in issues):
            issues.append(RightsIssue(
                code="no_valid_consent",
                message=(
                    f"No performer on source '{sid}' has valid consent for {gate}."
                ),
                source_id=sid,
            ))

    errors = [i for i in issues if i.severity == "error"]
    return RightsVerdict(allowed=len(errors) == 0, issues=issues, gate=gate)


def validate_dataset_for_training(
    dataset: SpeechDataset,
    *,
    gate: GateKind = "voice_model_training",
    now: datetime | None = None,
) -> RightsVerdict:
    """All sessions must pass the gate before voice-identity training is allowed."""
    all_issues: list[RightsIssue] = []
    if not dataset.sessions:
        all_issues.append(RightsIssue(
            code="empty_sessions",
            message="Dataset has no sessions; cannot authorize training.",
        ))
    for session in dataset.sessions:
        verdict = validate_session(session, gate=gate, now=now)
        all_issues.extend(verdict.issues)
    errors = [i for i in all_issues if i.severity == "error"]
    return RightsVerdict(allowed=len(errors) == 0, issues=all_issues, gate=gate)


def assert_training_allowed(
    dataset: SpeechDataset,
    *,
    gate: GateKind = "voice_model_training",
) -> None:
    """Raise ``PermissionError`` when the rights gate fails."""
    verdict = validate_dataset_for_training(dataset, gate=gate)
    if not verdict.allowed:
        msgs = "; ".join(i.message for i in verdict.errors[:5])
        raise PermissionError(f"Voice training blocked ({gate}): {msgs}")
