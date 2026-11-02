# Handoff

- Job: JOB-026
- From: model-training
- To: cto
- Status: REVIEW
- Date: 2026-10-26

## Scope

Paths touched:

- data/khmer_spoken/versions/translate-sft-spoken-20261026/ (new)
- data/khmer_spoken/versions/owner-approval-sidecar-20261026/ (new)
- data/outputs/voice_training/2026-10-26-spoken-translate-sft/build_export.py (new)
- data/khmer_spoken/workspace/spoken_scale.jsonl (read, then filled by pid 58618 only)
- data/outputs/voice_training/2026-10-23-spoken-500/fill_scale.log (appended by the fill)
- .agents/jobs/active.yaml
- .agents/handoffs/2026-10-26-spoken-translate-sft.md

Not touched: scale-lock1000-20261023/, owner-approval-sidecar-20261023/, older version directories, trainer.py, fill_scale.py. No commit. No push.

## What changed

- Friday's fill was finished. Pids 20809 and 26002 were not running. `fill_scale.pid` was absent until a new fill started. The log ends the Friday run with FILL_DONE at kp-720.
- Snapshot before the new fill: 2,000 source rows, 720 with Gemini candidates and a Jev line that matches a candidate, no gaps from kp-001 through kp-720, next empty kp-721. Train pool still had 280 empty rows (kp-721–kp-1000). Holdout kp-1001–kp-2000 had no candidates. Lock files on disk are train kp-001–kp-1000 and holdout kp-1001–kp-2000.
- Translation SFT export: `data/khmer_spoken/versions/translate-sft-spoken-20261026/sft.jsonl`, 720 lines. Each line is id, source text, Jev Khmer, licence unknown, split=train. Holdout ids in the file: 0. `started: false`. No weights were written.
- `export_ranked_training` drops `pending_native_review`. Those 620 rows stay pending in the live file so the filler can resume. The export uses the same `training_khmer()` target, which keeps the Jev line. The stub was not used. 42 of the 100 already-gold rows have stored approved text that differs from the Jev line; the export target is the Jev line.
- Owner quote recorded: "next translate train spoke khmer." New sidecar approves kp-637–kp-720 only (84 rows), licence unknown, not gold, not promoted, live file not edited. kp-101–kp-636 stay in the 20261023 sidecar.
- One fill is running for the remaining train pool: pid 58618, parent launchd (ppid 1), `--limit 280 --max-minutes 80 --write-split`. The limit is 280 because 300 would continue into kp-1001. The first saved row is kp-721. A nohup pid 58474 died with its launcher shell and saved no rows.
- dry_run: true. No weights written. No weights uploaded. Vertex was not called. trainer.start was not called and was not changed. peft/mlx are not installed. Promotion stays not_promoted. chrF, COMET, and human scores were not measured.

## Evidence

Commands actually run:

- `ps -p 26002` and `ps -p 20809` printed nothing. `pgrep` found no `fill_scale.py` or `fill_kp101.py` before the new fill.
- A count of `spoken_scale.jsonl` reported source_rows 2000, with_candidates 720, jev_ranked_matching 720, last_cand kp-720, next_empty kp-721, train_empty 280, holdout_with_candidates 0, gaps 0.
- `PYTHONPATH=src .venv/bin/python data/outputs/voice_training/2026-10-26-spoken-translate-sft/build_export.py` wrote 720 SFT rows and 84 sidecar approvals. Live sha256 stayed `462eb6ecd88a03bf91d44069489006fdbbb037f3a4e95e2b37aa1cfb78eb0aef` until the fill saved kp-721.
- A read-back of `sft.jsonl` confirmed 720 lines, ids kp-001–kp-720, licence unknown, split train, holdout ids 0. `cmp` of the copied locked ids against `scale-lock1000-20261023/locked_ids.txt` matched.
- After the launcher shell exited, `ps -p 58618` showed pid 58618, ppid 1, args `--limit 280 --max-minutes 80 --write-split`. The log showed `ROW kp-721 1/280` with three candidates, Jev applied, pending_native_review, licence unknown.
- `git diff --stat -- src/claynext/models/training/trainer.py` was empty.

## Risks

- Pid 58618 is still filling kp-721 onward and rewrites `spoken_scale.jsonl` after each row. Do not start a second fill. Do not mark those new rows approved in the live file; the filler refuses rows past kp-100 that are no longer pending.
- The SFT export and the new sidecar stop at kp-720. Rows the live fill adds after that are not in this export.
- Licence unknown is not an external licence. These rows are not a native gold benchmark and this pass did not train weights.
- On 42 gold rows the stored approved line and the Jev line differ. The export target is the Jev line. No weights were trained on it.

## Not done

- Train pool kp-721–kp-1000 was not filled yet when the export was written. The fill is capped at those 280 rows and at 80 minutes.
- 10,000–30,000 reviewed rows and the 1,000–2,000 native-reviewed benchmark are still targets.
- JOB-011, JOB-019, JOB-020, JOB-021, and JOB-022 stay BLOCKED.
- No 3B, 7B, 8B, or 14B weights were trained.
