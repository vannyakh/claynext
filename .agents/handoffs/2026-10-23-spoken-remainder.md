# Handoff

- Job: spoken-draft remainder (not JOB-011, not JOB-020)
- From: model-training
- To: project-owner
- Status: REVIEW
- Date: 2026-10-23

## Scope

Paths touched:

- `src/claynext/models/khmer_spoken/providers/google_gemini_provider.py` (read timeout rolls the key)
- `src/claynext/models/llm_keys.py` (an untried ready key is used before the one cooldown wait)
- `tests/python/test_gemini_key_roll.py`
- `data/khmer_spoken/workspace/candidates.jsonl`
- `data/khmer_spoken/versions/owner-approved-20261023-remainder/` (new)
- `data/outputs/voice_training/2026-10-22-ai-first/resume_remainder.py`
- `data/outputs/voice_training/2026-10-22-ai-first/remainder_run.json`
- `data/outputs/voice_training/2026-10-22-ai-first/ranked_sft.jsonl`

No commit. No push. JOB-011 and JOB-020 stay blocked.

## What changed

Gemini candidates were added for 4 of the 42 empty rows: kp-057, kp-060, kp-061, kp-062. Each has 3 candidates. Jev ranked those 4. Licence stays `unknown`. They were already approved, so approval was not applied again. `approved_text` is still the previously approved stub. The ranked export target is the Jev line.

kp-063 stopped the batch: every Gemini key timed out or was cooling after the pool's one wait. kp-064 through kp-100 were not called. No weights were written. 7B, 8B, and 14B training was not started.

## Evidence

- `PYTHONPATH=src .venv/bin/python data/outputs/voice_training/2026-10-22-ai-first/resume_remainder.py` exited 1. Result: `data/outputs/voice_training/2026-10-22-ai-first/remainder_run.json` (`filled` 4, `jev_ranked` 4, `weights_written` false, `training_started` false, `qlora_14b_started` false, `new_version_count` 100).
- `KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=src .venv/bin/python tests/python/test_gemini_key_roll.py` → `13/13 passed`. That file's 14B check returned `status=refused`, `started=false`, `weights=null`.
- Protected gold hashes unchanged: `owner-approved-20261022`, `owner-approved-20261022-rejected-cleared`, `owner-approved-20261022-ranked`.

`dry_run: true` in the sense that no weight update ran. Consent/licence: `unknown` on all 100 workspace rows. No weights were uploaded.

## Risks

- The other 38 rows still have no Gemini text. Another pass will hit the same key timeouts unless the Gemini pool answers faster.
- Ranked export now has 62 lines. The new gold snapshot still stores the stub as `approved_text` for the four new rows; the Jev line is in candidates and in the ranked file.

## Not done

- kp-063 through kp-100 have no candidates.
- No 7B, 8B, or 14B train. No Vertex. No peft install. No `uv sync`.
