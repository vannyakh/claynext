"""Inline TTS expression tags for dubbing / speech synthesis.

Users can embed bracket or brace cues in dubbed text, e.g.::

    [laugh] I can't believe you did that! [sigh] What a mess.

Tags are kept in the script; at synthesize time they become silence,
short vocalizations, or rate/pitch style shifts for the following speech.
"""
from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

# [laugh] or {sigh} — capture inner token
_TAG_RE = re.compile(r"\[([^\[\]]+)\]|\{([^{}]+)\}")

# UI insert chips (label shown, token written into text)
EXPRESSION_CHIPS: list[tuple[str, str]] = [
    ("laugh", "[laugh]"),
    ("sigh", "[sigh]"),
    ("gasp", "[gasp]"),
    ("pause", "[pause]"),
    ("excited", "[excited]"),
    ("whisper", "[whisper]"),
    ("angry", "[angry]"),
    ("sad", "[sad]"),
    ("shout", "[shout]"),
]

# Normalized tag → behaviour
_TAG_DEFS: dict[str, dict[str, Any]] = {
    "laugh": {"kind": "vocal", "say": "ha ha ha"},
    "laughs": {"kind": "vocal", "say": "ha ha ha"},
    "laughter": {"kind": "vocal", "say": "ha ha ha"},
    "chuckle": {"kind": "vocal", "say": "heh heh"},
    "sigh": {"kind": "vocal", "say": "sigh"},
    "sighs": {"kind": "vocal", "say": "sigh"},
    "gasp": {"kind": "vocal", "say": "ah!"},
    "gasps": {"kind": "vocal", "say": "ah!"},
    "clears throat": {"kind": "vocal", "say": "ahem"},
    "ahem": {"kind": "vocal", "say": "ahem"},
    "cough": {"kind": "vocal", "say": "cough"},
    "hmm": {"kind": "vocal", "say": "hmm"},
    "pause": {"kind": "silence", "ms": 480},
    "break": {"kind": "silence", "ms": 360},
    "silence": {"kind": "silence", "ms": 550},
    "excited": {"kind": "style", "rate": 1.12, "pitch": 5.0},
    "happy": {"kind": "style", "rate": 1.08, "pitch": 4.0},
    "cheerful": {"kind": "style", "rate": 1.08, "pitch": 4.0},
    "angry": {"kind": "style", "rate": 1.10, "pitch": -3.0},
    "sad": {"kind": "style", "rate": 0.90, "pitch": -5.0},
    "whisper": {"kind": "style", "rate": 0.88, "pitch": -6.0},
    "shout": {"kind": "style", "rate": 1.15, "pitch": 7.0},
    "shouts": {"kind": "style", "rate": 1.15, "pitch": 7.0},
    "nervous": {"kind": "style", "rate": 1.14, "pitch": 3.0},
    "calm": {"kind": "style", "rate": 0.94, "pitch": -2.0},
}


@dataclass
class ExprPart:
    kind: str  # speech | vocal | silence | style
    text: str = ""
    ms: int = 0
    rate: float = 1.0
    pitch: float = 0.0


def normalize_tag(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip().lower())


def has_expression_tags(text: str) -> bool:
    return bool(_TAG_RE.search(text or ""))


def strip_expression_tags(text: str) -> str:
    """Remove tags for caption export / plain display."""
    cleaned = _TAG_RE.sub(" ", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_expression_text(text: str) -> list[ExprPart]:
    """Split dubbed text into speakable / silence / style parts."""
    raw = text or ""
    if not raw.strip():
        return []
    from claynext.adapters.ai import get_ai_adapter

    rust_segs = get_ai_adapter().parse_expression_tags(raw)
    if rust_segs:
        parts: list[ExprPart] = []
        for s in rust_segs:
            txt = s.get("text", "")
            rate = float(s.get("rate_multiplier", 1.0))
            pitch = float(s.get("pitch_offset", 0.0))
            pause_sec = float(s.get("pause_after_sec", 0.0))
            if txt:
                parts.append(ExprPart(kind="speech", text=txt, rate=rate, pitch=pitch))
            if pause_sec > 0:
                parts.append(ExprPart(kind="silence", ms=int(pause_sec * 1000)))
        if parts:
            return parts

    parts: list[ExprPart] = []
    style_rate, style_pitch = 1.0, 0.0
    pos = 0
    for match in _TAG_RE.finditer(raw):
        before = raw[pos:match.start()]
        if before.strip():
            parts.append(ExprPart(kind="speech", text=before.strip(), rate=style_rate, pitch=style_pitch))
        elif before and parts and parts[-1].kind == "speech":
            # Keep intentional spacing as a short breath between clauses
            parts.append(ExprPart(kind="silence", ms=80))
        token = normalize_tag(match.group(1) or match.group(2) or "")
        # Allow "pause:600" / "break 800"
        base, ms_override = token, None
        if ":" in token:
            base, _, rest = token.partition(":")
            base = normalize_tag(base)
            try:
                ms_override = int(float(rest.strip()))
            except ValueError:
                ms_override = None
        elif " " in token and token.split()[0] in {"pause", "break", "silence"}:
            bits = token.split()
            base = bits[0]
            try:
                ms_override = int(float(bits[1]))
            except ValueError:
                ms_override = None
        defn = _TAG_DEFS.get(base)
        if not defn:
            # Unknown tag: speak the word so authors hear a cue rather than silence
            parts.append(ExprPart(kind="speech", text=base, rate=style_rate, pitch=style_pitch))
        elif defn["kind"] == "silence":
            parts.append(ExprPart(kind="silence", ms=int(ms_override or defn.get("ms") or 400)))
        elif defn["kind"] == "vocal":
            parts.append(
                ExprPart(
                    kind="vocal",
                    text=str(defn.get("say") or base),
                    rate=style_rate,
                    pitch=style_pitch,
                )
            )
            parts.append(ExprPart(kind="silence", ms=220))
        elif defn["kind"] == "style":
            if parts and parts[-1].kind != "silence":
                parts.append(ExprPart(kind="silence", ms=80))
            style_rate = float(defn.get("rate") or 1.0)
            style_pitch = float(defn.get("pitch") or 0.0)
            # Style applies to following speech; the short silence is the turn delay
        pos = match.end()
    tail = raw[pos:]
    if tail.strip():
        parts.append(ExprPart(kind="speech", text=tail.strip(), rate=style_rate, pitch=style_pitch))
    return parts


def _concat_audio(paths: list[str], output_path: str) -> str:
    from claynext.adapters.ffmpeg_adapter import run_ffmpeg

    if not paths:
        raise RuntimeError("No audio parts to join.")
    if len(paths) == 1:
        src = Path(paths[0])
        dst = Path(output_path)
        if src.resolve() != dst.resolve():
            dst.parent.mkdir(parents=True, exist_ok=True)
            # Normalize container via ffmpeg so mp3/wav mix is fine
            proc = run_ffmpeg(["-y", "-i", str(src), "-ar", "24000", "-ac", "1", str(dst)])
            if proc.returncode != 0 or not dst.is_file():
                raise RuntimeError("Could not write expressive TTS audio.")
        return str(dst)

    list_path = Path(output_path).with_suffix(".concat.txt")
    list_path.parent.mkdir(parents=True, exist_ok=True)
    with list_path.open("w", encoding="utf-8") as fh:
        for path in paths:
            escaped = str(path).replace("'", "'\\''")
            fh.write(f"file '{escaped}'\n")
    proc = run_ffmpeg([
        "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-ar", "24000", "-ac", "1", output_path,
    ])
    try:
        list_path.unlink(missing_ok=True)
    except OSError:
        pass
    if proc.returncode != 0 or not Path(output_path).is_file():
        raise RuntimeError("Could not join expressive TTS parts.")
    return output_path


def synthesize_with_tags(
    text: str,
    voice_id: str,
    output_path: str,
    *,
    speed: float = 1.0,
    pitch: float = 0.0,
    model_name: str = "",
    reference_wav: str = "",
    progress_callback: Callable | None = None,
) -> str:
    """
    Synthesize ``text``, honouring inline ``[tag]`` / ``{tag}`` cues.

    Falls back to plain TTS when no tags are present.
    """
    from claynext.adapters.ffmpeg_adapter import make_silence
    from claynext.models.tts_service import TTSEngine

    raw = (text or "").strip()
    if not raw:
        raise RuntimeError("No text to speak.")

    plain = TTSEngine._synthesize_plain
    if not has_expression_tags(raw):
        return plain(
            raw,
            voice_id,
            output_path,
            speed=speed,
            pitch=pitch,
            model_name=model_name,
            reference_wav=reference_wav,
            progress_callback=progress_callback,
        )

    parts = parse_expression_text(raw)
    if not parts:
        return plain(
            strip_expression_tags(raw) or raw,
            voice_id,
            output_path,
            speed=speed,
            pitch=pitch,
            model_name=model_name,
            reference_wav=reference_wav,
            progress_callback=progress_callback,
        )

    if progress_callback:
        progress_callback(35, "Synthesizing with expression tags…")

    work = Path(tempfile.mkdtemp(prefix="claynext_expr_"))
    clip_paths: list[str] = []
    try:
        for i, part in enumerate(parts):
            clip = str(work / f"part_{i:03d}.wav")
            if part.kind == "silence":
                # Mono 24 kHz to match speech parts for concat.
                from claynext.adapters.ffmpeg_adapter import run_ffmpeg as _ff

                dur = max(0.05, part.ms / 1000.0)
                proc = _ff([
                    "-y", "-f", "lavfi",
                    "-i", f"anullsrc=r=24000:cl=mono:d={dur:.3f}",
                    "-c:a", "pcm_s16le", clip,
                ])
                if proc.returncode != 0 or not Path(clip).is_file():
                    make_silence(clip, dur, rate=24000)
                clip_paths.append(clip)
                continue
            speak = (part.text or "").strip()
            if not speak:
                continue
            part_mp3 = str(work / f"part_{i:03d}.mp3")
            part_speed = max(0.5, min(2.0, speed * (part.rate or 1.0)))
            part_pitch = pitch + float(part.pitch or 0.0)
            plain(
                speak,
                voice_id,
                part_mp3,
                speed=part_speed,
                pitch=part_pitch,
                model_name=model_name,
                reference_wav=reference_wav,
            )
            # Normalize to wav for concat
            from claynext.adapters.ffmpeg_adapter import run_ffmpeg

            proc = run_ffmpeg(["-y", "-i", part_mp3, "-ar", "24000", "-ac", "1", clip])
            if proc.returncode != 0 or not Path(clip).is_file():
                raise RuntimeError("Expression clip failed to render.")
            clip_paths.append(clip)

        if not clip_paths:
            raise RuntimeError("No speakable content after expression tags.")
        return _concat_audio(clip_paths, output_path)
    finally:
        # Best-effort cleanup of temp dir contents
        try:
            for child in work.iterdir():
                child.unlink(missing_ok=True)
            work.rmdir()
        except OSError:
            pass

