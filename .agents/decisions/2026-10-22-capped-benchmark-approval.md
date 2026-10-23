# Decision: capped benchmark probe and local dry-run

- Date: 2026-10-22
- From: project-owner
- Quote: "yes i alway approve for do somethink."
- Interpreted as approval to finish the measurement system, validate LoRA/SFT configs, and attempt one capped raw probe.

## Allowed

- Benchmark schema, runner, metrics, promotion gate, and unit tests with fakes.
- A hosted raw probe of at most 20 rows, temperature 0, one prompt version, if a key is free.
- An untuned Ollama comparison on a model that is already installed and already running, on those same rows, without downloading weights.
- Trainer dry-run. A real local train only for a tiny adapter that already fits in 16 GB and whose code path already exists.

## Not allowed

- JOB-011 hosted fine-tune stays BLOCKED. No Vertex, no paid tuning API.
- No 7B, 8B, or 14B fine-tune on this M4.
- No `uv sync` and no new training stack.
- The 55 `gemini_teacher` rows are not gold, even where `review_status` says gold. Their notes still say `pending_native_review`.
- No commit and no push.
