---
name: expressive-tts
description: >-
  Fits Khmer TTS and expression into Claynext dubbing. Use for tts_service,
  DubbingEngine, tts_text, or voice inference. Requires consent and a worker
  off the Qt UI thread.
---

# Expressive TTS

## When to use

Changes to `models/tts_service.py`, `tts_expression.py`, `dubbing_service.py`, `voice_clone.py`, or `voice_training/inference/`.

## Steps

1. Read `khmer_localization/tts_normalizer.py` for `tts_text`. Subtitles stay `localized_text`.
2. Duration, speed, and ducking: `get_dubbing_adapter()` (`speech quota`, `align speed`, `duck volume`). Do not recompute them in Python.
3. Synthesis stays in the Python TTS SDK already used by `tts_service.py`.
4. From the GUI, start work with `Worker` / `QThreadPool` (`core/worker.py`). `gui/dialogs/voice_training_dialog.py` is the pattern.
5. Cloned or trained voices need consent and a licence on the source segment.
6. JOB-010 (feed `tts_text` into `DubbingEngine`) is plan-only until that job is `IN_PROGRESS`.

## Do not

- Block the Qt UI thread.
- Add a new TTS app or replace Edge-TTS casually.
- Speak profanity or dialect forms that the linguist has not verified.
