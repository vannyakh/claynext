"""Dialogue Performance Planner: the step between translation and TTS.

For every line it records the style (neutral, happy, sad, angry, fearful,
whispering, shouting, crying, laughing), intensity 0..1, timing targets with
natural pauses, pronunciation hints, and confidence. The translated words are
carried through unchanged.

Rust ``claynext-ai plan-performance`` owns the rules; ``_plan_fallback``
mirrors them when the binary is missing.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claynext.models.character_intel.expression_mapper import STYLES, normalize_style

PLAN_VERSION = 1

_STYLE_PARTS = {
    "neutral": ("neutral", "normal"),
    "happy": ("happy", "normal"),
    "sad": ("sad", "normal"),
    "angry": ("angry", "normal"),
    "fearful": ("fearful", "normal"),
    "whispering": ("neutral", "whispering"),
    "shouting": ("angry", "shouting"),
    "crying": ("sad", "crying"),
    "laughing": ("happy", "laughing"),
}

_CUE_TO_STYLE = {
    "laugh": "laughing", "laughs": "laughing", "laughter": "laughing", "chuckle": "laughing", "laughing": "laughing",
    "whisper": "whispering", "whispers": "whispering", "whispering": "whispering", "aside": "whispering",
    "shout": "shouting", "shouts": "shouting", "shouting": "shouting", "yell": "shouting", "scream": "shouting",
    "angry": "angry", "anger": "angry", "furious": "angry", "rage": "angry",
    "sad": "sad", "sigh": "sad", "sighs": "sad", "grief": "sad", "sorrow": "sad",
    "cry": "crying", "crying": "crying", "sob": "crying", "sobbing": "crying",
    "gasp": "fearful", "fear": "fearful", "fearful": "fearful", "scared": "fearful",
    "afraid": "fearful", "nervous": "fearful", "panic": "fearful",
    "excited": "happy", "happy": "happy", "cheerful": "happy", "joy": "happy", "joyful": "happy",
    "calm": "neutral", "neutral": "neutral", "plain": "neutral",
}

_PACE = {
    "Khmer": 3.6, "Khmer (ភាសាខ្មែរ)": 3.6, "Chinese (Simplified)": 4.0, "Chinese (Traditional)": 4.0,
    "Japanese": 4.2, "Korean": 4.0, "Vietnamese": 3.8, "Thai": 3.8, "English": 3.2,
    "Spanish": 3.4, "French": 3.3, "German": 3.1, "Russian": 3.2,
}
_STYLE_RATE = {
    "shouting": 1.08, "angry": 1.06, "happy": 1.05, "fearful": 1.10, "laughing": 1.0,
    "sad": 0.90, "crying": 0.85, "whispering": 0.92,
}
_PAUSE_FACTOR = {
    "sad": 1.3, "crying": 1.4, "whispering": 1.2, "fearful": 0.9,
    "shouting": 0.7, "angry": 0.8, "happy": 0.9,
}
_INTENSITY_FLOOR = {
    "shouting": 0.65, "angry": 0.6, "crying": 0.6, "laughing": 0.5, "fearful": 0.5,
    "happy": 0.35, "sad": 0.35, "whispering": 0.3,
}
_BASE_INTENSITY = {
    "neutral": 0.3, "whispering": 0.45, "sad": 0.55, "happy": 0.55,
    "fearful": 0.6, "laughing": 0.6, "angry": 0.7, "crying": 0.7, "shouting": 0.8,
}
_CRY_CUES = ("sob", "crying", "cries", "tears", "呜呜", "哭", "流泪", "យំ")
_FEAR_CUES = ("help!", "help me", "no, no", "please don't", "救命", "不要", "害怕", "ជួយផង", "ខ្លាច")
_CLAUSE = set(",，、;；…—។:：")
_LATIN_TARGETS = ("english", "spanish", "french", "german", "vietnamese")


def style_parts(style: str) -> tuple[str, str]:
    return _STYLE_PARTS.get(normalize_style(style), ("neutral", "normal"))


def _seg_text(seg: dict[str, Any]) -> str:
    return str(seg.get("translated_text") or seg.get("text") or "")


def _seg_times(seg: dict[str, Any]) -> tuple[float, float]:
    from claynext.models.dubbing_service import timestamp_to_sec

    start = float(seg.get("start_sec") or timestamp_to_sec(str(seg.get("start", ""))))
    end = float(seg.get("end_sec") or timestamp_to_sec(str(seg.get("end", ""))))
    return start, max(start, end)


def build_request(
    segments: list[dict[str, Any]],
    *,
    lang: str,
    names: list[str] | None = None,
    prosody: list[dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    lines = []
    for index, seg in enumerate(segments):
        start, end = _seg_times(seg)
        perf = seg.get("performance") if isinstance(seg.get("performance"), dict) else {}
        manual = bool(perf.get("manual"))
        expr_source = "manual" if seg.get("expression_manual") else str(seg.get("expression_source") or "")
        row: dict[str, Any] = {
            "index": index,
            "text": _seg_text(seg),
            "source_text": str(seg.get("original_text") or seg.get("text") or ""),
            "start_sec": start,
            "end_sec": end,
            "speaker": str(seg.get("speaker") or ""),
            "expression": str(seg.get("expression") or ""),
            "expression_source": expr_source,
            "intent": str(seg.get("intent") or ""),
            "style": str(perf.get("style") or "") if manual else "",
            "intensity": float(perf["intensity"]) if manual and perf.get("intensity") is not None else None,
            "manual": manual,
        }
        if prosody and index < len(prosody) and prosody[index]:
            row["prosody"] = prosody[index]
        lines.append(row)
    return {"lang": lang or "", "names": list(names or []), "lines": lines}


def plan_lines(request: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    """(line plans, engine) where engine is ``rust`` or ``python``."""
    try:
        from claynext.adapters.dubbing import get_dubbing_adapter

        plan = get_dubbing_adapter().plan_performance(request)
    except Exception:
        plan = None
    if plan and len(plan.get("lines") or []) == len(request.get("lines") or []):
        return list(plan["lines"]), "rust"
    return _plan_fallback(request), "python"


def plan_performance(
    segments: list[dict[str, Any]],
    *,
    lang: str,
    names: list[str] | None = None,
    prosody: list[dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Plan every line and write ``seg["performance"]``. Returns the plan document."""
    request = build_request(segments, lang=lang, names=names, prosody=prosody)
    plans, engine = plan_lines(request)
    rows = []
    for plan in plans:
        index = int(plan.get("index", -1))
        if not 0 <= index < len(segments):
            continue
        seg = segments[index]
        feats = prosody[index] if prosody and index < len(prosody) else None
        apply_line_plan(seg, plan, feats)
        rows.append(plan_row(index, seg))
    return {
        "version": PLAN_VERSION,
        "engine": engine,
        "lang": lang or "",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lines": rows,
    }


def apply_line_plan(seg: dict[str, Any], plan: dict[str, Any], prosody: dict[str, Any] | None = None) -> None:
    style = normalize_style(plan.get("style"))
    perf = {
        "style": style,
        "emotion": str(plan.get("emotion") or style_parts(style)[0]),
        "delivery": str(plan.get("delivery") or style_parts(style)[1]),
        "intensity": round(float(plan.get("intensity") or 0.0), 3),
        "source": str(plan.get("source") or ""),
        "manual": str(plan.get("source") or "") == "manual",
        "target_duration_sec": plan.get("target_duration_sec"),
        "speech_sec": plan.get("speech_sec"),
        "pause_before_sec": plan.get("pause_before_sec"),
        "pause_after_sec": plan.get("pause_after_sec"),
        "internal_pause_sec": plan.get("internal_pause_sec"),
        "units": plan.get("units"),
        "rate_ratio": plan.get("rate_ratio"),
        "tempo_min": plan.get("tempo_min"),
        "tempo_max": plan.get("tempo_max"),
        "pronunciation": list(plan.get("pronunciation") or []),
        "confidence": dict(plan.get("confidence") or {}),
        "evidence": list(plan.get("evidence") or []),
    }
    if prosody:
        perf["prosody"] = {
            key: prosody.get(key)
            for key in ("rms_db", "loudness_rel_db", "pitch_hz", "pitch_range_st", "voiced_ratio", "confidence")
        }
    seg["performance"] = perf


def plan_row(index: int, seg: dict[str, Any]) -> dict[str, Any]:
    perf = dict(seg.get("performance") or {})
    return {
        "index": index,
        "id": seg.get("id", index + 1),
        "character_id": str(seg.get("character_id") or ""),
        "speaker": str(seg.get("speaker") or ""),
        "voice_id": str(seg.get("tts_voice_hint") or seg.get("voice_id") or ""),
        "text": _seg_text(seg),
        "source_text": str(seg.get("original_text") or seg.get("text") or ""),
        **perf,
    }


def set_line_style(seg: dict[str, Any], style: str, intensity: float) -> dict[str, Any]:
    """Editor override for one line. Kept as ``manual`` so a re-plan does not replace it."""
    clean = normalize_style(style)
    emotion, delivery = style_parts(clean)
    perf = dict(seg.get("performance") or {})
    conf = dict(perf.get("confidence") or {})
    conf.update({"emotion": 1.0, "intensity": 1.0})
    perf.update({
        "style": clean,
        "emotion": emotion,
        "delivery": delivery,
        "intensity": round(max(0.0, min(1.0, float(intensity))), 3),
        "source": "manual",
        "manual": True,
        "confidence": conf,
    })
    seg["performance"] = perf
    return perf


def save_plan(plan: dict[str, Any], path: str | Path) -> str:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(dest)
    return str(dest)


def tempo_window(seg: dict[str, Any], min_t: float, max_t: float) -> tuple[float, float]:
    """Narrow the sync-mode tempo range with the planned style's bounds.

    Soft styles cap the speed-up, but never below 1.45x so a line still lands
    near its slot instead of spilling over the next actor.
    """
    perf = seg.get("performance") if isinstance(seg.get("performance"), dict) else None
    if not perf:
        return min_t, max_t
    try:
        plan_max = float(perf.get("tempo_max") or max_t)
    except (TypeError, ValueError):
        return min_t, max_t
    hi = max(min_t, min(max_t, max(plan_max, 1.45)))
    return min_t, hi


# ── Python fallback (mirror of backends/ai-runtime/src/performance.rs) ────────

def _spoken_units(text: str, lang: str) -> int:
    try:
        from claynext.models.translate_service import TranslateEngine

        return max(0, int(TranslateEngine.spoken_units_fast(text, lang)))
    except Exception:
        bare = re.sub(r"\[[^\]]*\]", " ", text or "")
        return len(re.findall(r"[aeiouy]+", bare.lower())) or len(bare.strip())


def _text_style(text: str) -> tuple[str, float, str] | None:
    low = (text or "").lower()
    bangs = text.count("!") + text.count("！")
    latin = [c for c in text if c.isascii() and c.isalpha()]
    upper = sum(1 for c in latin if c.isupper())
    if len(latin) >= 6 and upper * 10 >= len(latin) * 7:
        return "shouting", 0.55, "all-caps line"
    if bangs >= 2:
        return "shouting", 0.55, f"{bangs} exclamation marks"
    if any(c in low for c in _CRY_CUES):
        return "crying", 0.5, "crying cue in text"
    if any(c in low for c in _FEAR_CUES):
        return "fearful", 0.45, "fear cue in text"
    return None


def _cue_conf(source: str) -> float:
    return {"manual": 1.0, "llm": 0.7, "text": 0.6, "": 0.6, "intent": 0.45}.get(source, 0.5)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return s[len(s) // 2]


def _hints(text: str, names: list[str], lang: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: list[str] = []
    for name in names:
        clean = (name or "").strip()
        if len(clean) < 2 or clean in seen:
            continue
        if clean in text:
            seen.append(clean)
            out.append({"text": clean, "kind": "name", "hint": "character name; keep one consistent reading"})
    low_lang = (lang or "").lower()
    non_latin = not (not low_lang or low_lang.startswith(_LATIN_TARGETS))
    for match in re.finditer(r"[0-9]+|[A-Za-z]+|[\u4e00-\u9fff]+", text):
        word = match.group(0)
        if any(s == word or word in s for s in seen):
            continue
        if word[0].isdigit():
            kind, hint = "number", "read the number as words in the target language"
        elif word[0].isascii():
            kind = "foreign"
            hint = "Latin-script word in the line; check the TTS reading" if non_latin and len(word) >= 2 else ""
        else:
            kind = "untranslated"
            hint = "source-script text left in the line" if non_latin and not low_lang.startswith("chinese") else ""
        if hint:
            seen.append(word)
            out.append({"text": word, "kind": kind, "hint": hint})
    return out


def _plan_fallback(request: dict[str, Any]) -> list[dict[str, Any]]:
    lang = str(request.get("lang") or "")
    names = [str(n) for n in request.get("names") or []]
    lines = list(request.get("lines") or [])

    base: dict[str, tuple[float, float]] = {}
    acc: dict[str, tuple[list[float], list[float]]] = {}
    for line in lines:
        p = line.get("prosody") or None
        if not p or float(p.get("confidence") or 0) <= 0 or float(p.get("rms_db", -90)) <= -80:
            continue
        rms, pitch = acc.setdefault(str(line.get("speaker") or ""), ([], []))
        rms.append(float(p["rms_db"]))
        if float(p.get("pitch_hz") or 0) > 0:
            pitch.append(float(p["pitch_hz"]))
    for spk, (rms, pitch) in acc.items():
        base[spk] = (_median(rms) if rms else -30.0, _median(pitch) or 0.0)

    order = sorted(range(len(lines)), key=lambda i: float(lines[i].get("start_sec") or 0))
    prev_end: dict[int, float] = {}
    next_start: dict[int, float] = {}
    for a, b in zip(order, order[1:]):
        next_start[a] = float(lines[b].get("start_sec") or 0)
        prev_end[b] = float(lines[a].get("end_sec") or 0)

    return [
        _plan_line(line, lang, names, base.get(str(line.get("speaker") or "")), prev_end.get(pos), next_start.get(pos))
        for pos, line in enumerate(lines)
    ]


def _plan_line(line, lang, names, base, prev_end, next_start) -> dict[str, Any]:
    evidence: list[str] = []
    text = str(line.get("text") or "")
    source_text = str(line.get("source_text") or "")
    spoken = text if text.strip() else source_text
    p = line.get("prosody") or None
    if p and (float(p.get("confidence") or 0) <= 0 or float(p.get("rms_db", -90)) <= -80):
        p = None
    arousal, rel_loud, rel_pitch = 0.5, 0.0, 0.0
    if p:
        rms_base, pitch_base = base or (float(p["rms_db"]), float(p.get("pitch_hz") or 0))
        rel_loud = float(p["rms_db"]) - rms_base
        ph = float(p.get("pitch_hz") or 0)
        rel_pitch = 12.0 * math.log2(ph / pitch_base) if ph > 0 and pitch_base > 0 else 0.0
        arousal = 0.5 + rel_loud / 12.0 + rel_pitch / 24.0 + (float(p.get("pitch_range_st") or 0) - 4.0) / 20.0
        arousal = max(0.0, min(1.0, arousal))

    expression = str(line.get("expression") or "")
    expr_source = str(line.get("expression_source") or "")
    manual_style = _CUE_TO_STYLE.get(str(line.get("style") or "").strip().lower(), "")
    if line.get("manual") and manual_style:
        evidence.append("set in the editor")
        intensity = line.get("intensity")
        intensity = max(0.0, min(1.0, float(0.5 if intensity is None else intensity)))
        style, emotion_conf, source = manual_style, 1.0, "manual"
    else:
        labelled = _CUE_TO_STYLE.get(expression.strip().lower(), "")
        from_text = _text_style(source_text) or _text_style(spoken)
        if labelled:
            src = expr_source or "text"
            evidence.append(f"{src} cue '{expression}'")
            style, conf, source = labelled, _cue_conf(src), src
        elif from_text:
            evidence.append(from_text[2])
            style, conf, source = from_text[0], from_text[1], "text"
        else:
            style, conf, source = "neutral", 0.5, "default"
        if from_text:
            if from_text[0] == "crying" and style == "sad":
                style, conf = "crying", max(conf, from_text[1])
                evidence.append(from_text[2])
            if from_text[0] == "shouting" and style == "angry":
                style, conf = "shouting", max(conf, from_text[1])
                evidence.append(from_text[2])
        if p:
            if style == "neutral" and rel_loud >= 6.0 and arousal >= 0.75:
                style, conf, source = "shouting", 0.5, "prosody"
                evidence.append(f"{rel_loud:+.1f} dB over this speaker's level")
            elif style == "neutral" and rel_loud <= -9.0 and float(p.get("voiced_ratio") or 0) < 0.35:
                style, conf, source = "whispering", 0.4, "prosody"
                evidence.append(f"{rel_loud:+.1f} dB and little voicing")
            elif style == "angry" and rel_loud >= 6.0:
                style, conf = "shouting", max(conf, 0.6)
                evidence.append(f"angry and {rel_loud:+.1f} dB louder")
            elif style in {"shouting", "angry"} and rel_loud >= 2.0:
                conf = min(conf + 0.15, 0.95)
                evidence.append(f"audio agrees: {rel_loud:+.1f} dB")
            if abs(rel_pitch) >= 3.0:
                evidence.append(f"pitch {rel_pitch:+.1f} st vs speaker")
        base_i = _BASE_INTENSITY.get(style, 0.5)
        intensity = 0.6 * base_i + 0.4 * arousal if p else base_i
        if expression.strip().lower() in {"calm", "sigh"}:
            intensity = min(intensity, 0.35)
        if line.get("intent") == "command" and style == "shouting" and expr_source == "intent":
            intensity = min(intensity, 0.6)
        intensity = max(0.0, min(1.0, max(intensity, _INTENSITY_FLOOR.get(style, 0.0))))
        emotion_conf = conf

    if source == "manual":
        intensity_conf = 1.0
    elif p:
        intensity_conf = 0.6 + 0.3 * float(p.get("confidence") or 0)
    else:
        intensity_conf = 0.45

    start = float(line.get("start_sec") or 0)
    end = float(line.get("end_sec") or 0)
    slot = max(0.15, end - start)
    pause_before = max(0.0, min(2.0, start - prev_end)) if prev_end is not None else 0.0
    pause_after = max(0.0, min(2.0, next_start - end)) if next_start is not None else 0.0
    breaks = sum(1 for c in spoken if c in _CLAUSE)
    internal = min(breaks * 0.15 * _PAUSE_FACTOR.get(style, 1.0), slot * 0.35)
    speech = max(0.1, slot - internal)
    units = _spoken_units(spoken, lang)
    natural = _PACE.get(lang, 3.5) * _STYLE_RATE.get(style, 1.0)
    needed = units / speech
    ratio = needed / natural if natural > 0 and units > 0 else 1.0
    tempo_min, tempo_max = {
        "sad": (0.85, 1.30), "crying": (0.85, 1.30), "whispering": (0.85, 1.30),
        "shouting": (0.90, 1.80), "angry": (0.90, 1.80), "fearful": (0.90, 1.80),
    }.get(style, (0.85, 1.60))
    if units == 0:
        timing_conf = 0.3
    elif ratio <= 1.0:
        timing_conf = max(0.0, min(1.0, 1.0 - (1.0 - ratio) * 0.6))
    else:
        timing_conf = max(0.0, min(1.0, 1.0 - math.log(ratio) / math.log(2)))
    if ratio > tempo_max:
        evidence.append(f"needs {ratio:.2f}x pace; line may run long")
    emotion, delivery = style_parts(style)
    overall = 0.5 * emotion_conf + 0.2 * intensity_conf + 0.3 * timing_conf
    r3 = lambda v: round(float(v), 3)  # noqa: E731
    return {
        "index": int(line.get("index") or 0),
        "style": style,
        "emotion": emotion,
        "delivery": delivery,
        "intensity": r3(intensity),
        "source": source,
        "target_duration_sec": r3(slot),
        "speech_sec": r3(speech),
        "pause_before_sec": r3(pause_before),
        "pause_after_sec": r3(pause_after),
        "internal_pause_sec": r3(internal),
        "units": units,
        "natural_units_per_sec": r3(natural),
        "needed_units_per_sec": r3(needed),
        "rate_ratio": r3(ratio),
        "tempo_min": tempo_min,
        "tempo_max": tempo_max,
        "pronunciation": _hints(spoken, names, lang),
        "confidence": {
            "emotion": r3(emotion_conf),
            "intensity": r3(intensity_conf),
            "timing": r3(timing_conf),
            "overall": r3(overall),
        },
        "evidence": evidence,
    }


__all__ = [
    "STYLES",
    "build_request",
    "plan_lines",
    "plan_performance",
    "apply_line_plan",
    "set_line_style",
    "save_plan",
    "style_parts",
    "tempo_window",
]
