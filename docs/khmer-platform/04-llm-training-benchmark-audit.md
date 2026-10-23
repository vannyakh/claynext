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

Apple M4, 16 GB RAM. During this session `ollama ps` showed no model loaded. Installed names included `aya-expanse:8b`, `qwen2.5:7b`, and `qwen3:8b`. Free pages were about 150 MB and the machine was already swapping, so an 8B generation was not started. 7B/8B/14B fine-tunes do not fit.
