"""Speech audio dataset schema, builder, and validator."""
from claynext.voice_training.datasets.dataset_builder import (
    assign_splits,
    load_dataset,
    save_dataset,
)
from claynext.voice_training.datasets.dataset_validator import validate_dataset
from claynext.voice_training.datasets.speech_schema import (
    PerformerConsent,
    RecordingSession,
    SpeechDataset,
    SpeechSegment,
)

__all__ = [
    "PerformerConsent",
    "RecordingSession",
    "SpeechDataset",
    "SpeechSegment",
    "assign_splits",
    "load_dataset",
    "save_dataset",
    "validate_dataset",
]
