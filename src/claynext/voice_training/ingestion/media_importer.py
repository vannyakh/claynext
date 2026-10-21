"""Import authorized WAV/MP3/MP4 into a voice dataset workspace."""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from claynext.voice_training.datasets.speech_schema import (
    PerformerConsent,
    RecordingSession,
    SpeechDataset,
)
from claynext.voice_training.ingestion.audio_extractor import extract_audio_wav, probe_duration_sec
from claynext.voice_training.ingestion.rights_validator import validate_session
from claynext.voice_training.paths import VOICE_DATASETS_DIR, VOICE_IMPORT_DIR, ensure_voice_dirs

logger = logging.getLogger("claynext.voice_training.media_importer")

Ping = Callable[[int, str], None] | None


def _source_id_for(path: Path) -> str:
    digest = hashlib.sha1(f"{path.resolve()}|{path.stat().st_size}".encode()).hexdigest()[:12]
    return f"src_{digest}"


def import_media(
    media_path: str | Path,
    *,
    dataset_dir: str | Path | None = None,
    title: str = "",
    owner: str = "",
    license_type: str = "",
    license_doc_path: str = "",
    performers: list[PerformerConsent] | list[dict[str, Any]] | None = None,
    catalog_role: str = "training_source",
    notes: str = "",
    progress_callback: Ping = None,
) -> dict[str, Any]:
    """
    Copy media, extract WAV, write/update ``dataset.json`` with a new session.

    Does not auto-enable training — callers must pass valid consent for
    voice-identity paths (enforced later by the rights gate / trainer).
    """
    ensure_voice_dirs()
    src = Path(media_path)
    if not src.is_file():
        raise FileNotFoundError(f"Media not found: {src}")

    root = Path(dataset_dir) if dataset_dir else VOICE_DATASETS_DIR / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    audio_dir = root / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(2, "Validating import metadata…")

    perf_objs: list[PerformerConsent] = []
    for item in performers or []:
        if isinstance(item, PerformerConsent):
            perf_objs.append(item)
        else:
            perf_objs.append(PerformerConsent.from_dict(dict(item)))

    source_id = _source_id_for(src)
    session_id = f"sess_{uuid.uuid4().hex[:10]}"
    session = RecordingSession(
        source_id=source_id,
        title=title or src.stem,
        owner=owner,
        license_type=license_type,
        license_doc_path=license_doc_path,
        performers=perf_objs,
        imported_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        session_id=session_id,
        media_path=str(src),
        notes=notes,
        catalog_role=catalog_role,
    )

    # Soft check for ingest (warnings only for missing consent on annotate path).
    verdict = validate_session(session, gate="ingest_annotate")
    if progress_callback:
        progress_callback(10, "Extracting audio…")

    staging = VOICE_IMPORT_DIR / session_id
    staging.mkdir(parents=True, exist_ok=True)
    raw_copy = staging / src.name
    shutil.copy2(src, raw_copy)

    wav_out = audio_dir / f"{session_id}.wav"
    extract_audio_wav(raw_copy, wav_out, progress_callback=progress_callback)
    duration = probe_duration_sec(wav_out)

    dataset_path = root / "dataset.json"
    if dataset_path.is_file():
        data = json.loads(dataset_path.read_text(encoding="utf-8"))
        dataset = SpeechDataset.from_dict(data)
    else:
        dataset = SpeechDataset(
            dataset_id=f"ds_{root.name}",
            name=root.name,
            language="km",
            notes="Khmer cinematic voice training workspace",
            language_dataset_ref="claynext.models.datasets / Khmer Spoken Language Dataset",
        )

    session.media_path = str(wav_out)
    dataset.sessions.append(session)
    dataset_path.write_text(
        json.dumps(dataset.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if progress_callback:
        progress_callback(100, "Import complete")

    return {
        "dataset_path": str(dataset_path),
        "session": session.to_dict(),
        "wav_path": str(wav_out),
        "duration_sec": duration,
        "rights": verdict.to_dict(),
    }
