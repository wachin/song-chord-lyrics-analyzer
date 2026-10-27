# Agent Handoff

> This file is a **dated session handoff**, not the setup guide. For a fresh
> developer or agent, read [`docs/AGENT_ONBOARDING.md`](docs/AGENT_ONBOARDING.md)
> and [`AGENTS.md`](AGENTS.md) first; current status is `ROADMAP.md` §1. The
> `.venv`/`.venv-chords` commands below are the author's local environments;
> substitute your own and prefer `python scripts/check.py`.

---

## Project

**Project:** `song-chord-lyrics-analyzer`
**Package:** `song_chord_lyrics_analyzer`
**CLI:** `songlab`
**License:** GPL-3.0-or-later
**Language:** Python 3.10+ (developed on 3.13, Linux), core has **zero required dependencies**
**Target platforms:** Linux, Windows, macOS
**GUI:** PyQt6 behind the optional `gui` extra — the window exists
(`songlab gui`, roadmap Phase D, 2026-10-08); the `[F]` features landed phase by
phase after it (lyrics view, the **chord-over-lyrics chart** 2026-10-21, editing,
transpose/simplify and `songlab export` — see `docs/GUI_REQUIREMENTS.md` for what
is still open: translations).

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
  (CQT chroma + harmonic-weighted triad templates + majority/Viterbi decoder,
  change penalty 0.40 measured 2026-10-21), **lyrics** `parakeet-onnx`,
  **key** `krumhansl`, **tempo** `librosa-tempo`. Kinds `BEATS`, `STEMS`,
  `NOTES` have **no** engine.
- Canonical typed model (`models/`), JSON codec with `SCHEMA_VERSION=1`
  (`schema/codec.py`), engine protocols (`engines/base.py`), error handling,
  logging. **Note (2026-10-20):** `models/` had been silently excluded from every
  commit by an unanchored `models/` rule in `.gitignore`; the rule is now
  `/models/` and the package is tracked. A fresh clone before this fix could not
  import the package.
- **Chord measurement and confidence (2026-10-19/20/21):**
  `scripts/chord_benchmark.py` plus the committed GuitarSet manifest measure the
  chord engine reproducibly (CSR **0.6312**, triad 0.6384, on 180 comping takes,
  2026-10-27), and every `ChordEvent` carries a calibrated confidence derived
  from its score margin (held-out Brier 0.1485, ECE 0.0363, accuracy 0.809 at
  coverage 0.476, refitted 2026-10-27). The raw margin stays in
  `metadata["score_margin"]`. Method and tables: `docs/ENGINE_COMPARISON.md` §6,
  §7 (previous defaults) and §8 (adopted defaults and ablations). The engine is
  `chroma-baseline` 0.2.0: `sqrt` chroma, harmonic templates, change penalty
  0.40 and a 0.50 s minimum-duration merge; each is an option.
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
- Tests: **2136 passed / 2 skipped in 262 s** (`.venv-chords`, DSP + GUI +
  real output device, `QT_QPA_PLATFORM=offscreen`, 2026-10-27); `.venv` reports
  **2128 passed / 10 skipped** (no output device); `ruff check`,
  `ruff format --check` (173 files), `mypy` (93 files) all green.
- **Phase H transforms + export (2026-10-13):**
  - `app/editing.py` — `TransposeDocument` / `SimplifyDocument` over the
    effective layer, on the same tape as the per-chord edits (undo, redo and
    sidecar persistence come for free).
  - `gui/main_window.py` — "Transpose all chords..." (-11..+11 dialog) and
    "Simplify all chords" on the Edit toolbar.
  - `export/` — `render_json` / `render_chordpro` / `render_markdown` and
    `export_document()`; `cli/commands/export.py` exposes the flag-first
    `songlab export` (sidecar edits fold in, `--transpose/--simplify` last).
  - Tests: round-trip export → parse and unit suites for the two commands.

### Partially implemented

- **Decoding**: closed on 2026-10-16 — `chroma_baseline`, `key_krumhansl`,
  `tempo_librosa` and `lyrics_parakeet` all decode through `decode_audio()`,
  as do the player and the session's waveform fallback, so nothing owns
  decoding privately any more (roadmap Phase A, now `[x]`).
- **Synchronized display**: `songlab play` (terminal) and `songlab gui`
  (window) both render the same `DisplayFrame`, and the window now draws the
  **chord-over-lyrics chart** (`app/chord_lyrics.py` + `gui/lyrics_view.py`,
  2026-10-21): each chord above the timed word it starts on, instrumental gap
  rows, active-chord highlight and key-aware spelling. A **plain-text chart
  import** (`app/chart_import.py`, 2026-10-27) makes a user's chart the timed
  chord and lyric base. What the window does **not** have yet is the remaining
  `[F]` depth - translations, and section-aware chart timing.
- **GUI testing without a screen**: the presenters are pure Python and the
  widgets are driven offscreen, but nothing here has been run by hand on
  Windows or macOS (no claim is made about them beyond the shared code path).
- **Chord confidence**: measured since 2026-10-20, but calibrated on GuitarSet
  solo acoustic guitar only. On a mixed recording the number keeps its ordering
  and loses its probability meaning, and an `N` event's value is extrapolation
  because GuitarSet has no notated silence (`docs/ENGINE_COMPARISON.md` §6).
- **Transpose / simplify / export (Phase H, 2026-10-13)**: `TransposeDocument`
  and `SimplifyDocument` commands in `app/editing.py` ride the same tape as the
  per-chord edits; the window pitches them as "Transpose all chords..." (a
  -11..+11 dialog) and "Simplify all chords". `export/` now has
  `render_json` / `render_chordpro` / `render_markdown`, and `songlab export`
  writes JSON / ChordPro / Markdown from the effective layer — sidecar edits
  included, `--transpose`/`--simplify` applied last so the flags reflect the
  same workflow the GUI uses.

### Chord-detection audit (2026-10-18, read-only)

A full audit of the chord path is in
[`docs/CHORD_DETECTION_AUDIT.md`](docs/CHORD_DETECTION_AUDIT.md). It changed no
code. The findings another session must not re-derive:

- **The real path:** `SongSession.open()` → `run_analysis()` →
  `ChromaBaselineEngine.analyze()` → `decode_audio()` (mono 22.05 kHz) →
  `librosa.feature.chroma_cqt(hop_length=2048)` → cosine similarity against 24
  root-position triad templates + a constant no-chord score →
  `viterbi_decode()` (flat 0.80 change penalty) → `segments_from_labels()` →
  `ChordEvent`. The GUI only renders `chord_at()` through `app/` presenters.
- **Vocabulary is phase 1 only:** the engine emits major, minor or `N`. The
  model/parser support sevenths, sus, dim/aug, add9/6/9 and slash basses, but
  the engine never produces them and refuses `vocabulary_phase > 1`.
- **Not modelled:** key conditioning, bass/inversions, tuning estimation,
  harmonic-percussive separation, onsets/beats, instrument changes. Boundaries
  are frame-grid only (2048/22050 ≈ 92.9 ms). Per-chord confidence *was* in this
  list and is now implemented (2026-10-20).
- **Test gap:** no committed test asserts label correctness on audio. The E2E
  test (`tests/integration/test_analysis_e2e.py`) checks timestamp coverage,
  vocabulary and provenance only; `tests/fixtures/csr_oracle.json` pins metric
  semantics with stored hypotheses. The audit ran 381 chord-related tests in
  `.venv-chords` on 2026-10-18: all passed.
- **Small defects found:** the Viterbi path ignores `match_threshold` but
  records it in metadata; `raw.frame_labels` is the majority-decoder output even
  on Viterbi runs; `analysis/chunking.py`'s seam comment says a frame is ~23 ms
  while the chord hop is ~92.9 ms; `docs/ENGINE_COMPARISON.md` begins at section
  4, so the chord-measurement method table is missing from the current tree.
- **Resolved since the audit (2026-10-20):** P1 (the harness and manifest) and P2
  (per-chord confidence) are implemented, the Viterbi run now records
  `match_threshold_used` / `smoothing_window_used`, and the ENGINE_COMPARISON
  method table is restored. Still open from that list: `raw.frame_labels` remains
  the majority output on Viterbi runs, and the chunking seam comment is stale.
- **Manual GUI check:** the user launched the window on MX Linux 25 in
  `.venv-chords` and reported waveform, lyrics panel, analysis info, working
  playback, moving playhead, changing chords, and an estimated ~75 % correct.
  This is a user observation, **not** a benchmark; do not cite it as measured
  accuracy. The README records the commands and screenshot. The window has since
  gained the chord chart; re-check it by hand after a rebuild if you are
  changing the lyrics widget.

**Next accuracy work, in order (audit §10):** P1–P3 are **implemented**
(2026-10-19..21), including the measured sqrt/harmonic/penalty/minimum-duration
pass (CSR 0.6121 → 0.6312; the 0.30 s step measured 0.6283). Remaining: P4 bass/slash chords, P5
duration/metrical model, P6 vocabulary phase 2 only with separate bass evidence,
P7 shared decode/chroma, P8 alternative engine last. The measured ceiling of the
template pipeline on GuitarSet is ~0.63, so the next real step is a
licence-clean **learned** engine with a documented train/held-out split; do not
repeat the rejected 109-class ONNX probe or the aggressive seventh pass
(`docs/ENGINE_COMPARISON.md` §8, `docs/CHORD_DETECTION_AUDIT.md` §14).

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

- The window's `[F]` features: confidence/engine panels, translations
  (`docs/GUI_REQUIREMENTS.md`; landed already: the lyrics view 2026-10-09,
  chord and lyric editing with undo/redo and persistence 2026-10-10..12,
  transpose + chord simplification 2026-10-13, the Export document...
  save dialog over the Phase H exporters 2026-10-13). Each remaining item is
  small enough to land on its own and every one of them needs an `app/`
  presenter with offscreen tests.
- Packaging; translations; a beat engine; a licence-clean learned chord engine.
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
- **Chord decoding** — Viterbi change penalty measured on 180 GuitarSet comping
  takes (2026-10-19, `scripts/chord_benchmark.py`): CSR 0.6029 vs 0.5300 for the
  majority smoother; change-F1 0.8270 vs 0.4033. The *current* defaults
  (`tuning=zero` since 2026-10-20, then sqrt chroma + harmonic templates +
  penalty 0.40 + 0.50 s merge since 2026-10-27) measure **CSR 0.6312 /
  change-F1 0.8553**; the penalty was re-swept for the new emissions. The
  previously cited 0.4260 did not reproduce and is retired
  (`docs/ENGINE_COMPARISON.md` §2 has the traceability note, §7 the front-end
  sweep, §8 the adopted scoring stage and ablations). Do not measure it again —
  measure the *next* change against this vector.
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

## Immediate Next Task — what the next session should pick up

**The chord chart landed 2026-10-21; the 2026-10-27 pass tightened it.** The
window draws the effective chord layer over the effective lyric layer
(`app/chord_lyrics.py` and the rewritten `gui/lyrics_view.py`), with key-aware
spelling and instrumental gap rows. Long rows are now `NoWrap` (wrapping used to
break the chord columns), the chart gets half the default width, the minimum
chord duration is 0.50 s after the measured pass,
`evaluation/chart.py` + `scripts/chord_chart_check.py` compare a hand chart to
the detector, and `app/chart_import.py` can make that chart the timed base. The gate is green (2136 passed / 2 skipped in `.venv-chords`).
Use the completed work as the reference for how a GUI feature is split into a
pure presenter plus a thin widget:

* `app/chord_lyrics.py` — `chord_lyric_lines()`, `ChordLyricLine`, `PlacedChord`:
  word-onset anchoring, proportional fallback, gap grouping, collision nudging,
  flat-key spelling through `normalization/spelling.py`,
* `gui/lyrics_view.py` — one `QTextBlock` per row (chord line + lyric line),
  active chord from the same frame as the big label, block→display-index mapping
  preserved for the lyric edit commands,
* `gui/main_window.py` — `_populate_lyrics()` passes the effective chords and the
  session's `prefer_flats`; `refresh()` passes the frame's chord,
* tests: `tests/unit/test_chord_lyrics.py`, `tests/unit/test_spelling.py`,
  `tests/unit/test_gui_lyrics_view.py`, `TestChordsAboveTheLyrics` in
  `tests/unit/test_gui_main_window.py`,
* `ROADMAP.md` §1/§7, `docs/GUI_REQUIREMENTS.md` and the changelog were updated
  in the same change.

**Chart import landed 2026-10-27.** `app/chart_import.py` parses the user's
plain-text chart, anchors its chords under the chart's chord columns, times its
lyric lines from the transcript's words, distributes instrumental runs, and
`MainWindow.load_chart_from()` (Edit →
Load chord chart..., `Ctrl+Shift+L`) replaces both bases through
`with_chart_bases`; the chart base is saved to the sidecar like any edit. It was
verified on the private 5:27 song: 86 timed chart chords and 36 correct lyric
lines, with 83/182 chart words anchored (ROADMAP Phase F,
`tests/unit/test_chart_import.py` (14 tests), `TestImportingAChordChart`). The next
refinements are section-aware timing, recording the chart path in provenance,
beat-level placement, and manual correction of a badly aligned line (ROADMAP §16, `docs/GUI_REQUIREMENTS.md` 1c).

The next accuracy task is the **learned chord engine** specified in
[`ROADMAP.md`](ROADMAP.md) §10 and
[`docs/CHORD_DETECTION_AUDIT.md`](docs/CHORD_DETECTION_AUDIT.md) §15: a
licence-clean dataset, a `scripts/` training path, a compact inference path
behind `ChordEngine` with an optional extra, and the same 180-take before/after
vector plus a documented held-out split. P4–P8 remain open. Do not ship weights
of unknown provenance, do not train and test on the same takes, and do not
promise the proprietary apps' accuracy numbers.

The gate is known and unforgiving (same as every phase):
`.venv/bin/ruff check . --output-format=concise`, `.venv/bin/ruff format --check`,
`.venv/bin/python -m mypy` and `.venv/bin/python -m pytest -q` — plus the
`.venv-chords` suite with the DSP and GUI extras, and the privacy grep that
must exit 1. Nothing extra lands between the code and the commit: the
`ROADMAP.md` markers move in the same change, the docs update together and
then the signed commit goes out.
