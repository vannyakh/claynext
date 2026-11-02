# LLM training and benchmark audit (2026-10-22)

Scope: what already exists for Khmer dialogue measurement and training, and what this milestone adds. This note does not replace `01-current-architecture.md`. That October note still says the dataset layer was missing; `models/datasets/` and `models/llm_gateway/` have since shipped (JOB-101, JOB-102).

## Call path

```text
GUI/CLI → models → adapters → rust_bridge → backends/* or crates/editor-*
```

Benchmark and training code in this milestone stays in `models/`. It does not import `rust_bridge` and it does not add a GUI page.

## What already existed

| Module | What it does | What it does not do |
|:---|:---|:---|
| `models/datasets/` | Import, validate, dedupe, group split, review, promote, SFT export. `split.find_leaks` catches a group that sits in two splits. | No held-out movie benchmark schema with an explicit test lock. |
| `models/llm_gateway/` | OpenAI-compatible chat, retries, traces, caller-supplied `Pricing`. `chat_text` in `llm_chat.py`. | Gemini is not in `CHAT_PROVIDERS`. No built-in price list. |
| `models/khmer_spoken/providers/google_gemini_provider.py` | AI Studio teacher over the existing key pool. | Not a benchmark runner. Not Vertex tuning. |
| `models/evaluation/runner.py` | `run_evaluation` scores a dataset **test** split with a callable or gateway provider, then the Khmer pronoun resolver and post-check. Cost is the trace cost only. | No promotion gate, no human rubric, no leakage refusal by dialogue family before the call. |
| `models/khmer_localization/` | Pronoun resolver, post-check, evaluator. Dictionaries are `pending_native_review`. | Not a movie-dialogue leaderboard. |
| `models/khmer_spoken/evaluation/khmer_translation_benchmark.py` | Character-overlap harness and an optional judge flag. | Overlap is not chrF or COMET. Do not treat it as a quality score. |
| `models/khmer_spoken/training/local_lora_stub.py` | `plan_local_lora` returns refused. | Does not train. |
| `models/khmer_spoken/training/vertex_tuning_client.py` | Hosted tuning client. | JOB-011 stays blocked. Not called by this milestone. |
| `voice_training/training/tts_trainer.py` | Speech dry-run. | Not an LLM LoRA trainer. |
| `prompts/evaluations/khmer_pronoun_cases.jsonl` | Draft pronoun cases. | `pending_native_review`. Not a locked gold movie set. |

`AiProvider` and the gateway are still two paths (JOB-007, still READY).

## What this milestone adds

- `models/benchmarks/` — row schema, family leakage refusal, split lock, blind prompt, metric structures, human rubric, promotion gate, leaderboard, runner that wraps `run_evaluation`.
- `models/training/` — SFT+LoRA, QLoRA 7B/8B, QLoRA 14B, and DPO YAML. `start` validates and refuses a real GPU job. 7B/8B/14B are blocked on this 16 GB M4. 3B is not started either: it is not a tiny adapter and no trainer library is launched.
- Tests: `tests/python/test_llm_benchmark.py`, `tests/python/test_llm_training_config.py`.

## Not available as gold

- No files under `data/datasets/`.
- `prompts/evaluations/khmer_pronoun_cases.jsonl`: 100 rows, all `pending_native_review`.
- `data/khmer_spoken/versions/owner-approved-20261022/dialogue.jsonl` has 55 rows with `review_status: gold`, `verified_by: project-owner`, and `origin: gemini_teacher`. The reviewer note on each row says the seed status is `pending_native_review` and the line is an unverified stub. Licence is `unknown`. The manifest says synthetic text is not gold. This milestone does not accept those rows as a gold set.
- `data/khmer_spoken/fixtures/dialogue_100.jsonl`: 100 rows, all `pending_native_review`.
- This audit did not run `data/outputs/voice_training/2026-10-22-ai-first/run_ai_first.py`.

## Hardware

Apple M4, 16 GB RAM. During this session `ollama ps` showed no model loaded. Installed names included `aya-expanse:8b`, `qwen2.5:7b`, and `qwen3:8b`. Free pages were about 150 MB and the machine was already swapping, so an 8B generation was not started. 7B/8B/14B fine-tunes do not fit. `trainer.start` also refuses a 3B run on this machine, including when approval is set.

## 500-row plan (2026-10-23)

The owner replaced the 80/20 held-out plan with a larger spoken pool. `data/khmer_spoken/versions/heldout-locked-20261023-kp081-100/` is still 80 train / 20 test and is not deleted. The new rule is in `models/benchmarks/spoken_split.py` and `data/khmer_spoken/versions/spoken-500-train100-spec-20261023/split.json`.

When 500 spoken rows exist, train is exactly 100 rows. The other 400 are locked and must not be used to train or tune. Assignment is by dialogue family with seed 13, so a family is not split across the two sides. Until kp-101–kp-500 exist, that spec says the locked pool is incomplete and must not be treated as the 1,000–2,000 native gold benchmark.

The 100 Jev-ranked rows already on disk are synthetic/`gemini_teacher` with licence `unknown`. They stay `not_promoted`. They are not the KSLD gold set. Targets that are still unmet: 10,000–30,000 reviewed training examples, and 1,000–2,000 native-reviewed benchmark rows. A capped probe is not a promotion.

`models/benchmarks/comparison.py` is the A–E report shape (untuned, prompted baseline, LoRA/QLoRA, DPO if present, hosted GPT/Gemini). Quality, latency, VRAM, cost, and regression risk stay null until measured. Cost comes from a caller-supplied price or a provider trace. The judge prompt does not include the model name. The report does not promote and does not declare a winner.

GPU training stays blocked on this 16 GB machine. DPO stays blocked until human preference pairs exist. Hosted scoring stays blocked until a native gold set exists. Filling kp-101 onward is a separate process and is not started from this spec. One observed batch exited after writing candidates for kp-101 through kp-120. The locked pool is still incomplete.

## Scale cut (2026-10-23)

The owner set the forward targets at 10,000–30,000 dataset rows and a 1,000–2,000 held-out benchmark, and named 3B, 7B/8B, and 14B. That message allows Gemini candidate generation on the existing key pool and Jev ranking when a typesafe key is already stored. It does not allow a Vertex fine-tune or a local weight update. `trainer.start` still refuses 3B, 7B, 8B, and 14B on this 16 GB M4, including when approval is passed. No 7B or 14B weights were downloaded.

`plan_spoken_split` is unchanged: train cap 100, target 500. Its version directories were not deleted. The forward id rule is `plan_scale_holdout`. Once a file has at least 1,000 kp ids, the last 1,000 are locked and earlier ids are the train pool for a later adapter. Until that lock exists, every id outside the lowest 100 stays locked. The cut is frozen in `data/khmer_spoken/versions/scale-lock1000-20261023/` and must not slide if more rows are appended later.

This turn stopped at 2,000 source rows in `data/khmer_spoken/workspace/spoken_scale.jsonl` (kp-001–kp-2000). Writing 10,000 unique lines in one pass would have been thinner copies of the same templates. Train ids are kp-001–kp-1000. Locked ids are kp-1001–kp-2000. `spoken_500.jsonl` is still the 500-row file. New lines are original synthetic English, licence `unknown`, `pending_native_review`, not gold. The locked 1,000 rows are not the native-reviewed benchmark. 10,000–30,000 reviewed training rows and 1,000–2,000 native-reviewed benchmark rows remain targets. No chrF, COMET, or human score was measured. Promotion stays `not_promoted`. Gemini is the teacher and Jev is the ranker. Neither one updates weights.
