# Handoff

- Job: JOB-026
- From: model-training
- To: cto
- Status: REVIEW
- Date: 2026-10-26

## Scope

Paths touched:

- data/khmer_spoken/versions/owner-approval-sidecar-20261026-next/ (new)
- data/outputs/voice_training/2026-10-26-spoken-approval-next/record_sidecar.py (new)
- .agents/jobs/active.yaml
- .agents/handoffs/2026-10-26-spoken-approval-next.md

Not touched: spoken_scale.jsonl, owner-approval-sidecar-20261023/, owner-approval-sidecar-20261026/, scale-lock1000-20261023/, fill_scale.py, trainer.start. No second fill. No commit. No push.

## What changed

- Owner quote recorded: "approvals next." Applied only as dataset-pipeline approval. It is not approval to train weights.
- Fill pid 58618 was alive (`fill_scale.py --limit 280 --max-minutes 80 --write-split`, ppid 1). A second fill was not started.
- Live `spoken_scale.jsonl` was not edited. The fill rewrites that file after every row and refuses rows past kp-100 that are no longer pending.
- New sidecar: 13 train-pool rows, kp-721–kp-733, no gaps. Each has Gemini candidates and a matching Jev line. Reviewer `project-owner`, status `approved`, licence `unknown`. Not gold. Promotion stays `not_promoted`.
- kp-001–kp-100 were left as already approved. kp-101–kp-636 stay in the 20261023 sidecar (536). kp-637–kp-720 stay in the 20261026 sidecar (84). Holdout kp-1001–kp-2000 had no candidates and was not approved. Empty stubs were not approved.
- The pending note on each row, "Synthetic English source only. No reference Khmer. review_status pending_native_review.", is copied into `prior_reviewer_notes`. The live rows still carry that note.
- dry_run: true. No weights written. No weights uploaded. Vertex was not called. Scores were not measured.

## Evidence

Commands actually run:

- `ps -p 58618` showed pid 58618, ppid 1, elapsed about 11 minutes at the final check. Args `--limit 280 --max-minutes 80 --write-split`.
- A read of `spoken_scale.jsonl` wrote the sidecar. Result: approvals 13, first kp-721, last kp-733, holdout with candidates 0. A later read of kp-721 was still `pending_native_review`, licence `unknown`, with empty `approved_text` and empty `verified_by`.
- Locked ids in the new directory match `scale-lock1000-20261023/locked_ids.txt` (sha256 `7600912095fd9b2fcb13255f468cceb9998efca87a0db03097a08c2e8949bfe8`).
- Sidecar check: every approval is `approved`, reviewer `project-owner`, licence `unknown`, Jev applied, not gold, contiguous kp-721–kp-733, overlap with the two prior sidecars 0.
- The log's last row line at the final check was `ROW kp-733 13/280`.
- A scan of the new sidecar for key-shaped strings returned no matches.

## Risks

- Pid 58618 keeps writing after this snapshot. Rows after kp-733 stay pending until a later approval pass. Do not apply this sidecar onto `spoken_scale.jsonl` while that pid is alive.
- Licence `unknown` is not an external licence. These rows are not a native gold set and are not cleared for weight training.
- The first snapshot in this pass stopped at kp-728. The sidecar directory was rewritten from a later read so the recorded range is kp-721–kp-733. The live file was not edited.

## Not done

- No second fill. No training.
- Train-pool rows kp-734–kp-1000 were still empty at the snapshot.
- JOB-011, JOB-019, JOB-020, JOB-021, and JOB-022 stay BLOCKED.
- No 3B, 7B, 8B, or 14B weights were trained.
