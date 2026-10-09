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
**GUI:** PyQt6 behind the optional `gui` extra — the minimal window exists
(`songlab gui`, roadmap Phase D, 2026-10-08); editing/lyrics/exports in it do not

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

Audit executed **2026-10-06** by running the code (not by reading docs); the
Phase C display work landed **2026-10-07**, the Phase D window landed
**2026-10-08**, and the counts below are from the gate re-run that day.

### Implemented (verified by execution)

- `songlab info`, `songlab doctor` — metadata probing (ffprobe / WAV stdlib),
  FFmpeg discovery (`audio/`).
- `songlab chords` — runs the registered chord engine. **Verified on a real
  MP3 song (296.8 s): 76 timestamped `ChordEvent`s (`start`/`end`/`label`).**
- `songlab analyze [--json]` — chords + key + tempo assembled into the
  canonical document with provenance (SHA-256, versions, engines, config) via
  `analysis/service.py`. **Verified on the same real MP3** (E major, 143.6 BPM,
  `run.steps` all `ok`).
- `songlab play` — **the product command**: opens one file through
  `SongSession`, plays it and draws the chord under the playhead, refreshing as
  the song advances (`app/display.py` + `cli/commands/play.py`). `--at SECONDS`
  prints one frame without playing. **Verified on a real device and headless.**
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
- **Headless Phase A/B/C work (same day, after the audit):**
  - `audio/decode.py` — one shared decode service (`decode_audio()`): a
    librosa/soundfile backend plus a dependency-free stdlib WAV backend,
    returning interleaved mono/stereo floats in `[-1, 1]` and the sample rate.
  - `audio/playback.py` — `Player` protocol (no Qt), pure `PlaybackTimeline`
    (injectable clock) and a `sounddevice` backend (optional `playback` extra,
    MIT, `docs/DEPENDENCY_MATRIX.md` §2.1). **Verified on a real device.**
  - `app/session.py` — `SongSession`: open → decode → analyze → player →
    `chord_at(seconds)` (binary search) and `SessionSnapshot`. No Qt, no ML.
  - New committed tests: real-file E2E (`tests/integration/test_analysis_e2e.py`),
    decode unit + integration tests, playback unit (fake PortAudio) + real-device
    tests, session unit (fake clock) + integration tests. A new CI job installs
    the `dsp` extra so the real engines run somewhere in CI.
- **Phase C display work (2026-10-07):**
  - `app/display.py` — the presenter: `DisplayFrame`, pure `frame_from()` /
    `render_frame()`, `ConsoleDisplay` (in-place redraw on a tty, one line per
    frame otherwise) and `follow(session, display, interval, sleep, max_frames)`
    with the sleep injected, so the refresh loop is tested on a fake clock.
  - `cli/commands/play.py` — **`songlab play`**: open → analyze → print a short
    header → play → draw the chord under the playhead while it advances.
    `--at SECONDS` prints one frame without playing (used by tests and CI),
    `--interval`, `--frames`, `--no-inline`, `--engine KIND=NAME`, `--no-hash`.
  - Tests: `tests/unit/test_display.py` (24), `tests/unit/test_play_command.py`
    (13), `tests/integration/test_display_integration.py` (3, real analysis and
    real playback with the assertion that every drawn frame carries exactly the
    chord `chord_at()` claims for its position).
- **Phase D window work (2026-10-08):**
  - `gui/main_window.py` — `MainWindow` + `launch()`: the transport (open,
    play/pause, stop, back/forward), the big chord label with the time and the
    state, the timeline, the analysis panel, one `snapshot()` per timer tick
    turned into the same `DisplayFrame` the terminal display renders, and an
    honest `QMessageBox` (plus exit code 1 when a file passed on the command
    line cannot be opened). `refresh()` is public on purpose: the tests drive it.
  - `gui/timeline.py` — `TimelineWidget`: waveform + chord strip + playhead
    painted together, `seek_requested(seconds)` on click or drag, geometry from
    the presenter (`seconds_at`, `x_at`).
  - `gui/analysis_panel.py` — `AnalysisPanel`: the rows `summarize()` produced,
    read back out of the widgets by the tests (`text_rows()`).
  - `gui/__init__.py` — `require_qt()` + `run()`; Qt is imported lazily, so a
    Qt-free install keeps every other command working and `songlab gui` raises
    `DependencyError` (exit 3) with the install hint.
  - `app/timeline.py` — `ChordBand`, `chord_bands()` (half-open semantics of
    `chord_at`, clipped to the track, latest start wins),
    `x_for_position()`/`position_for_x()`.
  - `app/summary.py` — `SummaryRow`, `summarize()` (file, duration, chords, key,
    tempo, engines, skipped/failed layers, run status, versions, platform, input
    hash, warning count; a missing value omits the row).
  - `audio/peaks.py` — `WaveformPeaks`, `waveform_peaks()`, `peaks_of()`: min/max
    per bucket, frame-aligned, **no numpy import**; reached through
    `SongSession.waveform_peaks(buckets)` (reuses the player's decoded samples,
    cached per resolution).
  - `cli/commands/gui.py` — `songlab gui [AUDIO] [--engine KIND=NAME] [--no-hash]`.
  - `pyproject.toml` — optional `gui` extra (`PyQt6>=6.5`).
  - Tests: `tests/unit/test_gui_main_window.py`, `tests/unit/test_gui_command.py`,
    `tests/unit/test_timeline_presenter.py`, `tests/unit/test_summary_presenter.py`,
    `tests/unit/test_peaks.py`, `tests/integration/test_gui_integration.py`
    (real engine, real file, real device where one exists, offscreen).
- Tests: **1340 passed / 57 skipped** (core `.venv`), **1395 passed / 2
  skipped** (DSP + GUI `.venv-chords`); `ruff check`, `ruff format --check` (118
  files), `mypy` (71 files) all green.

### Partially implemented

- **Decoding**: the shared service exists, but the DSP engines still call
  `librosa.load` themselves and are not yet switched over to it (roadmap
  Phase A).
- **Synchronized display**: `songlab play` (terminal) and `songlab gui`
  (window) both render the same `DisplayFrame`; what the window does **not**
  have yet is its `[F]` depth - editing, lyrics view, undo/redo, transpose,
  export dialogs, confidence/engine panels, translations.
- **GUI testing without a screen**: the presenters are pure Python and the
  widgets are driven offscreen, but nothing here has been run by hand on
  Windows or macOS (no claim is made about them beyond the shared code path).
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

- The window's `[F]` features: lyrics display, editing with undo/redo,
  transpose, chord simplification, export dialogs, confidence/engine panels,
  translations (`docs/GUI_REQUIREMENTS.md`).
- Lyrics engine integration (Phase E), synchronized lyrics, packaging.
- A Qt Multimedia `Player` backend: the window currently drives the session's
  `sounddevice` player, which is deliberate (one audio path) but is still the
  only backend.

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

**Status: all seven work in two front ends (2026-10-08)** — verified by running
them: `songlab play` on a real device while the chord changed with the playhead,
`songlab gui` (offscreen, and on a real device) drawing the same frame with the
waveform, the chord bands and the analysis panel, plus integration tests that
assert every drawn frame carries exactly the chord `chord_at()` claims for that
position. Links 1–4 were verified on real audio, 5–6 are the tested
player/playhead, and 7 is the terminal display plus the window.

Two honest limits on that claim: the window is the **minimal** one (no editing,
lyrics or exports yet - `docs/GUI_REQUIREMENTS.md` lists what is still `[F]`),
and the claim is about **synchronization, not accuracy** — wrong chords are still
wrong until Phase I.

---

## Existing Components To Reuse

Search the repository before creating anything new.

- `audio/` — `validation.py` (safe input), `probe.py` (ffprobe/WAV metadata),
  `ffmpeg.py` (discovery, install hints, no-shell execution), `decode.py`
  (the shared decode service) and `playback.py` (player + timeline).
- `app/session.py` — `SongSession` / `SessionSnapshot`: the headless service a
  GUI or CLI drives (open, play, `chord_at`, snapshot).
- `app/display.py` — the presenter both front ends reuse: `DisplayFrame`,
  `frame_from()`, `render_frame()`, `ConsoleDisplay`, `follow()`. The window
  renders `DisplayFrame` rather than re-deriving positions, and `app/` stays
  free of Qt imports.
- `app/timeline.py` — the timeline presenter: `ChordBand`, `chord_bands()`,
  `x_for_position()`, `position_for_x()`. Add timeline geometry here, not in a
  widget, so it stays testable without a display.
- `app/summary.py` — `SummaryRow`, `summarize()`; add panel rows here for the
  same reason.
- `audio/peaks.py` — `WaveformPeaks`, `waveform_peaks()`, `peaks_of()` (no numpy
  import); the waveforms a timeline draws come from here via
  `SongSession.waveform_peaks(buckets)`.
- `gui/` — the window itself: `main_window.py` (transport, refresh, file dialog),
  `timeline.py` (waveform + chord strip + playhead, click/drag seeks),
  `analysis_panel.py` (the summary rows). Hard rule: `gui/` imports Qt and `app/`
  only - never engines, numpy, `librosa` or `analysis/` internals. New behaviour
  goes into an `app/` presenter (pure, core-tested) and is only rendered here.
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
- Do **not** grow the GUI into the full feature list at once: the minimal window
  (Phase D) is done, and the remaining GUI work is the `[F]` list in
  `docs/GUI_REQUIREMENTS.md`, taken one feature at a time, each behind an `app/`
  presenter with offscreen tests.
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
  `mypy` type-checks `gui/` against the real PyQt6 stubs, so both venvs install
  the optional extras (`.venv`: `.[dev,gui]`; `.venv-chords`:
  `.[dev,dsp,playback,gui]`). That is a development-environment requirement, not
  a dependency of the installed package.
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

## Immediate Next Task — complete, recorded for the next session

**Phase E was completed 2026-10-08.** It is no longer the next task: the
lyrics engine is a registered, optional extra (`ParakeetLyricsEngine`, via
`onnx-asr`, MIT runtime / CC-BY-4.0 weights), chunked at 20 s, flow through
`run_analysis()`, `songlab lyrics` and both front ends, and structurally
verified on `samples/vocadito_6.wav` (real weights, real voice).

Use it as the reference for the session that wants to continue here
(`ROADMAP.md` §7 tracks the completion in the same change):

* `engines/lyrics_parakeet.py` (engine + `Transcriber` seam, `is_available()`
  honest, model download stays out of the repository),
* `engines/lyrics_chunking.py` (windowing, timestamp reassembly, the
  documented "earlier window wins" overlap rule),
* `cli/commands/lyrics.py` (`songlab lyrics`, `--engine NAME`, `--chunk-`*
  `--start`/`--end`/`--language`/`--no-words`),
* `analysis/service.py` (lyrics step, same skipped/failed handling as the
  other layers),
* `utils/text.py` (the English agreement helper shared by the two front ends),
* `tests/integration/test_lyrics_integration.py` and the `test_lyrics_*.py`
  units (injected transcriber, real decode + windows on a generated song,
  structural honesty only on the committed sample),
* `pyproject.toml` (optional `lyrics` extra), `ROADMAP.md` §7, the docs
  (`ENGINE_COMPARISON.md`, `DEPENDENCY_MATRIX.md`, `GUI_REQUIREMENTS.md`).

The gate for this work is known and unforgiving (same as every phase):
`.venv/bin/ruff check . --output-format=concise`, `.venv/bin/ruff format --check`,
`.venv/bin/python -m mypy` and `.venv/bin/python -m pytest -q` — plus the
`.venv-chords` suite with the DSP and GUI extras, and the privacy grep that
must exit 1. Nothing extra lands between the code and the commit: the
`ROADMAP.md` markers move in the same change, the docs update together and
then the signed commit goes out.

**What remains open (and what is not the next task):**

* The `[F]` GUI list in `docs/GUI_REQUIREMENTS.md` — lyrics view, chord/
  lyric editing with undo/redo, transpose, chord simplification, export
  dialogs, confidence/engine panels, translations. Each item is small enough to
  land on its own and every one of them needs an `app/` presenter with
  offscreen tests.
* **Confidence per chord + the JSON contract** — the `lyrics` step carries
  `unknown` confidence and the canonical `EngineResult` ships a `lyrics` field;
  exposing that honestly per position in the window is `[F]` work, not more
  engine work.
* Any of the four alternatives the user replies with, if they prefer not to
  follow the phase list.
