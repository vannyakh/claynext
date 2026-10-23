---
name: khmer-localization
description: >-
  Extends Claynext Khmer localization, dictionaries, and post-check. Use for
  pronouns, register, slang caps, tts_text, or gold review. Does not invent
  dialect or profanity.
---

# Khmer localization

## When to use

Edits in `src/claynext/models/khmer_localization/`, `src/claynext/prompts/dictionaries/khmer/`, or `docs/khmer-localization/`.

## Steps

1. Read `docs/khmer-localization/DESIGN.md` and `khmer_localization/skill.py`.
2. Change behavior in the existing modules (pronouns, lexicon, post-check, evaluator, `tts_normalizer`). Do not add a second engine.
3. Dictionary files are `pending_native_review`. Add a form only with a source you can cite. Otherwise leave it unverified.
4. Gold: human `reviewer_id`, `reviewed_at`, and a licence. Use `models/datasets/promote.py` rules.
5. Few-shot text must be copied from reviewed dataset records (JOB-005), not written by the model.
6. Optional check, only if you run it:

```bash
PYTHONPATH=src .venv/bin/python tests/python/test_khmer_localization.py
```

## Do not

- Invent dialect names, slang, or profanity.
- Mark synthetic rows gold.
- Wire `tts_text` into `DubbingEngine` unless JOB-010 is the active job.
