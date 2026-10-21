# AI Skills & Prompt Engineering — Migration Plan

Status: **Milestone 1 done** (registry + `movie.dialogue_translation` v1.0.0, off by default).

Skills **guide** a model: instructions, a typed contract, language notes, and a
glossary. They do not train a model and add no new capability. A skill is
data plus a contract. It never opens media files, calls a backend, or touches
a widget. The caller sends the rendered prompt through its existing provider
path.

---

## 1. Layout

```text
src/claynext/prompts/
  __init__.py            get_registry(), Skill, SkillRegistry
  registry.py            discovery, id@version lookup, deps + capability resolve,
                         render(), validate_input(), validate_output() (+ id coverage)
  loader.py              skill.yaml / language / schema / system loading
                         (PyYAML, or a block-YAML subset fallback)
  renderer.py            sandboxed Jinja2 (StrictUndefined), or a portable-subset fallback
  validator.py           JSON Schema subset validator (+ Pydantic when installed)
  contracts.py           Pydantic models mirroring the JSON schemas
  versioning.py          SemVer, specs (^ ~ >= < , exact), file fingerprints, lock file
  translation.py         movie.dialogue_translation session for the translate path
  evaluation.py          offline regression runner over JSONL cases
  versions.lock.json     pinned fingerprint per id@version
  system/                core.md, json_output.md (shared guardrails)
  skills/dialogue_translation/{skill.yaml, prompt.j2}
  languages/{khmer,english}.yaml   instructions, examples, glossary
  schemas/translation.schema.json, dialogue_translation.input.schema.json
  evaluations/translation_cases.jsonl
```

Data files ship in the wheel through hatch's default package inclusion
(`packages = ["src/claynext"]`, none of these paths are gitignored); no
`pyproject.toml` change.

### Library availability and fallbacks

| Library | In `.venv` | Declared dependency | Fallback |
|:---|:---|:---|:---|
| PyYAML 6.0.3 | yes | no (transitive) | block-YAML subset parser in `loader.py` |
| Jinja2 3.1.6 | yes | no (transitive) | portable-subset renderer in `renderer.py` |
| Pydantic 2.14.1 | yes | no (transitive) | JSON Schema subset validator (always runs) |

Tests force every fallback and check that both parsers, both renderers, and
both validators produce the same results on all shipped files and cases.

---

## 2. Rust vs Python prompt decision

The workspace rule says that dub and translate prompts belong in Rust
(`claynext-ai build-dub-prompt` / `build-translate-prompt`). This milestone
adds versioned templates in Python. The two are reconciled like this:

1. **The legacy path stays the default.** With the setting off, the Rust
   `build-dub-prompt`, which falls back to `TranslateEngine._dub_prompt`, is
   untouched. Backend request bodies stay byte-for-byte the same, and a test
   pins this.
2. **Templates are data, not code.** `skill.yaml`, `prompt.j2`, the schemas, and
   the language files are versioned assets. Python only renders them. That is
   orchestration (string assembly, once per batch of at most 16 lines), not a
   hot path.
3. **Numbers still come from Rust.** Speech quotas (`speech-quota`), spoken
   units, and the overflow tighten pass (`build-fit-prompt`) still go through
   `get_dubbing_adapter()` and are passed into the skill as inputs. The skill
   does not compute timing.
4. **Later convergence.** The template subset (`{{ }}`, `if`/`else`, `for`,
   `tojson`) was picked to be valid MiniJinja. If prompt building has to live
   in Rust later, `claynext-ai render-skill` can load the same files, and the
   JSON schemas can be checked there.

---

## 3. Existing AI workflows → skill interfaces

| Workflow | Today (file · function) | Model use | Proposed skill | Deterministic part (stays out of the LLM) |
|:---|:---|:---|:---|:---|
| Transcription | `asr_service.ASREngine.transcribe` (faster-whisper / WhisperX); `_transcribe_gemini`; `sglang_omni.transcribe` | ASR model; Gemini audio prompt (inline string) | none for ASR models; `media.transcription_cleanup` (later) for Gemini text only | Rust `energy-vad`, `fit-speech`, PCM decode; `transcript_keep`, `merge_dialogue_segments` |
| Burned-in captions | `ocr_service.OCREngine` (`_gemini_ocr_frame` prompt), Rust `scan-captions` / `extract-crop` | Vision OCR | `media.caption_read` (later, image + text contract) | Rust sampling, crop, `filter-ocr`, stitching |
| Speaker / character analysis | `gender_voices.llm_analyze_cast_and_gender` (inline prompt: characters, gender, intent, expression), `apply_character_cast`, `jev_decisions.refine_cast`; `character_intel/registry.py` | Gemini / Ollama JSON; Jev judgments | `movie.character_analysis` and `movie.speaker_attribution`, with output evidence (`line_indices`, cue words) and confidence; unknown when unsure | `character_intel/prosody.py` pitch / energy, `voice_casting.estimate_presentation`, `gender_audio` |
| Dialogue translation | `translate_service.TranslateEngine._dub_prompt` / Rust `build-dub-prompt`, `_translate_llm`, `_map_batch`; `movie_translate.translate_movie_dialogue` | Gemini / chat providers / Ollama / SGLang-Omni | **`movie.dialogue_translation` v1.0.0 (done)** | Rust `speech-quota`, spoken units, batch packing |
| Duration fit | `TranslateEngine._tighten_to_slot` + `_fit_prompt` / Rust `build-fit-prompt` | same backends | `movie.subtitle_refinement` (fit mode) | Rust unit counting, `align-speed` tempo |
| Emotion / expression | `gender_voices.detect_line_expression`, `detect_line_intent`; LLM `expression` field in cast analysis; `jev_decisions._EXPRESSIONS` | LLM labels | `movie.emotion_analysis` (label + intensity + evidence + confidence) | prosody features from `character_intel/prosody.py` |
| Expressive TTS direction | `tts_expression.py` (`[sigh]` tag parsing, `synthesize_with_tags`); `character_intel/performance_planner.py` and `expression_mapper.map_delivery` (style → provider controls) | none or LLM style | `movie.tts_direction`: writes a **description**. A per-provider mapper then turns it into real controls. Prompt text is never treated as a TTS control | Rust `parse-expression-tags`, tempo window, ducking |
| Subtitle work | `translate_service` (subtitle display text), Rust `chunk-subtitles`, `build-translate-prompt` | LLM / NMT | `movie.subtitle_refinement` (line length, reading speed, breaks) | Rust chunking and timing |
| Quality review | `jev_decisions.weak_translation_ids` (meaning / naturalness questions), `_fill_untranslated` | Jev (TypeSafe) | `movie.quality_review` (requires `movie.dialogue_translation`), plus a human review queue | heuristics in `_suspect_rows`; eval checks in `prompts/evaluation.py` |

Provider seam: `ai_provider.AiProvider` (`complete`, capabilities `transcribe` / `translate` / `speak`, `ProviderError`). Skills declare `model_capability` (for example `text_generation`). For this milestone, the existing engine chain picks the backend and `Skill.supports_backend` gates which backends get the skill (`gemini`, every chat provider, `ollama`, `sglang-omni`; never NLLB or Google).

---

## 4. Milestone 1: `movie.dialogue_translation` v1.0.0

Manifest (`skills/dialogue_translation/skill.yaml`):

- `id: movie.dialogue_translation`, `version: 1.0.0`, `name: Cinematic Dialogue Translator`
- `model_capability: text_generation`, `requires: []`
- inputs: `source_language`, `target_language`, `dialogue`, `scene_context`, `character_profile`, `glossary`
  (contract: `schemas/dialogue_translation.input.schema.json`)
- output: `schemas/translation.schema.json`: `{"translations": [{"id", "translation", "confidence"?, "notes"?}]}`.
  A bare array is accepted. Coverage rules: every input id exactly once, no extras, no duplicates.
- settings: `temperature: 0.2`, `max_output_tokens: 2048`, `response_format: json`
- limits: `max_lines_per_call: 16`. Each translate batch is split into chunks this size, so 2048 output tokens is enough.

Template rules: meaning and intent, natural spoken language, character personality, emotion through word choice only (no tags), consistent names, cultural adaptation, no additions or omissions, timing (`recommended_syllables` min / target / max, never past max), glossary consistency, and valid JSON. Shared system text treats film text as data (a prompt-injection guard) and asks for low confidence plus a note when something is uncertain.

Languages: `khmer.yaml` (pronouns by relationship, particles, no `តើ` in casual questions, drop `បាន / កំពុង / របស់`, examples, glossary) and `english.yaml`. The glossary sent to the model is the language default merged with the project glossary (project entries win), filtered to terms that appear in the chunk.

### Turning it on

Studio feature setting **`skill_dialogue_translation`** (store tool `studio`, default `"0"`).
There is no UI toggle yet. To turn it on:

```python
from claynext.models.features import set_feature_setting
set_feature_setting("skill_dialogue_translation", "1")
```

`MovieTranslateOptions` also takes `prompt_skill` (True / False overrides the setting), `glossary`, and `skill_run_dir`.

### Call path when on

```text
translate_movie_dialogue → _open_translation_skill (setting) → TranslationSkillSession
  → TranslateEngine._translate_llm(..., skill=session)          # same chain, same key pool
    → _skill_batch: per 16-line chunk
        _payload_for (speech quota from Rust) → session.render → _skill_complete
        (gemini: generationConfig temperature / maxOutputTokens; ollama: options;
         chat: temperature; sglang-omni: no settings, recorded as {})
        → session.check (schema + Pydantic + coverage; soft warnings for glossary misses and timing overflow)
        ok → _map_batch      fail → legacy _dub_prompt path for that chunk
  → _tighten_to_slot (unchanged) → _merge_cast / Jev (unchanged)
```

Rate-limit, invalid-key, and `ProviderError` failures are re-raised rather than retried with the legacy prompt, so the engine chain moves on as before. The skill writes no expression tags. Delivery stays on the segment's `expression` field for the TTS and performance layer.

### What is persisted

One JSON file per project:

- `<skill_run_dir>/skill_runs/movie.dialogue_translation.json` when `skill_run_dir` is passed (meant for the dub job dir), otherwise
- `CACHE_DIR/skills/runs/<project_key>.json`. `project_key` hashes the languages, the line count, and the first 64 source lines.

The last 20 runs are kept. Each run records the skill id, version, fingerprint, lock status, settings, languages, and line count. Each call records the backend, model, settings actually applied, line and glossary counts, prompt size, the validation summary (ok, engine, errors, warnings), whether it fell back, and any error. Runs also carry a summary (calls / validated / fallbacks / lines from skill / lines from legacy) and a `review` list: lines with confidence below 0.6 or with a model note. Nothing is written to the project root.

### Versioning

`versions.lock.json` pins `sha256` over the manifest, template, system text, schemas, and language files. `test_registry_catalog_and_lock` fails on drift. To change a prompt: bump `version` in `skill.yaml`, add a changelog entry, then re-pin:

```python
from claynext.prompts.registry import SkillRegistry
from claynext.prompts.versioning import write_lock
s = SkillRegistry().load().get("movie.dialogue_translation")
write_lock({s.manifest.key: s.fingerprint})
```

---

## 5. Tests and evaluations

- `tests/python/test_prompt_skills.py` (20 tests). It runs without pytest:
  `KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=src .venv/bin/python tests/python/test_prompt_skills.py`
  It covers the manifest contract, semver, dependency / cycle / capability resolution, backend gating, parity of the YAML / renderer / validator fallbacks, the eval suite in both modes, session inputs (quota kept, scene context, glossary filter), chunking, skill off = legacy prompt with no `skill` kwarg, skill on = validated + persisted, invalid reply → legacy fallback, rate limit not retried, Gemini / Ollama bodies unchanged without settings, and the setting default.
- `evaluations/translation_cases.jsonl` (17 cases). These use recorded replies, so no live LLM is called. Cases cover valid Khmer and English, bare-array and fenced replies, omission, addition, duplicate, blank, not-JSON, legacy keys, confidence range, glossary miss, timing overflow, review flagging, scene context plus an injection line, auto source, and a generic target language.
  `run_suite()` returns `{total, passed, failed, results}` for a future UI panel.

---

## 6. Next milestones

1. **UI (read-only first)**: a Settings → Features toggle for `skill_dialogue_translation`. Skill catalog, prompt preview, and eval results load through a `Worker` (`get_registry().catalog()`, `Skill.render`, `run_suite`). Show the last run summary and the review queue from the run JSON.
2. **Per-movie persistence**: pass `skill_run_dir=_job_dir(...)` from `dubbing_service` (owned by the Character Intelligence work; coordinate). Load the project glossary from the movie project file into `MovieTranslateOptions.glossary`.
3. **`movie.character_analysis` / `movie.speaker_attribution`**: move the inline prompt in `gender_voices.llm_analyze_cast_and_gender` into a skill with an evidence + confidence contract. Feed deterministic prosody / voice-presentation features as inputs, and output `unknown` below threshold.
4. **`movie.emotion_analysis` + `movie.tts_direction`**: the output is a description. The per-provider mapper in `character_intel/expression_mapper.py` stays the only place that makes TTS controls.
5. **`movie.subtitle_refinement`**: replaces `_fit_prompt` for the tighten pass and subtitle display text.
6. **`movie.quality_review`** (requires `movie.dialogue_translation`): a regression and human review workflow that runs alongside Jev.
7. **Model selection**: per-skill preferred backends and fallback order in the manifest, joined with `resolve_movie_engine_chain`. Read SGLang-Omni capabilities via `ProviderCapabilities`.
8. **Rust convergence (optional)**: `claynext-ai render-skill` on MiniJinja plus schema checks, if prompt building has to leave Python.
