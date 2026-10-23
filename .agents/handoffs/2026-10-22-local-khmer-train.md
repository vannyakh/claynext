# Handoff

- Job: local Khmer spoken train continuation (not JOB-011)
- From: model-training
- To: project-owner
- Status: REVIEW
- Date: 2026-10-22

## Scope

Paths touched:

- `data/outputs/voice_training/2026-10-22-continue/owner_report.json` (new)
- `.agents/handoffs/2026-10-22-local-khmer-train.md` (new)

No source edits. JOB-011 stays BLOCKED. No commit, no push, no Vertex, no hosted API.

## What changed

Owner approved continuing local training and dataset preparation. Torch 2.8.0 is now installed, and the local Gemini key pool has keys, but there are still no spoken rows to train or to attach candidates to. No weights were written. No training process was left running.

`dry_run: true` for this session in the sense that no weight update ran. No new dry-run manifest was written. Owner approval quote: "This is approval to continue LOCAL training and dataset preparation. It is NOT approval for paid/Vertex/hosted fine-tune, deploy, commit, or push."

Consent/licence: speech fixture remains `internal_test_fixture` with restriction `tests_only` (2 segments, 1.1 s nominal, not used). KSLD v0.1 is still absent. `data/datasets/` has 0 files. Library MP4s were not ingested. No weights were uploaded.

## Evidence

Commands actually run:

- `KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=src .venv/bin/python` importing `trainer_capability()` → `torch true`, `coqui_tts false`, `can_gpu_train false`, `recommended_mode dry_run`. torch 2.8.0, torchaudio 2.8.0, omnivoice 0.2.1 import. `TTS`, `peft`, and `mlx_lm` do not import.
- `memory_pressure` → system-wide memory free percentage 73%. Studio `uv run main.py` pids 2514 and 2515 were left running (about 0.1% CPU at the sample).
- Disk inventory: `data/datasets/` empty; `data/voice_datasets/` empty; only Khmer spoken file is `data/khmer_spoken/jobs/lora-669cecadf965.json` status `refused`. `dialogue_100.jsonl` missing. Documented KSLD path missing. `mdfind` / `find` found no `dialogues.jsonl`.
- Gemini teacher `available()` is true via the local key pool (4 enabled gemini keys). Env `GEMINI_API_KEY` and `GOOGLE_API_KEY` are unset. No secret was printed. `generate_candidates_batch` was not called because there are zero source rows.
- Previous dry-run manifest `data/cache/voice_training/checkpoints/khmer_tts_20261021T154503Z/manifest.json` still has `checkpoint.weights` null. Not rewritten.

Rights tests were not re-run. Voice-training code was not changed. The overnight 14/14 result is not a new measurement.

## Risks

- Importing `khmer_spoken.paths` creates empty `fixtures/`, `workspace/`, `versions/`, `evals/`, and `tts_previews/` directories. They hold no rows.
- The rights gate does not itself reject `restrictions: tests_only`. The fixture was refused because the owner instruction, the fixture notes, and the 1.1 s duration say it is not a training set. The gate was not weakened.
- OmniVoice's installed package contains a full Accelerate trainer. Claynext does not call it. Starting it on this 16 GB machine while Studio is open would be a new stack and still has no licensed audio.

## Not done

- No weight update, no new checkpoint, no background trainer.
- No Gemini candidate file under `data/khmer_spoken/` or `data/datasets/`.
- No SFT export.
- JOB-011 hosted fine-tune was not started.
