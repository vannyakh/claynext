# Handoff

- Job: JOB-026
- From: model-training
- To: cto
- Status: REVIEW
- Date: 2026-10-23

## Scope

Paths touched:

- src/claynext/models/benchmarks/spoken_split.py
- src/claynext/models/benchmarks/__init__.py
- tests/python/test_llm_benchmark.py
- docs/khmer-platform/04-llm-training-benchmark-audit.md
- .agents/jobs/backlog.yaml
- .agents/jobs/active.yaml
- data/khmer_spoken/workspace/spoken_scale.jsonl
- data/khmer_spoken/fixtures/dialogue_1500_scale.jsonl
- data/khmer_spoken/versions/scale-lock1000-20261023/
- data/outputs/voice_training/2026-10-23-spoken-500/fill_scale.py
- data/outputs/voice_training/2026-10-23-spoken-500/write_scale_sources.py

## What changed

- Froze a scale cut: train pool kp-001–kp-1000, locked benchmark kp-1001–kp-2000. Old split directories were not deleted.
- Added 1,500 original synthetic English source lines. Licence unknown. pending_native_review. Not gold.
- Started Gemini candidate fill and Jev ranking from kp-121. Gemini is the teacher and Jev is the ranker. Neither updates weights.
- dry_run: true. No weights written. No weights uploaded. Vertex was not called. trainer.start was not weakened.

## Evidence

Commands actually run:

- PYTHONPATH=src .venv/bin/python tests/python/test_llm_benchmark.py — 11/11 passed.
- PYTHONPATH=src .venv/bin/python data/outputs/voice_training/2026-10-23-spoken-500/write_scale_sources.py — 2000 rows, 120 with candidates at cut, jev 120.
- Fill process pid 20809, log data/outputs/voice_training/2026-10-23-spoken-500/fill_scale.log. First saved row kp-121 had 3 candidates, jev applied, licence unknown, pending_native_review. Process was still running after the launcher exited.

## Risks

- The fill uses the existing Gemini pool and a stored typesafe key. It stops on auth failure or if the pool is still cooling after one wait, or at 80 minutes / 300 rows.
- Do not start a second fill while pid 20809 is alive.
- The locked 1,000 rows are synthetic. They are not the native-reviewed benchmark.

## Not done

- 10,000–30,000 reviewed rows are still a target. This cut stops at 2,000 source rows.
- 1,000–2,000 native-reviewed benchmark rows are still a target.
- JOB-011, JOB-019, JOB-020, JOB-021, and JOB-022 stay BLOCKED.
- No 3B, 7B, 8B, or 14B weights were trained.

Resume, only if pid 20809 is not running:

```
PYTHONPATH=src .venv/bin/python data/outputs/voice_training/2026-10-23-spoken-500/fill_scale.py --limit 25 --write-split
```
