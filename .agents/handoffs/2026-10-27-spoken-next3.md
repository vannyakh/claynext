# Handoff

- Job: JOB-026
- From: dataset-engineer
- To: cto
- Status: REVIEW
- Date: 2026-10-27

JOB-026 stays IN_PROGRESS. The 10,000 reviewed-row target is not met. The next3 fill finished all 200 rows. This pass packaged the stored Jev lines into a new export. No weights were started.

## Scope

Paths touched:

- data/khmer_spoken/workspace/spoken_train_next3.jsonl (200 rows, kp-2401–kp-2600, filled by the existing process)
- data/outputs/voice_training/2026-10-27-spoken-next3/fill_next3.py (already present; not replaced)
- data/outputs/voice_training/2026-10-27-spoken-next3/fill_next3.log (the fill appended its own rows)
- data/outputs/voice_training/2026-10-27-spoken-next3/package_kp2600.py (new)
- data/khmer_spoken/versions/translate-sft-spoken-20261027-f/ (new)
- data/khmer_spoken/versions/owner-approval-sidecar-20261027-kp2600/ (new)
- data/khmer_spoken/versions/owner-licence-grant-20261027-kp2600/ (new)
- .agents/handoffs/2026-10-27-spoken-next3.md

Not touched: data/khmer_spoken/workspace/spoken_scale.jsonl, spoken_train_next.jsonl, spoken_train_next2.jsonl, holdout kp-1001–kp-2000, translate-sft-spoken-20261026/sft.jsonl, the -b 758-row file, the -c 1000-row file, the -d 1200-row file, the -e 1400-row file, live review fields, job YAML status. No commit. No push.

## What changed

- Final fill counts for `spoken_train_next3.jsonl`: last filled id `kp-2600`, filled 200 of 200, empty left 0. Every filled row has 3 candidates and a stored Jev line. Licence unknown. review_status pending_native_review. origin gemini_teacher. approved_text and verified_by empty. Not human. Not gold.
- Pid 78663 (ppid 1) was the only fill. Command: `fill_next3.py --limit 200 --max-minutes 90`. It was left running until it exited on its own. No second fill was started. A resume was not needed: the process finished the batch with `still_empty` 0 and an empty `stop_reason`. It did not stop on time_budget, cooldown, auth, or a missing key.
- The fill script reads only `spoken_train_next3.jsonl`. It refuses kp-1001–kp-2000. It does not open `spoken_scale.jsonl`.
- No extra Jev call was needed. After the fill exited, every row that had candidate text already had a stored Jev line, so `rank_khmer_candidates` was not called again. Live review fields were not edited.
- spoken_scale.jsonl still has 2000 source rows. holdout_filled is 0. sha256 unchanged `c9a14bfaacf91261c6f3b88502afd3761c7dd6ad0b3131fcb03ed9dc54ddb662`. spoken_train_next.jsonl sha256 unchanged `9543a34ae84356013624e34a033964f87ee7f7e3a945ce1204c04ed6610350ea`. spoken_train_next2.jsonl sha256 unchanged `394f1e26687bd153e2c9e987c1774ae3863227ed026954a2ad9aa200d9551dd9`. spoken_train_next3.jsonl sha256 `713f2c9635d4cc8ba9baada247a4f0037f36db5901875e27df3e5d461cdcbee7` (unchanged by the package).
- SFT export: `data/khmer_spoken/versions/translate-sft-spoken-20261027-f/sft-train-approved.jsonl`, 1600 lines. Ids are kp-001–kp-1000, then kp-2001–kp-2600. The khmer field is the stored Jev line. Fields: id, source, khmer, licence unknown, owner_training_approved true, split=train. Holdout ids in the file: 0. started false. sha256 `42b7b220bcc4b963183588d26c0dfeb9f3acb4156c8712d929f8a514fb17a0e2`. The model card says these are 1,600 Jev lines, not a trained language model, not promoted, licence unknown, and no weights.
- Approval sidecar: `data/khmer_spoken/versions/owner-approval-sidecar-20261027-kp2600/`. It covers the newly filled next3 ids only, kp-2401–kp-2600 (200 rows, no gaps). Reviewer `project-owner`, status `approved`, licence `unknown`, purpose training-export. Not gold. Not promoted. The live rows stay `pending_native_review`.
- Licence grant: `data/khmer_spoken/versions/owner-licence-grant-20261027-kp2600/`. It covers kp-001–kp-1000 and kp-2001–kp-2600 (1600 ids). Holdout kp-1001–kp-2000 is excluded. The standing approval is quoted as written: "if licence is still unknown i approve you do sometihnk and continue trained." That is approval to use the rows for training while licence stays unknown. It is not CC-BY and not any other external licence. The earlier grants were not overwritten.
- Older exports were left in place: -e 1400 rows, sha256 `4c2824d069f568e971fa533c98200001131d9fb1eb1237f73b98cfae03bd9e3e`; -d 1200; -c 1000; -b 758; translate-sft-spoken-20261026/sft.jsonl 720.
- No weights. trainer.start was not called. peft and mlx_lm were not installed. No 3B, 7B, 8B, or 14B fine-tune was started. No Hugging Face Job was started.

## Evidence

Commands actually run:

- `ps -p 78663` while the fill was alive: pid 78663, ppid 1, state S, `.venv/bin/python data/outputs/voice_training/2026-10-27-spoken-next3/fill_next3.py --limit 200 --max-minutes 90`. No other fill_next3 process.
- The same pid was polled until it exited. Log `data/outputs/voice_training/2026-10-27-spoken-next3/fill_next3.log` ends:

```
ROW kp-2600 200/200 candidates=3 jev=applied status=pending_native_review origin=gemini_teacher license=unknown
FILL_DONE {"source_rows": 200, "with_candidates": 200, "filled": 200, "last_id": "kp-2600", "next_id": "", "still_empty": 0, "stop_reason": "", "jev_ranked_this_process": 200, "weights_written": false, "training_started": false}
```

- A count after exit, with no fill process alive: next3 200 rows, ids kp-2401–kp-2600, filled 200, empty 0, stored Jev 200, missing Jev 0, reviews only pending_native_review, licence only unknown, origin only gemini_teacher, human marks 0, approved fields 0. spoken_scale holdout_filled 0. The -e export was 1400 rows, kp-001–kp-1000 then kp-2001–kp-2400, and each of those khmer lines matched the stored Jev line. Prior line counts stayed 720, 758, 1000, 1200, and 1400.
- `.venv/bin/python -m py_compile data/outputs/voice_training/2026-10-27-spoken-next3/package_kp2600.py` exited 0.
- `PYTHONPATH=src .venv/bin/python data/outputs/voice_training/2026-10-27-spoken-next3/package_kp2600.py` wrote the sidecar, grant, and SFT export. Printed sft_count 1600, last_filled_id kp-2600, next3_filled 200, next3_empty 0, sidecar_count 200, grant_count 1600, holdout_ids_in_export 0, holdout_filled 0, ranked_this_pass 0, needs_rank_before 0, started false, weights_written false, trainer_start_called false, fill_started false, live_review_fields_edited false. Scale, train-next, and train-next2 sha256 values were unchanged. The -e sha256 was unchanged.
- A later read of the written files: export 1600 unique ids, holdout 0, licence only unknown, split only train; grant 1600 ids from kp-001 through kp-1000 and kp-2001 through kp-2600, holdout 0; sidecar 200 ids, kp-2401–kp-2600 only. Live next3 review fields were still pending_native_review and licence unknown. `.agents/jobs/active.yaml` still has `status: IN_PROGRESS` for JOB-026. No fill or trainer process was running.
- tests/python/test_datasets.py and tests/python/test_llm_benchmark.py were not run.

## Risks

- Licence remains unknown. The sidecar and the grant are not a native gold mark. Jev ranking is not native review. The live rows stay pending_native_review.
- 1,600 packaged lines are not 10,000 reviewed rows.
- The new export is a snapshot of stored Jev lines. It is not a trained model and it was not promoted.

## Not done

- Holdout kp-1001–kp-2000 was not filled. holdout_filled stayed 0.
- No row was marked gold or human-reviewed. No live review field was edited.
- No 3B, 7B, 8B, or 14B weights were trained. `trainer.start` was not called. No Hugging Face Job was started.
- 10,000 reviewed rows remain a target. JOB-026 stays IN_PROGRESS.
- No commit and no push.
