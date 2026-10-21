"""Persistent character registry: one profile per character, stable across scenes and reruns.

Stored per source movie under ``STUDIO_CACHE/characters/<hash>.json`` and also
saved inside the project file (``character_registry``). Editor overrides
(name, voice, presentation, role) always win over automatic guesses.

A name stays ``Unknown`` until dialogue, credits, metadata, or the editor gives
evidence, and that evidence is recorded.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claynext.models.character_intel.expression_mapper import provider_for_voice
from claynext.models.character_intel.voice_casting import (
    estimate_presentation,
    gender_from_presentation,
    pitch_band,
)

REGISTRY_VERSION = 1
UNKNOWN_NAME = "Unknown"
_OVERRIDE_KEYS = ("name", "voice_id", "presentation", "role", "age_range_estimate")
_ROLE_WORDS = {
    "man", "woman", "boy", "girl", "child", "narrator", "old man", "old woman",
    "voice", "guard", "soldier", "crowd", "male", "female", "lead", "co-star",
}
_SPEAKER_MATCH_BASE = {
    "diarization": 0.85,
    "provider": 0.75,
    "turn_heuristic": 0.35,
}


def registry_path(media_path: str | Path) -> Path:
    from claynext.utils.config import STUDIO_CACHE

    key = hashlib.sha1(os.path.abspath(str(media_path)).encode("utf-8")).hexdigest()[:16]
    return Path(STUDIO_CACHE) / "characters" / f"{key}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _is_generic(label: str) -> bool:
    from claynext.models.gender_voices import is_generic_speaker

    clean = str(label or "").strip()
    return (
        is_generic_speaker(clean)
        or clean.upper().startswith("SPEAKER_")
        or clean in {"UNKNOWN_SPEAKER", UNKNOWN_NAME}
        or re.sub(r"\s+\d+$", "", clean).casefold() in _ROLE_WORDS
    )


def _new_profile(character_id: str) -> dict[str, Any]:
    return {
        "character_id": character_id,
        "name": UNKNOWN_NAME,
        "label": "",
        "speaker_id": "",
        "aliases": [],
        "role": "",
        "lines": 0,
        "voice_profile": {
            "presentation": "uncertain",
            "presentation_confidence": 0.0,
            "age_range_estimate": "unknown",
            "age_confidence": 0.0,
            "pitch": "unknown",
            "pitch_hz": 0.0,
            "timbre": "unknown",
            "accent": "unknown",
            "speaking_rate": 1.0,
        },
        "tts": {
            "provider": "",
            "voice_id": "",
            "language": "",
            "base_voice": "",
            "emotion": "neutral",
            "intensity": 0.5,
        },
        "confidence": {"speaker_match": 0.0, "character_identity": 0.0},
        "name_evidence": [],
        "overrides": {},
        "updated_at": _now(),
    }


class CharacterRegistry:
    def __init__(self, path: str | Path | None = None, data: dict[str, Any] | None = None):
        self.path = Path(path) if path else None
        data = data if isinstance(data, dict) else {}
        self.media = str(data.get("media") or "")
        self.characters: list[dict[str, Any]] = [
            self._upgrade(dict(row)) for row in data.get("characters") or [] if isinstance(row, dict)
        ]

    # ── persistence ─────────────────────────────────────────────────────
    @classmethod
    def load(cls, path: str | Path) -> "CharacterRegistry":
        dest = Path(path)
        data: dict[str, Any] = {}
        if dest.is_file():
            try:
                data = json.loads(dest.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        return cls(dest, data)

    @classmethod
    def for_media(cls, media_path: str | Path) -> "CharacterRegistry":
        reg = cls.load(registry_path(media_path))
        reg.media = os.path.abspath(str(media_path))
        return reg

    @classmethod
    def restore_for_media(cls, media_path: str | Path, data: dict[str, Any]) -> "CharacterRegistry":
        """Seed the cache from a project file when it is newer than (or missing from) the cache."""
        current = cls.for_media(media_path)
        incoming = cls(current.path, data)
        if not incoming.characters:
            return current
        newest = max((str(c.get("updated_at") or "") for c in current.characters), default="")
        theirs = max((str(c.get("updated_at") or "") for c in incoming.characters), default="")
        if not current.characters or theirs > newest:
            incoming.media = current.media
            incoming.save()
            return incoming
        return current

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": REGISTRY_VERSION,
            "media": self.media,
            "updated_at": _now(),
            "characters": [dict(row) for row in self.characters],
        }

    def save(self, path: str | Path | None = None) -> str:
        dest = Path(path) if path else self.path
        if dest is None:
            raise ValueError("Character registry has no path")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(dest)
        self.path = dest
        return str(dest)

    @staticmethod
    def _upgrade(row: dict[str, Any]) -> dict[str, Any]:
        base = _new_profile(str(row.get("character_id") or ""))
        for key, value in row.items():
            if isinstance(base.get(key), dict) and isinstance(value, dict):
                base[key] = {**base[key], **value}
            else:
                base[key] = value
        return base

    # ── lookup ──────────────────────────────────────────────────────────
    def get(self, character_id: str) -> dict[str, Any] | None:
        return next((c for c in self.characters if c.get("character_id") == character_id), None)

    def find(self, *, label: str = "", speaker_id: str = "", exclude: set[str] | None = None) -> dict[str, Any] | None:
        exclude = exclude or set()
        pool = [c for c in self.characters if c.get("character_id") not in exclude]
        if label:
            for c in pool:
                over = str((c.get("overrides") or {}).get("name") or "")
                if label in {over, str(c.get("label") or "")} or label in (c.get("aliases") or []):
                    return c
        if speaker_id:
            for c in pool:
                if c.get("speaker_id") == speaker_id:
                    return c
        return None

    def _new_id(self) -> str:
        taken = {str(c.get("character_id") or "") for c in self.characters}
        n = len(self.characters) + 1
        while f"CHAR_{n:03d}" in taken:
            n += 1
        return f"CHAR_{n:03d}"

    # ── reconcile with a dub run ────────────────────────────────────────
    def reconcile(
        self,
        segments: list[dict[str, Any]],
        *,
        lang: str = "",
        base_voice: str = "",
        reuse_voices: bool = True,
    ) -> list[dict[str, Any]]:
        """Map every line to a stable character, apply editor overrides, and keep voices stable."""
        groups: dict[str, list[int]] = {}
        for index, seg in enumerate(segments):
            label = str(seg.get("speaker") or "").strip() or "Character 1"
            groups.setdefault(label, []).append(index)

        used: set[str] = set()
        plan: list[tuple[dict[str, Any], str, list[int], dict[str, Any]]] = []
        for label, idxs in groups.items():
            lines = [segments[i] for i in idxs]
            ids = Counter(str(s.get("speaker_id") or "") for s in lines if s.get("speaker_id"))
            sid, sid_n = ids.most_common(1)[0] if ids else ("", 0)
            sources = Counter(str(s.get("speaker_source") or "") for s in lines)
            source = sources.most_common(1)[0][0] if sources else ""
            known = str(lines[0].get("character_id") or "")
            profile = self.get(known) if known and known not in used else None
            if profile is None:
                stable_id = sid if source != "turn_heuristic" else ""
                profile = self.find(label=label, speaker_id=stable_id, exclude=used)
            if profile is None:
                profile = _new_profile(self._new_id())
                self.characters.append(profile)
            used.add(profile["character_id"])
            prev_tts = dict(profile.get("tts") or {})
            self._update_profile(profile, label, lines, segments, sid, sid_n, source, lang)
            for seg in lines:
                seg["character_id"] = profile["character_id"]
            plan.append((profile, label, idxs, prev_tts))

        self.apply_overrides(segments)
        if reuse_voices:
            self._keep_previous_voices(segments, plan, base_voice=base_voice, lang=lang)
        for profile, _label, idxs, _prev in plan:
            self._update_tts(profile, [segments[i] for i in idxs], lang=lang, base_voice=base_voice)
        return [p for p, *_ in plan]

    def _update_profile(self, profile, label, lines, segments, sid, sid_n, source, lang) -> None:
        overrides = profile.get("overrides") or {}
        profile["label"] = label
        aliases = list(profile.get("aliases") or [])
        if label not in aliases:
            aliases.append(label)
        profile["aliases"] = aliases[-12:]
        if sid and source != "turn_heuristic":
            profile["speaker_id"] = sid
        elif not profile.get("speaker_id"):
            profile["speaker_id"] = sid
        profile["lines"] = len(lines)
        roles = Counter(str(s.get("character_role") or "") for s in lines if s.get("character_role"))
        profile["role"] = overrides.get("role") or (roles.most_common(1)[0][0] if roles else profile.get("role") or "")

        if any(s.get("speaker_manual") for s in lines):
            match = 1.0
        else:
            base = _SPEAKER_MATCH_BASE.get(source, 0.5)
            match = base * (sid_n / len(lines)) if sid_n else base * 0.6
        profile["confidence"]["speaker_match"] = round(match, 3)

        vp = profile["voice_profile"]
        if overrides.get("presentation"):
            vp["presentation"] = overrides["presentation"]
            vp["presentation_confidence"] = 1.0
        else:
            vp["presentation"], vp["presentation_confidence"] = estimate_presentation(lines)
        if overrides.get("age_range_estimate"):
            vp["age_range_estimate"] = overrides["age_range_estimate"]
            vp["age_confidence"] = 1.0

        self._update_name(profile, label, lines, segments)
        profile["updated_at"] = _now()

    def _update_name(self, profile, label, lines, segments) -> None:
        overrides = profile.get("overrides") or {}
        evidence = [e for e in profile.get("name_evidence") or [] if e.get("source") != "dialogue"]
        if overrides.get("name"):
            profile["name"] = overrides["name"]
            if not any(e.get("source") == "editor" for e in evidence):
                evidence.append({"source": "editor", "text": overrides["name"]})
            profile["name_evidence"] = evidence
            profile["confidence"]["character_identity"] = 1.0
            return
        voice_label = any(s.get("speaker_label_source") == "voice" for s in lines)
        candidate = "" if voice_label or _is_generic(label) else re.sub(r"\s+\d+$", "", label).strip()
        if candidate and len(candidate) >= 2:
            for i, seg in enumerate(segments):
                text = str(seg.get("original_text") or seg.get("text") or "")
                if candidate in text:
                    evidence.append({"source": "dialogue", "line_index": i, "text": text[:80]})
                    if len([e for e in evidence if e.get("source") == "dialogue"]) >= 5:
                        break
        dialogue = [e for e in evidence if e.get("source") == "dialogue"]
        external = [e for e in evidence if e.get("source") in {"credits", "metadata"}]
        if candidate and (dialogue or external):
            profile["name"] = candidate
            profile["confidence"]["character_identity"] = round(min(0.9, 0.5 + 0.1 * len(dialogue) + 0.2 * len(external)), 3)
        else:
            profile["name"] = UNKNOWN_NAME
            profile["confidence"]["character_identity"] = 0.15 if candidate else 0.0
        profile["name_evidence"] = evidence

    def _keep_previous_voices(self, segments, plan, *, base_voice: str, lang: str) -> None:
        taken: dict[str, str] = {}
        for profile, _label, idxs, _prev in plan:
            for i in idxs:
                voice = str(segments[i].get("tts_voice_hint") or segments[i].get("voice_id") or "")
                if voice:
                    taken.setdefault(voice, profile["character_id"])
        for profile, _label, idxs, prev in plan:
            if (profile.get("overrides") or {}).get("voice_id"):
                continue
            old = str(prev.get("voice_id") or "")
            if not old or old.startswith("clone:"):
                continue
            if str(prev.get("base_voice") or "") != base_voice or str(prev.get("language") or "") != lang:
                continue
            owner = taken.get(old)
            if owner and owner != profile["character_id"]:
                continue
            for i in idxs:
                seg = segments[i]
                current = str(seg.get("tts_voice_hint") or seg.get("voice_id") or "")
                if current.startswith("clone:") and (seg.get("reference_wav") or seg.get("clone_voice")):
                    continue
                seg["tts_voice_hint"] = old
                seg["voice_id"] = old
            taken[old] = profile["character_id"]

    def _update_tts(self, profile, lines, *, lang: str, base_voice: str) -> None:
        voices = Counter(str(s.get("tts_voice_hint") or s.get("voice_id") or "") for s in lines)
        voices.pop("", None)
        voice = voices.most_common(1)[0][0] if voices else ""
        tts = profile["tts"]
        tts["voice_id"] = voice
        tts["provider"] = provider_for_voice(voice) if voice else ""
        tts["language"] = lang or tts.get("language") or ""
        if base_voice:
            tts["base_voice"] = base_voice

    def apply_overrides(self, segments: list[dict[str, Any]]) -> None:
        for seg in segments:
            profile = self.get(str(seg.get("character_id") or ""))
            if not profile:
                continue
            over = profile.get("overrides") or {}
            if over.get("name"):
                seg["speaker"] = over["name"]
                seg["character"] = over["name"]
                seg["speaker_manual"] = True
            if over.get("role"):
                seg["character_role"] = over["role"]
            presentation = str(over.get("presentation") or "")
            if presentation and presentation != "uncertain":
                seg["gender"] = gender_from_presentation(presentation)
                seg["gender_manual"] = True
            voice = str(over.get("voice_id") or "")
            if voice:
                seg["tts_voice_hint"] = voice
                seg["voice_id"] = voice
                if not voice.startswith("clone:"):
                    seg.pop("reference_wav", None)
                    seg.pop("clone_voice", None)

    # ── after the performance plan ──────────────────────────────────────
    def update_from_plan(self, segments: list[dict[str, Any]], *, source_lang: str = "") -> None:
        by_char: dict[str, list[dict[str, Any]]] = {}
        for seg in segments:
            cid = str(seg.get("character_id") or "")
            if cid:
                by_char.setdefault(cid, []).append(seg)
        for cid, lines in by_char.items():
            profile = self.get(cid)
            if not profile:
                continue
            perfs = [s.get("performance") for s in lines if isinstance(s.get("performance"), dict)]
            if perfs:
                styles = Counter(str(p.get("style") or "neutral") for p in perfs)
                profile["tts"]["emotion"] = styles.most_common(1)[0][0]
                profile["tts"]["intensity"] = round(
                    sum(float(p.get("intensity") or 0) for p in perfs) / len(perfs), 3
                )
            pitches = sorted(
                float((p.get("prosody") or {}).get("pitch_hz") or 0)
                for p in perfs
                if float((p.get("prosody") or {}).get("pitch_hz") or 0) > 0
            )
            vp = profile["voice_profile"]
            if pitches:
                vp["pitch_hz"] = round(pitches[len(pitches) // 2], 1)
                vp["pitch"] = pitch_band(vp["pitch_hz"])
            rate = _source_rate(lines, source_lang)
            if rate:
                vp["speaking_rate"] = rate
            profile["updated_at"] = _now()

    # ── editor ──────────────────────────────────────────────────────────
    def set_override(self, character_id: str, **fields: Any) -> dict[str, Any] | None:
        profile = self.get(character_id)
        if profile is None:
            return None
        over = dict(profile.get("overrides") or {})
        for key in _OVERRIDE_KEYS:
            if key not in fields:
                continue
            value = fields[key]
            if value in (None, ""):
                over.pop(key, None)
            else:
                over[key] = value
        profile["overrides"] = over
        if over.get("name"):
            profile["name"] = over["name"]
            profile["label"] = over["name"]
            if over["name"] not in profile["aliases"]:
                profile["aliases"].append(over["name"])
            profile["confidence"]["character_identity"] = 1.0
            evidence = [e for e in profile.get("name_evidence") or [] if e.get("source") != "editor"]
            evidence.append({"source": "editor", "text": over["name"]})
            profile["name_evidence"] = evidence
        if over.get("presentation"):
            profile["voice_profile"]["presentation"] = over["presentation"]
            profile["voice_profile"]["presentation_confidence"] = 1.0
        if over.get("voice_id"):
            profile["tts"]["voice_id"] = over["voice_id"]
            profile["tts"]["provider"] = provider_for_voice(over["voice_id"])
        if over.get("role"):
            profile["role"] = over["role"]
        profile["updated_at"] = _now()
        return profile

    def override_by_label(self, label: str, **fields: Any) -> dict[str, Any] | None:
        profile = self.find(label=label)
        if profile is None:
            profile = _new_profile(self._new_id())
            profile["label"] = label
            profile["aliases"] = [label]
            self.characters.append(profile)
        return self.set_override(profile["character_id"], **fields)

    def add_name_evidence(self, character_id: str, name: str, *, source: str, text: str = "") -> None:
        """Credits / metadata evidence for a name (``source`` is credits or metadata)."""
        profile = self.get(character_id)
        if profile is None or not name:
            return
        profile.setdefault("name_evidence", []).append({"source": source, "name": name, "text": text[:80]})
        if not (profile.get("overrides") or {}).get("name"):
            profile["name"] = name
            profile["confidence"]["character_identity"] = max(
                float(profile["confidence"].get("character_identity") or 0), 0.7
            )
        profile["updated_at"] = _now()


def _source_rate(lines: list[dict[str, Any]], source_lang: str) -> float:
    """Source speaking pace against a typical pace for that language (1.0 = typical)."""
    from claynext.models.character_intel.performance_planner import _PACE, _seg_times
    from claynext.models.translate_service import TranslateEngine

    pace = _PACE.get(source_lang, 0.0) or (4.0 if str(source_lang).startswith("Chinese") else 3.5)
    rates = []
    for seg in lines:
        start, end = _seg_times(seg)
        if end - start < 0.6:
            continue
        text = str(seg.get("original_text") or seg.get("text") or "")
        try:
            units = TranslateEngine.spoken_units_fast(text, source_lang)
        except Exception:
            continue
        if units > 0:
            rates.append(units / (end - start) / pace)
    if not rates:
        return 0.0
    rates.sort()
    return round(rates[len(rates) // 2], 3)
