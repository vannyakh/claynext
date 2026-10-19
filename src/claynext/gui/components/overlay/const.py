"""Overlay kinds and the selection chrome sizes."""
from __future__ import annotations

TEXT_KINDS = {"text", "caption"}
MEDIA_KINDS = {"logo", "image"}
HANDLE_KINDS = TEXT_KINDS | MEDIA_KINDS | {"shape", "mask"}

HANDLE_R = 5
SNAP_PCT = 2
ROTATE_GAP = 18
ROTATE_SNAP = 4.0
TOOL_SIZE = 22.0
TOOL_GAP = 6.0
TOOL_NAMES = ("delete", "eye", "more")
