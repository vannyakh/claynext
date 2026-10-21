"""Dialogue localization record schema and validators.

One record is one line of dialogue with its source text, one or more Khmer translation
candidates, the speaking context (speaker, listener, relationship, emotion, register),
provenance and licensing, review state, quality scores, and group keys for leakage-safe
splitting.

Hard rules enforced by ``validate_record``:

- ``reviewed`` and ``gold`` need a reviewer id and an ISO timestamp.
- ``gold`` needs a human reviewer and a license. Synthetic data is never gold without that review.
- A region claim needs provenance and a confidence; a ``verified`` region needs provenance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from claynext.models.datasets.normalize import has_khmer

SCHEMA_VERSION = "1.0.0"

REVIEW_STATUSES = ("draft", "staging", "reviewed", "gold", "rejected")
STATUS_RANK = {s: i for i, s in enumerate(("rejected", "draft", "staging", "reviewed", "gold"))}
ORIGINS = ("human_authored", "human_reviewed", "synthetic")
REVIEWER_TYPES = ("human", "model")
CATEGORIES = (
    "everyday",
    "family",
    "friendship",
    "romance",
    "argument",
    "comedy_sarcasm",
    "fear_sadness",
    "anger_profanity",
    "regional",
    "action_drama",
)
CANDIDATE_STYLES = ("literal", "natural", "unspecified")
# Same vocabulary as khmer_localization.speech_profile.REGISTERS.
REGISTERS = ("formal", "neutral", "casual", "street", "regional")
KNOWN_EMOTIONS = (
    "neutral", "happy", "caring", "affectionate", "angry", "annoyed", "fearful", "sad",
    "surprised", "playful", "excited", "sarcastic", "disgusted", "anxious", "tender", "contempt",
)
QUALITY_DIMENSIONS = (
    "semantic_accuracy",
    "naturalness",
    "character_consistency",
    "pronoun_correctness",
    "emotion_fit",
    "regional_authenticity",
    "tts_suitability",
)
SCORE_MIN, SCORE_MAX = 1.0, 5.0
LEVEL_MIN, LEVEL_MAX = 0, 3
GROUP_KEYS = ("film_id", "script_id", "dialogue_family", "speaker_id")
CANDIDATE_PREFERENCE = ("natural", "unspecified", "literal")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _opt(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _opt_int(value: Any) -> int | None:
    if value is None or _text(value) == "":
        return None
    return int(float(value))


def _opt_float(value: Any) -> float | None:
    if value is None or _text(value) == "":
        return None
    return float(value)


def parse_iso(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class Candidate:
    text: str
    style: str = "unspecified"
    origin: str | None = None
    notes: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Candidate":
        return cls(
            text=_text(data.get("text")),
            style=_text(data.get("style")) or "unspecified",
            origin=_opt(data.get("origin")),
            notes=_opt(data.get("notes")),
        )


@dataclass
class Regional:
    region: str | None = None
    verified: bool = False
    provenance: str | None = None
    confidence: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Regional":
        data = data or {}
        return cls(
            region=_opt(data.get("region")),
            verified=bool(data.get("verified") or False),
            provenance=_opt(data.get("provenance")),
            confidence=_opt_float(data.get("confidence")),
        )


@dataclass
class Provenance:
    dataset: str | None = None
    file: str | None = None
    source_id: str | None = None
    license: str | None = None
    attribution: str | None = None
    notes: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Provenance":
        data = data or {}
        return cls(**{k: _opt(data.get(k)) for k in cls.__dataclass_fields__})


@dataclass
class Review:
    status: str = "draft"
    reviewer_id: str | None = None
    reviewer_type: str | None = None
    reviewed_at: str | None = None
    notes: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Review":
        data = data or {}
        return cls(
            status=_text(data.get("status")) or "draft",
            reviewer_id=_opt(data.get("reviewer_id")),
            reviewer_type=_opt(data.get("reviewer_type")),
            reviewed_at=_opt(data.get("reviewed_at")),
            notes=_opt(data.get("notes")),
        )


@dataclass
class Quality:
    scores: dict[str, float | None] = field(default_factory=dict)
    scored_by: str | None = None
    extra: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Quality":
        data = data or {}
        raw = data.get("scores") or {}
        return cls(
            scores={k: _opt_float(raw.get(k)) for k in QUALITY_DIMENSIONS if raw.get(k) not in (None, "")},
            scored_by=_opt(data.get("scored_by")),
            extra={str(k): float(v) for k, v in (data.get("extra") or {}).items() if v not in (None, "")},
        )


@dataclass
class DialogueRecord:
    id: str
    source_text: str
    source_lang: str = "en"
    target_lang: str = "km"
    candidates: list[Candidate] = field(default_factory=list)
    tts_text: str | None = None
    speaker_id: str | None = None
    listener_id: str | None = None
    relationship: str | None = None
    emotion: str | None = None
    intensity: int | None = None
    register: str | None = None
    slang_level: int | None = None
    profanity_level: int | None = None
    category: str | None = None
    regional: Regional = field(default_factory=Regional)
    provenance: Provenance = field(default_factory=Provenance)
    origin: str = "synthetic"
    review: Review = field(default_factory=Review)
    quality: Quality = field(default_factory=Quality)
    groups: dict[str, str] = field(default_factory=dict)
    split: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    @property
    def status(self) -> str:
        return self.review.status

    def preferred_candidate(self) -> Candidate | None:
        """Natural rendering first, then unspecified, then literal."""
        for style in CANDIDATE_PREFERENCE:
            for cand in self.candidates:
                if cand.style == style and cand.text:
                    return cand
        return next((c for c in self.candidates if c.text), None)

    def group_key(self, keys: tuple[str, ...] = GROUP_KEYS) -> str:
        """First present key in ``keys`` order. Records with none fall back to their own id."""
        for key in keys:
            value = self.groups.get(key)
            if value:
                return f"{key}:{value}"
        return f"id:{self.id}"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["groups"] = {k: v for k, v in self.groups.items() if v}
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DialogueRecord":
        return cls(
            id=_text(data.get("id")),
            source_text=_text(data.get("source_text")),
            source_lang=_text(data.get("source_lang")) or "en",
            target_lang=_text(data.get("target_lang")) or "km",
            candidates=[Candidate.from_dict(c) for c in data.get("candidates") or []],
            tts_text=_opt(data.get("tts_text")),
            speaker_id=_opt(data.get("speaker_id")),
            listener_id=_opt(data.get("listener_id")),
            relationship=_opt(data.get("relationship")),
            emotion=_opt(data.get("emotion")),
            intensity=_opt_int(data.get("intensity")),
            register=_opt(data.get("register")),
            slang_level=_opt_int(data.get("slang_level")),
            profanity_level=_opt_int(data.get("profanity_level")),
            category=_opt(data.get("category")),
            regional=Regional.from_dict(data.get("regional")),
            provenance=Provenance.from_dict(data.get("provenance")),
            origin=_text(data.get("origin")) or "synthetic",
            review=Review.from_dict(data.get("review")),
            quality=Quality.from_dict(data.get("quality")),
            groups={k: _text(v) for k, v in (data.get("groups") or {}).items() if _text(v)},
            split=_opt(data.get("split")),
            metadata=dict(data.get("metadata") or {}),
            schema_version=_text(data.get("schema_version")) or SCHEMA_VERSION,
        )


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" | "warning"
    code: str
    field: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def validate_record(rec: DialogueRecord) -> list[Issue]:
    issues: list[Issue] = []

    def err(code: str, fld: str, msg: str) -> None:
        issues.append(Issue("error", code, fld, msg))

    def warn(code: str, fld: str, msg: str) -> None:
        issues.append(Issue("warning", code, fld, msg))

    if not rec.id:
        err("missing_id", "id", "Record has no id.")
    if not rec.source_text:
        err("missing_source_text", "source_text", "Source dialogue text is empty.")
    if not rec.candidates:
        err("missing_candidates", "candidates", "At least one Khmer translation candidate is required.")
    for i, cand in enumerate(rec.candidates):
        if not cand.text:
            err("empty_candidate", f"candidates[{i}].text", "Candidate text is empty.")
        elif rec.target_lang == "km" and not has_khmer(cand.text):
            warn("candidate_not_khmer", f"candidates[{i}].text", "Candidate has no Khmer characters.")
        if cand.style not in CANDIDATE_STYLES:
            err("bad_candidate_style", f"candidates[{i}].style", f"Style must be one of {CANDIDATE_STYLES}.")

    status = rec.review.status
    if status not in REVIEW_STATUSES:
        err("bad_status", "review.status", f"Status must be one of {REVIEW_STATUSES}.")
    if rec.origin not in ORIGINS:
        err("bad_origin", "origin", f"Origin must be one of {ORIGINS}.")
    if rec.review.reviewer_type and rec.review.reviewer_type not in REVIEWER_TYPES:
        err("bad_reviewer_type", "review.reviewer_type", f"Reviewer type must be one of {REVIEWER_TYPES}.")
    if rec.review.reviewed_at and parse_iso(rec.review.reviewed_at) is None:
        err("bad_reviewed_at", "review.reviewed_at", "reviewed_at is not an ISO 8601 timestamp.")

    if status in ("reviewed", "gold"):
        if not rec.review.reviewer_id:
            err("review_missing_reviewer", "review.reviewer_id", f"Status {status} needs a reviewer id.")
        if not rec.review.reviewed_at:
            err("review_missing_timestamp", "review.reviewed_at", f"Status {status} needs a review timestamp.")
    if status == "gold":
        human = rec.review.reviewer_type == "human" and bool(rec.review.reviewer_id)
        if rec.origin == "synthetic" and not human:
            err("synthetic_gold_unreviewed", "review", "Synthetic data cannot be gold without human review.")
        elif not human:
            err("gold_requires_human_review", "review.reviewer_type", "Gold needs reviewer_type=human.")
        if not rec.provenance.license:
            err("gold_requires_license", "provenance.license", "Gold data needs a license.")
    if rec.origin == "human_reviewed" and not rec.review.reviewer_id:
        err("human_reviewed_without_reviewer", "review.reviewer_id", "Origin human_reviewed needs a reviewer id.")

    if not rec.provenance.license:
        warn("missing_license", "provenance.license", "No license recorded; the data cannot be gold or redistributed.")
    if not rec.provenance.dataset and not rec.provenance.file:
        warn("missing_provenance", "provenance", "No source dataset or file recorded.")

    if rec.category is None:
        warn("missing_category", "category", "No dialogue category.")
    elif rec.category not in CATEGORIES:
        err("bad_category", "category", f"Category must be one of {CATEGORIES}.")
    if rec.register is not None and rec.register not in REGISTERS:
        err("bad_register", "register", f"Register must be one of {REGISTERS}.")
    if rec.emotion is None:
        warn("missing_emotion", "emotion", "No emotion label.")
    elif rec.emotion not in KNOWN_EMOTIONS:
        warn("unknown_emotion", "emotion", f"Emotion {rec.emotion!r} is not in the known list.")
    if not rec.speaker_id:
        warn("missing_speaker", "speaker_id", "No speaker character id.")
    if not rec.relationship:
        warn("missing_relationship", "relationship", "No speaker/listener relationship.")

    for name in ("intensity", "slang_level", "profanity_level"):
        value = getattr(rec, name)
        if value is not None and not LEVEL_MIN <= value <= LEVEL_MAX:
            err("level_out_of_range", name, f"{name} must be {LEVEL_MIN}-{LEVEL_MAX}.")

    for dim, score in rec.quality.scores.items():
        if score is not None and not SCORE_MIN <= score <= SCORE_MAX:
            err("score_out_of_range", f"quality.scores.{dim}", f"Scores are {SCORE_MIN:g}-{SCORE_MAX:g}.")
    if rec.quality.scored_by and rec.quality.scored_by not in REVIEWER_TYPES:
        err("bad_scored_by", "quality.scored_by", f"scored_by must be one of {REVIEWER_TYPES}.")

    reg = rec.regional
    if reg.confidence is not None and not 0.0 <= reg.confidence <= 1.0:
        err("regional_confidence_range", "regional.confidence", "Confidence must be 0-1.")
    if reg.verified and not reg.provenance:
        err("regional_verified_without_provenance", "regional.provenance", "A verified region needs provenance.")
    if reg.region and (not reg.provenance or reg.confidence is None):
        msg = "A region claim needs provenance and a confidence."
        if status in ("reviewed", "gold"):
            err("regional_unsupported", "regional", msg)
        else:
            warn("regional_unsupported", "regional", msg)

    if not any(rec.groups.get(k) for k in GROUP_KEYS):
        warn("no_group_key", "groups", "No film/script/dialogue/speaker group; splits fall back to the record id.")
    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)
