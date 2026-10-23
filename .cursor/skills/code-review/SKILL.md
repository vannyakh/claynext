---
name: code-review
description: >-
  Reviews Claynext diffs against adapter boundaries, secrets, and job scope.
  Use before QA or when a specialist hands work back to the CTO.
---

# Code review

## When to use

A job is in `REVIEW`, or the owner asks for a review. This is a checklist in the parent or QA session. It is not the Bugbot subagent unless the owner asked for Bugbot.

## Steps

1. Read the job `scope` and the diff. Extra files are a finding.
2. Reject imports of `rust_bridge` from `models/` or `gui/`.
3. Reject new Python copies of timing, VAD, probe, quota, align, or ducking.
4. Reject hardcoded keys, tokens, or a built-in price list.
5. Reject UI work that calls the network or TTS on the Qt thread, or uses colors outside `theme_constants.py`.
6. Reject gold or training data without reviewer, timestamp, and licence.
7. Write findings in the handoff: blocking, or note. Do not rewrite the feature in the review pass.

## Do not

- Approve by saying tests passed unless a command output is attached.
- Review unrelated dirty files as if they were this job.
