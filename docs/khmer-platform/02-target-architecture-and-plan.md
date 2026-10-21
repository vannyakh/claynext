# Target architecture and migration plan

The CTO tree is a target, mapped onto this repo's layers (GUI/CLI → models → adapters → rust_bridge → Rust).
Nothing existing is moved or deleted; new packages sit beside the current ones.

## Target layout

```text
src/claynext/
  models/
    datasets/              # NEW (Phase 1, done) dialogue dataset foundation
      schema.py            #   record schema + validators (review / origin / license rules)
      normalize.py         #   Khmer-aware normalization + shingles
      io.py                #   CSV / JSON / JSONL / KSLD import, canonical JSONL
      dedupe.py            #   exact + MinHash-LSH near duplicates (deterministic)
      split.py             #   group-aware split, leakage check
      store.py             #   working set + immutable versions under data/datasets/
      report.py            #   quality report
      export.py            #   canonical JSONL, chat SFT files
      review.py            #   apply native-speaker review sheets
    llm_gateway/           # NEW (done) provider-neutral chat calls
      base.py              #   ChatRequest / ChatResponse / ProviderError / TraceLog / Pricing
      openai_provider.py   #   OpenAI + any CHAT_PROVIDERS entry; key pool, retries, schema check
    khmer_localization/    # EXISTS, extend: engine reads profiles + dataset few-shots, calls gateway
    character_intel/       # EXISTS, source of character ids
    evaluation/            # PLANNED: run dataset test split through engine + gateway, score
  prompts/
    dictionaries/khmer/    # EXISTS: pronouns / regional / profanity / tts YAML (all pending review)
    skills/                # EXISTS: khmer_natural_dialogue@0.1.0
  cli/cmd_dataset.py       # NEW (done) `claynext dataset …`
  voice_training/          # PARALLEL work (speech audio datasets); language data comes from models/datasets
data/
  datasets/<name>/working|versions/vNNNN   # dataset store (gitignored)
  outputs/datasets/<name>/<version>/       # exports
backends/ai-runtime        # PLANNED only if needed: `claynext-ai near-dups` for >1M rows
```

Why `models/datasets` and not top-level `datasets/`: domain packages already live under `models/`
(`khmer_localization`, `character_intel`), and the CLI/GUI call models. Pure Python is fine at current sizes
(1,000 rows dedupe + split in well under a second); see backlog for the Rust port trigger.

## File-by-file plan

| File | Change | Phase | Status |
|:---|:---|:---|:---|
| `utils/paths.py` | Add `DATASETS_DIR = data/datasets` | 1 | done |
| `models/datasets/*` | New package (above) | 1 | done |
| `cli/cmd_dataset.py`, `cli/app.py` | `claynext dataset import|validate|dedupe|split|report|version|export|review-apply` | 1 | done |
| `tests/python/test_datasets.py` | 19 tests incl. real KSLD import | 1 | done |
| `models/llm_gateway/*` | Gateway + OpenAI-compatible provider | 2 | done |
| `tests/python/test_llm_gateway.py` | 10 tests, fake transport | 2 | done |
| `models/llm_chat.py` | Re-implement `chat_text` on the gateway (same signature) | 2 | backlog |
| `models/translate_service.py` | `_chat_batch` → gateway; keep Gemini/Ollama paths until they have providers | 2 | backlog |
| `models/khmer_localization/skill.py` | Accept a gateway provider; record trace ids in the run log | 3 | backlog |
| `models/khmer_localization/evaluator.py` | Accept dataset records (test split) as cases, not only the 100 JSONL cases | 3 | backlog |
| `models/evaluation/` | Batch eval runner: dataset version × provider × prompt version → scores + cost | 3 | backlog |
| `models/dubbing_service.py` | Use `normalize_for_tts` / stored `tts_text` for Khmer | 4 | backlog |
| `gui/views/…` dataset page | Read-only report + review queue via `Worker`/`QThreadPool`, theme tokens | 4 | backlog |

## Workstreams, owners, dependencies

| Workstream | Owner (agent) | Depends on | Delivers |
|:---|:---|:---|:---|
| A. Dataset foundation | data agent | — | schema, import, dedupe, split, versions, CLI (done) |
| B. Provider gateway | platform agent | — | gateway, OpenAI provider (done); migrate callers |
| C. Localization engine | Khmer agent | A (few-shots), B | engine uses profiles + gateway, structured output |
| D. Evaluation pipeline | eval agent | A, B, C | test-split runs, deterministic + judge scores, cost report |
| E. Review tooling | data agent + GUI agent | A | review sheets out/in (CLI done), GUI queue |
| F. Native review | humans | E | reviewed records, reviewed dictionaries → first gold |
| G. Fine-tuning | platform agent | A (gold), D, provider check | hosted SFT job only after availability is confirmed |
| H. TTS integration | TTS agent | C | `tts_text` into `DubbingEngine` |

Critical path: A → E → F (humans) → D → G. Nothing should be trained until F produces reviewed data.

## Constraints and decisions to respect

- **Hosted fine-tuning availability must be checked before implementing G.** Which models accept SFT, the file format,
  limits, and pricing change; confirm with the provider's current docs at the time. The exporter writes the common
  `{"messages": [...]}` chat format only.
- **Proprietary model weights cannot be trained locally.** Local training means open-weight models only (separate
  licence review per model).
- **Licensing and consent.** Every record carries `provenance.license`; gold requires it. The KSLD v0.1 package has no
  licence ("confirm applicable rights"). Voice data needs performer consent (see `voice_training`).
- **Synthetic is never gold without human review.** Enforced by `validate_record`; review sheets never promote to gold.
- **No invented dialects or profanity.** Regional claims need provenance + confidence; reviewed/gold records with an
  unsupported region claim are rejected.
