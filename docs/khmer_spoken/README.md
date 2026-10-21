# Khmer Spoken Language Dataset (KSLD) — Gemini Teacher Milestone

Studio package: `src/claynext/models/khmer_spoken/`  
Data root: `data/khmer_spoken/` (never the project root)  
UI: **Tools → Khmer Spoken Dataset…**

## What this milestone does

End-to-end text dataset workflow:

1. Import ~100 dialogue examples (fixture: `data/khmer_spoken/fixtures/dialogue_100.jsonl`)
2. Generate natural Khmer translation candidates with **Google AI Studio Gemini**
3. Native Khmer human review (approve / reject / edit / gold)
4. Export a versioned gold dataset under `data/khmer_spoken/versions/`
5. Offline translation evaluation (+ optional Gemini-as-judge)
6. Optional Gemini TTS previews (graceful skip if key/model missing)

**Synthetic candidates ≠ gold.** Gold requires `verified_by`, `verified_at`, and `review_status=gold` after human review.

## Platform map (do not conflate)

| Path | What it is | What it is not |
|:---|:---|:---|
| **Google AI Studio / Gemini API** | Teacher: generate Khmer conversational translations, slang/character styles, emotional cues; optional audio-analyze hooks; Gemini TTS *experiments* | Does **not** retrain the base model by uploading a dataset |
| **Google Cloud Vertex AI** | Supervised fine-tuning of *eligible* Gemini text models with labeled data | Separate client, GCP project, ADC/service-account credentials. AI Studio keys **cannot** submit Vertex tune jobs |
| **Local LoRA / QLoRA** | Separate stub entrypoint for open-weight adapters | Not Vertex; not AI Studio |
| **Text SFT** | Improves text generation / translation behaviour | Does **not** train the Gemini TTS *voice* model |
| **Speech / voice training** | `src/claynext/voice_training/` + `data/voice_datasets/` | How to *sound*. KSLD is how to *say* (text). Link only in docs |

Official refs:

- Gemini speech generation: https://ai.google.dev/gemini-api/docs/speech-generation
- Vertex supervised tuning: Google Cloud Vertex AI Gemini fine-tuning docs

## Workflow (prose diagram)

```text
JSONL import / fixture
        │
        ▼
  pending_native_review rows
        │
        ▼
 Gemini AI Studio teacher  ──(candidates, still pending)──► review table
        │                                                      │
        │                                                      ▼
        │                                         human approve / edit / reject
        │                                                      │
        │                                                      ▼
        │                                         gold export → versions/ksld-*/
        │                                                      │
        ├──────────────── offline metrics (+ optional judge) ◄─┘
        │
        └──────────────── optional Gemini TTS preview (WAV)
```

Vertex SFT and local LoRA are **out of band**: enqueue via `TrainingJobManager` (refuses without eligibility / stubs).

## How to run (milestone)

```bash
# Offline tests (no network)
KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=src .venv/bin/python tests/python/test_khmer_spoken.py

# Studio UI (restart Studio after Python/GUI changes)
KMP_DUPLICATE_LIB_OK=TRUE uv run main.py
# Tools → Khmer Spoken Dataset…
```

API key (AI Studio only): configure Gemini keys in Settings → API Keys, or `GEMINI_API_KEY` / `GOOGLE_API_KEY`. Used for candidate generation, optional judge, and TTS preview.

Vertex SFT (later): `GOOGLE_CLOUD_PROJECT` + Application Default Credentials / `GOOGLE_APPLICATION_CREDENTIALS`. The stub refuses without these and never invents a successful tune.

## Cost / quota notes

- Candidate generation and judge calls use the existing `llm_keys` rotating pool and `note_llm_usage` cost ledger (same Gemini free-tier RPM/RPD limits as translate).
- Milestone UI generates at most 20 rows per click by default to limit spend.
- TTS preview tries documented model ids and skips if the model is unsupported on this key/region.

## Package layout

```text
models/khmer_spoken/
  providers/google_gemini_provider.py   # AI Studio teacher
  providers/google_tts_provider.py      # Gemini TTS preview
  datasets/gemini_candidate_generator.py
  datasets/khmer_human_review.py
  training/vertex_tuning_client.py      # stub + eligibility
  training/training_job_manager.py      # Vertex vs local LoRA ledger
  evaluation/khmer_translation_benchmark.py
  tts/gemini_voice_registry.py
  tts/khmer_pronunciation_evaluator.py
```

Prompt skill: `prompts/skills/khmer_spoken_candidates/` (`ksld.gemini_candidates`).

## Link to voice training

When building cinematic speech datasets, keep:

- **KSLD gold text** (`data/khmer_spoken/versions/`) = licensed, reviewed *what to say*
- **Voice datasets** (`data/voice_datasets/`, package `claynext.voice_training`) = consented *how to sound*

Do not treat AI Studio TTS previews as voice-cloning training data.

## Next steps

1. Small Vertex SFT experiment when a project + eligible Gemini 2.5 Flash variant is available.
2. Expand human review UX (multi-select, CSV round-trip).
3. Wire optional Gemini-as-judge toggle in the dialog.
4. Keep local LoRA trainer as a separate milestone on open weights.
