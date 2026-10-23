# Handoff

- Job: local overnight Khmer spoken train (not JOB-011)
- From: model-training
- To: project-owner
- Status: REVIEW
- Date: 2026-10-21

## Scope

Paths touched:

- `data/outputs/voice_training/2026-10-21-overnight/owner_report.json` (new)
- `data/cache/voice_training/checkpoints/khmer_tts_20261021T154407Z/` (test dry-run)
- `data/cache/voice_training/checkpoints/khmer_tts_20261021T154438Z/` (failed real-path attempt, no weights)
- `data/cache/voice_training/checkpoints/khmer_tts_20261021T154503Z/` (dry-run, no weights)
- `data/khmer_spoken/jobs/lora-669cecadf965.json` (refused local LoRA stub)

No source edits. JOB-011 stays BLOCKED. No commit, no push, no Vertex, no hosted API.

## What changed

Owner asked for a local overnight train. The licensed spoken set is not on this machine, and the repo trainer cannot update weights. A rights-gated dry-run was run. No training process was left running.

`dry_run: true`. Owner approval quote was for local training only, not hosted spend. Consent/licence: speech fixture is `internal_test_fixture` with restriction `tests_only`; KSLD v0.1 is absent and documented as unlicensed synthetic drafts; library MP4s have no consent. No weights were uploaded or written.

## Evidence

Commands actually run:

- `KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=src .venv/bin/python tests/python/test_voice_training.py` → `14/14 passed`
- `run_finetune(..., dry_run=True)` → manifest `data/cache/voice_training/checkpoints/khmer_tts_20261021T154503Z/manifest.json`, status `dry_run_complete`, `checkpoint.weights` null
- `run_finetune(..., dry_run=False)` → `RuntimeError: No compatible TTS fine-tuner is wired in this environment. Re-run with dry_run=True.` Manifest `khmer_tts_20261021T154438Z` status `failed`. No weights.
- `TrainingJobManager.enqueue_local_lora` → job `lora-669cecadf965` status `refused`
- `memory_pressure` before the run reported system-wide memory free percentage 69%. `torch`, `TTS`, `peft`, and `mlx` were not installed. `uv sync` was not started. Studio (`uv run main.py`) was already running and was left running.

## Risks

- Experiment ids are second-resolution, so two `run_finetune` calls in the same second share one manifest path. The 15:44:38 dry-run file was overwritten by the failed attempt. The 15:45:03 file is the intact dry-run.
- `export_sft` filters by review status and does not itself drop a reviewed row that lacks `provenance.license`. Gold promotion does refuse a missing licence. Nothing was exported.

## Not done

- No weight update, no checkpoint tensors, no background trainer.
- No SFT export under `data/outputs/datasets/`.
- JOB-011 hosted fine-tune was not started.
