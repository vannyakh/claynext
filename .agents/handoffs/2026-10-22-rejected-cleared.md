# Handoff

- Job: owner approval of rejected.json kp-056..kp-100 (not JOB-011)
- From: model-training
- To: project-owner
- Status: REVIEW
- Date: 2026-10-22

## Scope

Paths touched:

- `data/khmer_spoken/workspace/candidates.jsonl` (kp-056..kp-100 set to approved)
- `data/khmer_spoken/versions/owner-approved-20261022-rejected-cleared/` (new snapshot)
- `data/outputs/voice_training/2026-10-22-ai-first/apply_rejected_approval.py`
- `data/outputs/voice_training/2026-10-22-ai-first/rejected_cleared_run.json`

`owner-approved-20261022/dialogue.jsonl` (55) and `owner-approved-20261022-ranked/dialogue.jsonl` (58) were not rewritten. `rejected.json` was not edited. No commit, no push, no Gemini, no Jev, no training.

## What changed

Owner quote: `x/Users/server2/Documents/Project/claynext/data/khmer_spoken/versions/owner-approved-20261022/rejected.json approve all`.

All 45 rows in that file were `pending_native_review` / `not_approved_or_gold` at export time. The rejection reason is kept on `metadata.review_history[].prior_rejection`. Licence stays `unknown`. No candidate sentences were added.

42 rows had no Gemini candidates. Their existing `stub_khmer` was copied to `approved_text` by the review helper. 3 rows (kp-056, kp-058, kp-059) were already approved and only gained a second history entry.

`dry_run: true` for weights. No weights were uploaded. qlora_14b was not started.

## Evidence

Command:

`KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=src .venv/bin/python data/outputs/voice_training/2026-10-22-ai-first/apply_rejected_approval.py`

Result: `{"rejected_file_count": 45, "newly_approved": 42, "already_approved_confirmed": 3, "owner_approved_in_rejected_file": 45, "workspace_approved": 100, "workspace_pending": 0, "gold_export_count": 100, "gold_export_rejected": 0, "gold_export_path": "/Users/server2/Documents/Project/claynext/data/khmer_spoken/versions/owner-approved-20261022-rejected-cleared/dialogue.jsonl", "approved_but_not_exported": [], "rows_still_without_text": [], "rows_without_gemini_text_count": 42, "ranked_export_count": 58, "weights_written": false}`

## Risks

- `unknown` is not an external licence. The 42 stub rows are marked gold in the new snapshot because stored stub text is non-empty. They still have zero Gemini candidates.
- `ranked.jsonl` has 58 rows. That exporter skips rows with no candidates, so kp-057 and kp-060..kp-100 are in `dialogue.jsonl` and not in `ranked.jsonl`.
- `metadata.not_for_gold` is still true on the workspace rows, same as the earlier 55.

## Not done

- No Gemini call. No Jev call. No training. JOB-011 was not started.
- No row was left without text. None are approved-but-not-exported.
