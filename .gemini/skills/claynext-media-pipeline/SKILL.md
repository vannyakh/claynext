---
name: claynext-media-pipeline
description: Procedures for debugging and extending audio/video pipelines in Claynext (FFmpeg extraction, Faster-Whisper ASR, Edge-TTS synthesis, subtitle translation, and automated dubbing).
---

# Claynext Media Pipeline & AI Engine Workflows

This skill guides you through interacting with, testing, and debugging the core media and AI pipelines in claynext.

---

## 1. Speech-to-Text (ASR) Pipeline

Claynext uses `faster-whisper` for fast CTranslate2-accelerated transcription.

### Key Class: `ASREngine` ([asr_engine.py](file:///H:/Claynext/src/claynext/core/asr_engine.py))
- **Model Sizes**: `tiny`, `base`, `small`, `medium`, `large-v3`.
- **Supported Formats**: `.mp4`, `.mkv`, `.avi`, `.mov`, `.mp3`, `.wav`, `.flac`, `.m4a`.
- **Device Support**: Auto-detects CUDA (`float16`) or CPU (`int8`).

### Testing ASR Headlessly via Python:
```python
from claynext.core.asr_engine import ASREngine

engine = ASREngine(model_size="tiny", device="cpu")
segments, info = engine.transcribe("path/to/audio.wav")
for s in segments:
    print(f"[{s.start:.2f}s -> {s.end:.2f}s]: {s.text}")
```

### Export Formats:
- SubRip (`.srt`)
- WebVTT (`.vtt`)
- Plain Text (`.txt`)
- JSON (`.json`) with word-level confidence scores.

---

## 2. Text-to-Speech (TTS) Pipeline

Claynext integrates Microsoft Edge TTS neural voices with pitch and speed modulation.

### Key Class: `TTSEngine` ([tts_engine.py](file:///H:/Claynext/src/claynext/core/tts_engine.py))
- **Voices**: 100+ multi-lingual neural voices (e.g. `en-US-AriaNeural`, `en-US-GuyNeural`, `es-ES-AlvaroNeural`, `fr-FR-HenriNeural`).
- **Modifiers**: Rate adjustment (`+0%`, `+20%`, `-10%`), pitch adjustment (`+0Hz`, `+5Hz`).

### Testing TTS Headlessly:
```python
import asyncio
from claynext.core.tts_engine import TTSEngine

engine = TTSEngine()
output_path = "data/outputs/test_tts.mp3"
asyncio.run(engine.synthesize("Hello from Claynext Studio", voice="en-US-AriaNeural", output_file=output_path))
print(f"Generated TTS audio at: {output_path}")
```

---

## 3. Automated Movie Dubbing Pipeline

The AI Movie Dubbing workflow performs an end-to-end multi-step conversion:
1. **Audio Demux**: Extract 16-bit PCM 48kHz stereo WAV from video using FFmpeg.
2. **ASR Timestamp Extraction**: Transcribe original dialogue lines with start and end timestamps.
3. **Translation**: Translate lines into target language while respecting maximum duration constraints.
4. **TTS Speech Synthesis**: Synthesize speech chunks for each line.
5. **Time-Stretching**: If synthesized audio duration differs from original speech window, stretch/compress with FFmpeg `atempo` (clamped between 0.8x and 1.3x).
6. **Timeline Multiplexing & Ducking**: Duck background audio bed (-12dB) during dialogue segments, overlay synthesized speech, and mux back into MP4 container.

### Key CLI Dubbing Plan:
```bash
uv run claynext-dub-plan --help
# Or run tool view directly:
uv run main.py --tool dubbing --no-splash
```

---

## 4. Media Compatibility & Proxy Processor

Qt's `QMediaPlayer` can fail on variable framerates or heavy 4K/8K codecs.
Always route media through [media_compat.py](file:///H:/Claynext/src/claynext/core/media_compat.py):

```python
from claynext.core.media_compat import ready_playback_path, prepare_playback_media

# Check if a Qt-safe cached path exists:
safe_path = ready_playback_path(video_path)

# Or generate proxy in background:
def _on_proxy_ready(proxy_path: str):
    self.media_player.setSource(QUrl.fromLocalFile(proxy_path))
```

- **Audio Normalization**: Transcoded into AAC-LC 44.1kHz stereo in `data/cache/playback/`.
- **Video Proxies**: Transcoded into lightweight 720p H.264 MP4 with fast-start moov atom in `data/cache/proxies/`.
