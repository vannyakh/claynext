"""Validate speech dataset JSON/JSONL structure and split integrity."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from claynext.voice_training.datasets.speech_schema import (
    EMOTIONS,
    SPEAKING_STYLES,
    SpeechDataset,
    SpeechSegment,
)

Severity = Literal["error", "warning"]


@dataclass
class SchemaIssue:
    code: str
    message: str
    severity: Severity = "error"
    segment_id: str = ""
    source_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "segment_id": self.segment_id,
            "source_id": self.source_id,
        }


@dataclass
class ValidationReport:
    ok: bool
    issues: list[SchemaIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[SchemaIssue]:
        return [i for i in self.issues if i.severity == "error"]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "issues": [i.to_dict() for i in self.issues]}


def validate_segment(seg: SpeechSegment) -> list[SchemaIssue]:
    issues: list[SchemaIssue] = []
    sid = seg.segment_id
    if not sid:
        issues.append(SchemaIssue("missing_segment_id", "segment_id is required."))
    if not seg.audio_path:
        issues.append(SchemaIssue("missing_audio_path", "audio_path is required.", segment_id=sid))
    if seg.end_sec < seg.start_sec:
        issues.append(SchemaIssue(
            "bad_timing",
            f"end_sec ({seg.end_sec}) < start_sec ({seg.start_sec}).",
            segment_id=sid,
        ))
    if seg.train_split not in ("train", "val", "test"):
        issues.append(SchemaIssue(
            "bad_split",
            f"train_split must be train|val|test, got {seg.train_split!r}.",
            segment_id=sid,
        ))
    if seg.emotion and seg.emotion not in EMOTIONS:
        issues.append(SchemaIssue(
            "unknown_emotion",
            f"emotion {seg.emotion!r} is not in the known set.",
            severity="warning",
            segment_id=sid,
        ))
    if seg.speaking_style and seg.speaking_style not in SPEAKING_STYLES:
        issues.append(SchemaIssue(
            "unknown_style",
            f"speaking_style {seg.speaking_style!r} is not in the known set.",
            severity="warning",
            segment_id=sid,
        ))
    if not seg.session_id:
        issues.append(SchemaIssue(
            "missing_session_id",
            "session_id is required on segments.",
            severity="warning",
            segment_id=sid,
        ))
    if not seg.source_id:
        issues.append(SchemaIssue(
            "missing_source_id",
            "source_id is required on segments.",
            severity="warning",
            segment_id=sid,
        ))
    return issues


def validate_dataset(dataset: SpeechDataset) -> ValidationReport:
    issues: list[SchemaIssue] = []
    if not dataset.dataset_id:
        issues.append(SchemaIssue("missing_dataset_id", "dataset_id is required."))
    if not dataset.name:
        issues.append(SchemaIssue("missing_name", "name is required."))

    session_ids = {s.session_id or s.source_id for s in dataset.sessions}
    source_ids = {s.source_id for s in dataset.sessions}

    for session in dataset.sessions:
        if not session.source_id:
            issues.append(SchemaIssue("session_missing_source_id", "Session missing source_id."))
        if not session.license_type:
            issues.append(SchemaIssue(
                "session_missing_license",
                f"Session {session.source_id} missing license_type.",
                severity="warning",
                source_id=session.source_id,
            ))

    seen_seg: set[str] = set()
    for seg in dataset.segments:
        if seg.segment_id in seen_seg:
            issues.append(SchemaIssue(
                "duplicate_segment_id",
                f"Duplicate segment_id {seg.segment_id}.",
                segment_id=seg.segment_id,
            ))
        seen_seg.add(seg.segment_id)
        issues.extend(validate_segment(seg))
        if seg.session_id and session_ids and seg.session_id not in session_ids:
            issues.append(SchemaIssue(
                "orphan_session",
                f"segment session_id {seg.session_id} not in sessions.",
                severity="warning",
                segment_id=seg.segment_id,
            ))
        if seg.source_id and source_ids and seg.source_id not in source_ids:
            issues.append(SchemaIssue(
                "orphan_source",
                f"segment source_id {seg.source_id} not in sessions.",
                severity="warning",
                segment_id=seg.segment_id,
            ))

    # Split leakage: same session/source should not span train and test.
    by_session: dict[str, set[str]] = {}
    by_source: dict[str, set[str]] = {}
    for seg in dataset.segments:
        if seg.session_id:
            by_session.setdefault(seg.session_id, set()).add(seg.train_split)
        if seg.source_id:
            by_source.setdefault(seg.source_id, set()).add(seg.train_split)
    for key, splits in by_session.items():
        if "train" in splits and "test" in splits:
            issues.append(SchemaIssue(
                "split_leak_session",
                f"Session {key} appears in both train and test.",
            ))
    for key, splits in by_source.items():
        if "train" in splits and "test" in splits:
            issues.append(SchemaIssue(
                "split_leak_source",
                f"Source {key} appears in both train and test.",
            ))

    errors = [i for i in issues if i.severity == "error"]
    return ValidationReport(ok=len(errors) == 0, issues=issues)
