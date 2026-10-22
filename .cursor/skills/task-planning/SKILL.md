---
name: task-planning
description: >-
  Plans Claynext agent jobs with one owner, real paths, and the READY to
  DONE states. Use when splitting work, updating .agents/jobs, or writing
  a handoff. Does not start blocked training.
---

# Task planning

## When to use

When creating or moving a job, or before delegating.

## Steps

1. Copy `.agents/templates/task.yaml`.
2. Set `scope` to paths that exist (`src/claynext/...`, `backends/...`, `crates/...`, `docs/...`, `tests/...`).
3. Assign one `owner` from `.cursor/agents/`. Pick a different `reviewer`.
4. Status flow: `BACKLOG` → `READY` → `IN_PROGRESS` → `REVIEW` → `QA` → `DONE`. Use `BLOCKED` for hosted fine-tune until the owner approves.
5. Put `IN_PROGRESS` jobs in `.agents/jobs/active.yaml` and remove them from the backlog list.
6. Parallelize only when `scope` paths do not overlap.
7. Hand off with `.agents/templates/handoff.md` into `.agents/handoffs/`.

## Delegation

If the Task tool is in this session, delegate to a native subagent and give it the role file plus the job. Otherwise do the job here and say Task was not used.

## Do not

- Mark DONE without evidence paths.
- Claim a specialist ran because a markdown file exists.
- Put secrets or price lists in the job.
