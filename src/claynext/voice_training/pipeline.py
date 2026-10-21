"""
Ingest → extract → segment → annotate orchestration for the Voice Training UI.

Heavy work must be called from a Worker / QThreadPool, never the Qt UI thread.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from claynext.voice_training.annotation.emotion_annotator import normalize_emotion, normalize_style
from claynext.voice_training.annotation.prosody_analyzer import analyze_prosody
from claynext.voice_training.annotation.speaker_diarizer import diarize
from claynext.voice_training.datasets.dataset_builder import (
    assign_splits,
    load_dataset,
    save_dataset,
    upsert_segment,
)
from claynext.voice_training.datasets.speech_schema import SpeechSegment
from claynext.voice_training.ingestion.media_importer import import_media
from claynext.voice_training.preprocessing.audio_quality_filter import score_wav
from claynext.voice_training.preprocessing.speech_segmenter import segment_speech
from claynext.voice_training.preprocessing.vocal_separator import separate_vocals

logger = logging.getLogger("claynext.voice_training.pipeline")

Ping = Callable[[int, str], None] | None


def ingest_and_segment(
    media_path: str | Path,
    *,
    dataset_dir: str | Path,
    title: str = "",
    owner: str = "",
    license_type: str = "",
    license_doc_path: str = "",
    performers: list[dict[str, Any]] | None = None,
    catalog_role: str = "training_source",
    default_speaker: str = "spk_01",
    default_emotion: str = "neutral",
    default_style: str = "spoken",
    isolate_vocals: bool = False,
    progress_callback: Ping = None,
) -> dict[str, Any]:
    """Import media, optionally isolate vocals, VAD-segment, and persist segments."""

    def ping(pct: int, msg: str) -> None:
        if progress_callback:
            progress_callback(pct, msg)

    ping(2, "Importing authorized media…")
    imported = import_media(
        media_path,
        dataset_dir=dataset_dir,
        title=title,
        owner=owner,
        license_type=license_type,
        license_doc_path=license_doc_path,
        performers=performers,
        catalog_role=catalog_role,
        progress_callback=lambda p, m: ping(min(35, 2 + int(p * 0.3)), m),
    )
    wav_path = Path(imported["wav_path"])
    session = imported["session"]
    dataset_path = Path(imported["dataset_path"])

    work_audio = wav_path
    if isolate_vocals:
        ping(40, "Isolating vocals…")
        stems = separate_vocals(wav_path, Path(dataset_dir) / "stems" / session["session_id"])
        if stems.get("vocals"):
            work_audio = Path(str(stems["vocals"]))

    ping(50, "Segmenting speech…")
    turns = segment_speech(work_audio)
    labeled = diarize(work_audio, turns, default_speaker=default_speaker)

    ping(70, "Scoring quality and writing segments…")
    dataset = load_dataset(dataset_path)
    quality = score_wav(work_audio)
    created = 0
    for turn in labeled:
        start = float(turn.get("start") or 0.0)
        end = float(turn.get("end") or start)
        if end <= start:
            continue
        seg_id = f"seg_{uuid.uuid4().hex[:10]}"
        prosody = analyze_prosody(work_audio, start_sec=start, end_sec=end)
        segment = SpeechSegment(
            segment_id=seg_id,
            audio_path=str(work_audio),
            start_sec=start,
            end_sec=end,
            speaker_id=str(turn.get("speaker_id") or default_speaker),
            emotion=normalize_emotion(default_emotion),
            speaking_style=normalize_style(default_style),
            quality_score=float(quality.get("quality_score") or 0.0),
            session_id=session["session_id"],
            source_id=session["source_id"],
            train_split="train",
            prosody=prosody,
        )
        if quality.get("keep", True):
            upsert_segment(dataset, segment)
            created += 1

    assign_splits(dataset, group_by="session")
    save_dataset(dataset, dataset_path)
    ping(100, f"Ready — {created} segments")
    return {
        "dataset_path": str(dataset_path),
        "session": session,
        "segments_added": created,
        "rights": imported.get("rights"),
        "quality": quality,
    }


def update_segment_annotation(
    dataset_path: str | Path,
    segment_id: str,
    *,
    transcript_display: str | None = None,
    transcript_spoken: str | None = None,
    tts_pronunciation: str | None = None,
    speaker_id: str | None = None,
    emotion: str | None = None,
    speaking_style: str | None = None,
    dialect: str | None = None,
    slang_level: float | None = None,
    rudeness_level: float | None = None,
    verified_by: str | None = None,
) -> dict[str, Any]:
    """Persist human annotations for one segment."""
    dataset = load_dataset(dataset_path)
    found = None
    for seg in dataset.segments:
        if seg.segment_id == segment_id:
            found = seg
            break
    if found is None:
        raise KeyError(f"Segment not found: {segment_id}")

    if transcript_display is not None:
        found.transcript_display = transcript_display
    if transcript_spoken is not None:
        found.transcript_spoken = transcript_spoken
    if tts_pronunciation is not None:
        found.tts_pronunciation = tts_pronunciation
    if speaker_id is not None:
        found.speaker_id = speaker_id
    if emotion is not None:
        found.emotion = normalize_emotion(emotion)
    if speaking_style is not None:
        found.speaking_style = normalize_style(speaking_style)
    if dialect is not None:
        found.dialect = dialect
    if slang_level is not None:
        found.slang_level = max(0.0, min(1.0, float(slang_level)))
    if rudeness_level is not None:
        found.rudeness_level = max(0.0, min(1.0, float(rudeness_level)))
    if verified_by:
        found.verified_by = verified_by
        found.verified_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    if found.transcript_spoken and not found.tts_pronunciation:
        found.tts_pronunciation = found.transcript_spoken
    if found.transcript_display and not found.transcript_spoken:
        found.transcript_spoken = found.transcript_display

    save_dataset(dataset, dataset_path)
    return found.to_dict()
