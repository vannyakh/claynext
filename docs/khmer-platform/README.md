# Khmer dubbing / localization platform

| Doc | Contents |
|:---|:---|
| [01-current-architecture.md](01-current-architecture.md) | Audit: module map, data flow, reusable pieces, debt |
| [02-target-architecture-and-plan.md](02-target-architecture-and-plan.md) | Target layout, file-by-file plan, workstreams, constraints |
| [03-backlog-and-acceptance.md](03-backlog-and-acceptance.md) | Milestone acceptance tests, prioritized backlog |
| [../khmer-localization/DESIGN.md](../khmer-localization/DESIGN.md) | Existing localization engine (pronouns, profiles, skill) |

## Dataset CLI

Code: `src/claynext/models/datasets/`, CLI: `src/claynext/cli/cmd_dataset.py`. Stdlib only.
Data goes to `data/datasets/<name>/` (gitignored); exports to `data/outputs/datasets/<name>/<version>/`.

Use the venv directly (`uv run` re-syncs the environment):

```bash
cx() { PYTHONPATH=src .venv/bin/python -m claynext.cli "$@"; }
KSLD=/Users/vannya/Documents/SourceCode/AiProject/khmer_spoken_language_dataset_v0.1

cx dataset import  "$KSLD/dialogues.jsonl" --name ksld_v0_1   # add --replace to start over
cx dataset validate --name ksld_v0_1                           # exit 1 if any record has errors
cx dataset dedupe   --name ksld_v0_1 [--threshold 0.8] [--drop-exact]
cx dataset split    --name ksld_v0_1 [--seed 13] [--ratios 0.8,0.1,0.1]
cx dataset report   --name ksld_v0_1 [--json] [--version v0001]
cx dataset version  --name ksld_v0_1 --note "why"              # --list to show versions + integrity
cx dataset review-export --name ksld_v0_1 [--status draft,staging|all] [--category …] [--split …] [--out sheet.csv]
cx dataset review-apply sheet.csv --name ksld_v0_1 [--reviewed-at 2026-10-21T10:00:00+07:00]
cx dataset promote  --name ksld_v0_1 --to staging|reviewed|gold [--ids a,b] [--by lead-1] [--dry-run]
cx dataset export   --name ksld_v0_1 --format sft [--version v0002] [--include-unreviewed] [-o DIR]
cx dataset export   --name ksld_v0_1 --format jsonl -o out.jsonl
```

Every subcommand takes `--root DIR` to use another datasets folder (tests use a temp dir).

Typical order: import → validate → dedupe → split → report → version → review loop (below) → export.
`split` refuses to write if any group leaks. `version` refuses an unchanged working set.

### Review workflow

1. **Export a sheet**: `cx dataset review-export --name ksld_v0_1 --status draft --out review.csv`.
   UTF-8 with BOM so spreadsheet apps show Khmer. One row per record. Context columns are prefilled and read-only
   for the reviewer: id, status, origin, split, category, source text, current Khmer + style + alternatives,
   speaker/listener, relationship, emotion, intensity, register, slang/profanity levels, region, licence, current
   reviewer and timestamp, and current scores as `current_<dimension>` (shown for reference, never read back).
2. **Fill it in** (reviewer columns, empty on export): `reviewer_id` (pseudonymous, required),
   `reviewed_at` (ISO 8601, e.g. `2026-10-21T14:30:00+07:00`), `decision` (`approved` | `rejected` |
   `needs_changes`), `corrected_khmer`, the seven score columns (1–5), `relationship_fit_1_5`, `notes`.
   Rows with an empty decision are skipped.
3. **Apply it**: `cx dataset review-apply review.csv --name ksld_v0_1`. Decisions map to `reviewed` / `rejected` /
   `staging`. Timestamp: the row's `reviewed_at`, else `--reviewed-at`, else the time of applying (reported as
   `timestamp_source`, with a note on stderr). Approved synthetic records become `origin=human_reviewed`; a correction
   becomes the preferred candidate and the original is kept. A sheet can never set gold (`gold` / `promote`
   decisions are rejected) and never changes a gold record. The KSLD `review_template.csv` columns are also accepted.
4. **Promote**: `cx dataset promote --name ksld_v0_1 --to gold --ids KSLD1-0001,KSLD1-0002 --by lead-1`.
   Transitions: draft → staging | reviewed, staging → reviewed | gold, reviewed → gold. `reviewed` and `gold` need the
   record to already carry a reviewer id and `reviewed_at`; promotion never creates review data. `gold` also needs
   `reviewer_type=human` (synthetic data without human review is blocked) and a licence. `--require-license` adds the
   licence check to staging/reviewed; for gold it is always on. The new record is re-validated; any schema error
   blocks it. Each promotion is logged in `metadata.promotions`. Without `--ids`, every record that could make the
   transition is tried. Exit code 1 if anything was blocked. `--dry-run` reports without writing.
5. **Snapshot**: `cx dataset version --name ksld_v0_1 --note "review batch 1"`.
6. **Export for training**: `cx dataset export --name ksld_v0_1 --format sft` (reviewed + gold only).

### Accepted input

CSV (UTF-8, BOM ok), JSON (list or `{"records": [...]}`), JSONL. Row shape is detected per row:

- **canonical**: rows written by this tool (have a `candidates` list);
- **KSLD**: Khmer Spoken Language Dataset rows (`scene_id`, `source_text`, `target_text`, `variation_method`);
- **flat**: one column per field: `id, source_text, source_lang, target_lang, khmer_natural, khmer_literal,
  target_text|khmer, tts_text, speaker_id, listener_id, relationship, emotion, intensity, register, slang_level,
  profanity_level, category, region, region_verified, region_provenance, region_confidence, dataset, license,
  attribution, origin, review_status, reviewer_id, reviewer_type, reviewed_at, film_id, script_id, dialogue_family,`
  plus any quality dimension column.

Rows with errors are not imported; they go to `working/rejects.jsonl` with reasons. Every import is logged with
the source file's SHA-256 in `working/imports.jsonl`.

### KSLD mapping

| KSLD field | Record field |
|:---|:---|
| `target_text` | one candidate, style `unspecified` (literal vs natural is not stated in the source) |
| `tts_text` | dropped when identical to `target_text` (README: placeholder copy); flag in metadata |
| `genre` | `category`, see the genre table below |
| `review_status` | needs_native_review→draft, approved→reviewed, rejected→rejected |
| `region=unspecified` | no region claim |
| `scene_id` | `groups.dialogue_family` (split unit; keeps the 10 variants of a base line together) |
| `character_id` / `listener_id` | `speaker_id` / `listener_id` (ids are local to this dataset) |
| everything else | `metadata` (source split, variation method, base pair, age group, notes) |

Genre → category (`KSLD_GENRE_CATEGORY` in `models/datasets/io.py`). Any other genre stays uncategorized
with a `missing_category` warning; nothing is guessed.

| KSLD genre | Category | Note |
|:---|:---|:---|
| daily | everyday | |
| argument | argument | |
| romance | romance | |
| comedy | comedy_sarcasm | |
| fear, sad | fear_sadness | |
| care | family | product decision, Oct 2026 |
| surprise | everyday | product decision, Oct 2026 |
| excited | comedy_sarcasm | product decision, Oct 2026 |

All KSLD rows import as `origin=synthetic`, `status=draft`, no licence. The source README calls the package a
"synthetic draft" built from "100 authored base utterance pairs" without saying who authored them, so the seed lines
also stay `synthetic`. Change that only with evidence that a person wrote them. Licence stays empty until the owner
decides; gold still requires one.

Imported versions of `ksld_v0_1`: `v0001` (first import), `v0002` (genre mappings above; 0 uncategorized).

### Record rules

Statuses: `draft`, `staging`, `reviewed`, `gold`, `rejected`. Origins: `human_authored`, `human_reviewed`, `synthetic`.

- `reviewed` and `gold` need `review.reviewer_id` (pseudonymous) and an ISO `review.reviewed_at`.
- `gold` needs `review.reviewer_type=human` and `provenance.license`. Synthetic data is never gold without that.
- A region claim needs `regional.provenance` and `regional.confidence` (0–1); error once reviewed.
- Quality scores are 1–5 on: semantic_accuracy, naturalness, character_consistency, pronoun_correctness,
  emotion_fit, regional_authenticity, tts_suitability. `quality.scored_by` is `human` or `model`.
- Split groups: first present of `film_id`, `script_id`, `dialogue_family`, `speaker_id`; else the record id.
  Near-duplicate clusters (character 3-gram Jaccard ≥ 0.8, MinHash LSH with fixed seeds) merge their groups.

### SFT export

One `{"messages": [system, user, assistant]}` per line, per split (`train.jsonl`, `validation.jsonl`, `test.jsonl`),
plus `<split>.ids.txt` and `manifest.json` (statuses, hashes, source version). The user message is a JSON context
(source text, speaker, listener, relationship, emotion, register, caps). Only `reviewed`/`gold` by default.
Check that the target provider currently supports fine-tuning the chosen model before uploading anything.

## Tests

```bash
PYTHONPATH=src .venv/bin/python tests/python/test_datasets.py      # 27 tests, includes the real KSLD import
PYTHONPATH=src .venv/bin/python tests/python/test_llm_gateway.py   # 10 tests, fake transport, no network
```

## Provider gateway (for engine and evaluation work)

```python
from claynext.models.llm_gateway import ChatMessage, ChatRequest, get_provider

provider = get_provider("openai")            # any id in llm_providers.CHAT_PROVIDERS
resp = provider.complete(
    ChatRequest(messages=[ChatMessage("user", "...")], json_schema=schema, max_retries=2),
    control=job_control,                     # JobControl; optional
)
resp.parsed, resp.usage.tokens_in, resp.usage.cost_usd, resp.trace_id
```

Keys come from the existing pool (Settings → API Keys, or `OPENAI_API_KEY`). Cost is `None` unless you pass
`pricing={"model": Pricing(in_per_million, out_per_million)}`; no prices are built in. Traces hold the prompt's
SHA-256, never the prompt or the key. Call it from a `Worker`, never the Qt thread.
