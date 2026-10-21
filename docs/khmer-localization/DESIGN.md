# Character-Aware Khmer Dialogue Localization Engine

Status: **milestone 1** (pronoun resolution, speech profiles, natural dialogue skill, 100-case evaluation set).
Nothing in the data has native-speaker review yet. Every dictionary and every evaluation case ships as
`pending_native_review`.

## Goal

Khmer subtitles and dubs should sound like people talking, not like a dictionary. The same English
"I" / "you" becomes ខ្ញុំ / អ្នក, កូន / ម៉ាក់, បង / អូន, អញ / ឯង, or ខ្ញុំព្រះករុណា / ព្រះអង្គ depending on who is
speaking to whom, how they feel, and where they are. The engine decides those choices from data and
rules, lets the model write the line inside those constraints, then checks the result.

## Non-negotiable rules

1. Meaning first. Naturalization never adds or drops information.
2. No blanket swaps. ញ៉ុំ is chosen only from the character's own habit and never in a formal scene.
3. No escalation. Anger does not add swearing or rough pronouns. Profanity is capped at
   `min(source level, character level, project cap, scene cap)`.
4. No guessed dialects. Regional vocabulary is applied only from verified dictionary entries with
   evidence, for a region set by the editor or project config.
5. Pronouns follow listener and relationship, not just the speaker.
6. Three separate fields per line: `source_text`, `localized_text`, `tts_text`.
7. Uncertain choices are flagged for human review, never silently "fixed".
8. The Rust media engine is unchanged. Milestone 1 is pure Python data + rules.

## Architecture

```text
segments (speaker, character_id, listener?, expression, scene_id?)
   │
   ├─ LocalizationStore (per project JSON) ── SpeechProfile, RelationshipGraph, LocalizationConfig
   │        ▲ seeded read-only from character_intel CharacterRegistry (character_id)
   │
   ├─ Relationship Context Analyzer   relationships.py   editor / config edges, vocative hints
   ├─ Khmer Pronoun Resolver           pronouns.py        dictionaries/khmer/pronouns.yaml
   ├─ Slang and Profanity Selector     slang.py           dictionaries/khmer/profanity.yaml
   ├─ Emotion-Aware Naturalizer        naturalizer.py     constraints only (M1)
   │
   ▼
movie.khmer_natural_dialogue@0.1.0  (prompts/skills/khmer_natural_dialogue)
   │  Jinja2 template + YAML manifest, rendered by the prompt skill registry
   ▼
existing provider path (Gemini, chat providers, Ollama, SGLang-Omni) via TranslateEngine._skill_batch
   │
   ▼
post-check (postcheck.py) → TTS Pronunciation Normalizer (tts_normalizer.py) → run log + review queue
   │
   └─ Translation Quality Evaluator (evaluator.py) over evaluations/khmer_pronoun_cases.jsonl
```

All code lives in `src/claynext/models/khmer_localization/`. Data lives next to the skills system in
`src/claynext/prompts/` (dictionaries, skill, schemas, evaluation set). Network and model calls stay in
the existing `TranslateEngine` provider path; this package only sees data.

### Module status

| Module | File | Milestone 1 |
|:---|:---|:---|
| Character Speech Profile | `speech_profile.py` | Implemented |
| Relationship Context Analyzer | `relationships.py` | Implemented (explicit edges + vocative hints) |
| Khmer Pronoun Resolver | `pronouns.py` | Implemented |
| Slang and Profanity Selector | `slang.py` | Implemented (levels + detection; no insertion) |
| Regional Dialect Adapter | `dialect.py` | Interface + gating; no dictionary entries yet |
| Emotion-Aware Dialogue Naturalizer | `naturalizer.py` | Constraints only; rewrite pass is a stub |
| TTS Pronunciation Normalizer | `tts_normalizer.py` | Implemented, not hooked into TTS |
| Translation Quality Evaluator | `evaluator.py` | Implemented (offline, deterministic) |

## Pronoun Resolver

### Order of authority

1. Per-scene override: `config.scene_overrides[{scene_id, speaker, listener, first, second}]`.
2. Character override for this listener: `profile.pronoun_overrides[{listener|"*", first, second}]`.
3. Relationship rule from `pronouns.yaml`, then matching `variants`, the formal-register adjustment,
   and the speaker's habits when the rule allows that form.
4. Age fallback when the relationship is unknown (always reviewed).
5. Defaults ខ្ញុំ / អ្នក.

### Review triggers (`needs_review` + `review_reasons`)

- relationship unknown, listener unknown, or listener inferred from turn order;
- relationship came from a vocative heuristic ("Mom", "boss", "bro");
- a rough form (អញ / ឯង / ហ្អែង) chosen where the rule does not allow rough forms;
- a character habit that the relationship forbids (for example habitual ឯង toward a stranger);
- habit ញ៉ុំ in a formal scene;
- couple of the same or unknown gender with unknown ages (បង / អូន direction unclear);
- relation-specific variants (angry child to parent, angry employee to boss);
- confidence below `review_confidence` (default 0.6).

### `pronouns.yaml` schema (v0.1.0)

```yaml
version: "0.1.0"
review: {status, reviewer, reviewed_at}           # block style in the file
forms:                                            # inventory used for detection and validation
  - form: ញ៉ុំ
    person: first | second | both
    tone: neutral | colloquial | formal | rough | kin | title | humble | religious | royal | intimate
    rough: true            # optional; អញ, ឯង, ហ្អែង
    habit_gated: true      # optional; only via character habit (ញ៉ុំ)
    gender: male | female  # optional
    boundary: word         # optional; short kin terms need whitespace/punctuation on both sides
    variants: [ញុំ]         # optional spelling variants
compounds_not_pronoun: [ខ្លួនឯង, ម្នាក់ឯង, បងប្អូន, កូនក្មេង, អ្នកណា, ...]
defaults: {first, second, confidence}
formal_second / formal_first_alt: slot           # used when register or scene is formal
age_fallback: {older|younger|peer|unknown: {first, second, second_alt}}
relations:
  <relation_id>:
    inverse: <relation_id>   # stored automatically for the reverse direction
    prefer: age | gender     # slot key order, default age
    register_locked: true    # formal register does not swap in polite forms
    respect: true            # listener is owed deference (street register gets reviewed)
    allow_rough: true        # rough forms are normal for this pair
    reciprocal: [បង, អូន]   # couple rule; same/unknown gender falls back to age
    first / second / first_alt / second_alt: slot
    forbidden: [forms]
    confidence: 0.0-1.0
    variants:
      - when: {register: [...], emotion: [...], hostility_min: N, age: [older|younger|peer],
               listener_age: [...], scene_formality: [...], slang_min: N}
        first / second: slot      # replaces
        first_alt / second_alt: slot  # extends
        allow_rough: bool
        confidence: number
        review: "reason"
aliases: {spouses: romantic, rivals: enemies, ...}
vocative_cues: [{pattern: regex, relation, listener_gender?}]
```

A **slot** is a list, or a mapping with keys `older` / `younger` / `peer` / `male` / `female` / `default`.
For `first` the keys describe the speaker; for `second` they describe the listener.

Relations shipped: child↔parent, grandchild↔grandparent, younger↔older sibling, niece/nephew↔aunt/uncle,
romantic, friends_close, friends, boss↔employee, teacher↔student, lay↔monk, younger↔elder (non-kin),
strangers, enemies, servant↔master, subject↔royalty, police↔civilian.

### Detection in unsegmented Khmer

Khmer has no spaces between words. A form matches only if it is not glued to a subscript (coeng) or a
dependent vowel / sign on either side, after masking known compounds. That keeps បង្ហាញ, បង់, អញ្ជើញ,
ប្អូន, ខ្លួនឯង, ម្នាក់ឯង, អ្នកណា, and កូនក្មេង from being read as pronouns. Short kin terms (តា, ពូ, ប៉ា, ...)
also need whitespace or punctuation on both sides, so តាម and ពូកែ do not match. Misses are acceptable
because a missing pronoun is never a violation (Khmer drops pronouns freely).

## Character Speech Profile

```json
{
  "character_id": "CHAR_001",          // same id as character_intel's CharacterRegistry
  "name": "Dara",
  "gender": "male|female|unknown",
  "age_group": "child|teen|adult|elder|unknown",
  "register": "formal|neutral|casual|street|regional",
  "slang_level": 0,                    // 0-3
  "profanity_level": 0,                // 0-3, capped by project config
  "habitual_first_person": ["ញ៉ុំ"],
  "habitual_second_person": [],
  "pronoun_overrides": [{"listener": "CHAR_003|*", "first": "បង", "second": "អូន", "note": ""}],
  "catchphrases": [],
  "region": null,                      // needs region_source when set
  "region_source": "|editor|project_config|evidence",
  "social_role": "son",
  "evidence": [{"source": "character_registry|segment|editor", "...": "..."}],
  "confidence": 0.7,
  "overrides": {"register": "casual"}, // editor values; win over everything except project caps
  "updated_at": "..."
}
```

**Precedence**: editor `overrides` > values from project config / evidence > values seeded from the
character registry > defaults. Project `profanity_cap` / `slang_cap` are ceilings applied last, even over
editor overrides. `allow_regional: false` clears `region` in the effective profile.

**Persistence**: `LocalizationStore` writes one JSON per project: `CACHE_DIR/khmer_localization/<project_key>.json`,
or `<run_dir>/khmer_localization.json` for a job directory. Never the project root. Writes are atomic
(tmp + replace). A corrupt file raises on load so editor work is never silently replaced.
Example: `docs/khmer-localization/examples/khmer_localization.example.json`.

**Seeding**: `seed_from_characters(rows)` reads character_intel registry rows (read-only) and fills empty
fields only: name, gender from `voice_profile.presentation`, age group from `age_range_estimate`, role.

## Skill: `movie.khmer_natural_dialogue@0.1.0`

Files: `prompts/skills/khmer_natural_dialogue/{skill.yaml,prompt.j2}`,
`prompts/schemas/khmer_natural_dialogue.input.schema.json`, `prompts/schemas/khmer_localization.schema.json`.
Pinned in `prompts/versions.lock.json`. Discovered by the existing `SkillRegistry`; Pydantic contracts are
registered into `claynext.prompts.contracts.CONTRACTS` when `khmer_localization.contracts` is imported.
Backends: gemini, chat providers, ollama, sglang-omni. Settings: temperature 0.3, 4096 output tokens,
12 lines per call. The template uses only the portable subset, so it renders identically without Jinja2.

**Input** per line: `id, text, speaker, listener, gender, expression, duration_sec,
recommended_syllables, pronoun_plan{first_person, second_person, first_alternatives,
second_alternatives, forbidden, allow_rough, relation, confidence, needs_review},
style{emotion, intensity, register, slang_max, profanity_max, source_profanity, keep_intensity, catchphrases}`,
plus `characters`, `scene_context`, `glossary`.

**Output** (`khmer_localization` contract):

```json
{"lines": [{
  "id": 1,
  "source_text": "input text unchanged",
  "localized_text": "spoken Khmer line",
  "tts_text": null,
  "pronouns_used": {"first_person": [], "second_person": []},
  "register": "neutral",
  "candidates": [{"text": "...", "register": "...", "note": "..."}],
  "confidence": 0.0,
  "review_flags": ["pronoun_uncertain", "register_uncertain", "idiom_uncertain",
                   "intensity_uncertain", "regional_variant", "meaning_uncertain", "timing_tight"],
  "notes": ""
}]}
```

Schema or coverage failure (missing / extra / duplicate ids) sends that chunk to the legacy prompt, as
for `movie.dialogue_translation`. A valid reply is then post-checked line by line. Violations
(`forbidden_pronoun`, `rough_pronoun_unplanned`, `profanity_above_limit`) and warnings
(`unplanned_pronoun`, `habit_gated_form_unplanned`, `declared_pronoun_missing`, `source_text_changed`,
`timing_overflow`) are recorded; the line is **kept and flagged**, not rewritten. When `tts_text` is null
the normalizer fills it. The run log (`skill_runs/movie.khmer_natural_dialogue.json`, or
`CACHE_DIR/skills/runs/<key>.movie.khmer_natural_dialogue.json`) stores, per line: the three text fields,
candidates, pronoun decision with reasons, levels, confidence, violations, warnings, and review reasons.

## TTS Pronunciation Normalizer

`normalize_for_tts(localized_text)` / `tts_field(localized_text)` (None when identical). Applies NFC,
removes zero-width characters, expands ៗ for listed words (ឆាប់ៗ → ឆាប់ឆាប់), and spells out standard
abbreviations (គ.ស., ព.ស.). Unverified respellings apply only with `include_unverified=True`.
The subtitle line is never modified.

## Evaluation set

`prompts/evaluations/khmer_pronoun_cases.jsonl`: 100 cases, 23 categories. Each case has
`id, category, source_language, source_text, speaker{id,name,gender,age_group,profile?}, listener,
relationship{relation,hostility,intimacy,source}, scene{id,formality,setting}, register, emotion,
expected{first_person{allowed,forbidden,not_auto}, second_person{allowed,forbidden},
needs_review, max_profanity_level, third_person_refs?}, reference_khmer, notes,
review{status, reviewer, reviewed_at}`, plus optional `project` caps.

All cases are `pending_native_review`. The references and expectations were drafted without a native
speaker and must be reviewed before they count as ground truth.

### Review workflow

1. A native speaker edits `reference_khmer` / `expected` and sets
   `review: {"status": "reviewed", "reviewer": "<name>", "reviewed_at": "<ISO date>"}`
   (or `needs_changes` / `rejected`). `reviewed` without reviewer and date fails validation.
2. Run `evaluator.run(reviewed_only=True)` to score only verified cases.
3. When a reviewed case disagrees with the resolver, fix `pronouns.yaml`, bump its `version`, and
   re-run the suite.

Run it: `KMP_DUPLICATE_LIB_OK=TRUE PYTHONPATH=src .venv/bin/python -m claynext.models.khmer_localization.evaluator [--reviewed-only]`.
Model outputs can be scored with `evaluator.run(outputs={"kp-001": "..."})`.

## Integration instructions

### Translation (done, default off)

- Setting `skill_khmer_natural_dialogue` (`DEFAULT_CONFIG` "0", listed in `FEATURE_SETTING_KEYS`).
- `movie_translate._open_translation_skill` first asks `_open_khmer_dialogue_skill`, which returns a
  `KhmerDialogueSession` only when the setting is "1" and the target language is Khmer; otherwise the
  existing `movie.dialogue_translation` path runs unchanged. `prompt_skill=False` disables both.
- Turn on: `set_feature_setting("skill_khmer_natural_dialogue", "1")`, or through the studio store.
- Relationships and profiles: edit the project store JSON (see example) until the UI lands. Lines may carry
  `listener` / `listener_id` and `scene_id`; without a listener the adjacent speaker is used and reviewed.

### TTS (not hooked yet; one line)

In `src/claynext/models/dubbing_service.py`, inside `_one()` of the per-line synthesis loop:

```python
text_to_speak = str(item.get("translated_text") or item.get("text") or "")
```

becomes, for Khmer projects:

```python
text_to_speak = normalize_for_tts(str(item.get("translated_text") or item.get("text") or ""))
```

with `from claynext.models.khmer_localization.tts_normalizer import normalize_for_tts`. Normalizing at
synthesis time (rather than carrying a stored `tts_text`) keeps TTS in sync after an editor changes the
subtitle line. If a stored, editor-approved `tts_text` is added to segments later, prefer it only while
its source subtitle still matches `translated_text`.

### Character registry

Pass character_intel registry rows to `open_session(..., characters=registry.characters)` (read-only) so
profiles key on the same `character_id`. Segments that already carry `character_id` use it automatically.

## Editable desktop controls (milestone 2, not built)

All edits go through a `Worker` on `QThreadPool`; the store is saved off the UI thread.

- **Characters panel → Speech tab**: register, slang 0–3, profanity 0–3 (shows project cap), habitual
  first/second person (chips from the inventory), catchphrases, region (disabled unless the project
  enables regional vocabulary), evidence list.
- **Relationship matrix**: speaker × listener grid with relation dropdown (from `pronouns.yaml`),
  hostility / intimacy sliders, source badge (editor / config / heuristic); setting one edge offers the inverse.
- **Script line inspector**: source / localized / TTS text side by side, pronoun decision with reasons,
  alternatives as one-click swaps, candidates list, violation and review badges, "approve" action.
- **Scene style**: per scene register, formality, slang / profanity caps, scene pronoun overrides.
- **Review queue**: all lines with `needs_review`, filterable by reason.

## Next milestones

1. **M2 UI + review**: the controls above; native-speaker review of the 100 cases and `pronouns.yaml`;
   bump dictionary to 1.0.0 only after review.
2. **M3 Naturalizer + evaluator scoring**: rewrite pass that proposes naturalized variants under the same
   constraints, LLM-judge plus deterministic checks for meaning, register, intensity, and timing.
3. **M4 Regional dialects**: curated entries with evidence per region; reviewer sign-off per entry.
4. **M5 TTS layer**: hook the normalizer, per-engine pronunciation lexicons, verified respellings.
5. **Relationship inference**: diarization turn graph + multi-line context to propose edges (still reviewed).
6. If any of the rules become a hot path, port detection / resolution to `crates/` behind
   `get_dubbing_adapter()` with this Python as the fallback.

## Known limitations

- Detection is orthographic, not a word segmenter; uncommon compounds can produce `unplanned_pronoun`
  warnings or missed detections.
- Third-person reference with kin terms ("tell Mom" → ម៉ាក់) is indistinguishable from address; the
  evaluator allows `third_person_refs`, the post-check only warns.
- Source intensity markers exist for English only. Other source languages get level 0, which is the safe
  direction (no profanity) but may soften strong source lines.
- Royal and monastic registers are simplified and carry low confidence.
