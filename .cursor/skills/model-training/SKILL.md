---
name: model-training
description: >-
  Runs Claynext voice-training dry-runs and checks consent. Use for
  voice_training stubs, rights validation, and M4 notes. Hosted fine-tune
  only after the Project Owner unblocks the job.
---

# Model training

## When to use

`src/claynext/voice_training/`, `models/khmer_spoken/training/`, or `docs/voice_training/`.

## Steps

1. Confirm the job is not `BLOCKED`. Hosted fine-tune stays blocked until the owner says to run it.
2. Default trainer path is dry-run: `voice_training/training/tts_trainer.py` (`dry_run=True` when GPU training is unavailable).
3. Reject audio that fails `voice_training/ingestion/rights_validator.py` (licence and consent).
4. Write artifacts under `data/`, not the repo root. Guide: `docs/guides/m4-mac-mini-start.md`.
5. Dialogue text for language comes from `models/datasets/`, not a second unlabeled corpus.
6. Optional check:

```bash
PYTHONPATH=src .venv/bin/python tests/python/test_voice_training.py
```

## Do not

- Call a hosted tuning API, upload weights, or spend money.
- Train on uncleared voices.
- Report a dry-run as a trained model.
