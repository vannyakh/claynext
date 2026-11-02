# Handoff

- Job: JOB-026
- From: dataset-engineer
- To: cto
- Status: REVIEW
- Date: 2026-10-27

JOB-026 stays IN_PROGRESS. The 10,000 reviewed-row target is not met. This pass packages the finished 200-row train-next cut and starts one candidate fill on a new source file only.

## Scope

Paths touched:

- data/khmer_spoken/versions/owner-approval-sidecar-20261027-kp2200/ (new)
- data/khmer_spoken/versions/owner-licence-grant-20261027-kp2200/ (new)
- data/khmer_spoken/versions/translate-sft-spoken-20261027-d/ (new)
- data/khmer_spoken/workspace/spoken_train_next2.jsonl (new, 200 source rows)
- data/outputs/voice_training/2026-10-27-spoken-next2/package_kp2200.py (new)
- data/outputs/voice_training/2026-10-27-spoken-next2/write_train_next2.py (new)
- data/outputs/voice_training/2026-10-27-spoken-next2/fill_next2.py (new)
- data/outputs/voice_training/2026-10-27-spoken-next2/fill_next2.log (fill still writing)
- .agents/handoffs/2026-10-27-spoken-next2.md

Not touched: data/khmer_spoken/workspace/spoken_scale.jsonl, data/khmer_spoken/workspace/spoken_train_next.jsonl review fields, holdout kp-1001–kp-2000, translate-sft-spoken-20261026/sft.jsonl, the 758-row -b export, the 1000-row -c export, job YAML status. No commit. No push.

## What changed

- spoken_train_next.jsonl has 200 rows, kp-2001–kp-2200, each with 3 Gemini candidates and a matching Jev line. Licence unknown. review_status pending_native_review. origin gemini_teacher. approved_text and verified_by empty. Those review fields were not edited.
- spoken_scale.jsonl still has 2000 source rows. holdout_filled is 0. sha256 unchanged `c9a14bfaacf91261c6f3b88502afd3761c7dd6ad0b3131fcb03ed9dc54ddb662`.
- Approval sidecar: `data/khmer_spoken/versions/owner-approval-sidecar-20261027-kp2200/`. It covers kp-2001–kp-2200 only (200 rows, no gaps). Reviewer `project-owner`, status `approved`, licence `unknown`, purpose training-export. Not gold. Not promoted. The live rows stay `pending_native_review`.
- Licence grant: `data/khmer_spoken/versions/owner-licence-grant-20261027-kp2200/`. It covers kp-001–kp-1000 and kp-2001–kp-2200 (1200 ids). Holdout kp-1001–kp-2000 is excluded. The standing approval is quoted as written: "if licence is still unknown i approve you do sometihnk and continue trained." That is approval to use the rows for training while licence stays unknown. It is not CC-BY and not any other external licence. The earlier kp-001–kp-1000 grant was not overwritten.
- SFT export: `data/khmer_spoken/versions/translate-sft-spoken-20261027-d/sft-train-approved.jsonl`, 1200 lines. The first 1000 khmer fields are the Jev lines from the -c export. The next 200 are the stored Jev lines from spoken_train_next.jsonl. Fields: id, source, khmer, licence unknown, owner_training_approved true, split=train. Holdout ids in the file: 0. started false. The model card beside it says these are 1,200 Jev lines, not a trained language model, not promoted, licence unknown, holdout excluded, and no weights.
- New source file: `data/khmer_spoken/workspace/spoken_train_next2.jsonl`, 200 rows, ids kp-2201–kp-2400. The same gate as write_train_next.py refused exact normalized copies, content-word overlap at or above 0.42, and shared content 5-grams against kp-001–kp-2200 and inside the new file. One line was rewritten after that gate rejected a shared 5-gram, then the gate passed and the file was written. Licence unknown. review_status pending_native_review. origin synthetic at write time. Not human. Not gold.
- One fill is running: pid 67267, ppid 1, `fill_next2.py --limit 200 --max-minutes 90`. It reads only spoken_train_next2.jsonl. It has no --write-split flag and does not open spoken_scale.jsonl. An earlier nohup pid 67058 printed the first FILL line and died before a ROW line. It is not running. Pid 67267 is the only fill.
- At the snapshot after the first saved row: kp-2201 has 3 candidates, Jev applied, status still pending_native_review, licence unknown, origin gemini_teacher. The other 199 rows were still empty. The fill was still running.
- dry_run on weights: no weights. trainer.start was not called. peft and mlx_lm were not installed. No 3B, 7B, 8B, or 14B fine-tune was started. No Hugging Face Job was started.

## Evidence

Commands actually run:

- `ps` before the package found no `fill_scale.py`, `fill_next.py`, or `fill_kp` process. Pid 64817 was not running. The prior log ends `FILL_DONE` at kp-2200, filled 200, still_empty 0, weights_written false.
- A count before the package: spoken_train_next 200 rows, filled with 3 candidates and a matching Jev line 200, empty 0, reviews only pending_native_review, licence only unknown, origin only gemini_teacher. spoken_scale holdout_filled 0, train_filled 1000. sha256 `c9a14bfaacf91261c6f3b88502afd3761c7dd6ad0b3131fcb03ed9dc54ddb662`.
- `PYTHONPATH=src .venv/bin/python data/outputs/voice_training/2026-10-27-spoken-next2/package_kp2200.py` wrote the sidecar, grant, and SFT export. Printed train_next_filled 200, holdout_filled 0, sidecar 200, grant 1200, sft 1200, from_c_export 1000, from_train_next_jev 200, holdout_ids_in_export 0, started false, weights_written false, trainer_start_called false, fill_started false, live_jsonl_edited false.
- `PYTHONPATH=src .venv/bin/python data/outputs/voice_training/2026-10-27-spoken-next2/write_train_next2.py` first rejected 1 shared 5-gram and wrote nothing. After that line was replaced, it wrote 200 rows, kp-2201–kp-2400, 20 lines in each of 10 settings, licence unknown, review pending_native_review, origin synthetic, holdout_filled_on_scale 0, both compared sha256 values unchanged, weights_started false.
- nohup pid 67058 printed `FILL empty=200 batch=200 gemini_available=True jev=True max_minutes=90.0` and exited before a ROW line. It did not save a candidate. A detached nohup then started pid 67267 (ppid 1).
- Log `data/outputs/voice_training/2026-10-27-spoken-next2/fill_next2.log` at the first saved row:

```
FILL empty=200 batch=200 gemini_available=True jev=True max_minutes=90.0
FILL empty=200 batch=200 gemini_available=True jev=True max_minutes=90.0
ROW kp-2201 1/200 candidates=3 jev=applied status=pending_native_review origin=gemini_teacher license=unknown
```

- A later read, while pid 67267 was still the only matching process, showed next2 rows 200, filled 1, empty 199, reviews only pending_native_review, licence only unknown. spoken_train_next sha256 was still `9543a34ae84356013624e34a033964f87ee7f7e3a945ce1204c04ed6610350ea`. spoken_scale sha256 was unchanged and holdout_filled was 0. The new SFT file had 1200 rows, ids kp-001–kp-1000 then kp-2001–kp-2200, holdout ids 0, started false. The open sft.jsonl stayed 720 lines, the -b export stayed 758, and the -c export stayed 1000, with the same sha256 values as before this pass. `.agents/jobs/active.yaml` still has `status: IN_PROGRESS`.
- tests/python/test_datasets.py and tests/python/test_llm_benchmark.py were not run.

## Risks

- Pid 67267 rewrites `spoken_train_next2.jsonl` after each row. Do not approve rows in that live file. Do not start a second fill. The batch limit is 200 and the time limit is 90 minutes.
- The first FILL line in the log is from dead pid 67058. The saved row belongs to pid 67267.
- Licence remains unknown. The sidecar and the grant are not a native gold mark. Jev ranking is not native review.
- The new kp-2201–kp-2400 source rows are not in the 1200-row grant or the SFT export. They stay pending until a later pass.
- 1,200 packaged lines and 200 new source lines are not 10,000 reviewed rows.

## Not done

- The fill has not finished. kp-2202–kp-2400 were still empty at the snapshot.
- Holdout kp-1001–kp-2000 was not filled. holdout_filled stayed 0.
- No row in spoken_train_next.jsonl or spoken_train_next2.jsonl was marked gold.
- No 3B, 7B, 8B, or 14B weights were trained. `trainer.start` was not called. JOB-011, JOB-019, JOB-020, JOB-021, and JOB-022 stay BLOCKED.
- 10,000 reviewed rows remain a target. JOB-026 stays IN_PROGRESS.
- No commit and no push.
