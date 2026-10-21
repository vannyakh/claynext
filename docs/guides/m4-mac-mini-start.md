# Claynext Studio — Start guide (Apple Silicon / M4 Mac Mini)

For checking the latest update on an **M4 Mac Mini** (arm64).  
Repo: [github.com/vannyakh/claynext](https://github.com/vannyakh/claynext) · branch: **`main`**

Latest push this guide tracks:

```text
ca5da52  feat(khmer): add spoken dataset, voice training, and Gemini teacher tooling
```

(Also includes the prior OmniVoice / character-intel / Khmer localization work on `main`.)

---

## 1. Prerequisites

| Need | Notes |
|:---|:---|
| **macOS** | Recent macOS on Apple Silicon (M4). |
| **Xcode Command Line Tools** | `xcode-select --install` (compilers for some wheels / optional Rust). |
| **Git** | To pull the repo. |
| **`uv`** | Python env + runner. Install: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Homebrew** | Optional. Useful for `ffmpeg` / `rustup` if you want system tools. |
| **FFmpeg** | Studio prefers Rust `claynext-ffmpeg` when built; otherwise it falls back to **`imageio-ffmpeg`** (bundled with `uv sync`). A Homebrew `ffmpeg` on PATH is nice but not required. |
| **Rust / Cargo** | Optional — only if you want native backends (`claynext-ai`, `claynext-ffmpeg`). |

Python: **3.12+** (see `pyproject.toml`).

---

## 2. Get the update

```bash
cd /path/to/claynext
git fetch origin
git checkout main
git pull origin main
```

Confirm you are on the expected tip:

```bash
git log -1 --oneline
# expect something like: ca5da52 feat(khmer): add spoken dataset, voice training, and Gemini teacher tooling
```

Clone (first time only):

```bash
git clone https://github.com/vannyakh/claynext.git
cd claynext
```

---

## 3. Python environment (`uv sync` on M4)

On **Apple Silicon (M4), `uv sync` is fine** — arm64 wheels for PySide6, torch extras, etc. are available.

```bash
cd /path/to/claynext
uv sync
```

Optional extras (install only what you need; first run may download large weights later):

```bash
uv sync --extra demucs-mlx   # Apple-friendly stem separation (preferred on Mac)
# or: uv sync --extra demucs
uv sync --extra voxcpm       # VoxCPM2 local TTS
uv sync --extra omnivoice    # OmniVoice local TTS (600+ languages)
uv sync --extra whisperx     # optional ASR; needs newer torch on arm64
```

### Apple Silicon vs Intel (brief)

| | **M4 / arm64** | **Intel Mac** |
|:---|:---|:---|
| `uv sync` | OK — use current deps | Often pinned / fragile; avoid blind re-sync if torch is locked |
| Torch / WhisperX | Newer torch wheels usually install | Older pins; WhisperX / heavy TTS often blocked |
| OmniVoice / VoxCPM2 | Much more likely to install and run | Often missing wheels; Studio falls back to Edge / Kitten |
| Voice training fine-tune | Still mostly dry-run scaffolding; better host than Intel for future trainers | Dry-run only; do not force-upgrade torch to “fix” it |

---

## 4. Optional Rust backends

Studio **runs without** Rust binaries (Python fallbacks). For faster probe / VAD / OCR caption scan / prompts:

```bash
# needs rustup: https://rustup.rs
cargo build -p claynext-ai -p claynext-ffmpeg
# or everything:
cargo build --workspace
```

Binaries land in `target/debug/` (or `target/release/` with `--release`). Python discovers them automatically.

---

## 5. Launch

```bash
uv run main.py
# or
uv run claynext gui

# open a project
uv run main.py --project path/to/file.claynext.json
uv run claynext gui --project path/to/file.claynext.json
```

If OpenMP / Intel MKL duplicate-lib warnings appear (common with numpy / torch stacks on Mac):

```bash
KMP_DUPLICATE_LIB_OK=TRUE uv run main.py
```

---

## 6. First-run setup

1. Open **Settings** (`⌘,` or the gear).
2. **Features** tab  
   - Download / install **Whisper** ASR (default model in config: `whisper-medium`).  
   - Optional packages show as cards (Demucs, VoxCPM2, OmniVoice, WhisperX).  
   - **“Check burned-in captions before transcription”** is **off by default** (`transcript_ocr=0`) — leave it off unless you need OCR-before-ASR.  
   - **SGLang-Omni URL** — only set if you run a remote/local SGLang server (default `http://127.0.0.1:8000`). Leave alone for normal Whisper + Gemini / Edge workflows.
3. **API Keys** tab  
   - Add a **Gemini** (Google AI Studio) key if you will translate, use the Khmer Spoken Gemini teacher, or try Gemini TTS previews.  
   - Do not commit keys; Studio stores them in app settings / env (`GEMINI_API_KEY` / `GOOGLE_API_KEY` also work).
4. Models download under **`data/models/`** (kept across cleans). Never dump temp files into the repo root.

New Tools menus (after this update):

- **Tools → Khmer Spoken Dataset…** — Gemini teacher + human review for spoken Khmer text ([docs/khmer_spoken](../khmer_spoken/README.md))
- **Tools → Khmer Voice Training…** — consented speech dataset scaffolding ([docs/voice_training](../voice_training/README.md))

---

## 7. What’s new in this update (accurate to `main`)

From recent commits on `main` (Khmer milestone + prior OmniVoice / localization work):

- **Khmer Spoken Language Dataset (KSLD)** — import dialogue → Gemini AI Studio candidates → native review → gold export under `data/khmer_spoken/`; optional TTS preview; Vertex SFT / LoRA are stubs only.
- **Voice training scaffolding** — rights-gated ingest, segment, annotate, dry-run trainer, evaluation harness; data under `data/voice_datasets/` (not movie-stem auto-cloning).
- **Dataset CLI** — `uv run claynext dataset …` for import / validate / dedupe / split / review / promote / export ([docs/khmer-platform](../khmer-platform/README.md)).
- **OmniVoice + VoxCPM2** in the TTS / Features catalog (`uv sync --extra omnivoice` / `--extra voxcpm`).
- **Character intel / performance** — delivery style, intensity, character registry hooks; Rust `plan-performance` / prosody when `claynext-ai` is built.
- **Khmer localization engine** — pronouns, speech profiles, slang, skill-based natural dialogue (see `docs/khmer-localization/DESIGN.md`).
- **Settings** — Features cards, API key management, stem mode, OCR-before-transcript toggle (default off).

Not claimed as production-ready: Vertex fine-tune of Gemini, full GPU TTS fine-tune, or training from commercial movie catalogs without documented rights.

---

## 8. Quick smoke checklist

1. `uv run main.py` → Studio opens (Cyber Dark UI).
2. **Settings → Features** — Whisper / model cards look healthy; optional extras show installed or “install” hints.
3. Open or create a project with a **short clip**.
4. **Script** tab → **Transcribe** (local Whisper). Confirm lines appear.
5. If a Gemini key is set → **Translate** a few lines (or open **Tools → Khmer Spoken Dataset…** and generate a small candidate batch).
6. Optional: pick an Edge / Kitten voice and speak one line; try OmniVoice/VoxCPM2 only after the matching `uv sync --extra …`.

Headless import check:

```bash
QT_QPA_PLATFORM=offscreen uv run python -c "from claynext.app import main; print('Ready')"
```

---

## 9. Troubleshooting

| Symptom | What to try |
|:---|:---|
| OpenMP / KMP duplicate library | `KMP_DUPLICATE_LIB_OK=TRUE uv run main.py` |
| Gemini / translate fails | Settings → **API Keys**; or export `GEMINI_API_KEY` / `GOOGLE_API_KEY` in the shell (never commit secrets) |
| ASR / TTS model missing | Settings → **Features**; weights live in `data/models/` |
| FFmpeg / extract errors | Rebuild `claynext-ffmpeg`, or rely on `imageio-ffmpeg` after `uv sync`; optional `brew install ffmpeg` |
| OmniVoice / VoxCPM2 import errors | `uv sync --extra omnivoice` or `--extra voxcpm`, restart Studio |
| SGLang errors | Only relevant if you set the URL — start the server or clear the field / leave default unused |
| Temps / caches cluttering git | Use `data/cache/`, `data/outputs/`, `data/models/` — **never** write job temps into the repo root |
| Intel vs M4 confusion | This machine is arm64 — prefer current `uv sync` + optional extras; do not copy Intel torch pins here |

More detail: [AGENTS.md](../../AGENTS.md), [docs/khmer_spoken](../khmer_spoken/README.md), [docs/voice_training](../voice_training/README.md).
