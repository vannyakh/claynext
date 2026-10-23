---
name: rust-development
description: >-
  Extends Claynext Rust backends and editor crates, then the domain adapter.
  Use when changing backends/, crates/editor-*, or hot-path timing, VAD, and
  probe. Points at the claynext-rust-core skill instead of replacing it.
---

# Rust development

## When to use

For changes under `backends/` or `crates/`. Read `.agents/skills/claynext-rust-core/SKILL.md` for the command list. This skill only adds the job rules.

## Steps

1. Read `claynext-rust-core` and `.cursor/rules/rust-backends-crates.mdc`.
2. Extend the crate that already owns the behavior (`backends/ai-runtime`, `backends/ffmpeg`, or `crates/editor-*`).
3. Add or extend a CLI subcommand with JSON stdout, UTF-8.
4. Ask the architecture lead to thread it through `rust_bridge` and the domain adapter (`get_ai_adapter`, `get_dubbing_adapter`, `get_ffmpeg_adapter`). Models must not import the bridge.
5. Keep the adapter's Python fallback so Studio runs without the binary.
6. Build: `cargo build -p <package> --bin <name>` with output in repo `target/`.

## Do not

- Copy this skill over `claynext-rust-core`.
- Reimplement quota, VAD, probe, align, or ducking only in Python.
- Add PyO3 or an egui UI.
- Near-dup MinHash in Rust is backlog (after datasets are large). Do not start it early.
