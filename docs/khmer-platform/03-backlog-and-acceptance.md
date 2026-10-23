# Backlog and acceptance tests

## First milestone acceptance tests

Milestone = Dataset Manager + Provider Gateway + Localization Engine wired to a translation and evaluation pipeline.

| # | Test | Status |
|:---|:---|:---|
| 1 | KSLD v0.1 (`dialogues.jsonl` and `.csv`) imports with 0 rejects; CSV and JSONL give identical records | pass |
| 2 | Synthetic record cannot be `gold` without a human reviewer + timestamp; gold needs a licence | pass |
| 3 | Re-running dedupe and split with the same seed gives identical output; no group or near-dup cluster crosses splits | pass |
| 4 | A version snapshot is read-only, hashed, chained to its parent; an unchanged working set cannot be re-snapshotted | pass |
| 5 | SFT export contains only `reviewed`/`gold` unless `--include-unreviewed`, and the manifest says so | pass |
| 6 | A filled review sheet sets `reviewed`/`rejected`, adds the human correction as preferred candidate, never sets gold | pass |
| 6b | Review sheet export has `reviewed_at`; apply prefers the sheet timestamp; promote blocks gold for unreviewed synthetic or unlicensed records and allows it for reviewed, licensed human-authored records | pass |
| 7 | Gateway: structured output validated, invalid output retried, 5xx/timeout retried, 4xx not, cancellation honoured, keys never in traces/errors | pass (fakes) |
| 8 | Engine translates the KSLD test split through the gateway with pronoun plan + post-check, run log carries trace ids | pass (fakes) |
| 9 | Eval report per dataset version × provider × prompt version: pronoun accuracy (evaluator), post-check violations, cost | pass (fakes) |
| 10 | At least one reviewed slice (≥100 records) from native review | blocked on humans |

## Prioritized backlog

P0 (finish milestone)
1. ~~Wire `khmer_localization` skill calls through `llm_gateway` (opt-in provider), log `trace_id` per chunk.~~ done: `skill_khmer_gateway=1` or a provider on the session.
2. ~~Evaluation runner: dataset test split → engine → evaluator + post-check → report JSON under `data/outputs/eval/`.~~ done: `run_evaluation`.
3. ~~`llm_chat.chat_text` on the gateway (same signature) so existing callers get retries and tracing.~~ done: `chat_text` / `chat_through`; `last_chat()` holds the trace.
4. ~~Review sheet export (`claynext dataset review-export`)~~ done: includes a `reviewed_at` column.

P1
5. ~~`claynext dataset promote`~~ done: transition rules, human-review and licence checks.
6. ~~Category mapping for KSLD `care` / `surprise` / `excited`~~ done: family / everyday / comedy_sarcasm (`ksld_v0_1` v0002).
7. Few-shot retrieval from reviewed records for the localization prompt (by relationship + emotion).
8. GUI: dataset report + review queue page (`Worker`/`QThreadPool`, theme tokens, read-only first).
9. Unify `models/ai_provider.AiProvider` and `llm_gateway.LlmProvider`.
10. Pricing config file for cost tracking (user-supplied; no built-in price list).

P2
11. Rust `claynext-ai near-dups` (MinHash LSH) behind `get_ai_adapter()` with the Python fallback, once datasets pass
    ~200k rows or dedupe exceeds a few seconds. Pure Python today: 1,000 rows in well under a second.
12. Hosted fine-tuning job runner (after availability check and a gold set exists).
13. `tts_text` normalization into `DubbingEngine` for Khmer.
14. Port `test_translate_service.py` off pytest or add pytest to the dev group (needs a deliberate `uv` change).
