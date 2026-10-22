---
name: dataset-engineering
description: >-
  Extends the Claynext dialogue dataset manager and claynext dataset CLI.
  Use for import, dedupe, splits, review sheets, versions, and SFT export.
  Does not rebuild the manager or train models.
---

# Dataset engineering

## When to use

Work on `src/claynext/models/datasets/`, `src/claynext/cli/cmd_dataset.py`, or dataset docs in `docs/khmer-platform/`.

## Steps

1. Read `docs/khmer-platform/03-backlog-and-acceptance.md`. Import, dedupe, split, version, review export/apply, promote, and SFT export are done.
2. Store data under `data/datasets/`. Exports under `data/outputs/datasets/`.
3. Keep version snapshots read-only and hashed. Do not edit a snapshot in place.
4. New fields belong on `models/datasets/schema.py` and the CLI that reads them.
5. Review states: a sheet may set `reviewed` or `rejected`. It must not set `gold` by itself.
6. Optional check:

```bash
PYTHONPATH=src .venv/bin/python tests/python/test_datasets.py
```

## Do not

- Rebuild the dataset manager.
- Commit bulk datasets or API keys.
- Treat unlicensed or unreviewed rows as training-ready.
- Start the GUI review queue here; that is JOB-006 for the UI engineer.
