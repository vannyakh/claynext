---
name: release-validation
description: >-
  Validates a Claynext job with the repo's script tests, Cargo, and headless
  Qt smoke. Use at QA or before a release note. Does not invent results or
  deploy.
---

# Release validation

## When to use

Job status is `QA`, or the owner asks if a change is safe to keep.

## Steps

1. Map each acceptance criterion to a command. Skip criteria that need hardware you do not have, and say so.
2. Python suites (pytest is not installed; do not claim pytest passed):

```bash
PYTHONPATH=src .venv/bin/python tests/python/<file>.py
```

Typical files: `test_datasets.py`, `test_llm_gateway.py`, `test_khmer_localization.py`, `test_evaluation.py`, `test_voice_training.py`.

3. `tests/python/test_translate_service.py` imports pytest. Leave it unrun until JOB-009.
4. Rust, only if Rust files changed: `cargo test -p <package>`.
5. GUI smoke, only if GUI files changed: `QT_QPA_PLATFORM=offscreen` steps in `.agents/skills/claynext-dev-workflow/SKILL.md`.
6. Record command, exit code, and a short excerpt in `.agents/reports/`. Redact secrets.

## Do not

- Fabricate a green run.
- Deploy, tag, or push.
- Add pytest as part of validation. That is a separate owner decision (JOB-009).
