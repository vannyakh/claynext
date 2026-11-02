# Handoff

- Job: JOB-026
- From: model-training
- To: cto
- Status: REVIEW
- Date: 2026-10-23

## Scope

Paths touched:

- data/khmer_spoken/versions/owner-approval-sidecar-20261023/ (new)
- .agents/handoffs/2026-10-23-spoken-approval-sidecar.md

Not touched: spoken_scale.jsonl, scale-lock1000-20261023/, older version directories, fill_scale.py, trainer.start, job YAML. No commit. No push.

## What changed

- Fill pid 26002 was still running (`fill_scale.py --limit 300 --max-minutes 80 --write-split`). A second fill was not started.
- Owner quote recorded: "i allow you do every think." Applied only as dataset-pipeline approval. It is not approval to train weights.
- Live `spoken_scale.jsonl` was not edited. The fill rewrites that file after every row and refuses rows past kp-100 that are no longer pending.
- Sidecar snapshot: 636 train-pool rows with Gemini candidates (kp-001–kp-636, no gaps). 536 of those were still `pending_native_review` and received owner approval (kp-101–kp-636), verified by project-owner, review status `approved`, licence `unknown`. Empty stubs were not approved. Holdout kp-1001–kp-2000 had no candidates and was not approved.
- Locked ids in the new directory are byte-identical to `scale-lock1000-20261023/locked_ids.txt`.
- dry_run: true. No weights written. No weights uploaded. Vertex was not called. Promotion stays `not_promoted`. Scores were not measured.

## Evidence

Commands actually run:

- `ps -p 26002` showed the fill alive (about 49 minutes elapsed at the sidecar write). `pgrep` found no `fill_kp101.py`.
- A one-shot read of `spoken_scale.jsonl` wrote the sidecar. Result: approvals 536, train ids with candidates 636, last id kp-636, next empty id kp-637, holdout with candidates 0, locked ids identical.
- `cmp` of the two `locked_ids.txt` files matched.
- Sidecar check: every approval is `approved`, licence `unknown`, non-empty text, contiguous kp-101–kp-636, zero gold labels, zero holdout ids.

## Risks

- The fill kept writing after the snapshot. At the final check the log had reached kp-642 (222/300) while the sidecar stops at kp-636. Newer rows stay pending in the live file until a later approval pass.
- Applying the sidecar onto `spoken_scale.jsonl` while pid 26002 is alive would be overwritten or would trip the fill's pending-row check.
- Licence `unknown` is not an external licence. These rows are not a native gold set and are not cleared for weight training.

## Not done

- No second fill. No key roll during the live fill.
- JOB-011, JOB-019, JOB-020, JOB-021, and JOB-022 stay BLOCKED.
- No 3B, 7B, 8B, or 14B weights were trained.
