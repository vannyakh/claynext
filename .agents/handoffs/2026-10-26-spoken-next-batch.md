# Handoff

- Job: JOB-026
- From: dataset-engineer
- To: cto
- Status: REVIEW
- Date: 2026-10-26

JOB-026 stays IN_PROGRESS. The 10,000 reviewed-row target is not met. This pass adds 200 new train-pool source rows in a separate file and starts one candidate fill on that file only.

## Scope

Paths touched:

- data/khmer_spoken/workspace/spoken_train_next.jsonl (new, 200 source rows)
- data/outputs/voice_training/2026-10-26-spoken-next/write_train_next.py (new)
- data/outputs/voice_training/2026-10-26-spoken-next/fill_next.py (new)
- data/outputs/voice_training/2026-10-26-spoken-next/fill_next.log (fill still writing)
- .agents/handoffs/2026-10-26-spoken-next-batch.md

Not touched: data/khmer_spoken/workspace/spoken_scale.jsonl, the locked holdout kp-1001–kp-2000, data/khmer_spoken/versions/translate-sft-spoken-20261026-c/sft-train-approved.jsonl, data/khmer_spoken/versions/translate-sft-spoken-20261026/sft.jsonl, the 758-row -b export, fill_scale.py, job YAML status. No commit. No push.

## What changed

- The 2,000-row author is `data/outputs/voice_training/2026-10-23-spoken-500/write_scale_sources.py`. It copies kp-001–kp-500 and then takes a finite handwritten bank (`scale_drafts_a.py`, `scale_drafts_b.py`, `scale_drafts_c.py`). It is not a template stamper. The bank has 1,522 unique lines. After the 2,000-row cut, 11 lines were unused. The 2,000 source texts are 2,000 unique normalized lines. No 6-word opening is repeated 3 or more times. Cloning templates was not used.
- New file: `data/khmer_spoken/workspace/spoken_train_next.jsonl`, 200 rows, ids kp-2001–kp-2200. 11 rows are the unused bank lines (`situation_kind` bank_leftover). 189 rows are new situations (barber, harvest, moto repair, tailor, wedding kitchen, library, print shop, rooftop tank, volleyball). A gate refused exact normalized copies, content-word overlap at or above 0.42, and shared content 5-grams against kp-001–kp-2000 and inside the new file. The gate passed, so the file was written.
- Licence on every new row is `unknown`. `review_status` is `pending_native_review`. Origin at write time was `synthetic`. Not human. Not gold. `approved_text` and `verified_by` are empty. These rows are not in the owner training grant.
- One fill is running: pid 64817, ppid 1, `fill_next.py --limit 200 --max-minutes 90`. It reads only `spoken_train_next.jsonl` and refuses ids kp-1001–kp-2000. An earlier nohup pid 64646 printed the first FILL line and died before saving a row. It is not running. Pid 64817 is the only fill.
- At the snapshot after the third saved row: filled kp-2001–kp-2003, 3 candidates each, Jev applied, status still `pending_native_review`, licence `unknown`, origin `gemini_teacher` on those filled rows. The other rows were still `synthetic`. The fill was still running. Those three rows were not approved.
- dry_run on weights: no weights. `trainer.start` was not called. peft and mlx_lm were not installed. No 3B, 7B, 8B, or 14B fine-tune was started. No Hugging Face Job was started.

## Evidence

Commands actually run:

- A count of the draft bank against `spoken_scale.jsonl`: draft_lines 1522, unique_drafts 1522, unused_exact 11, unused near-overlap 0, scale_rows 2000, scale_unique_norm 2000, prefixes repeated 3 or more times 0, holdout_filled 0.
- `ps -ax` before the write found no `fill_scale.py`, `fill_next.py`, or `fill_kp` process.
- `PYTHONPATH=src .venv/bin/python data/outputs/voice_training/2026-10-26-spoken-next/write_train_next.py` wrote 200 rows, kp-2001–kp-2200, kinds bank_leftover 11 and new_situation 189, licence unknown, review pending_native_review, origin synthetic, holdout_filled_on_scale 0, scale sha256 unchanged `c9a14bfaacf91261c6f3b88502afd3761c7dd6ad0b3131fcb03ed9dc54ddb662`, weights_started false.
- `ps` again found no fill. nohup pid 64646 exited before a ROW line and did not write candidates. A detached nohup then started pid 64817 (ppid 1).
- Log `data/outputs/voice_training/2026-10-26-spoken-next/fill_next.log` begins:

```
FILL empty=200 batch=200 gemini_available=True jev=True max_minutes=90.0
FILL empty=200 batch=200 gemini_available=True jev=True max_minutes=90.0
ROW kp-2001 1/200 candidates=3 jev=applied status=pending_native_review origin=gemini_teacher license=unknown
ROW kp-2002 2/200 candidates=3 jev=applied status=pending_native_review origin=gemini_teacher license=unknown
ROW kp-2003 3/200 candidates=3 jev=applied status=pending_native_review origin=gemini_teacher license=unknown
```

- A later read of the new file, while pid 64817 was still the only matching process, showed next_rows 200, filled 3 (kp-2001–kp-2003), reviews only pending_native_review, licence only unknown, approved 0, gold or human origin 0. `spoken_scale.jsonl` was still 2000 lines, sha256 `c9a14bfaacf91261c6f3b88502afd3761c7dd6ad0b3131fcb03ed9dc54ddb662`, holdout_filled 0. No trainer process was in that process list.

## Risks

- Pid 64817 rewrites `spoken_train_next.jsonl` after each row. Do not approve rows in that live file. Do not start a second fill. The batch limit is 200 and the time limit is 90 minutes.
- The first FILL line in the log is from dead pid 64646. The saved rows belong to pid 64817.
- Licence remains unknown. Jev ranking is not native review and is not gold. The new rows are not covered by the kp-001–kp-1000 training-use grant.
- 200 new situations are not 10,000 reviewed rows. Further growth still needs new source dialogue, not copies of these lines.

## Not done

- The fill has not finished. Most of kp-2004–kp-2200 were still empty at the snapshot.
- Holdout kp-1001–kp-2000 was not filled. holdout_filled stayed 0.
- No row in the new file was approved.
- No 3B, 7B, 8B, or 14B weights were trained. `trainer.start` was not called. JOB-011, JOB-019, JOB-020, JOB-021, and JOB-022 stay BLOCKED.
- 10,000 reviewed rows remain a target. JOB-026 stays IN_PROGRESS.
- No commit and no push.
