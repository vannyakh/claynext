"""TTS pronunciation field helpers (display vs spoken vs TTS-normalized)."""
from __future__ import annotations

from typing import Any


def sync_pronunciation_fields(
    *,
    transcript_display: str = "",
    transcript_spoken: str = "",
    tts_pronunciation: str = "",
) -> dict[str, str]:
    """
    Keep the three transcript layers consistent for annotation UI.

    - display: orthographic / subtitle form
    - spoken: how the actor actually said it (colloquial)
    - tts_pronunciation: form preferred by the TTS engine
    """
    display = (transcript_display or "").strip()
    spoken = (transcript_spoken or display).strip()
    tts = (tts_pronunciation or spoken or display).strip()

    # Soft link to Khmer localization TTS normalizer when present.
    if spoken and not tts_pronunciation:
        try:
            from claynext.models.khmer_localization.tts_normalizer import normalize_for_tts

            tts = normalize_for_tts(spoken) or spoken
        except Exception:
            tts = spoken

    return {
        "transcript_display": display,
        "transcript_spoken": spoken,
        "tts_pronunciation": tts,
    }


def apply_to_segment(segment: dict[str, Any], **fields: str) -> dict[str, Any]:
    synced = sync_pronunciation_fields(
        transcript_display=fields.get("transcript_display", segment.get("transcript_display", "")),
        transcript_spoken=fields.get("transcript_spoken", segment.get("transcript_spoken", "")),
        tts_pronunciation=fields.get("tts_pronunciation", segment.get("tts_pronunciation", "")),
    )
    row = dict(segment)
    row.update(synced)
    return row
