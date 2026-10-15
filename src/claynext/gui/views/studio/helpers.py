"""Subtitle and script export / import for dubbed segments."""
from __future__ import annotations

import json
import re
from pathlib import Path

_TS_ARROW = re.compile(
    r"^\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})"
)
_SPEAKER_PREFIX = re.compile(r"^\[([^\]]+)\]\s*")


def export_segments(path: str, fmt: str, segments: list) -> None:
    if fmt == "srt":
        with open(path, "w", encoding="utf-8") as handle:
            for i, seg in enumerate(segments, 1):
                txt = str(seg.get("translated_text") or seg.get("text") or "").strip()
                speaker = seg.get("speaker")
                prefix = f"[{speaker}] " if speaker else ""
                start = str(seg.get("start", "00:00:00,000")).replace(".", ",")
                end = str(seg.get("end", "00:00:00,000")).replace(".", ",")
                handle.write(f"{i}\n{start} --> {end}\n{prefix}{txt}\n\n")
        return
    if fmt == "vtt":
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("WEBVTT\n\n")
            for i, seg in enumerate(segments, 1):
                txt = str(seg.get("translated_text") or seg.get("text") or "").strip()
                speaker = seg.get("speaker")
                prefix = f"[{speaker}] " if speaker else ""
                start = str(seg.get("start", "00:00:00.000")).replace(",", ".")
                end = str(seg.get("end", "00:00:00.000")).replace(",", ".")
                handle.write(f"{i}\n{start} --> {end}\n{prefix}{txt}\n\n")
        return
    if fmt == "json":
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(segments, handle, ensure_ascii=False, indent=2)
        return
    raise ValueError(f"Unsupported export format: {fmt}")


def _normalize_ts(raw: str, *, srt: bool) -> str:
    text = (raw or "").strip().replace(",", ".")
    parts = text.split(":")
    if len(parts) != 3:
        return "00:00:00,000" if srt else "00:00:00.000"
    h, m, rest = parts
    if "." in rest:
        sec, ms = rest.split(".", 1)
    else:
        sec, ms = rest, "0"
    ms = (ms + "000")[:3]
    stamp = f"{int(h):02d}:{int(m):02d}:{int(sec):02d}"
    return f"{stamp},{ms}" if srt else f"{stamp}.{ms}"


def _cue_to_segment(index: int, start: str, end: str, body: str) -> dict:
    text = "\n".join(line.strip() for line in body.splitlines() if line.strip()).strip()
    speaker = ""
    match = _SPEAKER_PREFIX.match(text)
    if match:
        speaker = match.group(1).strip()
        text = text[match.end():].strip()
    return {
        "id": index,
        "start": start,
        "end": end,
        "speaker": speaker or f"Character {(index - 1) % 2 + 1}",
        "gender": "Unknown",
        "original_text": text,
        "text": text,
        "translated_text": text,
    }


def _parse_cue_file(text: str, *, srt: bool) -> list[dict]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    # Drop WEBVTT header / NOTE blocks for VTT.
    if not srt:
        while lines and (not lines[0].strip() or lines[0].strip().upper().startswith("WEBVTT")
                         or lines[0].strip().upper().startswith("NOTE")):
            lines.pop(0)
    segments: list[dict] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        # Optional cue index / identifier
        match = _TS_ARROW.match(line)
        if match is None and i < n:
            match = _TS_ARROW.match(lines[i].strip())
            if match is not None:
                i += 1
        if match is None:
            continue
        start = _normalize_ts(match.group(1), srt=True)
        end = _normalize_ts(match.group(2), srt=True)
        body_lines: list[str] = []
        while i < n and lines[i].strip():
            body_lines.append(lines[i])
            i += 1
        body = "\n".join(body_lines).strip()
        if not body:
            continue
        segments.append(_cue_to_segment(len(segments) + 1, start, end, body))
    return segments


def import_segments(path: str, fmt: str | None = None) -> list[dict]:
    """Load script lines from SRT, VTT, or JSON (Claynext export shape)."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(path)
    kind = (fmt or file_path.suffix.lstrip(".")).lower()
    if kind == "json":
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("segments") or data.get("lines") or []
        if not isinstance(data, list):
            raise ValueError("JSON script must be a list of lines")
        rows: list[dict] = []
        for i, row in enumerate(data, 1):
            if not isinstance(row, dict):
                continue
            text = str(
                row.get("translated_text") or row.get("original_text") or row.get("text") or ""
            ).strip()
            if not text and not row.get("start"):
                continue
            start = _normalize_ts(str(row.get("start") or "00:00:00,000"), srt=True)
            end = _normalize_ts(str(row.get("end") or start), srt=True)
            speaker = str(row.get("speaker") or f"Character {(i - 1) % 2 + 1}")
            original = str(row.get("original_text") or row.get("text") or text)
            rows.append({
                "id": row.get("id", i),
                "start": start,
                "end": end,
                "speaker": speaker,
                "gender": str(row.get("gender") or "Unknown"),
                "gender_manual": bool(row.get("gender_manual")),
                "original_text": original,
                "text": str(row.get("text") or original),
                "translated_text": str(row.get("translated_text") or text),
                "tts_voice_hint": str(row.get("tts_voice_hint") or row.get("voice_id") or ""),
                "voice_id": str(row.get("voice_id") or row.get("tts_voice_hint") or ""),
            })
        return rows
    if kind in {"srt", "vtt"}:
        return _parse_cue_file(file_path.read_text(encoding="utf-8"), srt=(kind == "srt"))
    raise ValueError(f"Unsupported import format: {kind}")
