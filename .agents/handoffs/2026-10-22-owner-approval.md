# Handoff

- Job: owner approval of 55 Khmer spoken drafts (not JOB-011)
- From: model-training
- To: project-owner
- Status: REVIEW
- Date: 2026-10-22

## Scope

Paths touched:

- `data/khmer_spoken/workspace/candidates.jsonl` (kp-001..kp-055 set to approved)
- `data/khmer_spoken/versions/owner-approved-20261022/` (gold export, 55 rows)
- `data/outputs/voice_training/2026-10-22-ai-first/owner_report.json`
- `data/outputs/voice_training/2026-10-22-ai-first/owner_approval.json`

Fixture `dialogue_100.jsonl` was not changed. No commit, no push, no Gemini, no Vertex.

## What changed

Owner quote: "pls approve all", applied only to the 55 Gemini drafts. Reviewer `project-owner`, status `approved`. Licence stays the schema value `unknown`. Prior pending notes and all 3 candidates were kept; approval was appended in `metadata.review_history`.

`dry_run: true` for weights. The spoken gold exporter accepted the 55 rows because `unknown` is a non-empty `license_type`. The version file marks those copies `gold`. Workspace rows stay `approved`. No weights were uploaded.

## Evidence

Command:

`KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=src .venv/bin/python data/outputs/voice_training/2026-10-22-ai-first/apply_owner_approval.py`

Result: `{"approved": 55, "workspace_pending": 45, "gold_export_count": 55, "gold_export_rejected": 45, "lora_status": "refused", "skipped": []}`

## Risks

- `unknown` is not an external licence. The dialogue-dataset gold gate still requires `provenance.license`. That gate was not used and was not weakened.
- kp-056..kp-100 are still pending and have no candidates.

## Not done

- No LoRA weights. `plan_local_lora` returned refused.
- JOB-011 was not started.
