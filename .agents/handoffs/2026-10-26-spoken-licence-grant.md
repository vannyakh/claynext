# Handoff

- Job: JOB-026
- From: model-training
- To: cto
- Status: REVIEW
- Date: 2026-10-26

## Scope

Paths touched:

- data/khmer_spoken/versions/owner-licence-grant-20261026/ (new)
- data/khmer_spoken/versions/translate-sft-spoken-20261026-b/ (new)
- data/outputs/voice_training/2026-10-26-spoken-licence-grant/record_grant_and_export.py (new)
- .agents/jobs/active.yaml
- .agents/handoffs/2026-10-26-spoken-licence-grant.md

Read only: data/khmer_spoken/workspace/spoken_scale.jsonl, the scale lock, and data/khmer_spoken/versions/translate-sft-spoken-20261026/sft.jsonl. That 720-line file was not rewritten. trainer.py was not changed. No commit. No push.

## What changed

- dry_run: true. The project owner approved training use of spoken Khmer train-pool rows while `license_type` stays `unknown`. The quote is recorded as written: "if licence is still unknown i approve you do sometihnk and continue trained." The grant is project-owner approval to train on these rows despite unknown licence. It is not CC-BY and not any other external licence.
- Grant path: `data/khmer_spoken/versions/owner-licence-grant-20261026/`. Included ids: kp-001–kp-758 (758 rows, no gaps). Holdout kp-1001–kp-2000 is not in the grant and was not changed. Empty train rows kp-759–kp-1000 were not included because they had no Jev line in the snapshot.
- SFT path: `data/khmer_spoken/versions/translate-sft-spoken-20261026-b/sft-train-approved.jsonl`, 758 rows. Fields: id, source, khmer (Jev line), licence unknown, owner_training_approved true, split=train. Holdout ids in the file: 0. The open file `translate-sft-spoken-20261026/sft.jsonl` is still 720 lines.
- trainer.start was called with approval true. The 3B SFT config, the 7B/8B config, the 14B config, and the DPO config each returned status refused, started false, weights null. Exact reason: "this M4 has 16 GB RAM; 3B/7B/8B/14B fine-tunes are not started (7B/8B/14B do not fit; 3B is not a tiny adapter)". No weights were written. No weights were uploaded. peft was not installed. Vertex was not called. Promotion stays not_promoted. chrF, COMET, and human scores were not measured.
- Fill pid 58618 was alive before and after the snapshot (`--limit 280 --max-minutes 80 --write-split`, ppid 1). Log tail at the read: ROW kp-758. No second fill was started. spoken_scale.jsonl was not edited by this pass.

## Evidence

Commands actually run:

- `ps -p 58618` showed pid 58618, ppid 1, `fill_scale.py --limit 280 --max-minutes 80 --write-split`.
- `PYTHONPATH=src .venv/bin/python data/outputs/voice_training/2026-10-26-spoken-licence-grant/record_grant_and_export.py` wrote the grant and the 758-row SFT file and called trainer.start. Printed id_range kp-001–kp-758, trainer_started false, weights_written false, fill_alive_after true, second_fill_started false.
- A read-back confirmed 758 SFT rows, ids contiguous kp-001–kp-758, licence unknown, owner_training_approved true, split train, holdout ids 0, and the same 758 ids in the grant list. The open sft.jsonl still has 720 lines. `git diff --stat -- src/claynext/models/training/trainer.py` was empty.
- After the script, `ps -p 58618` still showed the same fill command.

## Risks

- Pid 58618 is still filling past kp-758 and rewrites spoken_scale.jsonl after each row. Do not start a second fill. Rows saved after this snapshot are not in the grant or the new SFT file.
- Licence unknown remains the row licence. The grant does not make these rows a native gold benchmark.
- On 42 gold rows the stored approved line and the Jev line differ. The export khmer field is the Jev line. No weights were trained on it.

## Not done

- Train pool kp-759–kp-1000 was not filled yet at the snapshot. The live fill is capped at 280 rows from kp-721 and at 80 minutes, so it stops at kp-1000.
- No 3B, 7B, 8B, or 14B weights were trained. JOB-011, JOB-019, JOB-020, JOB-021, and JOB-022 stay BLOCKED.
- 10,000 reviewed rows and the 1,000–2,000 native-reviewed benchmark are still targets.
