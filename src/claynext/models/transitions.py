"""Video transitions presentation models."""
from __future__ import annotations

DEFAULT_DURATION_MS = 1000
DEFAULT_INTENSITY = 100

TRANSITIONS = (
    ("none", "None", "Direct cut without transition"),
    ("cross_dissolve", "Cross Dissolve", "Smooth crossfade blend"),
    ("fade_black", "Fade to Black", "Fade out then in"),
    ("wipe_left", "Wipe Left", "Linear wipe towards left"),
    ("wipe_right", "Wipe Right", "Linear wipe towards right"),
    ("slide_left", "Slide Left", "Push incoming clip left"),
    ("slide_right", "Slide Right", "Push incoming clip right"),
)

TRANSITION_LABELS = {k: label for k, label, *_ in TRANSITIONS}


def transition_label(key: str) -> str:
    return TRANSITION_LABELS.get(key, key.title())

