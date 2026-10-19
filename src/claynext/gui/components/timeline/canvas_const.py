"""Shared timeline-canvas constants."""
from __future__ import annotations

import numpy as np

WAVE_PITCH = 3  # px per waveform bar slot (2 px bar + 1 px gap) at every zoom level
TRIM_REACH = 6
TRIM_MIN_MS = 200
# Eye-off keeps clips on the timeline; only dims them (preview/export still skip the track).
HIDDEN_VIEW_OPACITY = 0.34


def _as_envelope(peaks) -> np.ndarray:
    if peaks is None:
        return np.zeros(0, dtype=np.float32)
    return np.clip(np.asarray(peaks, dtype=np.float32), 0.0, 1.0)


def _copy_extra(extra: dict) -> dict:
    out = dict(extra)
    if isinstance(out.get("keys"), list):
        out["keys"] = [list(key) for key in out["keys"]]
    for key in ("overlay", "fx", "transition"):
        if isinstance(out.get(key), dict):
            out[key] = dict(out[key])
    return out

