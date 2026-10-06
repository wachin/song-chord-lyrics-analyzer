# Agent Handoff

> This file lets a **new AI-agent session** continue the project without the
> context of previous conversations. Read it first, then `ROADMAP.md`.

---

## Project

**Project:** `song-chord-lyrics-analyzer`
**Package:** `song_chord_lyrics_analyzer`
**CLI:** `songlab`
**License:** GPL-3.0-or-later
**Language:** Python 3.10+ (developed on 3.13, Linux), core has **zero required dependencies**
**Target platforms:** Linux, Windows, macOS
**Planned GUI:** PyQt6 (never started)

---

## Product Goal

Build a **free, open-source alternative to Chordify / Chord AI**: an offline
desktop application where a user

1. opens an MP3/audio file,
2. plays the song,
3. gets it analyzed automatically,
4. sees detected chords **with timestamps**,
5. sees the current chord **synchronized with playback** (plus a
   waveform/timeline),
6. later: sees transcribed lyrics synchronized too,
7. can edit/correct chords and lyrics, transpose, simplify,
8. exports the analysis,
9. on Linux, Windows and macOS.

Core workflow:

```text
MP3/audio file → audio decoding → chord detection → timestamped ChordEvent
sequence → audio playback → synchronized chord display
```

---

## Current State

Audit executed **2026-10-06** by running the code (not by reading docs).

### Implemented (verified by execution)

- `songlab info`, `songlab doctor` — metadata probing (ffprobe / WAV stdlib),
  FFmpeg discovery (`audio/`).
- `songlab chords` — runs the registered chord engine. **Verified on a real
  MP3 song (296.8 s): 76 timestamped `ChordEvent`s (`start`/`end`/`label`).**
- `songlab analyze [--json]` — chords + key + tempo assembled into the
  canonical document with provenance (SHA-256, versions, engines, config) via
  `analysis/service.py`. **Verified on the same real MP3** (E major, 143.6 BPM,
  `run.steps` all `ok`).
- `songlab benchmark --engine` — kind-agnostic benchmark runner (`benchmark/`).
- Engines registered in `engines/registry.py`: **chords** `chroma-baseline`
  (CQT chroma + 24 triad templates + majority/Viterbi decoder, change penalty
  0.80 measured), **key** `krumhansl`, **tempo** `librosa-tempo`.
  Kinds `LYRICS`, `BEATS`, `STEMS`, `NOTES` have **no** engine.
- Canonical typed model (`models/`), JSON codec with `SCHEMA_VERSION=1`
  (`schema/codec.py`), engine protocols (`engines/base.py`), error handling,
  logging.
- Metrics/evaluation as library code (`metrics/`, `evaluation/`), pinned
  GuitarSet annotation oracles in `tests/fixtures/`.
- Tests: **1165 passed / 9 skipped** (core `.venv`), **1173 passed / 1
  skipped** (DSP `.venv-chords`); `ruff check`, `ruff format --check` (84
  files), `mypy` (57 files) all green.

### Partially implemented

- **Real-file E2E**: verified manually during the audit, but **no committed
  automated test** runs a real song end to end (tests use synthetic WAV +
  fake engines).
- **Decoding**: each DSP engine calls `librosa.load` itself; there is **no
  shared application-level decode service** usable by analysis *and* playback.
- **Chord confidence**: field exists, baseline engine reports `unknown`.
- **Transpose**: `transpose_chord_label()` / `transpose_note_name()` exist as
  library functions only — no user-facing workflow.
- **JSON export**: only `analyze --json`; `export/` package is an empty
  placeholder (`__init__.py` only). Same for `alignment/`, `fusion/`, `i18n/`.

### Research only (measured, recorded, NOT wired into the product)

- Lyrics ASR: Parakeet-1B-v3 via `onnx-asr` (WER 0.3722) vs faster-whisper
  small (WER 0.3799), both MIT; **long audio must be chunked (~20 s windows)**;
  Demucs stems do **not** help by default. Corpus cached in `.cache/`
  (gitignored). Details in `docs/ENGINE_COMPARISON.md`.
- Datasets: GuitarSet (CC BY 4.0) adopted; IDMT/CASD blocked (NC/ND/SA).
  `docs/DATASET.md`, `docs/LICENSE_AUDIT.md`, `docs/DEPENDENCY_MATRIX.md`.
- Key/tempo/chord measurements on GuitarSet (see `docs/ENGINE_COMPARISON.md`).
- Candidate tools investigated: Chordino, madmom, beat_this, basic-pitch,
  Guitariz, musicpractice — all in `external/` as **read-only reference**.

### Planned / not started (product path)

- **Audio playback** — zero playback code in `src/` (only inside `external/`).
- **Current playback timestamp** — follows from playback.
- **Any GUI / display** — zero Qt code in `src/`; `docs/GUI_REQUIREMENTS.md`
  is a plan only.
- Lyrics engine integration, synchronized lyrics, editing/undo-redo,
  transpose/simplify/export workflows, packaging.

---

## Critical Product Direction

The project previously ran as a research lab with the loop
`research → benchmark → dataset → model → engine → experiment`.
**That stopped on 2026-10-06.** Research and benchmarking are now *supporting*
activities. The main path is:

**working vertical slice → validation → GUI → lyrics → editing/export →
improvements → additional engines/research.**

Preserve all existing code, docs and research — but do not let any of it
become the main development path again. The product (open → analyze → play →
synchronized chords) is the priority.

---

## First Milestone

**MP3/audio file → audio decoding → chord analysis → timestamped ChordEvents →
playback → synchronized chord display.**

Acceptance (all seven, from `ROADMAP.md` §4): a user can provide a real
MP3/audio file and the application can (1) load it, (2) analyze it,
(3) produce timestamped chords, (4) play the audio, (5) determine the current
playback timestamp, (6) display the corresponding chord, (7) update the
displayed chord as playback advances.

**Until this works, the project must not be described as a functional
Chordify/Chord AI-style application — it is an analysis laboratory.**
Links 1–4 of that path already exist and were verified on real audio; links
5–7 (playback, position, synchronized display) do not exist at all.

---

## Existing Components To Reuse

Search the repository before creating anything new.

- `audio/` — `validation.py` (safe input), `probe.py` (ffprobe/WAV metadata),
  `ffmpeg.py` (discovery, install hints, no-shell execution).
- `engines/base.py` — protocols `ChordEngine`, `LyricsEngine`, `BeatEngine`,
  `KeyEngine`, `TempoEngine`; `EngineKind`; options dataclasses.
- `engines/registry.py` — `EngineRegistry`, `create_default_registry()`.
- `engines/chroma_baseline.py` + `engines/decoding.py` — the chord engine and
  pure-Python Viterbi.
- `analysis/service.py` — `run_analysis()`: orchestration, honest
  ok/skipped/failed step statuses, provenance assembly.
- `models/` — `ChordEvent` (start/end/label/confidence), `AudioDocument`,
  `KeyEstimate`, `TempoEstimate`, `LyricSegment`/`LyricWord`, `AnalysisResult`,
  `Provenance`, `AnalysisRun`.
- `schema/codec.py` — canonical JSON encode/decode (`SCHEMA_VERSION = "1"`).
- `cli/` — argument parsing, error→exit-code handling; add commands the same way.
- `normalization/chords.py` — label rendering, parsing, **transposition**.
- `metrics/` + `evaluation/` — chord/key/tempo/lyrics metrics, CSR, MIREX
  equality; `benchmark/` runner and report.
- `performance.py` — timing/RTF harness.
- Tests: `tests/unit`, `tests/integration`, `tests/regression`, fixtures with
  fake engines and GuitarSet annotation oracles.
- Docs: `docs/ARCHITECTURE.md`, `ENGINE_COMPARISON.md`, `DATASET.md`,
  `DEPENDENCY_MATRIX.md`, `LICENSE_AUDIT.md`, `BENCHMARK.md`,
  `GUI_REQUIREMENTS.md`, `TROUBLESHOOTING.md`.

---

## Things Already Researched

Do **not** repeat these; they are measured and recorded:

- **Datasets with timed chord labels** — full search done; GuitarSet is the
  only permissive real-audio source; others blocked by licence.
- **Licensing** — code/model/dataset licences audited
  (`docs/LICENSE_AUDIT.md`). Re-open only for a concrete new dependency.
- **Lyrics ASR comparison** — Parakeet vs faster-whisper numbers, chunking
  requirement, stems conclusion (see Current State).
- **Chord decoding** — Viterbi change penalty 0.80 measured on 180 GuitarSet
  takes (CSR 0.4260 vs 0.3676 majority; change-F1 0.6202 vs 0.3144).
- **Key** — Krumhansl: 0.4278 exact / 0.1333 relative over 360 takes.
- **Tempo** — librosa: 22.63 BPM mean error; octave readings kept, not hidden.
- **Candidate engines/tools** — Chordino, madmom, beat_this, basic-pitch, etc.
  evaluated; `external/` submodules are reference-only.

---

## Things NOT To Do Yet

- Do **not** restart dataset research or licensing research (unless a concrete
  new dependency requires it).
- Do **not** build experimental engines or add models before the First Product
  Milestone.
- Do **not** expand benchmarks/metrics/datasets without a product reason.
- Do **not** implement the complete GUI — only the Minimal Viable GUI, after
  the vertical slice (Phase D in `ROADMAP.md`).
- Do **not** rewrite working architecture or duplicate existing components —
  search first, reuse second.
- Do **not** import, install or lint anything from `external/`
  (see `AGENTS.md` hard rule).
- Do **not** make lyrics work block the chord vertical slice.
- Do **not** commit `.cache/`, `mp3/`, `.venv*`, real song audio, or private
  file names (privacy grep runs on every commit).

---

## New ROADMAP

[`ROADMAP.md`](ROADMAP.md) is **the authoritative development plan**
(rewritten 2026-10-06, product-first). Structure: §0 goal, §1 baseline audit,
Phases A–K, §13 Research Backlog, §14 Experimental Engines, §15 Long-Term.
Markers: `[x]` implemented (verified by execution), `[~]` partial, `[ ]` not
implemented — be conservative. The pre-reset roadmap is archived at
`docs/archive/ROADMAP-pre-product-reset.md` (history only; its `[*]` markers
are obsolete).

---

## Development Rules

- **Verify before declaring complete**: run the thing, then run the gate.
- Gate before every commit:
  ```bash
  .venv/bin/ruff check . --output-format=concise
  .venv/bin/ruff format .            # then --check
  .venv/bin/mypy
  .venv/bin/python -m pytest -q
  .venv-chords/bin/python -m pytest -q   # DSP-dependent tests
  ```
- Privacy check (must exit 1 = no matches). The pattern below is written with
  bracketed characters so this file never trips its own check:
  ```bash
  (git diff; git diff --cached) | grep "^+" | \
    grep -inE "[.]mp3|cifr[a]|ciph[e]r|Espin[o]sa|Sensin[i]|Hernande[z]|youtube[.]com/watch"
  ```
- Use `[x]`, `[~]`, `[ ]` honestly; never claim completion from docs alone.
- Reuse existing code; avoid duplicate implementations.
- Keep the GUI separated from low-level ML infrastructure (GUI → `app/`
  services → engines; never GUI → librosa).
- Test real end-to-end workflows, not only units.
- Update `ROADMAP.md` truthfully in the same change that completes work.
- Document in English; respond to the user in Spanish; commit message footer:
  `Generated with Codebuff` + `Co-Authored-By: Codebuff <noreply@codebuff.com>`.

---

## Immediate Next Task

**Do not begin by researching.** First read, in order:

1. `AGENT_HANDOFF.md` (this file),
2. `ROADMAP.md`,
3. the relevant source modules (start with `analysis/service.py`,
   `engines/`, `audio/`, `cli/`).

Then **audit the first incomplete product-critical phase** (currently
Phase A — audio input & playback foundation, and the untested real-file E2E in
Phase B) and propose the **smallest** implementation sequence that advances
the First Product Milestone. Wait for the user/developer's direction before
undertaking large or unrelated work. No new features were to be implemented in
the reset session itself — that boundary was respected.
