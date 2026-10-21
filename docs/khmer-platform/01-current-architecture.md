# Current architecture assessment (Oct 2026)

Scope: what the character-aware Khmer dubbing platform can build on. Audited on `main` (clean tree).

## Headline findings

1. **The Khmer localization engine already exists (milestone 1)** in `src/claynext/models/khmer_localization/`
   (pronoun resolver, relationship graph, speech profiles with per-project persistence, slang/profanity caps,
   post-check, TTS normalizer, offline evaluator). Design: `docs/khmer-localization/DESIGN.md`. It is off by
   default (`skill_khmer_natural_dialogue`). New work must extend it, not re-create it.
2. **The pronoun YAML already exists** at `src/claynext/prompts/dictionaries/khmer/pronouns.yaml` (with
   `regional.yaml`, `profanity.yaml`, `tts_pronunciation.yaml`), all `pending_native_review`, regional and profanity
   entries unverified. That is where relationship → pronoun rules belong, not `prompts/languages/`.
3. **There was no dataset layer.** Evaluation sets are hand-written JSONL in `prompts/evaluations/`
   (100 pronoun cases, 17 translation cases). There was nothing for import, review state, dedupe, splits, or versions.
   Phase 1 adds that (`src/claynext/models/datasets/`).
4. **OpenAI is already a provider** in `llm_providers.CHAT_PROVIDERS` (`gpt-4o-mini`), with keys in the rotating pool
   (`llm_keys.ApiKeyPool`, SQLite store, RPM limits, cooldowns, token logging). `llm_chat.chat_text` is a single
   untyped call: no structured output, no retries for 5xx or timeouts, no cancellation, no tracing, no cost.
5. **Translation is coupled to providers inside one class.** `translate_service.TranslateEngine` (1,241 lines)
   mixes prompt building, batching, provider HTTP (Gemini, chat, Ollama, SGLang, NLLB, Google), and Khmer timing.
   `movie_translate.resolve_movie_engine_chain` picks a fallback chain. Skills (`prompts/registry.py`) already separate
   prompt templates and contracts from the call.
6. **Rust owns the hot paths that exist today** (`claynext-ai`: speech quota, prompts, VAD, OCR, key-pool choice;
   `claynext-ffmpeg`: probe, decode, export). Nothing in the dataset or localization layer is a hot path yet.
7. **Testing is runner-based, not pytest.** pytest is not installed; most suites have a `__main__` runner.
   `test_translate_service.py` imports pytest and cannot run in this venv.
8. **A parallel `src/claynext/voice_training/` package** (speech audio datasets, rights gates) appeared during this work
   and is untracked. It defers language data to `claynext.models.datasets`, which matches this plan.

## Module map

| Module | Role | Reuse for the platform |
|:---|:---|:---|
| `models/movie_translate.py` | Film dialogue translate entry: engine chain, cast merge, Google fill, skill session choice | Keep as orchestration entry; route new localization through it |
| `models/translate_service.py` | `TranslateEngine`: batching, prompts, provider calls, speech quota (via `get_dubbing_adapter`) | Reuse batching + quota; move provider HTTP behind the gateway over time |
| `models/llm_keys.py` | Rotating key pool, RPM/RPD limits, usage log | Reused unchanged by the gateway |
| `models/llm_providers.py` | OpenAI-compatible platform table (incl. `openai`) | Reused as the gateway's provider registry |
| `models/llm_chat.py` | One chat call via the pool | Superseded by `llm_gateway` for new code; keep for current callers |
| `models/ai_provider.py` | `AiProvider` protocol (transcribe / complete / speak) | Overlaps the gateway; unify later (backlog) |
| `models/dub_project.py` | Project JSON save / load / recent list | Character profiles stay per project via `LocalizationStore` |
| `models/tts_service.py` | `TTSEngine`: Edge, Kitten, VoxCPM, OmniVoice, ElevenLabs, SGLang | TTS stays here; Khmer `tts_text` should feed it (backlog) |
| `models/dubbing_service.py` | `DubbingEngine`: stems, fit to soundtrack, per-line TTS, mix | `normalize_for_tts` hook point documented in DESIGN.md |
| `models/character_intel/` | Character registry, voice casting, prosody | Source of `character_id` for speech profiles |
| `models/khmer_localization/` | Pronouns, relationships, profiles, post-check, evaluator | The localization engine; extend |
| `prompts/` | Skill registry, Jinja/portable templates, JSON contracts, validator, language profiles (`languages/english.yaml`, `khmer.yaml`), Khmer dictionaries | Prompt + contract home; gateway reuses `validator.schema_errors` |
| `adapters/` + `rust_bridge/` | Domain facades over Rust binaries, Python fallbacks | Use for any future Rust dataset hashing |
| `backends/ai-runtime`, `crates/editor-*` | Rust CLI tools and shared domain crates | Candidate home for large-scale near-dup hashing later |

## Data flow today

```text
Translate:  GUI/CLI → movie_translate.translate_movie_dialogue
              → resolve_movie_engine_chain (gemini → chat providers → ollama → sglang → nllb → google)
              → _open_translation_skill (khmer_natural_dialogue if enabled, else dialogue_translation, else legacy)
              → TranslateEngine._translate_llm / _skill_batch → provider HTTP via key pool
              → post-check + run log (skill_runs/…) → _merge_cast → _fill_untranslated (Google)
Dub:        DubbingEngine → stems (Demucs) → fit lines to soundtrack (claynext-ai VAD)
              → _speak_lines (TTSEngine.synthesize per line, workers) → align speed / duck (get_dubbing_adapter) → mux
```

## Technical debt that matters for this platform

- Provider HTTP is duplicated (`llm_chat`, `TranslateEngine._gemini_generate`, `_ollama_generate`, `sglang_omni`).
- `TranslateEngine` is a static-method god class; hard to test without patching.
- No request tracing or per-job cost; usage is logged per key only.
- Khmer `tts_text` is not used by TTS yet (hook documented, not wired).
- Every Khmer dictionary and evaluation case is unreviewed; nothing can be called ground truth yet.
- `test_translate_service.py` depends on pytest, which the venv does not have.
