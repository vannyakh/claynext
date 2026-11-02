# Handoff

- Job: JOB-026
- From: dataset-engineer
- To: cto
- Status: REVIEW
- Date: 2026-10-27

JOB-026 stays IN_PROGRESS. The 10,000 reviewed-row target is not met. This pass waited for the live next2 fill, resumed it once after the time budget, and packaged the stored Jev lines.

## Scope

Paths touched:

- data/khmer_spoken/workspace/spoken_train_next2.jsonl (filled by fill_next2.py only; review fields left pending)
- data/khmer_spoken/versions/owner-approval-sidecar-20261027-kp2400/ (new)
- data/khmer_spoken/versions/owner-licence-grant-20261027-kp2400/ (new)
- data/khmer_spoken/versions/translate-sft-spoken-20261027-e/ (new)
- data/outputs/voice_training/2026-10-27-spoken-next2/package_kp2400.py (new)
- data/outputs/voice_training/2026-10-27-spoken-next2/fill_next2.log (appended by the fill)
- .agents/handoffs/2026-10-27-null-translate-ranked.md

Not touched: data/khmer_spoken/workspace/spoken_scale.jsonl, data/khmer_spoken/workspace/spoken_train_next.jsonl, data/khmer_spoken/workspace/spoken_500.jsonl, translate-sft-spoken-20261026/sft.jsonl, the 758-row -b export, translate-sft-spoken-20261026-c, translate-sft-spoken-20261027-d, job YAML status. No commit. No push.

## What changed

- Pid 67267 (`fill_next2.py --limit 200 --max-minutes 90`, ppid 1) was alive at the start and was not killed. It exited on `time_budget` at kp-2328. That process filled 128 rows. `still_empty` was 72. `next_id` was kp-2329. `stop_reason` was `time_budget`. `weights_written` false. `training_started` false.
- A resume was required. One shell-attached start, pid 68892, printed `FILL empty=72` and died before a ROW line. It saved nothing. The detached resume then ran as pid 68991, ppid 1: `fill_next2.py --limit 72 --max-minutes 108`. Limit 72 is the empty count in spoken_train_next2.jsonl. 108 minutes is 1.5 minutes per remaining row. It appended to the same log. It finished kp-2329–kp-2400. `FILL_DONE` reports filled 72, last_id kp-2400, still_empty 0, stop_reason empty, jev_ranked_this_process 72, weights_written false, training_started false. No second resume was started. The stop was not cooldown, auth, or a missing key.
- spoken_train_next2.jsonl now has 200 rows, kp-2201–kp-2400. Filled 200. Empty 0. Each filled row has 3 candidates and a stored Jev line. Licence unknown. review_status pending_native_review. origin gemini_teacher. verified_by and approved_text are empty. No row had candidate text without a stored Jev line, so `rank_khmer_candidates` was not called again. `ranked_this_pass` is 0.
- spoken_scale.jsonl was not edited. sha256 is still `c9a14bfaacf91261c6f3b88502afd3761c7dd6ad0b3131fcb03ed9dc54ddb662`. holdout_filled is 0. spoken_train_next.jsonl sha256 is still `9543a34ae84356013624e34a033964f87ee7f7e3a945ce1204c04ed6610350ea`. spoken_500.jsonl was not filled.
- Approval sidecar: `data/khmer_spoken/versions/owner-approval-sidecar-20261027-kp2400/`. It covers the newly filled ids only, kp-2201–kp-2400 (200 rows, no gaps). Reviewer `project-owner`, status `approved`, licence `unknown`, purpose training-export. Not gold. Not promoted. The live rows stay `pending_native_review`.
- Licence grant: `data/khmer_spoken/versions/owner-licence-grant-20261027-kp2400/`. It covers kp-001–kp-1000 and kp-2001–kp-2400 (1400 ids). Holdout kp-1001–kp-2000 is excluded. The standing approval is quoted as written: "if licence is still unknown i approve you do sometihnk and continue trained." That is approval to use the rows for training while licence stays unknown. It is not CC-BY and not any other external licence. The earlier grants were not overwritten.
- SFT export: `data/khmer_spoken/versions/translate-sft-spoken-20261027-e/sft-train-approved.jsonl`, 1400 lines. The first 1200 rows match the -d export. The next 200 are the stored Jev lines from spoken_train_next2.jsonl, kp-2201–kp-2400. Fields: id, source, khmer (the Jev line), licence unknown, owner_training_approved true, split=train. Holdout ids in the file: 0. started false. The model card says this is not a trained language model, not promoted, licence unknown, and no weights.
- Prior exports stayed in place: open sft.jsonl 720 lines, -b 758, -c 1000, -d 1200. Their sha256 values matched before and after the package.
- dry_run on weights: no weights. trainer.start was not called. peft and mlx_lm were not installed. No 3B, 7B, 8B, or 14B fine-tune was started. No Hugging Face Job was started.

## Evidence

Commands actually run:

- `ps -p 67267` showed pid 67267, ppid 1, `fill_next2.py --limit 200 --max-minutes 90`. The log was already past kp-2212 and still advancing. The process was left running.
- After it exited, the log ended `ROW kp-2329 STOP time_budget` and `FILL_DONE` with last_id kp-2328, still_empty 72, stop_reason time_budget, weights_written false. No fill process remained.
- A read of spoken_train_next2.jsonl after that exit: 200 rows, filled 128, empty 72, first empty kp-2329, last empty kp-2400, jev 128, rows with candidates but no Jev line 0.
- Pid 68892 printed one `FILL empty=72` line and was gone before a ROW line. Pid 68991, ppid 1, then ran `--limit 72 --max-minutes 108` and was the only fill.
- The resume log ends `ROW kp-2400 72/72 candidates=3 jev=applied status=pending_native_review origin=gemini_teacher license=unknown` and `FILL_DONE` with with_candidates 200, filled 72, last_id kp-2400, still_empty 0, stop_reason empty, weights_written false, training_started false.
- `PYTHONPATH=src .venv/bin/python data/outputs/voice_training/2026-10-27-spoken-next2/package_kp2400.py` wrote the sidecar, grant, and SFT export. Printed sft_count 1400, last_filled_id kp-2400, next2_filled 200, next2_empty 0, sidecar 200, grant 1400, holdout_ids_in_export 0, holdout_filled 0, ranked_this_pass 0, needs_rank_before 0, started false, weights_written false, trainer_start_called false, live_review_fields_edited false. sft_sha256 `4c2824d069f568e971fa533c98200001131d9fb1eb1237f73b98cfae03bd9e3e`.
- A read-back confirmed 1400 SFT rows, ids kp-001–kp-1000 then kp-2001–kp-2400, the first 1200 identical to the -d file, licence unknown, owner_training_approved true, split train, holdout ids 0. The sidecar is kp-2201–kp-2400. The grant ids match the SFT ids. Live next2 review stays pending_native_review, licence unknown, verified_by empty, approved_text empty, origin gemini_teacher. holdout_filled 0. Open sft.jsonl 720, -b 758, -c 1000, -d 1200. No key-shaped marker in the new version files. `.agents/jobs/active.yaml` still has `status: IN_PROGRESS`.
- tests/python/test_datasets.py and tests/python/test_llm_benchmark.py were not run.

## Risks

- Licence remains unknown. The sidecar and the grant are not a native gold mark. Jev ranking is not native review.
- 1,400 packaged lines are not 10,000 reviewed rows.
- The shell-attached pid 68892 died before a row. Pid 68991 is the resume that wrote kp-2329–kp-2400. No further fill is running.
- Live review fields in spoken_train_next2.jsonl were not changed. A later pass must not treat the sidecar as a gold review.

## Not done

- Holdout kp-1001–kp-2000 was not filled. holdout_filled stayed 0.
- spoken_500.jsonl was not filled. Its empty kp-121–kp-500 rows stay empty.
- No row was marked gold. No human reviewer was written onto a live row.
- No 3B, 7B, 8B, or 14B weights were trained. `trainer.start` was not called. JOB-011, JOB-019, JOB-020, JOB-021, and JOB-022 stay BLOCKED.
- 10,000 reviewed rows remain a target. JOB-026 stays IN_PROGRESS.
- No commit and no push.
