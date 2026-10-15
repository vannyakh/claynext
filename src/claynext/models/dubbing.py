"""AI Dubbing segment and voice models."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DubbingSegmentModel:
    id: int
    start_sec: float
    end_sec: float
    original_text: str = ""
    translated_text: str = ""
    speaker: str = "SPEAKER_00"
    voice_id: str = ""
    audio_path: str = ""
    status: str = "pending"  # pending | synthesized | reviewed


@dataclass
class SpeakerVoiceModel:
    speaker_id: str
    display_name: str
    gender: str = "neutral"
    voice_id: str = ""
    pitch_adjust: float = 0.0
    rate_adjust: float = 1.0

