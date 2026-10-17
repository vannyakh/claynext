"""
Character gender detection and gender-matched TTS voice assignment for dubbing.

Auto-detects Male / Female / Unknown from speaker labels and dialogue cues,
then maps each character to the best available TTS voice of that gender.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

GENDERS = ("Female", "Male", "Unknown")

_FEMALE_HINTS = (
    "female", "woman", "girl", "lady", "she", "her", "hers", "mrs", "miss", "ms",
    "mother", "mom", "mum", "wife", "daughter", "sister", "aunt", "grandma",
    "sreymom", "hoaimy", "ava", "nanami", "sunhi", "xiaoxiao", "bella", "luna",
    "rosie", "kiki", "她", "小姐", "女士", "妈妈", "姐姐", "妹妹", "娘",
)
_MALE_HINTS = (
    "male", "man", "boy", "gentleman", "he", "him", "his", "mr", "sir",
    "father", "dad", "husband", "son", "brother", "uncle", "grandpa",
    "piseth", "andrew", "namminh", "jasper", "bruno", "hugo", "leo",
    "他", "先生", "爸爸", "哥哥", "弟弟", "爷",
)


def normalize_gender(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw or raw in {"unknown", "?", "n/a", "na", "other"}:
        return "Unknown"
    if raw.startswith("f") or raw in {"woman", "girl", "female"}:
        return "Female"
    if raw.startswith("m") or raw in {"man", "boy", "male"}:
        return "Male"
    return "Unknown"


def voice_entry_gender(voice: dict[str, Any] | str) -> str:
    if isinstance(voice, str):
        blob = voice.lower()
    else:
        explicit = normalize_gender(voice.get("gender"))
        if explicit != "Unknown":
            return explicit
        blob = f"{voice.get('name', '')} {voice.get('id', '')} {voice.get('alias', '')}".lower()
    if "female" in blob or "woman" in blob:
        return "Female"
    if "male" in blob or " man" in blob or blob.endswith(" man"):
        return "Male"
    return "Unknown"


def infer_gender_from_text(text: str) -> str:
    """Lightweight pronoun / kinship cues from dialogue (source or dub)."""
    blob = f" {str(text or '').lower()} "
    female = sum(1 for hint in _FEMALE_HINTS if f" {hint} " in blob or hint in blob)
    male = sum(1 for hint in _MALE_HINTS if f" {hint} " in blob or hint in blob)
    # Prefer whole-word-ish English pronouns.
    for token, gender in ((" she ", "Female"), (" her ", "Female"), (" he ", "Male"), (" him ", "Male")):
        if token in blob:
            return gender
    if "她" in text:
        return "Female"
    if "他" in text and "她" not in text:
        return "Male"
    if female > male and female > 0:
        return "Female"
    if male > female and male > 0:
        return "Male"
    return "Unknown"


def infer_gender_from_speaker(speaker: str) -> str:
    name = str(speaker or "").strip()
    low = name.lower()
    if any(h in low for h in ("female", "woman", "girl", "lady", "sreymom", "ava")):
        return "Female"
    if any(h in low for h in ("male", "man", "boy", "piseth", "andrew")):
        return "Male"
    # WhisperX / pyannote SPEAKER_00 / SPEAKER_01 — no reliable gender; leave Unknown.
    return "Unknown"


def detect_segment_gender(seg: dict[str, Any], *, honor_manual: bool = True) -> str:
    """Best-effort gender for one line (manual → audio model → text cues)."""
    if honor_manual and seg.get("gender_manual"):
        return normalize_gender(seg.get("gender"))
    existing = normalize_gender(seg.get("gender"))
    if existing != "Unknown" and seg.get("gender_manual"):
        return existing
    # Wav2Vec2 Common-Voice gender classifier (ASR analysis).
    audio_g = normalize_gender(seg.get("audio_gender"))
    if audio_g != "Unknown":
        return audio_g
    if existing != "Unknown" and seg.get("gender_source") == "audio":
        return existing
    speaker_g = infer_gender_from_speaker(str(seg.get("speaker") or ""))
    if speaker_g != "Unknown":
        return speaker_g
    text = " ".join(
        part for part in (
            str(seg.get("original_text") or ""),
            str(seg.get("text") or ""),
            str(seg.get("translated_text") or ""),
        ) if part
    )
    text_g = infer_gender_from_text(text)
    if text_g != "Unknown":
        return text_g
    if existing != "Unknown":
        return existing
    return "Unknown"


def character_gender_map(segments: list[dict[str, Any]]) -> dict[str, str]:
    """Majority gender per character name."""
    votes: dict[str, Counter[str]] = {}
    for seg in segments:
        name = str(seg.get("speaker") or "").strip() or "Character 1"
        g = detect_segment_gender(seg)
        votes.setdefault(name, Counter())[g] += 1
    out: dict[str, str] = {}
    for name, counter in votes.items():
        # Ignore Unknown ties unless that is all we have.
        ranked = [g for g, _ in counter.most_common() if g != "Unknown"]
        out[name] = ranked[0] if ranked else "Unknown"
    return out


def _catalog_voices(lang: str = "") -> list[dict[str, Any]]:
    from claynext.models.tts_service import TTSEngine

    voices = list(TTSEngine.VOICE_PRESETS)
    if lang:
        matched = [v for v in voices if str(v.get("lang") or "") == lang]
        if matched:
            return matched
    return voices


def _lookup_voice_gender(voice_id: str) -> str:
    from claynext.models.tts_service import TTSEngine

    for voice in TTSEngine.VOICE_PRESETS:
        if voice.get("id") == voice_id:
            return voice_entry_gender(voice)
    return voice_entry_gender(voice_id)


def voice_display_name(voice_id: str) -> str:
    """Short cast name from a TTS voice id (e.g. Sreymom, Bella, Andrew)."""
    from claynext.models.tts_service import TTSEngine

    return TTSEngine.voice_label(voice_id)


def voices_for_lang(lang: str = "") -> list[dict[str, Any]]:
    """TTS presets for a language, each with ``id``, ``label``, ``gender``."""
    from claynext.models.tts_service import TTSEngine

    out: list[dict[str, Any]] = []
    for voice in TTSEngine.list_voices(lang or None):
        out.append({
            "id": voice["id"],
            "label": voice["name"],
            "gender": voice.get("gender") or voice_entry_gender(voice),
            "name": voice["name"],
            "tag": voice.get("tag") or "",
            "lang": voice.get("lang") or "",
        })
    return out


def _unique_cast_name(base: str, used: set[str]) -> str:
    name = (base or "Voice").strip() or "Voice"
    if name not in used:
        used.add(name)
        return name
    n = 2
    while f"{name} {n}" in used:
        n += 1
    label = f"{name} {n}"
    used.add(label)
    return label


def pick_voice_for_gender(
    gender: str,
    *,
    primary: str = "",
    secondary: str = "",
    lang: str = "",
    used: set[str] | None = None,
) -> str:
    """
    Choose a TTS voice id matching ``gender``.

    Prefers primary/secondary when their gender matches, then other catalog
    voices for the target language. Rotates away from ``used`` when possible.
    """
    target = normalize_gender(gender)
    used = used or set()
    catalog = _catalog_voices(lang)

    preferred: list[str] = []
    for vid in (primary, secondary):
        if vid and _lookup_voice_gender(vid) == target:
            preferred.append(vid)
    for voice in catalog:
        vid = str(voice.get("id") or "")
        if not vid or vid in preferred:
            continue
        if voice_entry_gender(voice) == target:
            preferred.append(vid)

    if target == "Unknown":
        for vid in (primary, secondary):
            if vid and vid not in preferred:
                preferred.append(vid)
        for voice in catalog:
            vid = str(voice.get("id") or "")
            if vid and vid not in preferred:
                preferred.append(vid)

    if not preferred:
        return primary or secondary or ""

    for vid in preferred:
        if vid not in used:
            return vid
    return preferred[0]


def assign_gender_and_voices(
    segments: list[dict[str, Any]],
    *,
    primary_voice: str,
    secondary_voice: str = "",
    lang: str = "",
    force_redetect: bool = False,
) -> list[dict[str, Any]]:
    """
    Fill ``gender``, ``tts_voice_hint``, and ``voice_id`` per line.

    Distinct characters share a stable voice; different characters of the same
    gender rotate through available voices when the catalog allows.
    """
    if not segments:
        return []

    # Detect / refresh gender on lines (keep manual overrides).
    for seg in segments:
        if seg.get("gender_manual"):
            seg["gender"] = normalize_gender(seg.get("gender"))
            continue
        if force_redetect:
            seg.pop("gender", None)
        seg["gender"] = detect_segment_gender(seg, honor_manual=False)

    char_gender = character_gender_map(segments)
    # If still Unknown, alternate Female/Male by character order for casting.
    order: list[str] = []
    for seg in segments:
        name = str(seg.get("speaker") or "").strip() or "Character 1"
        if name not in order:
            order.append(name)
    for idx, name in enumerate(order):
        if char_gender.get(name, "Unknown") == "Unknown":
            char_gender[name] = "Female" if idx % 2 == 0 else "Male"

    # Assign one voice per character, rotating within gender.
    used_voices: set[str] = set()
    char_voice: dict[str, str] = {}
    for name in order:
        g = char_gender[name]
        voice = pick_voice_for_gender(
            g,
            primary=primary_voice,
            secondary=secondary_voice or primary_voice,
            lang=lang,
            used=used_voices,
        )
        if not voice:
            voice = primary_voice if g != "Male" else (secondary_voice or primary_voice)
        char_voice[name] = voice
        if voice:
            used_voices.add(voice)

    # Rename cast to TTS voice names (Sreymom, Piseth, …) instead of Character N.
    used_labels: set[str] = set()
    rename: dict[str, str] = {}
    for name in order:
        voice = char_voice.get(name) or primary_voice
        # Keep a custom name if the user already set a non-generic speaker.
        generic = (
            not name
            or name.startswith("Character ")
            or name.startswith("SPEAKER_")
            or name in {"UNKNOWN_SPEAKER", "Unknown", "Speaker 1", "Speaker 2"}
        )
        if generic:
            rename[name] = _unique_cast_name(voice_display_name(voice), used_labels)
        else:
            rename[name] = _unique_cast_name(name, used_labels)

    for seg in segments:
        old = str(seg.get("speaker") or "").strip() or "Character 1"
        name = rename.get(old, old)
        g = char_gender.get(old, "Unknown")
        if not seg.get("gender_manual"):
            seg["gender"] = g
        voice = char_voice.get(old) or primary_voice
        seg["speaker"] = name
        seg["tts_voice_hint"] = voice
        seg["voice_id"] = voice

    return segments


def apply_manual_gender(
    segments: list[dict[str, Any]],
    rows: list[int],
    gender: str,
    *,
    primary_voice: str,
    secondary_voice: str = "",
    lang: str = "",
    apply_to_character: bool = True,
) -> None:
    """Set gender manually on rows (and optionally whole character), then refresh voices."""
    target = normalize_gender(gender)
    names: set[str] = set()
    for row in rows:
        if not (0 <= row < len(segments)):
            continue
        seg = segments[row]
        seg["gender"] = target
        seg["gender_manual"] = True
        names.add(str(seg.get("speaker") or "").strip() or "Character 1")

    if apply_to_character and names:
        for seg in segments:
            name = str(seg.get("speaker") or "").strip() or "Character 1"
            if name in names:
                seg["gender"] = target
                seg["gender_manual"] = True

    assign_gender_and_voices(
        segments,
        primary_voice=primary_voice,
        secondary_voice=secondary_voice,
        lang=lang,
        force_redetect=False,
    )

