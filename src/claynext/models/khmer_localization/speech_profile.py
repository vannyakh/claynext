"""Character Speech Profiles, project localization config, and their per-project store.

Precedence for every profile field, highest first:

1. editor overrides (``SpeechProfile.overrides``),
2. values set from project config or explicit evidence,
3. values seeded from the character registry (read-only input),
4. defaults.

Project caps (``profanity_cap``, ``slang_cap``) are ceilings applied after
all of the above, including editor overrides.

The store is JSON under ``CACHE_DIR/khmer_localization/<project_key>.json``
or ``<run_dir>/khmer_localization.json`` for a job directory.
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

STORE_VERSION = 1
REGISTERS = ("formal", "neutral", "casual", "street", "regional")
AGE_GROUPS = ("child", "teen", "adult", "elder", "unknown")
GENDERS = ("male", "female", "unknown")
FORMALITY = ("formal", "neutral", "informal")
REGION_SOURCES = ("", "editor", "project_config", "evidence")
_AGE_RANK = {"child": 0, "teen": 1, "adult": 2, "elder": 3}
_OVERRIDABLE = (
    "name", "gender", "age_group", "register", "slang_level", "profanity_level",
    "habitual_first_person", "habitual_second_person", "pronoun_overrides",
    "catchphrases", "region", "social_role",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _level(value: Any, name: str) -> int:
    try:
        level = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}: expected 0-3, got {value!r}") from exc
    if not 0 <= level <= 3:
        raise ValueError(f"{name}: expected 0-3, got {level}")
    return level


def _choice(value: Any, allowed: tuple[str, ...], name: str, default: str) -> str:
    text = str(value or default).strip().lower()
    if text not in allowed:
        raise ValueError(f"{name}: {text!r} not in {list(allowed)}")
    return text


def normalize_gender(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text.startswith(("f", "feminine")):
        return "female"
    if text.startswith(("m", "masculine")):
        return "male"
    return "unknown"


def normalize_age_group(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in AGE_GROUPS:
        return text
    if any(w in text for w in ("child", "kid", "boy", "girl")):
        return "child"
    if "teen" in text:
        return "teen"
    if any(w in text for w in ("elder", "senior", "old")):
        return "elder"
    nums = [int(n) for n in re.findall(r"\d+", text)]
    if nums:
        age = sum(nums) / len(nums)
        return "child" if age < 13 else "teen" if age < 20 else "adult" if age < 60 else "elder"
    if "adult" in text:
        return "adult"
    return "unknown"


def age_relation(speaker_age: str, listener_age: str) -> str:
    """``older`` / ``younger`` / ``peer`` for the speaker relative to the listener."""
    a, b = _AGE_RANK.get(speaker_age), _AGE_RANK.get(listener_age)
    if a is None or b is None:
        return "unknown"
    return "older" if a > b else "younger" if a < b else "peer"


@dataclass
class SpeechProfile:
    character_id: str
    name: str = ""
    gender: str = "unknown"
    age_group: str = "unknown"
    register: str = "neutral"
    slang_level: int = 0
    profanity_level: int = 0
    habitual_first_person: list[str] = field(default_factory=list)
    habitual_second_person: list[str] = field(default_factory=list)
    pronoun_overrides: list[dict[str, str]] = field(default_factory=list)
    catchphrases: list[str] = field(default_factory=list)
    region: str | None = None
    region_source: str = ""
    social_role: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    overrides: dict[str, Any] = field(default_factory=dict)
    updated_at: str = ""

    def validate(self) -> "SpeechProfile":
        if not str(self.character_id or "").strip():
            raise ValueError("character_id is required")
        self.gender = normalize_gender(self.gender)
        self.age_group = normalize_age_group(self.age_group)
        self.register = _choice(self.register, REGISTERS, "register", "neutral")
        self.slang_level = _level(self.slang_level, "slang_level")
        self.profanity_level = _level(self.profanity_level, "profanity_level")
        self.region = str(self.region).strip() or None if self.region else None
        self.region_source = _choice(self.region_source, REGION_SOURCES, "region_source", "")
        if self.region and not self.region_source:
            raise ValueError("region needs region_source (editor, project_config, or evidence)")
        self.confidence = max(0.0, min(1.0, float(self.confidence or 0.0)))
        for row in self.pronoun_overrides:
            if not isinstance(row, dict) or not (row.get("first") or row.get("second")):
                raise ValueError("pronoun_overrides rows need first and/or second")
        unknown = sorted(set(self.overrides) - set(_OVERRIDABLE))
        if unknown:
            raise ValueError(f"overrides: unknown field(s) {unknown}")
        return self

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpeechProfile":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in dict(data).items() if k in names}).validate()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def effective(self, config: "LocalizationConfig | None" = None) -> "SpeechProfile":
        """Profile with editor overrides applied, then project caps."""
        merged = replace(self, **{k: v for k, v in self.overrides.items() if k in _OVERRIDABLE})
        if "region" in self.overrides:
            merged.region_source = "editor" if merged.region else ""
        merged.overrides = {}
        merged.validate()
        if config is not None:
            merged.profanity_level = min(merged.profanity_level, config.profanity_cap)
            merged.slang_level = min(merged.slang_level, config.slang_cap)
            if not config.allow_regional:
                merged.region = None
                merged.region_source = ""
        return merged

    def overrides_for(self, listener: str) -> dict[str, str] | None:
        rows = [r for r in self.pronoun_overrides if str(r.get("listener") or "*") == listener]
        rows = rows or [r for r in self.pronoun_overrides if str(r.get("listener") or "*") == "*"]
        return dict(rows[-1]) if rows else None


@dataclass
class SceneStyle:
    scene_id: str
    register: str = ""
    formality: str = "neutral"
    slang_cap: int | None = None
    profanity_cap: int | None = None
    note: str = ""

    def validate(self) -> "SceneStyle":
        if self.register:
            self.register = _choice(self.register, REGISTERS, "scene.register", "neutral")
        self.formality = _choice(self.formality, FORMALITY, "scene.formality", "neutral")
        if self.slang_cap is not None:
            self.slang_cap = _level(self.slang_cap, "scene.slang_cap")
        if self.profanity_cap is not None:
            self.profanity_cap = _level(self.profanity_cap, "scene.profanity_cap")
        return self


@dataclass
class LocalizationConfig:
    profanity_cap: int = 1
    slang_cap: int = 2
    default_register: str = "neutral"
    allow_regional: bool = False
    review_confidence: float = 0.6
    scenes: dict[str, SceneStyle] = field(default_factory=dict)
    scene_overrides: list[dict[str, str]] = field(default_factory=list)

    def validate(self) -> "LocalizationConfig":
        self.profanity_cap = _level(self.profanity_cap, "profanity_cap")
        self.slang_cap = _level(self.slang_cap, "slang_cap")
        self.default_register = _choice(self.default_register, REGISTERS, "default_register", "neutral")
        self.allow_regional = bool(self.allow_regional)
        self.review_confidence = max(0.0, min(1.0, float(self.review_confidence)))
        for row in self.scene_overrides:
            if not row.get("scene_id") or not (row.get("first") or row.get("second")):
                raise ValueError("scene_overrides rows need scene_id and first and/or second")
        return self

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "LocalizationConfig":
        data = dict(data or {})
        scenes = {}
        for sid, row in (data.pop("scenes", None) or {}).items():
            row = dict(row or {})
            row["scene_id"] = str(sid)
            scenes[str(sid)] = SceneStyle(**row).validate()
        names = {f.name for f in fields(cls)}
        cfg = cls(**{k: v for k, v in data.items() if k in names}, scenes=scenes)
        return cfg.validate()

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["scenes"] = {k: asdict(v) for k, v in self.scenes.items()}
        return out

    def scene(self, scene_id: str | None) -> SceneStyle | None:
        return self.scenes.get(str(scene_id)) if scene_id else None

    def scene_override(self, scene_id: str | None, speaker: str, listener: str) -> dict[str, str] | None:
        if not scene_id:
            return None
        for row in reversed(self.scene_overrides):
            if str(row.get("scene_id")) != str(scene_id):
                continue
            if str(row.get("speaker") or "*") in ("*", speaker) and str(row.get("listener") or "*") in ("*", listener):
                return dict(row)
        return None


def default_store_dir() -> Path:
    from claynext.utils.paths import CACHE_DIR

    return CACHE_DIR / "khmer_localization"


class LocalizationStore:
    """Speech profiles, relationships, and project config for one project / job."""

    def __init__(self, path: Path | None = None, *, project_key: str = ""):
        from claynext.models.khmer_localization.relationships import RelationshipGraph

        self.path = path
        self.project_key = project_key
        self.config = LocalizationConfig()
        self.profiles: dict[str, SpeechProfile] = {}
        self.relationships = RelationshipGraph()
        self._lock = threading.Lock()

    @classmethod
    def for_project(cls, project_key: str, run_dir: str | Path | None = None) -> "LocalizationStore":
        path = Path(run_dir) / "khmer_localization.json" if run_dir else default_store_dir() / f"{project_key}.json"
        return cls.load(path, project_key=project_key)

    @classmethod
    def load(cls, path: str | Path, *, project_key: str = "") -> "LocalizationStore":
        """Missing file → empty store. A corrupt file raises, so edits are never silently dropped."""
        from claynext.models.khmer_localization.relationships import RelationshipGraph

        store = cls(Path(path), project_key=project_key)
        if not store.path.is_file():
            return store
        data = json.loads(store.path.read_text(encoding="utf-8"))
        store.project_key = str(data.get("project_key") or project_key)
        store.config = LocalizationConfig.from_dict(data.get("config"))
        store.profiles = {
            str(cid): SpeechProfile.from_dict(row) for cid, row in (data.get("profiles") or {}).items()
        }
        store.relationships = RelationshipGraph.from_list(data.get("relationships") or [])
        return store

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": STORE_VERSION,
            "project_key": self.project_key,
            "updated_at": _now(),
            "config": self.config.to_dict(),
            "profiles": {cid: p.to_dict() for cid, p in sorted(self.profiles.items())},
            "relationships": self.relationships.to_list(),
        }

    def save(self, path: str | Path | None = None) -> Path:
        dest = Path(path) if path else self.path
        if dest is None:
            raise ValueError("LocalizationStore has no path")
        with self._lock:
            payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(dest)
        self.path = dest
        return dest

    # ── profiles ────────────────────────────────────────────────────────
    def profile(self, character_id: str) -> SpeechProfile | None:
        return self.profiles.get(character_id)

    def upsert(self, profile: SpeechProfile) -> SpeechProfile:
        """Store a profile from config / evidence; keeps existing editor overrides."""
        profile.validate()
        old = self.profiles.get(profile.character_id)
        if old is not None:
            profile.overrides = {**old.overrides, **profile.overrides}
        profile.updated_at = _now()
        self.profiles[profile.character_id] = profile
        return profile

    def effective(self, character_id: str) -> SpeechProfile | None:
        profile = self.profiles.get(character_id)
        return profile.effective(self.config) if profile else None

    def set_override(self, character_id: str, **values: Any) -> SpeechProfile:
        profile = self.profiles.get(character_id) or SpeechProfile(character_id=character_id)
        over = dict(profile.overrides)
        for key, value in values.items():
            if key not in _OVERRIDABLE:
                raise ValueError(f"cannot override {key!r}")
            if value is None or value == "":
                over.pop(key, None)
            else:
                over[key] = value
        profile.overrides = over
        profile.effective()
        profile.updated_at = _now()
        self.profiles[character_id] = profile
        return profile

    def seed_from_characters(self, characters: Iterable[dict[str, Any]]) -> list[str]:
        """Fill empty fields from character registry rows (``character_intel``). Never touches overrides."""
        seeded = []
        for row in characters or []:
            cid = str(row.get("character_id") or "").strip()
            if not cid:
                continue
            profile = self.profiles.get(cid) or SpeechProfile(character_id=cid)
            name = str((row.get("overrides") or {}).get("name") or row.get("name") or "")
            if name and name != "Unknown" and not profile.name:
                profile.name = name
            voice = row.get("voice_profile") or {}
            if profile.gender == "unknown":
                profile.gender = normalize_gender(voice.get("presentation") if voice.get("presentation") != "uncertain" else "")
            if profile.age_group == "unknown":
                profile.age_group = normalize_age_group(voice.get("age_range_estimate"))
            if not profile.social_role and row.get("role"):
                profile.social_role = str(row["role"])
            if not any(e.get("source") == "character_registry" for e in profile.evidence):
                profile.evidence.append({"source": "character_registry", "character_id": cid})
            profile.updated_at = _now()
            self.profiles[cid] = profile.validate()
            seeded.append(cid)
        return seeded

    def seed_from_segments(self, segments: Iterable[dict[str, Any]]) -> None:
        """Make sure every speaker has a profile; uses the line's character_id when present."""
        for seg in segments or []:
            cid = character_key(seg)
            if not cid or cid in self.profiles:
                continue
            self.profiles[cid] = SpeechProfile(
                character_id=cid,
                name=str(seg.get("speaker") or ""),
                gender=normalize_gender(seg.get("gender")),
                evidence=[{"source": "segment", "id": str(seg.get("id"))}],
                updated_at=_now(),
            ).validate()


def character_key(seg: dict[str, Any]) -> str:
    """Stable key for a line's speaker: character registry id, else the speaker label."""
    return str(seg.get("character_id") or seg.get("speaker") or "").strip()
