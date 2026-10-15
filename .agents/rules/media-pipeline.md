# Rule: Media Pipeline & AI Engine Integration

## 1. FFmpeg Binary Resolution
Never invoke `subprocess.run(["ffmpeg", ...])` directly. Always resolve the FFmpeg executable dynamically via `imageio_ffmpeg` with fallback:

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"
```

## 2. Media Compatibility for Qt Playback
Qt's `QMediaPlayer` can fail or stutter on non-standard video/audio formats (variable frame rate, HE-AACv2, 10-bit color, high-bitrate 4K/8K).
- Always use [media_compat.py](file:///Users/vannya/Desktop/MinJ/src/claynext/core/media_compat.py):
  - `ready_playback_path(media_path)` checks for a pre-rendered compliant proxy or audio stream.
  - Generates lightweight 720p H.264 MP4 proxies (`PROXY_DIR`) or normalized AAC-LC 44.1kHz audio (`PLAYBACK_DIR`).
  - Cache files are named using SHA1 hashes of `(file_path, mtime, size)`.

## 3. Engine Specific Guidelines
- **ASR (Faster-Whisper)**:
  - Cache downloaded Whisper weights in `data/models/whisper/`.
  - Check device availability (`cuda` vs `cpu`) with `minj.core.sysinfo`.
  - Always support word-level timestamps and multi-format subtitle exports (`.srt`, `.vtt`, `.txt`, `.json`).
- **TTS (Edge TTS)**:
  - Use `edge_tts.Communicate(text, voice, rate=..., pitch=...)`.
  - Ensure temp audio files are generated with unique IDs or hashes in `data/cache/tts/` and cleaned up or moved to output on demand.
- **Dubbing Pipeline**:
  - Maintain timing alignment: when synthesis duration differs from original speech segment duration, utilize FFmpeg audio time-stretching (`atempo` filter) or duck the original audio bed.
  - Save project state using `DubbingProject` / `dub_project.py`.
- **OCR (EasyOCR)**:
  - Extract frames at specified timestamps using FFmpeg snapshot extraction.
  - Return bounding box coordinates normalized for display on `OverlayCanvas` ([overlay_canvas.py](file:///Users/vannya/Desktop/MinJ/src/claynext/gui/components/overlay_canvas.py)).
