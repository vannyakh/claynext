"""Speech audio dataset schema (sessions + segments).

Distinct from the Khmer Spoken Language Dataset (dialogue text): this schema
describes how speech sounds — waveforms, speakers, emotion, consent.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

TrainSplit = Literal["train", "val", "test"]

# Uses that unlock voice-identity / TTS synthesis paths.
VOICE_IDENTITY_USES = frozenset({"voice_model_training", "tts_synthesis", "voice_cloning"})
TTS_SYNTHESIS_USES = frozenset({"tts_synthesis", "voice_model_training"})

EMOTIONS = ("neutral", "angry", "sad", "excited", "romantic", "comedy", "fearful", "other")
SPEAKING_STYLES = ("formal", "normal", "spoken", "youth_slang", "whisper", "shout")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class PerformerConsent:
    name: str
    consent_id: str
    consent_doc_path: str = ""
    permitted_uses: list[str] = field(default_factory=list)
    restrictions: list[str] = field(default_factory=list)
    expires_at: str | None = None  # ISO-8601 UTC or None = no expiry
    revocable: bool = True
    revoked_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PerformerConsent:
        return cls(
            name=str(data.get("name") or ""),
            consent_id=str(data.get("consent_id") or ""),
            consent_doc_path=str(data.get("consent_doc_path") or ""),
            permitted_uses=[str(u) for u in (data.get("permitted_uses") or [])],
            restrictions=[str(r) for r in (data.get("restrictions") or [])],
            expires_at=data.get("expires_at"),
            revocable=bool(data.get("revocable", True)),
            revoked_at=data.get("revoked_at"),
        )


@dataclass
class RecordingSession:
    """One import / recording session with rights metadata."""

    source_id: str
    title: str
    owner: str
    license_type: str
    license_doc_path: str = ""
    performers: list[PerformerConsent] = field(default_factory=list)
    imported_at: str = field(default_factory=_utc_now)
    session_id: str = ""
    media_path: str = ""
    notes: str = ""
    # Commercial movie/TV catalogs without rights remain "catalog_candidate" only.
    catalog_role: str = "training_source"  # training_source | catalog_candidate

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["performers"] = [p.to_dict() if isinstance(p, PerformerConsent) else p for p in self.performers]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecordingSession:
        performers = [PerformerConsent.from_dict(p) if isinstance(p, dict) else p for p in (data.get("performers") or [])]
        return cls(
            source_id=str(data.get("source_id") or ""),
            title=str(data.get("title") or ""),
            owner=str(data.get("owner") or ""),
            license_type=str(data.get("license_type") or ""),
            license_doc_path=str(data.get("license_doc_path") or ""),
            performers=performers,
            imported_at=str(data.get("imported_at") or _utc_now()),
            session_id=str(data.get("session_id") or data.get("source_id") or ""),
            media_path=str(data.get("media_path") or ""),
            notes=str(data.get("notes") or ""),
            catalog_role=str(data.get("catalog_role") or "training_source"),
        )


@dataclass
class SpeechSegment:
    """One timed speech clip ready for review / training."""

    segment_id: str
    audio_path: str
    start_sec: float
    end_sec: float
    speaker_id: str = ""
    transcript_display: str = ""
    transcript_spoken: str = ""
    tts_pronunciation: str = ""
    emotion: str = "neutral"
    speaking_style: str = "spoken"
    quality_score: float = 0.0
    verified_by: str = ""
    verified_at: str | None = None
    train_split: TrainSplit = "train"
    session_id: str = ""
    source_id: str = ""
    dialect: str = "standard_khmer"
    slang_level: float = 0.0
    rudeness_level: float = 0.0
    prosody: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpeechSegment:
        split = str(data.get("train_split") or "train")
        if split not in ("train", "val", "test"):
            split = "train"
        return cls(
            segment_id=str(data.get("segment_id") or ""),
            audio_path=str(data.get("audio_path") or ""),
            start_sec=float(data.get("start_sec") or 0.0),
            end_sec=float(data.get("end_sec") or 0.0),
            speaker_id=str(data.get("speaker_id") or ""),
            transcript_display=str(data.get("transcript_display") or ""),
            transcript_spoken=str(data.get("transcript_spoken") or ""),
            tts_pronunciation=str(data.get("tts_pronunciation") or ""),
            emotion=str(data.get("emotion") or "neutral"),
            speaking_style=str(data.get("speaking_style") or "spoken"),
            quality_score=float(data.get("quality_score") or 0.0),
            verified_by=str(data.get("verified_by") or ""),
            verified_at=data.get("verified_at"),
            train_split=split,  # type: ignore[arg-type]
            session_id=str(data.get("session_id") or ""),
            source_id=str(data.get("source_id") or ""),
            dialect=str(data.get("dialect") or "standard_khmer"),
            slang_level=float(data.get("slang_level") or 0.0),
            rudeness_level=float(data.get("rudeness_level") or 0.0),
            prosody=dict(data.get("prosody") or {}),
            meta=dict(data.get("meta") or {}),
        )


@dataclass
class SpeechDataset:
    """Full dataset document (JSON) with sessions + segments."""

    dataset_id: str
    name: str
    version: str = "0.1.0"
    language: str = "km"
    sessions: list[RecordingSession] = field(default_factory=list)
    segments: list[SpeechSegment] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)
    notes: str = ""
    # Link to text/dialogue dataset (what to say), not audio.
    language_dataset_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "name": self.name,
            "version": self.version,
            "language": self.language,
            "sessions": [s.to_dict() for s in self.sessions],
            "segments": [s.to_dict() for s in self.segments],
            "created_at": self.created_at,
            "notes": self.notes,
            "language_dataset_ref": self.language_dataset_ref,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpeechDataset:
        return cls(
            dataset_id=str(data.get("dataset_id") or ""),
            name=str(data.get("name") or ""),
            version=str(data.get("version") or "0.1.0"),
            language=str(data.get("language") or "km"),
            sessions=[RecordingSession.from_dict(s) for s in (data.get("sessions") or [])],
            segments=[SpeechSegment.from_dict(s) for s in (data.get("segments") or [])],
            created_at=str(data.get("created_at") or _utc_now()),
            notes=str(data.get("notes") or ""),
            language_dataset_ref=str(data.get("language_dataset_ref") or ""),
        )
