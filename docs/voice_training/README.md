# Khmer Cinematic Voice Training

Prototype scaffolding for **licensed speech datasets** and expressive TTS training prep inside Claynext Studio.

## Rights policy (non-negotiable)

- **Buying or streaming a movie does not grant AI training or voice-cloning rights.**
- Voice-identity training / cloning requires:
  1. **Source licensing metadata** (`owner`, `license_type`, `license_doc_path`)
  2. **Performer consent** with `consent_id`, `consent_doc_path`, `permitted_uses`, `restrictions`, `expires_at`, `revocable`
- `permitted_uses` must include `voice_model_training` and/or `tts_synthesis` before the trainer will run.
- Recognizable **voice cloning** additionally requires explicit `voice_cloning` in `permitted_uses`.
- Commercial catalogs (TVB Khmer, KhDiamon, etc.) are **`catalog_candidate` only** until rights are documented. Do not auto-clone performers from movie/TV stems.
- Prefer **clean, isolated, consented actor booth recordings** over noisy movie stems.

The rights gate lives in `src/claynext/voice_training/ingestion/rights_validator.py` and is enforced by `training.tts_trainer.run_finetune`.

## Language dataset vs speech dataset

| Dataset | Question it answers | Location |
|:---|:---|:---|
| Khmer Spoken Language / dialogue dataset | **What** to say (text, pronouns, slang) | `claynext.models.datasets`, localization packages |
| Voice / speech audio dataset | **How** it should sound (waveform, speaker, emotion) | `data/voice_datasets/`, `claynext.voice_training` |

Link them with `SpeechDataset.language_dataset_ref` — do not mix text SFT rows into speech JSON.

## How to add consented actors (recommended start)

1. Recruit **~5 consenting actors** (diverse age/gender presentation).
2. Record clean booth audio for each emotion: **neutral, angry, sad, romantic, comedy** (plus optional excited/fearful).
3. Store signed consent PDFs under the dataset `docs/` folder; never commit secrets.
4. Fill a session with:
   - `owner`, `license_type`, `license_doc_path`
   - performers[{`name`, `consent_id`, `consent_doc_path`, `permitted_uses`: [`voice_model_training`, `tts_synthesis`], `restrictions`, `expires_at`, `revocable`}]
5. Import via **Tools → Khmer Voice Training…** (or `voice_training.pipeline.ingest_and_segment`).
6. Human-review transcripts; annotate speaker + emotion + speaking style.
7. Run **evaluation harness**, then **dry-run fine-tune** (Intel Mac default).

Synthetic / character voices from properly licensed data are preferred when cloning recognizable people is not authorized.

## Studio UI

**Tools → Khmer Voice Training…**

- Import authorized WAV/MP3/MP4 (FFmpeg via `get_ffmpeg_adapter` / `demux_wav`)
- Dataset segment table + transcript editor
- Speaker / emotion / slang controls (Cyber Dark)
- Dry-run training + offline evaluation
- Progress via `Worker` / `QThreadPool` (UI never blocked)

Restart Studio after pulling these changes.

## Package map

```text
src/claynext/voice_training/
  ingestion/       media_importer, audio_extractor, rights_validator
  preprocessing/   vocal_separator, noise_reducer, speech_segmenter, audio_quality_filter
  annotation/      khmer_transcriber, speaker_diarizer, emotion_annotator, prosody_analyzer, …
  datasets/        speech_schema, dataset_builder, dataset_validator
  training/        tts_trainer (dry-run), speaker_adapter, emotion_adapter, checkpoints
  evaluation/      intelligibility, naturalness, speaker_consistency, harness
  inference/       expressive_tts stubs, voice_registry
  pipeline.py      ingest → segment → annotate
```

Datasets: `data/voice_datasets/`  
Cache / manifests: `data/cache/voice_training/`  
Demo fixture: `data/voice_datasets/demo_consented/` and `tests/fixtures/khmer_speech/`

## Intel Mac behavior

| Path | Behavior |
|:---|:---|
| Import / extract / VAD segment / annotate / evaluate | Runs offline (FFmpeg adapters + stubs) |
| Demucs vocal isolation | Only if already installed; else FFmpeg mid-side / passthrough |
| WhisperX diarization | Heuristic fallback when missing |
| TTS fine-tune | **Dry-run by default** — writes checkpoint **manifest**, no GPU training |
| Newer TTS trainers | Likely **not installable** (torch 2.2.2 / numpy 1.26.4 pin; no Intel Mac wheels for newer torch) |

Do **not** run `uv sync` / `pip install` to “fix” training on this machine for milestone 1.

## Tests

```bash
KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=src .venv/bin/python tests/python/test_voice_training.py
```

Covers rights gate, schema round-trip, validator / split leakage, fixture evaluation, and dry-run trainer manifest.

## Next milestones

1. Wire real ASR draft into the review UI; batch verify workflows.
2. Prosody via `claynext-ai` when `analyze-prosody` is exposed on `AiAdapter`.
3. Compatible trainer backend on Apple Silicon / Linux GPU hosts (still rights-gated).
4. Speaker embedding consistency metrics; listening MOS panel.
5. Export adapters for synthetic character voices into Studio TTS presets.
