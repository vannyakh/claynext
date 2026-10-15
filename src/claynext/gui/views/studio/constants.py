"""Shared tokens for the AI Movie Dubbing workspace."""
from __future__ import annotations

SETTINGS_KEY = "studio_view/dock_state_v18"
LAYOUT_META_KEY = "studio_view/layout_meta_v18"
DUB_ACCENT = "#a855f7"
# Studio shelf (library / script / captions) resize bounds
SHELF_MIN_W = 320
SHELF_MAX_W = 940

# Preview / properties docks
PANEL_MIN_W = 320
PANEL_MAX_W = 640
# Right-dock Inspector (Properties) — keep compact
PROPS_MIN_W = 320
PROPS_MAX_W = 440

SOURCE_LANGS = (
    "Chinese",
    "Auto Detect",
    "English",
    "Vietnamese",
    "Japanese",
    "Korean",
    "Spanish",
    "French",
    "German",
    "Khmer",
    "Thai",
)

VOICE_SAMPLE_FALLBACK = "Hello. This is a preview of the dubbing voice."
VOICE_SAMPLES = {
    "Khmer": "សួស្តី នេះជាសំឡេងសម្រាប់ការបកប្រែ។",
    "English": VOICE_SAMPLE_FALLBACK,
    "Chinese": "你好，这是配音声音的试听。",
    "Thai": "สวัสดี นี่คือตัวอย่างเสียงพากย์",
    "Vietnamese": "Xin chào. Đây là giọng thuyết minh mẫu.",
    "Japanese": "こんにちは。これは声のプレビューです。",
    "Korean": "안녕하세요. 더빙 목소리 미리 듣기입니다.",
    "French": "Bonjour. Ceci est un aperçu de la voix.",
    "Spanish": "Hola. Esta es una muestra de la voz.",
    "German": "Hallo. Dies ist eine Stimmprobe.",
}

