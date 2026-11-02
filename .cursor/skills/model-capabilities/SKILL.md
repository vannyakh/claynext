---
name: model-capabilities
description: >-
  States what each wired Claynext Studio model can and cannot do. Use when
  choosing or describing Gemini, TypeSafe Jev, faster-whisper, WhisperX,
  Edge TTS, VoxCPM, OmniVoice, Ollama (aya-expanse:8b, qwen2.5:7b, qwen3:8b),
  the spoken-Khmer fixture lookup, a benchmark promotion, or a fine-tune.
---

# Model capabilities

Read the code path before claiming a model did something. This skill covers only the models wired below.

If `trainer.start` returns `status` `refused` or `dry_run`, or `started` is false, do not claim a fine-tune happened. Approval does not override that. No chrF, COMET, human score, or “beats GPT” unless a file in the repo records that measurement.

## Gemini pool

Code: `src/claynext/models/llm_keys.py` (`KeyPool.call_with_rotation`), `src/claynext/models/khmer_spoken/providers/google_gemini_provider.py` (`GeminiTeacherProvider`), `src/claynext/models/khmer_spoken/datasets/gemini_candidate_generator.py`.

- Can do: teacher candidates for pending spoken rows; roll to the next enabled key on HTTP 429. Studio translation also calls Gemini through `translate_service.py`.
- Cannot do: weight training. `GeminiTeacherProvider.capabilities` sets `supervised_fine_tuning` false. `vertex_tuning_client.py` does not accept an AI Studio key as a tuning credential, and this skill does not call Vertex.

## TypeSafe Jev

Code: `src/claynext/models/jev_decisions.py` (`rank_khmer_candidates`). Key name in the pool: `typesafe` (`TYPESAFE_API_KEY`).

- Can do: typed judgments that rank or drop existing Khmer candidates.
- Cannot do: write the translation. With no key, `rank_khmer_candidates` returns `{applied: false, reason: "no_key"}` and leaves the row unchanged. A failed call does not raise and does not invent a line.

## faster-whisper and WhisperX

Code: `src/claynext/models/asr_service.py` (`ASREngine` loads `faster_whisper.WhisperModel`), `src/claynext/models/dubbing_plan.py` (`whisperx_available`, `build_dubbing_plan`), `src/claynext/models/dubbing_service.py`.

- Can do: ASR. Dubbing uses WhisperX when the package imports and a Hugging Face token is present. Otherwise dubbing uses Faster-Whisper. `prefer_whisperx` defaults to `"1"` in `src/claynext/utils/config.py`. Preflight says a missing WhisperX install falls back to Faster-Whisper.
- Cannot do: translation training or a Khmer fine-tune.

## Edge voices, VoxCPM, OmniVoice

Code: `src/claynext/models/tts_service.py` (`TTSEngine`). Edge uses `edge_tts`. VoxCPM default repo is `openbmb/VoxCPM2`. OmniVoice default repo is `k2-fsa/OmniVoice`.

- Can do: synthesize speech from text already in hand.
- Cannot do: translation training, candidate ranking, or a spoken-Khmer SFT run.

## Ollama tags in this repo

Code: `src/claynext/models/movie_translate.py` (local order includes `qwen3:8b`, `aya-expanse:8b`, `qwen2.5:7b`), `src/claynext/models/benchmarks/probe.py` (`OLLAMA_CANDIDATES`).

- Can do: local inference when that tag is already installed in Ollama.
- Cannot do: a fine-tune on this 16 GB M4. `src/claynext/models/training/trainer.py` `start(..., approval=True)` still returns `refused` for the 3B, 7B/8B, and 14B configs. `started` stays false and `weights` stays null.

## Spoken-Khmer test model

Code: `src/claynext/models/training/spoken_fixture.py`. Card: `data/khmer_spoken/versions/translate-sft-spoken-20261026-b/model-card.md`. Rows: `sft-train-approved.jsonl` (758, kp-001–kp-758).

- Can do: return the stored Jev line for an approved train id or the exact source string.
- Cannot do: free generation, 7B/14B inference, or promotion. Holdout ids kp-1001–kp-2000 come back `refused_holdout` with an empty line. Any other miss comes back `not_in_test_set` and the message `source is not in the test set`. Licence on those rows stays `unknown`. The owner grant is training use, not CC-BY.
- Read `status` and `message` on the lookup dict. `coerce_output` keeps only `text`. Empty `text` is a miss, not a translation.

## Benchmark promotion gate

Code: `src/claynext/models/benchmarks/promotion.py` (`evaluate_promotion`).

- Can do: return `not_promoted` until a human review record fills the gates (two reviewers, dimension targets, baseline, zero critical semantic regressions, a deployable licence, CTO flag, QA flag).
- Cannot do: promote from automatic metrics, a synthetic fixture, or this lookup model. Missing reviews stay `promoted: false`.

## Do not

- Call Vertex or install peft from this skill.
- Train on kp-1001–kp-2000.
- Edit `data/khmer_spoken/workspace/spoken_scale.jsonl` while `fill_scale.py` is running, or start a second fill.
- Rewrite `data/khmer_spoken/versions/translate-sft-spoken-20261026/sft.jsonl`.
- Mark the fixture, a Gemini teacher pass, or a Jev rank as a fine-tune.
