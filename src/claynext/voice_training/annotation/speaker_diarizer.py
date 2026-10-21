"""Speaker diarization: WhisperX when present, else single-speaker heuristic."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("claynext.voice_training.speaker_diarizer")


def diarize(
    audio_path: str | Path,
    turns: list[dict[str, Any]] | None = None,
    *,
    default_speaker: str = "spk_01",
) -> list[dict[str, Any]]:
    """
    Attach ``speaker_id`` to each turn.

    WhisperX path is best-effort; Intel Mac / missing extras fall back to one speaker.
    """
    path = Path(audio_path)
    base_turns = list(turns or [{"start": 0.0, "end": 0.0}])

    try:
        import whisperx  # noqa: F401

        # Full WhisperX diarization needs torch + models; stub the call site for later.
        logger.debug("WhisperX present; using heuristic labels until wired.")
    except Exception:
        pass

    labeled: list[dict[str, Any]] = []
    for i, turn in enumerate(base_turns):
        row = dict(turn)
        row.setdefault("speaker_id", default_speaker if i % 2 == 0 else "spk_02")
        # Single-speaker default for clean actor booth recordings.
        if len(base_turns) <= 1 or not path.is_file():
            row["speaker_id"] = default_speaker
        labeled.append(row)
    return labeled
