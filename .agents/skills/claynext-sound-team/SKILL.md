---
name: claynext-sound-team
description: >-
  Sound team for Claynext dub jobs. Extract the soundtrack, split vocals from
  effects and music with audio-separator (UVR), and transcribe the vocal stem.
  Use when the user mentions audio-separator, python-audio-separator, UVR,
  vocal isolation, effects bed, stem split, or dubbing from a vocal track.
---

# Claynext Sound Team

Three jobs, in order. Do not skip ahead.

1. **Extract** the soundtrack to 48 kHz stereo WAV.
2. **Split** vocals from effects and music.
3. **Transcribe** the vocal stem, then let the existing dub job speak and mix.

The upstream repo [nomadkaraoke/python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator) is a Python library. It ships no Cursor agents or skills. This skill is the team.

## Call path

```text
DubbingEngine / timeline bed worker
  → stem_separation.separate_movie_stems
  → audio_separator.Separator   (when installed)
  → vocals WAV → ASR (asr_source)
  → instrumental WAV → music/effects bed
```

GUI and workers call `separate_movie_stems` or `ensure_demucs_speech_bed`. They do not import `audio_separator`.

| Role | Function | Result |
|:---|:---|:---|
| Extract + split | `claynext.models.stem_separation.separate_movie_stems` | `bed` (effects + music), `vocals` |
| Dub transcript | `DubbingEngine` uses `vocals_path or clean_audio or full_wav` as `asr_source` | lines timed to the vocal stem |
| Bed only | `ensure_speech_bed` | instrumental if a neural backend exists, otherwise the FFmpeg center-duck bed |

Cache stems under `CACHE_DIR/stems/`. Model weights go to `data/models/audio-separator/`, never the project root.

## Backend order

`backend_available()` picks the first one that imports:

1. `mlx` — Demucs MLX, Apple Silicon only
2. `torch` — Demucs
3. `separator` — UVR model `UVR-MDX-NET-Inst_HQ_3.onnx` (Instrumental + Vocals)
4. none — FFmpeg mid-side bed, and ASR hears the full mix

## Install

Do not add `audio-separator` to `pyproject.toml` extras yet.

- This Intel Mac cannot install it. PyTorch has no `macosx_*_x86_64` wheel, and `audio-separator` requires PyTorch.
- On Apple Silicon the current release wants PyTorch 2.13 or newer. The Demucs extra pins `torch==2.8.0`, so one environment cannot hold both.

Until that pin can move, `separator_available()` stays false and the FFmpeg bed remains the split. Transcription uses the full soundtrack. The first successful split should download `UVR-MDX-NET-Inst_HQ_3.onnx` into `data/models/audio-separator/`.

## Rules

- Run the split inside the existing worker. Never on the Qt thread.
- Keep the vocal file for ASR and the instrumental file for the mix bed. Do not transcribe the full mix when a vocal stem exists.
- Do not vendor the GitHub tree into this repo. The dependency is the `audio-separator` extra in `pyproject.toml`.
- If `separator_available()` is false, leave the FFmpeg fallback in place. Do not raise.
