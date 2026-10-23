---
name: repository-audit
description: >-
  Audits the Claynext tree before edits. Maps GUI to models to adapters to
  Rust, and checks .agents/jobs so shipped work is not rebuilt. Use before
  a new job, an architecture change, or when asked for a repo audit.
---

# Repository audit

## When to use

Before the first edit on a job, or when the owner asks what already exists.

## Steps

1. Read `.agents/jobs/completed.yaml` and `docs/khmer-platform/03-backlog-and-acceptance.md`.
2. Confirm the call path in code, not from memory:

```text
src/claynext/gui|cli → models → adapters → adapters/rust_bridge → backends/* | crates/editor-*
```

3. Check these shipped areas before proposing them: `models/datasets/`, `models/llm_gateway/`, `models/llm_chat.py` (`chat_text`), `models/khmer_localization/`, `models/evaluation/runner.py`, `voice_training/`.
4. Note stale docs. `docs/khmer-platform/01-current-architecture.md` predates some of that work.
5. Write findings under `.agents/reports/` only when the job asks for a report. Keep it short. Cite paths.

## Do not

- Invent a top-level `apps/`, `python-ai/`, or `rust/` tree.
- Schedule DONE jobs again.
- Claim tests passed without running them.
- Start product implementation during an audit.
