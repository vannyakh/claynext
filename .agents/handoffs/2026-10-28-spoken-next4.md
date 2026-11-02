# Handoff

- Job: JOB-026
- From: dataset-engineer
- To: cto
- Status: REVIEW
- Date: 2026-10-28

JOB-026 stays IN_PROGRESS. The 10,000 reviewed-row target is not met. This pass wrote the next source batch, filled it, and packaged the stored Jev lines. No weights were started.

## Scope

Paths touched:

- data/khmer_spoken/workspace/spoken_train_next4.jsonl (new, 200 source rows, kp-2601–kp-2800)
- data/outputs/voice_training/2026-10-28-spoken-next4/lines_draft.txt (new)
- data/outputs/voice_training/2026-10-28-spoken-next4/write_train_next4.py (new)
- data/outputs/voice_training/2026-10-28-spoken-next4/fill_next4.py (copied from fill_next3.py and pointed at the new file)
- data/outputs/voice_training/2026-10-28-spoken-next4/fill_next4.log (the fill wrote this)
- data/outputs/voice_training/2026-10-28-spoken-next4/package_next4.py (new)
- data/khmer_spoken/versions/translate-sft-spoken-20261028-g/ (new)
- data/khmer_spoken/versions/owner-approval-sidecar-20261028-next4/ (new)
- data/khmer_spoken/versions/owner-licence-grant-20261028-next4/ (new)
- .agents/handoffs/2026-10-28-spoken-next4.md

Not touched: data/khmer_spoken/workspace/spoken_scale.jsonl, spoken_train_next.jsonl, spoken_train_next2.jsonl, spoken_train_next3.jsonl, holdout kp-1001–kp-2000, rejected.json, translate-sft-spoken-20261026/sft.jsonl, the -b, -c, -d, -e, and -f exports, live review fields, job YAML status. No commit. No push.

## What changed

- rejected.json in ai-draft-not-gold-20261022 is a 100-row review index, kp-001–kp-100. Each row has id, review_status pending_native_review, and issue not_approved_or_gold. It has no source text, no Khmer, no candidates, and no Jev line. It is not native gold. The matching train rows in spoken_scale.jsonl already have candidates and an applied Jev line, and all 100 ids are already in the 1,600-row -f export with a nonempty Khmer line. No rank sidecar was written. Those rows were not the unfinished job.
- New source file: data/khmer_spoken/workspace/spoken_train_next4.jsonl, 200 rows, ids kp-2601–kp-2800. Licence unknown. review_status pending_native_review. Origin started as synthetic and became gemini_teacher on filled rows. Not human. Not gold. Distinctness gate against kp-001–kp-2600 refused exact copies, content-word overlap at or above 0.42, and shared content 5-grams. The gate reported 0 problems before the file was written. Ten new settings, 20 lines each. Not template copies of the earlier craft blocks.
- Fill pid 82656 (ppid 1) read only spoken_train_next4.jsonl with --limit 200 --max-minutes 90. It stopped on time_budget at kp-2769, with 167 rows having candidates, still_empty 33, next empty kp-2751, jev_ranked_this_process 166. One row, kp-2700, received 3 candidates and Jev returned not_applied. An earlier launcher pid 82505 died when its shell exited, before any row was saved; it was not a second live fill.
- One resume, pid 84437 (ppid 1), --limit 33 --max-minutes 49.5, filled the remaining empty rows. Log line: still_empty 0, last_id kp-2800, stop_reason empty, jev_ranked_this_process 33. No further resume. It did not stop on cooldown, auth, or a missing key.
- After both fills: next4 has 200 rows, candidates on 200, stored Jev on 199, no stored Jev on kp-2700. A package pass called rank_khmer_candidates once for kp-2700 without a new Gemini call. Jev still did not apply, so the row was left unchanged. Reason recorded: not_applied (no candidate cleared the rank floors). Licence unknown. review_status still pending_native_review.
- spoken_scale.jsonl sha256 unchanged c9a14bfaacf91261c6f3b88502afd3761c7dd6ad0b3131fcb03ed9dc54ddb662. spoken_train_next.jsonl sha256 unchanged 9543a34ae84356013624e34a033964f87ee7f7e3a945ce1204c04ed6610350ea. spoken_train_next2.jsonl sha256 unchanged 394f1e26687bd153e2c9e987c1774ae3863227ed026954a2ad9aa200d9551dd9. spoken_train_next3.jsonl sha256 unchanged 713f2c9635d4cc8ba9baada247a4f0037f36db5901875e27df3e5d461cdcbee7. holdout_filled is 0.
- SFT export: data/khmer_spoken/versions/translate-sft-spoken-20261028-g/sft-train-approved.jsonl, 1799 lines. Ids are kp-001–kp-1000, then kp-2001–kp-2800 except kp-2700. The khmer field is the stored Jev line. Fields: id, source, khmer, licence unknown, owner_training_approved true, split=train, started false. Holdout ids in the file: 0. sha256 03f3a1e3951fd3b5924c41a5e7d92d721c36e0e39a4961b31c820ae68d84a1e3. The model card says these are 1,799 Jev lines, not a trained language model, not promoted, licence unknown, and no weights.
- Approval sidecar: data/khmer_spoken/versions/owner-approval-sidecar-20261028-next4/. It covers the newly filled next4 ids that have a stored Jev line, kp-2601–kp-2800 except kp-2700 (199 rows). Reviewer project-owner, status approved, licence unknown, purpose training-export. Not gold. Not promoted. The live rows stay pending_native_review.
- Licence grant: data/khmer_spoken/versions/owner-licence-grant-20261028-next4/. It covers kp-001–kp-1000 and kp-2001–kp-2800 except kp-2700 (1799 ids). Holdout kp-1001–kp-2000 is excluded. The standing approval is quoted as written: "if licence is still unknown i approve you do sometihnk and continue trained." This session quote is "pls to complited this next". That is approval to use the rows for training while licence stays unknown. It is not CC-BY and not any other external licence. The earlier grants were not overwritten.
- Older exports were left in place: -f 1600 rows, sha256 42b7b220bcc4b963183588d26c0dfeb9f3acb4156c8712d929f8a514fb17a0e2; -e 1400; -d 1200; -c 1000; -b 758; translate-sft-spoken-20261026/sft.jsonl 720.
- No weights. trainer.start was not called. peft and mlx_lm were not installed. No 3B, 7B, 8B, or 14B fine-tune was started. No Hugging Face Job was started. .agents/jobs/active.yaml still has status IN_PROGRESS for JOB-026.

## Evidence

Commands actually run:

- A count of rejected.json: 100 rows, keys id, issues, review_status, ids kp-001–kp-100, no Khmer field. All 100 ids are in the -f export with nonempty khmer. Live scale rows for those ids have candidates and metadata.jev.applied true. holdout ids in rejected.json: 0.
- PYTHONPATH=src .venv/bin/python data/outputs/voice_training/2026-10-28-spoken-next4/write_train_next4.py wrote 200 rows, kp-2601–kp-2800, licence unknown, pending_native_review, holdout_filled_on_scale 0. Prior sha256 values were unchanged.
- Fill pid 82656, ppid 1: fill_next4.py --limit 200 --max-minutes 90. Log ends:

```
ROW kp-2769 STOP time_budget
FILL_DONE {"source_rows": 200, "with_candidates": 167, "filled": 167, "last_id": "kp-2768", "next_id": "kp-2751", "still_empty": 33, "stop_reason": "time_budget", "jev_ranked_this_process": 166, "weights_written": false, "training_started": false}
```

- Resume pid 84437, ppid 1: fill_next4.py --limit 33 --max-minutes 49.5. Log ends:

```
ROW kp-2800 33/33 candidates=3 jev=applied status=pending_native_review origin=gemini_teacher license=unknown
FILL_DONE {"source_rows": 200, "with_candidates": 200, "filled": 33, "last_id": "kp-2800", "next_id": "", "still_empty": 0, "stop_reason": "", "jev_ranked_this_process": 33, "weights_written": false, "training_started": false}
```

- The log also has `ROW kp-2700 100/200 candidates=3 jev=not_applied`. No other fill process was running after the resume exited.
- .venv/bin/python -m py_compile on fill_next4.py, write_train_next4.py, and package_next4.py exited 0.
- PYTHONPATH=src .venv/bin/python data/outputs/voice_training/2026-10-28-spoken-next4/package_next4.py printed sft_count 1799, last_filled_id kp-2800, next4_filled 199, next4_empty 1, sidecar_count 199, grant_count 1799, holdout_ids_in_export 0, holdout_filled 0, ranked_this_pass 0, needs_rank_before 1, started false, weights_written false, trainer_start_called false. Prior export sha256 values were unchanged.
- A later read: export 1799 unique ids, holdout 0, licence only unknown, split only train, started only false, kp-2700 absent, new-id gap only 2700. Grant 1799 ids, holdout 0. Sidecar 199 ids, kp-2601–kp-2800 except kp-2700. Live next4 review fields were still pending_native_review and licence unknown. Candidates empty 0. Stored Jev 199. No-Jev id kp-2700. holdout_filled 0. Prior line counts stayed 720, 758, 1000, 1200, 1400, and 1600. JOB-026 status in .agents/jobs/active.yaml is still IN_PROGRESS. No trainer process was running.
- tests/python/test_datasets.py and tests/python/test_llm_benchmark.py were not run.

## Risks

- Licence remains unknown. The sidecar and the grant are not a native gold mark. Jev ranking is not native review. The live rows stay pending_native_review.
- kp-2700 has three Gemini candidates and no stored Jev line. It is not in the export, the sidecar, or the grant. A later rank can be tried without a new Gemini call. The row was not marked gold.
- 1,799 packaged lines are not 10,000 reviewed rows.
- The new export is a snapshot of stored Jev lines. It is not a trained model and it was not promoted.

## Not done

- Holdout kp-1001–kp-2000 was not filled. holdout_filled stayed 0.
- No row was marked gold or human-reviewed. No live review field was edited.
- kp-2700 still has no stored Jev line.
- No 3B, 7B, 8B, or 14B weights were trained. trainer.start was not called. No Hugging Face Job was started.
- 10,000 reviewed rows remain a target. JOB-026 stays IN_PROGRESS.
- No commit and no push.
