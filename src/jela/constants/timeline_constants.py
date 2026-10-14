"""Layout tokens and track presets for the NLE timeline."""
from __future__ import annotations

RULER_H = 26
LANE_W = 190
LANE_COLLAPSED_W = 72
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}

TRACK_MIN_H = 28
TRACK_MAX_H = 120
LANE_MIN_W = 76
LANE_MAX_W = 300
LANE_RATIO = 0.16
CLIP_TEAL = "#2ec4b6"
BG_TL = "#080c14"
BG_LANE = "#0f172a"
BG_TOOLS = "#0d1320"
PLAYHEAD = "#f8fafc"
TRACK_DIVIDER = "#4a6078"
TRACK_PRESETS = (
    ("video", "Cover", 72, CLIP_TEAL, "video"),
    ("voice", "Voice", 40, "#6366f1", "volume"),
    ("audio", "Audio", 40, "#22d3ee", "mic"),
    ("text", "Text", 28, "#f59e0b", "type"),
    ("image", "Image", 36, "#a78bfa", "grid"),
    ("effect", "Effect", 28, "#f97316", "sparkles"),
    ("filter", "Filter", 28, "#c084fc", "filter"),
    ("shape", "Shape", 28, "#34d399", "shapes"),
    ("caption", "Caption", 28, "#fb7185", "log"),
)
PRESET = {k: (name, h, color, icn) for k, name, h, color, icn in TRACK_PRESETS}
OVERLAY_KINDS = frozenset({"text", "caption", "image", "logo", "shape"})
FX_KINDS = frozenset({"effect", "filter"})
