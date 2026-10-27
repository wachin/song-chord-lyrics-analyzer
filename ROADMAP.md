# Product Roadmap — song-chord-lyrics-analyzer

**Repository:** `song-chord-lyrics-analyzer`
**Python package:** `song_chord_lyrics_analyzer`
**CLI:** `songlab`
**GUI:** PyQt6 behind the optional `gui` extra (minimal window implemented, Phase D)
**Target platforms:** Linux, Windows, macOS
**License:** GPL-3.0-or-later
**Authoritative:** this file is the development plan. The former research-first
roadmap is preserved unchanged at
[`docs/archive/ROADMAP-pre-product-reset.md`](docs/archive/ROADMAP-pre-product-reset.md)
for history only. Where the two disagree, **this file wins**.

---

## Status rules

Every task and phase uses exactly these markers:

| Marker | Meaning |
| --- | --- |
| `[x]` | **Implemented.** The stated requirement exists in the repository, runs, and has been verified by executing it — not merely by documentation, design or partial tests. |
| `[~]` | **Partially implemented.** Some of the requirement works; the missing part is stated in the phase. |
| `[ ]` | **Not implemented.** |

Rules:

* Be conservative. Truthful progress beats a roadmap that looks complete.
* Never mark `[x]` because research finished, a design doc exists, a prototype
  exists, tests cover only part of the requirement, an engine exists but is not
  integrated, or a CLI command exists while the product workflow behind it is
  incomplete.
* Markers are updated in the same change that completes (or genuinely advances)
  the work, so the roadmap never lags the code.
* Every claim in the *Current Reality* section below was re-verified against the
  repository on **2026-10-06**, by running the code, not by reading docs.

### Work categories

Each section is tagged with its category so research can never silently become
the main path:

* **[P] Product-critical** — required for the end-user application.
* **[S] Supporting infrastructure** — tests, metrics, benchmark, docs that serve the product.
* **[R] Research / experimental** — subordinate to the product; never a blocker.
* **[F] Future enhancement** — after the product works.

---

## 0. Project Goal

**[P]** Build a free, open-source, offline-first alternative to Chordify and
Chord AI: a desktop application the user points at a song file, which analyzes
it and shows the chords (and later the lyrics) **synchronized with playback**,
and lets the user correct, transpose, simplify and export the result.

The central user experience:

```text
MP3/audio file
    ↓
audio decoding
    ↓
audio analysis
    ↓
chord detection
    ↓
timestamped ChordEvent sequence
    ↓
audio playback
    ↓
synchronized chord display
```

Later:

```text
audio → lyrics transcription → timestamped lyrics → synchronized lyrics + chords
```

### Priority order

1. Audio loading/decoding
2. Chord analysis
3. Timestamped chord events
4. Playback
5. Synchronization
6. Basic GUI
7. Lyrics engine integration
8. Synchronized lyrics
9. Editing
10. Transpose/simplification
11. Export
12. Additional engines and accuracy improvements
13. Advanced research/optimization

This order may be adjusted only when the repository proves another order is
technically necessary — never to insert more research ahead of the product.

### Direction change (2026-10-06)

The previous roadmap made research → benchmark → dataset → model → engine →
experiment the main path. That loop is now **supporting activity only**
(Phases I/J and the Research Backlog). All existing research, code, tests and
documentation are preserved; nothing is deleted because it is not on the
immediate product path. From now on the main path is:

**working vertical slice → validation → GUI → lyrics → editing/export →
improvements → additional engines/research.**

---

## 1. Current Reality / Baseline Audit

**[P]** Verified by execution on 2026-10-06 (Linux, Python 3.13, CPU-only).
Gate at the time of the audit: `ruff check` clean, `ruff format --check` 84 files
clean, `mypy` 57 files clean, `pytest` **1165 passed / 9 skipped** (core venv)
and **1173 passed / 1 skipped** (DSP venv with numpy/librosa).

Gate re-run after the headless Phase A/B/C work (same day): `ruff` clean,
`ruff format --check` 98 files,
`mypy` 61 files, `pytest` **1231 passed / 49 skipped** (core venv) and **1279
passed / 1 skipped** (DSP venv with numpy/librosa/soundfile/sounddevice).

Gate re-run after the Phase C display work (2026-10-07, same machine): `ruff`
clean, `ruff format --check` 103 files, `mypy` 63 files, `pytest` **1268 passed
/ 52 skipped** (core venv) and **1319 passed / 1 skipped** (DSP venv, where the
real-device playback and display-follow tests run).

Gate re-run after the Phase D window work (2026-10-08, same machine): `ruff`
clean, `ruff format --check` 118 files, `mypy` 71 files, `pytest` **1340 passed
/ 57 skipped** (core venv) and **1395 passed / 2 skipped** (DSP venv, which now
also installs the optional `gui` extra, so the window's tests run there on the
offscreen platform plugin, plus the real-device playback/follow tests).

Gate re-run after the playback playhead fix and the decode integration
(2026-10-16, same machine, Python 3.13.5): `ruff check` clean,
`ruff format --check` 150 files clean, `mypy` 87 files clean, `pytest` **1883
passed / 11 skipped** (`.venv` - on this machine it has the DSP and GUI extras
installed as well, so it is *not* the dependency-free core of the CI matrix)
and **1891 passed / 3 skipped** (`.venv-chords`: numpy 2.5.3, librosa 1.0.0,
sounddevice 0.5.6, real output device). The DSP suite was run a second time
under contention and gave **1891 passed / 3 skipped in 887 s** with eight
competing CPU processes (load average ~12 on 4 cores); `tests/integration/
test_display_integration.py` alone was run six times back to back, **3 passed
every time**, where the full-suite run of the same day *before* the fix failed
it with `AssertionError: the playhead must never go backwards` (positions
0.0503198 then 0.0385552) and both `.venv-chords` full-suite runs after the fix
passed it (`.venv` skips that test: no output device there).

Gate re-run after the chord chart and the measured front-end/template and
minimum-duration work (2026-10-27, same machine, Python 3.13.5, numpy 2.5.3,
librosa 1.0.0, PyQt6 offscreen): `ruff check` clean, `ruff format --check` 172
files clean, `mypy` 93 files clean, `pytest` **2136 passed / 2 skipped in
262 s**
(`.venv-chords`: numpy 2.5.3, librosa 1.0.0, sounddevice 0.5.6, PyQt6
6.11.0, real output device, `QT_QPA_PLATFORM=offscreen`; the two skips are the
intentional "the optional stack is installed here" branches) and **2128 passed
/ 10 skipped in 226 s** (`.venv`: no output device, so the eight playback
tests skip; the two "stack installed" branches differ too).

### Manual GUI verification — user-reported (2026-10-18)

The window was launched **by hand on MX Linux 25** (Debian 13 based) in this
repository's `.venv-chords` environment (CPython 3.13.5, PyQt6 installed), from
the repository root:

```bash
source .venv-chords/bin/activate
songlab gui
```

The **user** — not an automated test — opened an MP3 file, waited for the
analysis, and reported: the waveform appeared; a lyrics panel and the audio
information appeared on the right; playback worked; the position advanced along
the waveform; and chord names were displayed and changed during playback. The
same user estimated that roughly **75 % of the detected chords were correct**,
from listening and watching.

This is a **user-reported manual observation, not a benchmark**: one song, no
reference annotations, no defined matching rule, no repeatable procedure. It
must not be quoted as a validated 75 % chord-detection accuracy; an objective
figure needs a reference dataset with timed chords and a fixed evaluation
procedure (GuitarSet + `docs/BENCHMARK.md`). The launch steps, the screenshot
and the virtual-environment shutdown are documented in the README section
"Launching it by hand (MX Linux 25)". The read-only code audit that this
observation prompted is [`docs/CHORD_DETECTION_AUDIT.md`](docs/CHORD_DETECTION_AUDIT.md).

Separate from that manual session, the audit's own run on 2026-10-18 executed
the chord-related unit suites in `.venv-chords` and got **381 passed** (no GUI
and no real song).

### Chord-over-lyrics chart — verified (2026-10-21)

The window now draws a **chord chart over the synchronized lyrics**, the view
Chordify and Chord AI are known for, and it was verified by running the code:
`app/chord_lyrics.py` seats every chord above the timed word it starts on,
gives instrumental intros/breaks their own chord-only rows, never repeats a
chord that merely spans into the next line, and respells roots for a flat key;
`gui/lyrics_view.py` paints one monospace chord row plus one lyric row per
block, highlights the current chord from the same frame as the big label, and
keeps the block-to-display-index mapping exact for the lyric edits. The pure
presenter has 16 unit tests, the widget has 17 offscreen tests, and the window
has a test that C opens the first line, G starts a gap row, N opens the second
line and F starts the closing gap row. The measured accuracy of the engine
behind the chart is in §10 (Phase I); this section claims the **display**, not
a new accuracy number.

### The product path, link by link

| # | Link | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Real audio file input | `[x]` | `audio/validation.py` + `audio/probe.py` (ffprobe; WAV via stdlib). Verified on a real song file (296.8 s, MP3, 324 kbit/s). |
| 2 | Decoding to samples | `[x]` | One decode owner: `audio/decode.py` → `decode_audio()` (librosa/soundfile backend plus a stdlib WAV backend, mono/interleaved floats + sample rate) is asked by the chords, key, tempo and lyrics engines for the window they need, by `SoundDevicePlayer.load` for playback, and by `SongSession` for the waveform fallback; no component calls `librosa.load` privately any more. Verified 2026-10-16 on `samples/vocadito_6.wav` and `samples/vocadito_16.wav`: the three DSP engines return the same chord events (start/end/label), key and tempo before and after the switch, both whole-file and with a time window, plus a real compressed transcode through the service (`tests/integration/test_decode_integration.py`). |
| 3 | Chord engine on real audio | `[x]` | `ChromaBaselineEngine` registered, tested, measured (CSR **0.6312**, triad 0.6384, on 180 GuitarSet comping takes, instructed lead sheet, 2026-10-27 — `docs/ENGINE_COMPARISON.md` §8, reproducible with `scripts/chord_benchmark.py`; 0.6121 with the previous front end). Ran on a real song during the audit. |
| 4 | Timestamped ChordEvent sequence | `[x]` | `songlab chords` printed 76 events with `start`/`end`/`label` on a real song; `songlab analyze --json` emitted the same inside the canonical document with provenance (schema version 1, `schema/codec.py`). |
| 5 | Audio playback | `[x]` | `audio/playback.py`: `SoundDevicePlayer` streams decoded samples through PortAudio (`sounddevice`, optional `playback` extra), with `load`/`play`/`pause`/`stop`/`seek`/`close`. Verified on a real device on 2026-10-06; skipped honestly where no output device exists. |
| 6 | Lyrics engine (roadmap Phase E) | `[x]` | `ParakeetLyricsEngine` via `onnx-asr` (MIT runtime, CC-BY-4.0 weights), `songlab lyrics`, `run_analysis()` lyrics step. Chunked at 20 s; words carry `unknown` confidence. Verified on `samples/vocadito_6.wav` (real weights and real voice, offscreen) and structurally everywhere else. Model pulls (CC-BY-4.0) are fetched on first use and never committed. |
| 7 | Synchronized display (headless) | `[x]` | Phase C: `app/display.py` renders every `DisplayFrame` on a timer tick, terminal as the first front end. |
| 8 | Desktop window minimal slice | `[x]` | Phase D: `songlab gui`, `gui/` (`main_window.py`, `timeline.py`, `analysis_panel.py`, `__init__.py`), PyQt6 behind the `gui` extra, offscreen-verified; `app/timeline.py` + `app/summary.py` present all the data.
| 6 | Current playback timestamp | `[x]` | `position()` on the same player, backed by a pure `PlaybackTimeline` (injectable clock) and re-anchored to the frames PortAudio actually consumed. Deterministic unit tests plus a real-device test. |
| 7 | Synchronized chord display | `[x]` | `songlab play` draws the chord under the playhead from `SessionSnapshot` (`app/display.py`: `frame_from`, `render_frame`, `ConsoleDisplay`, `follow`; `cli/commands/play.py`), refreshing while the song plays and updating the frame as the chord changes. `--at SECONDS` prints one frame headlessly. Verified end to end on a real device on 2026-10-07 (the chord changed during real playback) and headlessly in CI. **Now with a window too:** since 2026-10-08 `songlab gui` renders the *same* frame, plus the waveform, the chord bands and the analysis panel (`gui/` + `app/timeline.py` + `app/summary.py`), so the display exists both as a terminal line and as a desktop window. |
| 9 | Chords above the lyrics | `[x]` | Phase F, 2026-10-21: `app/chord_lyrics.py` seats each chord above the timed word it starts on, with instrumental gap rows and flat-key spelling; `gui/lyrics_view.py` draws it in the same block the lyric edits address. 16 presenter tests, 17 offscreen widget tests and a window test (`TestChordsAboveTheLyrics`) were run. |

**Conclusion:** all seven links now exist, in **two** front ends, plus the chart
that seats the chords over the lyrics. Links 1–4 are verified on real audio, 5–6
are a tested player with a playhead, 7 is the display driven by the same
session, and 9 is the chord-over-lyrics chart driven by the effective chord and
lyric layers: the frame drawn at each refresh carries exactly the chord
`chord_at()` claims for that position, so neither the terminal line nor the
window can drift from the playhead, and a placed chord is anchored to the word
whose timestamps cover its onset. The **First Product Milestone (Phase C) is
therefore reached as a command-line product slice**, and **Phase D
(2026-10-08) adds the desktop window** around it: open a file, see the waveform
timeline with the detected chords, play, pause, seek, always see the chord for
the current position, and read the chords above the synchronized lyrics. What is
still missing from the *accuracy* of a Chordify/Chord AI-style application is a
learned chord model and a broader vocabulary; that is Phase I work, measured
against the same harness, not a missing foundation.

### What is genuinely implemented today

* `[x]` Canonical typed model: `models/` (AudioDocument, ChordEvent with
  start/end/label/confidence, KeyEstimate, TempoEstimate, LyricSegment/Word,
  AnalysisResult, Provenance, AnalysisRun).
* `[x]` Canonical JSON codec with `SCHEMA_VERSION = 1` (`schema/codec.py`).
* `[x]` Engine protocols + registry (`engines/base.py`, `engines/registry.py`).
  Registered engines: **chords** `chroma-baseline`, **lyrics** `parakeet-onnx`,
  **key** `krumhansl`, **tempo** `librosa-tempo` (verified through
  `create_default_registry()` on 2026-10-16). Kinds `BEATS`, `STEMS`, `NOTES`
  have **no** registered engine.
* `[x]` Chord engine: CQT chroma → 24 harmonic-weighted or binary triad
  templates → majority or Viterbi decoding (`engines/chroma_baseline.py`,
  `engines/decoding.py`), with a measured `sqrt` chroma compression, the
  change penalty 0.40, a 0.50 s minimum-duration merge, and every front-end /
  template option measurable separately (`docs/ENGINE_COMPARISON.md` §7, §8).
  Measured 2026-10-27: **CSR 0.6312 / triad 0.6384** on 180 GuitarSet comping
  takes (previous front end 0.6121 / 0.6183; the 0.30 s step measured 0.6283 /
  0.6356).
* `[x]` Application service `run_analysis()` (`analysis/service.py`): runs
  chords/key/tempo, skips unavailable engines honestly, assembles provenance
  (version, SHA-256, python, platform, engines, configuration).
* `[x]` CLI: `songlab info`, `doctor`, `chords`, `lyrics`, `analyze` (incl.
  `--json`), `export`, `play`, `gui`, `benchmark` (the command list of
  `songlab --help`, checked 2026-10-16).
* `[x]` Audio metadata probing, FFmpeg discovery with platform install hints,
  input validation (`audio/`).
* `[x]` Playback and the two displays: `audio/playback.py` (tested player with a
  playhead), `audio/peaks.py` (waveform peaks), `app/display.py` (terminal
  display), `app/timeline.py` + `app/summary.py` (timeline and panel presenters)
  and `gui/` (the PyQt6 window behind the optional `gui` extra). The window's
  lyrics view is a **chord chart**: `app/chord_lyrics.py` aligns chord onsets to
  timed words and `gui/lyrics_view.py` draws them, with instrumental gap rows
  and the active chord highlighted (2026-10-21).
* `[x]` Key-aware display spelling: `normalization/spelling.py` respells chord
  roots and slash basses for flat keys on the terminal, the chord strip, the big
  label and the chord chart, while the canonical document keeps its sharp
  spelling. An unknown key keeps the canonical spelling. Tests:
  `tests/unit/test_spelling.py`.
* `[x]` Metrics as library code: chord (CSR, boundary/change, timing), key,
  tempo (half/double kept), lyrics WER/CER (`metrics/`, `evaluation/`).
* `[x]` Benchmark infrastructure, kind-agnostic runner (`benchmark/`).
* `[x]` Tests: **1883 passed / 11 skipped** and **1891 passed / 3 skipped**
  (gate re-run dated 2026-10-16 above; the two local venvs differ by the eight
  tests that need an audio output device), fixtures with annotation-only
  GuitarSet oracles, CI workflow (the DSP job also runs the window offscreen).
  The chord-harness work on 2026-10-19 adds 27 tests; the gate then reported
  **1910 passed / 11 skipped** (same machine, `ruff` and `mypy` clean). The
  confidence work on 2026-10-20 adds 57 tests; the gate then reported **1967
  passed / 11 skipped** (`ruff` clean over 162 files, `ruff format --check` 162
  files, `mypy` 89 files). The chord-chart, spelling, chart-check and
  measured-front-end work through 2026-10-21..27 adds its own tests; the full
  `.venv-chords` suite reports **2136 passed / 2 skipped in 262 s**, `ruff`
  clean over 173 files and `mypy` 93 files clean.
* `[x]` Documentation of decisions: `docs/ARCHITECTURE.md`,
  `DEPENDENCY_MATRIX.md`, `LICENSE_AUDIT.md`, `DATASET.md`,
  `ENGINE_COMPARISON.md`, `BENCHMARK.md`, `TROUBLESHOOTING.md`.
* `[x]` Chord confidence: every `ChordEvent` carries a measured value. The
  current fit (2026-10-27, after the sqrt/harmonic front end and the 0.50 s
  minimum) is a logistic with slope 28.7942 / intercept -0.0738 on the event's
  mean score margin; the held-out 90 takes give Brier 0.1485 and ECE 0.0363,
  and accuracy is 0.809 on events scoring at least 0.60 (47.6 % of the held-out
  duration). The raw margin stays in `metadata["score_margin"]`. The earlier
  fits (slope 29.8735 / intercept -0.1484 for the 0.30 s step, and 23.4861 /
  0.1973 for the binary-template/tuning-zero front end) are kept in
  `docs/ENGINE_COMPARISON.md` as history.
* `[x]` Real-file E2E: `tests/integration/test_analysis_e2e.py` runs the real
  default registry (chroma-baseline + krumhansl + librosa-tempo) over a
  deterministic generated WAV and, with FFmpeg, over its MP3 transcode, and
  asserts timestamped chord events cover the file. It skips without the
  optional DSP stack.
* `[x]` Transposition: `transpose_chord_label()` /
  `transpose_note_name()` as tested library functions, plus the user-facing
  workflow since 2026-10-13 (Phase H): the window's "Transpose all chords..."
  dialog and `songlab export --transpose N`.
* `[x]` Playback foundation: `audio/playback.py` (`Player` protocol, timeline,
  `sounddevice` backend) and the shared decode service `audio/decode.py` it uses.
* `[x]` Synchronized chord display (terminal): `app/display.py` (pure
  `frame_from`/`render_frame`, `ConsoleDisplay`, `follow` with an injectable
  sleep) and `songlab play`, which draws the chord under the playhead and
  refreshes it while the song plays.
* `[x]` Minimal GUI window (Phase D): `gui/` + `songlab gui`, PyQt6 behind the
  optional `gui` extra, with the waveform timeline, the chord strip, the
  seekable playhead and the analysis panel.
* `[~]` GUI editing/undo-redo/exports/translations (`docs/GUI_REQUIREMENTS.md`
  `[F]` list: the lyrics view 2026-10-09, the editing/undo-redo/transpose/
  simplify/export-dialog work through 2026-10-13 and the confidence/engine
  panels 2026-10-14 are in; translations remain - the Language menu ships but
  no catalogue does), beats engine, stem separation, alignment, fusion,
  packaging.
* Empty package (placeholder only, `__init__.py`): `fusion/`. The packages that
  used to be placeholders hold real code now: `export/` (JSON / ChordPro /
  Markdown renderers), `alignment/` (`.lrc` and `.srt` parsing) and `i18n/`
  (catalogue discovery and the `QTranslator` wiring behind the window's
  Language menu).

### Known documentation drift (fix opportunistically, not a phase)

* Resolved on 2026-10-16: §1 claimed `export/`, `alignment/` and `i18n/` were
  empty packages (they have implementations), the link-2 row still said the DSP
  engines decode themselves, the registry bullet said `LYRICS` had no engine
  (`parakeet-onnx` is registered), the CLI bullet omitted `lyrics` and `export`,
  the transposition bullet still said there was no user-facing workflow, the
  same bullet still listed a lyrics engine as remaining work although Phases E
  and F are `[x]`, the test counts carried no date, and
  `docs/GUI_REQUIREMENTS.md` did not record
  the window's Language menu. The dated session handoff's "Partially implemented"
  entry for decoding said the same, and was corrected with it. The `AGENTS.md`
  line about the registered engines is now stale in the same way (it predates
  the lyrics engine) and was left alone as the instruction file.
* Resolved on 2026-10-08: the "no Qt code in `src/`" claims in `README.md`,
  `docs/GUI_REQUIREMENTS.md` and `docs/ARCHITECTURE.md`
  (the window exists now), the stale `README.md` test badge again, and the
  `docs/DEPENDENCY_MATRIX.md` §2.1/§8 rows that still spoke of PyQt6 and Qt
  Multimedia as future work.
* Resolved on 2026-10-06/07: the stale `README.md` test badge, the description
  of the old `[*]` marker convention in `README.md`/`AGENTS.md`, the "no
  analysis engine exists yet" wording, and the `last (phase 15)` GUI row, which
  referenced the pre-reset phase numbering. Counts are re-verified whenever the
  gate is re-run and are stated with their date, so they can never be read as
  live numbers.

---

## 2. Phase A — Audio Input and Playback Foundation **[P]**

**Objective:** load an audio file, decode it to samples, play it, and answer
"what is the current playback position?" — the substrate for everything after.

**Current status:** `[x]` — the two `[~]` tasks below (one decode owner) were
closed on 2026-10-16, which is what the acceptance criteria were waiting on.

### Tasks

- [x] Input validation and safe path handling (`audio/validation.py`)
- [x] Metadata probing: ffprobe + WAV fallback (`audio/probe.py`)
- [x] FFmpeg discovery, no-shell invocation, install hints (`audio/ffmpeg.py`)
- [x] Decoding to samples for **analysis** — every DSP engine decodes through
  the shared service below: `chroma_baseline.py`, `key_krumhansl.py` and
  `tempo_librosa.py` were switched over on 2026-10-16 (each keeps its own
  sample rate, mono downmix, offset/duration window and output; verified by
  comparing engine output before and after on real sample files)
- [x] Shared application-level decode service (path → mono/stereo samples +
  sample rate): `audio/decode.py` exposes `decode_audio()` with a librosa/soundfile
  backend and a dependency-free stdlib WAV backend, and returns one flat
  interleaved float buffer plus its sample rate. Tests: `tests/unit/test_decode.py`
  (WAV half runs in the core venv) and `tests/integration/test_decode_integration.py`
  (a real compressed transcode). It is the only decode path: the four engines,
  the player and the session's waveform fallback all call it, and each engine's
  unit suite pins the call it makes (`test_the_audio_comes_from_the_shared_decode_service`)
- [x] Playback abstraction: player interface with `load`, `play`, `pause`,
  `seek`, `position()`, `duration()`, `state` callbacks (no Qt types in it).
  `audio/playback.py`: a `Player` Protocol, a pure `PlaybackTimeline` (position
  state machine driven by an injectable clock) and `SoundDevicePlayer`
- [x] Playback backend decision: **`sounddevice`** chosen over Qt Multimedia.
  MIT, optional, behind the `playback` extra; licensed and justified in
  `docs/DEPENDENCY_MATRIX.md` §2.1. Confirmed in Phase D (2026-10-08): the window
  reuses `SoundDevicePlayer` through `SongSession` rather than adding a Qt
  Multimedia backend, so the CLI and the GUI share one tested audio path, and
  the `Player` Protocol still allows that backend later
- [x] Waveform peak data extraction for the timeline (downsampled min/max per pixel
  bucket): `audio/peaks.py` (`waveform_peaks()`, `peaks_of()`, `WaveformPeaks`),
  dependency-free (no numpy import) and frame-aligned, so the same reduction
  serves the stdlib WAV backend and the DSP one. Reached by the window through
  `SongSession.waveform_peaks(buckets)`, which reuses the samples the player
  already decoded and caches the result per resolution. Tests:
  `tests/unit/test_peaks.py`
- [x] Tests: unit tests with committed WAV fixtures, a fake-PortAudio stream test
  for the headless contract, and a real-device integration test that plays,
  pauses, resumes and seeks a short file (`tests/integration/test_playback_integration.py`,
  skipped when no output device exists). The decode half landed earlier
  (`tests/unit/test_decode.py`, `tests/integration/test_decode_integration.py`)
- [x] Works with a real MP3 file, not only WAV: `decode_audio()` reads a real
  compressed file through soundfile/librosa, and the E2E analysis test runs the
  whole pipeline on an MP3 transcode of its generated fixture

### Files / modules

`src/song_chord_lyrics_analyzer/audio/` (new `decode.py`, `playback.py`),
`models/audio.py`, `pyproject.toml` (optional extra), `tests/`.

### Acceptance criteria

The phase is complete only when: (1) a real MP3 is decoded through one shared
service; (2) a player can play, pause, seek and report its position in seconds;
(3) waveform peak data can be produced for a rendered timeline; (4) tests cover
the workflow and the gate stays green.

### Dependencies / blockers

Requires a playback library choice (small, license-audited). No other blocker.

### Must NOT be considered complete

Decoding that only works inside engines; a player that works only on the
developer's machine; position polling that is not tested.

---

## 3. Phase B — Functional Chord Analysis **[P]**

**Objective:** the existing baseline engine reliably turns real audio into
timestamped chord events exposed through the application service.

**Current status:** `[~]` — the engine and its output exist and were verified
on real audio during the audit; per-chord confidence landed on 2026-10-20, so
the remaining gap is the documented JSON serialization contract, not the
algorithm.

### Tasks

- [x] Existing `chroma-baseline` engine (templates, majority + Viterbi decoders)
- [x] Existing chord normalization (`normalization/chords.py`)
- [x] Existing temporal decoder with measured penalty (`engines/decoding.py`)
- [x] Timestamped `ChordEvent` output with `start`, `end`, `label`
- [x] Serialization through the canonical JSON codec (schema version 1)
- [x] Exposed via `run_analysis()` and `songlab analyze --json`
- [x] Verified manually on a real MP3 song (2026-10-06): 76 timestamped events, exit 0
- [x] Committed end-to-end integration test: real audio file → `run_analysis()`
  → assert timestamped chord events cover the duration (fixture audio committed
  or generated deterministically; must not depend on a private submodule).
  `tests/integration/test_analysis_e2e.py` writes a deterministic C–G–F–C WAV,
  runs the real default registry and, where FFmpeg exists, the same file as an
  MP3 transcode; skips honestly without the DSP stack.
- [x] Per-chord confidence from the baseline (score margin), so `confidence` is
  a measured number instead of always `unknown`. `segment_margins()` averages
  the emitted label's margin over the event's frames (negative where the
  decoder overrode a frame), `margin_confidence()` maps it with a logistic
  fitted on GuitarSet, and both are covered by `tests/unit/test_chroma_baseline.py`;
  the calibration, risk–coverage curve and refit (`--fit-confidence`) are in
  `docs/ENGINE_COMPARISON.md` §6
- [ ] Document the stable JSON serialization contract (fields of a chord event,
  units, edge cases: `N`, `?`, overlaps) in `docs/`

### Files / modules

`engines/chroma_baseline.py`, `analysis/service.py`, `models/music.py`,
`schema/codec.py`, `tests/integration/`, `docs/`.

### Acceptance criteria

The phase is complete only when: (1) a real MP3 loads; (2) the chord engine
analyzes it; (3) timestamped chord events are produced and cover the file
duration; (4) the result is exposed through `run_analysis()`/the CLI;
(5) an automated test verifies the workflow.

### Dependencies / blockers

None. Phase A's shared decode service is a nice-to-have here, not a blocker
(the engine decodes today).

### Must NOT be considered complete

The manual audit run alone (without a committed test); events without
timestamps; confidence claimed but unmeasured.

---

## 4. Phase C — First End-to-End Vertical Slice **[P] — FIRST PRODUCT MILESTONE**

**Objective:** the whole product path works on one real song, from file to a
chord that changes on screen as the song plays.

```text
REAL AUDIO → chord analysis → timestamped chord events → usable JSON/domain
representation → playback timeline → synchronized chord display
```

**Current status:** `[x]` — reached on 2026-10-07, as a **terminal display**: all
seven acceptance criteria work, verified on a real device and headless in CI.
The display is deliberately the smallest honest surface (one line of text over
`SessionSnapshot`); the desktop window that renders the same frame with widgets
is Phase D and is *not* part of this milestone.

This is the **first product milestone**. It is deliberately small: the first
version does not need perfect chord recognition — it needs to be real,
executable, testable, understandable, integrated, synchronized, and replaceable
by better engines later. Accuracy work happens in Phase I, **after** this works.

### Tasks

- [x] A single application session/service: open file → decode → analyze →
  player → `chord_at(position_seconds)` lookup (binary search over events).
  `app/session.py`: `SongSession` owns the player, keeps the chord events and
  answers `chord_at`/`current_chord`; no Qt, no ML imports
- [x] Playback timeline model: song duration, playhead position, current event
  — `SessionSnapshot` (frozen dataclass returned by `session.snapshot()`)
- [x] Deterministic test of the synchronization logic (fake clock: at t=0..n the
  right chord is returned; boundary and `N`/`?` handling defined). Half-open
  intervals `start <= t < end`; before the first event, inside a gap and at/past
  the last end return `None`; `N` is returned as a claim of silence, not skipped.
  `tests/unit/test_session.py` drives a fake clock; `tests/integration/test_session_integration.py`
  runs the real pipeline (and real playback where a device exists)
- [x] Minimal display surface showing the current chord, updating with
  playback: `app/display.py` (presenter + console renderer + refresh loop) and
  `songlab play`. Deliberately the first slice the Phase D window reuses: the Qt
  view renders the same `DisplayFrame`, which keeps the synchronization logic
  dependency-free and testable
- [x] One scripted demo path: real song file in → chord list + playback + live
  chord out, documented in the README with honest wording (the transcript is
  captured from a generated fixture and says so)

### Files / modules

`src/song_chord_lyrics_analyzer/app/` (`session.py`, `display.py` — session and
presenter layer, no Qt, no ML imports), `cli/commands/play.py`,
`audio/playback.py` (Phase A), `analysis/service.py`, tests.

### Acceptance criteria — **First Product Milestone**

A user can provide a real MP3/audio file and the application can:

1. load it,
2. analyze it,
3. produce timestamped chords,
4. play the audio,
5. determine the current playback timestamp,
6. display the corresponding chord,
7. update the displayed chord as playback advances.

**Until all seven work, the project must not be described as a functional
Chordify/Chord AI-style application.** It is an analysis laboratory.

**Status: all seven work (2026-10-07).** They were verified by running the code:
`songlab play` on a real device while the chord changed with the playhead, and a
headless integration test asserting that every rendered frame carries exactly
the chord the session claims for that position. The claim being made is
*synchronization*, not accuracy, and it is made about a **terminal** display —
the desktop application is Phase D.

### Dependencies / blockers

Depends on Phase A (playback) and Phase B (chord pipeline). No research task
may block this phase.

### Must NOT be considered complete

Analysis without playback; playback without synchronization; a demo that only
works on one hard-coded file; unverified claims in the README.

---

## 5. Phase D — Minimal PyQt6 GUI **[P]**

**Objective:** the smallest usable desktop application around the Phase C
vertical slice.

**Current status:** `[x]` — the minimal window landed **2026-10-08** as
`songlab gui`, verified by running it (offscreen, `QT_QPA_PLATFORM=offscreen`) on
a generated song: the waveform timeline, the chord strip and the playhead are
drawn, the transport plays/pauses/stops/seeks, and every refresh shows exactly
the chord `chord_at()` claims for that position - on a real device too
(`tests/integration/test_gui_integration.py`).

### Tasks

- [x] PyQt6 dependency (optional extra; core stays dependency-free) — license
  noted in `docs/LICENSE_AUDIT.md` (GPL compatible). `pyproject.toml` extra
  `gui`; `gui/` imports Qt lazily, so a Qt-free install still runs every other
  command and `songlab gui` reports a dependency error with the install hint
- [x] Main window consuming the **application session layer only**
  (hard rule: GUI never imports librosa, engines, numpy, or `analysis/` internals).
  `gui/main_window.py` imports `app/` (session, display frame, timeline, summary)
  and Qt, nothing else
- [x] Minimal Viable GUI, exactly:
  - [x] open an audio file (dialog + an optional file argument)
  - [x] play / pause
  - [x] seek (click/drag on timeline, plus back/forward actions and arrow keys)
  - [x] show current time (and track length)
  - [x] show detected chords (a big label for the playhead, a band per event in
    the timeline strip)
  - [x] synchronize chord display with playback (one `snapshot()` per timer tick,
    turned into the same `DisplayFrame` the terminal display renders)
- [x] Show key, tempo, engine name and provenance summary (cheap, already
  available): `app/summary.py` produces the rows, `gui/analysis_panel.py` shows
  them, skipped/failed engines included
- [x] Waveform/timeline rendering from Phase A peak data: `audio/peaks.py`
  (min/max per bucket, frame-aligned, no numpy import) reached through
  `SongSession.waveform_peaks(buckets)`, cached per resolution and redrawn on
  resize; the playhead and the bands are placed with the same presenter
  (`app/timeline.py`) the widget uses
- [x] Headless test strategy for GUI logic (logic in plain-Python presenters;
  Qt widgets thin and tested with `QT_QPA_PLATFORM=offscreen`):
  `tests/unit/test_gui_main_window.py` (fake player + fake clock),
  `tests/integration/test_gui_integration.py` (real engine, real file, real
  device where one exists) and `tests/unit/test_gui_command.py`. CI installs the
  `gui` extra in the DSP job and runs them offscreen; the core matrix stays
  Qt-free

- [x] Manual launch verified by the user on MX Linux 25 (2026-10-18): the
  window opened an MP3, drew the waveform, the lyrics panel, the analysis
  information and the changing chords during playback (user-reported; see §1).
  The launch commands and screenshot are in the README.

### Files / modules

New `src/song_chord_lyrics_analyzer/gui/` (`main_window.py`, `timeline.py`,
`analysis_panel.py`, `__init__.py`), new presenters `app/timeline.py` +
`app/summary.py`, new `audio/peaks.py`, `cli/commands/gui.py`, plus `app/` from
Phase C. Two modules the plan (`docs/GUI_REQUIREMENTS.md`) listed were folded in
rather than split: there is no `gui/player.py` because the window drives the
session's existing `SoundDevicePlayer` instead of adding a Qt Multimedia
backend, and no `gui/waveform.py` because the waveform, the chord strip and the
playhead share one widget (`gui/timeline.py`) and one `x_at` mapping.

### Acceptance criteria

A user can launch the app, open a song, see its waveform timeline, play it,
seek, and always see the chord for the current position. **Met on 2026-10-08**
(`songlab gui`; verified offscreen, on a generated song the real engine
analyses, and on a real output device).

### Dependencies / blockers

Phases A + C. Nothing else.

### Must NOT be considered complete

A window that only loads files; widgets importing engines directly; the full
feature list below — that is `[F]` work, added after the minimal GUI works.

### Later GUI features (progressive, `[F]`)

Delivered from this list, in order: the lyrics view (2026-10-09, `app/`
lyrics-view presenter + `gui/lyrics_view.py`, active segment and active word on
the same snapshot the chord label reads; see `docs/GUI_REQUIREMENTS.md` §5.1);
chord/lyric editing with undo/redo (2026-10-10..12); transpose and chord
simplification (2026-10-13); the Export document... save dialog over the
Phase H exporters (2026-10-13); and the **chord-over-lyrics chart** (2026-10-21,
`app/chord_lyrics.py` + the rewritten `gui/lyrics_view.py`: each chord above the
timed word it changes on, instrumental gap rows, active chord highlighted). Still
open: translations. The window's layout is already prepared for them (`app/`
produces the data, the widgets only render).

---

## 7. Phase E — Lyrics Integration adopted **[P]**

**Objective:** the recorded lyrics research became a real, registered
`ParakeetLyricsEngine` through `onnx-asr`: timestamped words from real audio,
chunked at 20 s, `unknown` confidence, model provenance recorded.

**Current status:** `[x]` — adopted on 2026-10-08; all six tasks above are
`[x]` and the engine flows through `run_analysis()`, `songlab lyrics` and both
front ends. The investigation is preserved in `docs/ENGINE_COMPARISON.md` (the
English result: WER 0.3722 vs 0.3799; RTF 0.20 vs 0.95) and the phase-4
open-questions are listed there.

### Tasks — all `x`

- [x] Lyrics engine adapter implementing `LyricsEngine` (`engines/lyrics_parakeet.py`),
  injected transcriber so the pipeline is testable without a model
- [x] Chunked transcription pipeline (`engines/lyrics_chunking.py`): windowing,
  timestamp reassembly, overlap handled by the documented "earlier window wins"
  rule
- [x] Register the engine; `songlab lyrics` command; `run_analysis()` gains a
  lyrics step with the same honest skipped/failed status handling
- [x] Integration test on committed fixture audio (`samples/vocadito_6.wav`,
  CC-BY-4.0): real weights and real voice on the committed sample, structural
  honesty only (no new WER claim)
- [x] Honour the contract: `README.md` and `docs/GUI_REQUIREMENTS.md` updated;
  `utils/text.py` holds the shared English agreement helper
- [x] Remaining phase-4 questions: overlap semantics, second candidate, language
  tag

### Files / modules

`engines/lyrics_chunking.py`, `engines/lyrics_parakeet.py`,
`cli/commands/lyrics.py`, `utils/text.py`, `analysis/service.py`,
`pyproject.toml` (optional `lyrics` extra), `tests/`; docs `ENGINE_COMPARISON.md`,
`README.md`, `CHANGELOG.md`, `DEPENDENCY_MATRIX.md`, `LICENSE_AUDIT.md`.

### Acceptance criteria

A real audio file produces timestamped lyric words through the same application
service and CLI pattern as chords, with model provenance (name, license,
version) recorded in the document.

### Dependencies / blockers

Optional DSP extra (onnx-asr, onnxruntime, huggingface-hub, numpy, librosa,
soundfile) — must stay optional; core and its tests never require it. Download
of the model happens once, on first use, into the Hugging Face cache, and
`test_lyrics_integration.py` never triggers it.

### Must NOT be considered complete

WER numbers from the old harness; an adapter that only runs on one machine;
un-timestamped transcripts; a `lyrics` extra that can be installed without
decoding (numpy/librosa), which the decoder and the engine both need.

**Pre-adoption status (history):** research measured, models/libraries known,
`engines/lyrics_chunking.py` (windowing, reassembly) and `metrics/lyrics.py`
existed; `LYRICS -> []` until **2026-10-08**, when `ParakeetLyricsEngine` was
registered through `onnx-asr` (MIT runtime, CC-BY-4.0 weights), chunked at 20 s,
behind the `lyrics` extra.

### Tasks

- [x] Lyrics models (`models/lyrics.py`) and WER/CER + word-timestamp metrics (`metrics/lyrics.py`)
- [x] Research already done (see §13 — do not repeat): Parakeet-1B-v3 via
  `onnx-asr` beats faster-whisper small on English (WER 0.3722 vs 0.3799);
  both are MIT; **long-audio chunking (~20 s windows) is mandatory**;
  stems do **not** improve transcription by default
- [x] Lyrics engine adapter implementing `LyricsEngine` (`engines/lyrics_parakeet.py`),
  injected transcriber so the pipeline is testable without a model
- [x] Chunked transcription pipeline (`engines/lyrics_chunking.py`: windowing,
  timestamp reassembly, overlap handled by the documented "earlier window
  wins" rule)
- [x] Register the engine; `songlab lyrics` command; `run_analysis()` gains a
  lyrics step with the same honest skipped/failed status handling
- [x] Integration test on committed fixture audio (`samples/vocadito_6.wav`,
  CC-BY-4.0) with the real weights when the local cache holds them; structural
  honesty only (no new WER claim)
- [x] Honest output: word timestamps carry `unknown` confidence unless measured;
  `lyrics_label()` keeps the two front ends in agreement

### Files / modules

New `engines/lyrics_chunking.py`, `engines/lyrics_parakeet.py`,
`cli/commands/lyrics.py`, change in `analysis/service.py`, new
`utils/text.py` (the English agreement helper), `pyproject.toml` (optional
`lyrics` extra), `tests/`.

### Acceptance criteria

A real audio file produces timestamped lyric words through the same application
service and CLI pattern as chords, with model provenance (name, license,
version) recorded in the document.

### Dependencies / blockers

Optional DSP extra (onnx-asr, onnxruntime, huggingface-hub, numpy, librosa,
soundfile) — must stay optional; core and its tests never require it. No
dataset research required. The heavy model downloads on first use; tests never
trigger it.

### Must NOT be considered complete

WER numbers from the old harness; an adapter that only runs on one machine;
un-timestamped transcripts; a `lyrics` extra that can be installed without its
decoding stack.

---

## 7. Phase F — Synchronized Lyrics + Chords **[P]**

**Objective:** show lyrics and chords together on the same playback clock.

**Current status:** `[x]` — the clock-sharing work landed and was tested
(2026-10-10, on top of the 2026-10-09 lyrics view): `SongSession.lyric_at()` /
`word_at()` answer the lyrics layer exactly the way `chord_at()` answers the
chords layer, and the window's refresh feeds both widgets from one snapshot.
The external timed-text alignment landed 2026-10-14: `alignment/lrc.py` and
`alignment/srt.py` parse a `.lrc`/`.srt` file into the same canonical
`LyricSegment` rows the lyrics engine produces, `songlab analyze --lyrics-from
FILE` takes the layer from a file instead of the engine, and the window loads
one with Ctrl+L (`with_lyric_base` swaps the tape's lyric base, keeping the
chord work and persisting the new base to the Phase G sidecar). The
**chord-over-lyrics chart** landed 2026-10-21: every chord is seated above the
timed word it starts on, instrumental gaps get chord-only rows, the active
chord is highlighted, and flat keys are respelled for display. The **plain-text
chart import** landed 2026-10-27: Edit → Load chord chart... uses the chart's
chords and lyrics while taking their times from the detected chord sequence and
the transcript's timed words.

### Tasks

- [x] Lyric timeline model aligned to the same position clock as chords
  (`app/lyrics_view.py` presenters, 2026-10-09)
- [x] `lyric_at(position)` + `word_at(position)` alongside `chord_at(position)`
  in the session layer (`app/session.py`, 2026-10-10); the same half-open
  `start <= position < end` coverage, the same `None` = "no claim"
- [x] GUI: lyric line display synchronized with playback (active word
  highlighted when word timestamps exist). The widget takes the session's
  answers (`set_active(segment, word)`) and decides nothing about the clock
- [x] Alignment rules when lyrics come from an external timed-text file
  (`.lrc`/`.srt`) — `alignment/lrc.py` + `alignment/srt.py` in the shared
  `alignment/` package (2026-10-14), one entry point (`parse_timed_text`)
  for both front ends:
  * LRC: `[mm:ss.xx]` with the fraction padded **on the right** to ms,
    repeated stamps repeating the text, `[offset:±ms]`, metadata tags
    consumed as annotations, enhanced A2 word stamps, a line's `end` = the
    next line's `start`, the last line open-ended, untimed lines kept but
    never active
  * SRT: `HH:MM:SS,mmm --> HH:MM:SS,mmm` (dot also accepted) with trailing
    position markers ignored, internal line breaks joined into one display
    line, empty blocks skipped as silence markers, inverted timings reported
  * CLI: `songlab analyze --lyrics-from FILE` replaces the lyrics layer
    (the file wins) and records it in the step summary + provenance
  * GUI: the Edit menu's "Load lyrics from file..." (Ctrl+L) swaps the
    lyric base; the file's lines are saved by Ctrl+S like any other edit
- [x] Tests: fake-clock synchronization for both streams; boundary cases
  (`TestLyricLookup` in `tests/unit/test_session.py` pins the same edges as
  `chord_at`; `TestTheLyricsViewFollowsTheSameClock` asserts both front-end
  views read one snapshot)
- [x] **Chord chart over the lyrics** (2026-10-21): `app/chord_lyrics.py` is the
  pure presenter (`chord_lyric_lines`, `ChordLyricLine`, `PlacedChord`). A chord
  is seated above the timed word whose `start <= chord.start < end`; without
  word timestamps the line falls back to a proportional column; a chord that
  starts in an instrumental gap gets its own chord-only row, grouped by the
  lyric line it precedes; a chord merely spanning into a line is not repeated;
  two chords on one word are nudged apart rather than overwritten; canonical
  labels are respelled for a flat key through `normalization/spelling.py`.
  `gui/lyrics_view.py` draws each row as one monospace chord line plus one lyric
  line in the same `QTextBlock`, so the right-click-to-display-index mapping the
  lyric commands rely on stays exact. Tests: 16 presenter tests
  (`tests/unit/test_chord_lyrics.py`), 17 offscreen widget tests
  (`tests/unit/test_gui_lyrics_view.py`) and a window test that the chart is
  built from the effective layers (`TestChordsAboveTheLyrics`)
- [x] **Plain-text chart import** (2026-10-27): `app/chart_import.py` parses the
  chart's chord sequence, chord columns and sung lines. A chord written above a
  lyric word takes that word's start; instrumental runs are distributed between
  the surrounding anchors, and every chart chord gets a positive slot. Chart
  words are aligned to the transcript's timed words, keeping the chart text and
  interpolating unmatched words; the detected sequence is the fallback when the
  chart has no word anchors. Title/artist lines before the first section/chord
  line are excluded. The window's
  **Edit → Load chord chart...** (`Ctrl+Shift+L`) replaces both bases through
  `with_chart_bases` (old commands dropped), reports unmatched layers in the
  status bar, and saves the chart base to the sidecar. Tests: 14 importer
  tests (`tests/unit/test_chart_import.py`) and 6 window tests
  (`TestImportingAChordChart`). Verified on the private 5:27 song: 86 timed
  chart chords, 36 correct lyric lines, 83/182 chart words anchored to the
  transcript (2026-10-27). Limitation: the timing is column/word-based, not
  beat-level; chart sections are not used for timing, and the chart file path is
  not yet recorded in provenance.

### Acceptance criteria

While a song plays, both the current chord and the current lyric line update in
sync, from one timestamped source of truth. **Met for the engine-transcribed
lyrics on 2026-10-10, for an external `.lrc`/`.srt` lyric base on 2026-10-14,
for the chord-over-lyrics chart on 2026-10-21, and for the plain-text chart
import on 2026-10-27** (the parsed rows carry
`start`/`end` in the same clock the chord layer uses, the session's `lyric_at`
does not care where they came from, and the chart's placed chords read the same
effective layers the playback clock does). The chart positions chords at the
word whose onset the chord changes on; a chord change inside a long held word
therefore lands on that word, which is the resolution the word timestamps
support. It is **not** a claim of sub-word or beat-level alignment.

### Dependencies / blockers

Phases C + D + E.

### Must NOT be considered complete

Lyrics shown without timestamps; two unsynchronized position clocks.

---

## 8. Phase G — Editing and User Corrections **[P]**

**Objective:** the user can fix what the engines got wrong, without losing the
original analysis.

**Current status:** `[x]` — the chord-editing core landed 2026-10-10
(`app/editing.py`: command-pattern edits over an immutable engine base,
`SetChordLabel`/`SplitChord`/`MergeChords`/`TrimChord`/`DeleteChord`/
`InsertChord` + a `CommandStack` undo/redo tape; the window edits the chord
under the clicked position and undoes/redoes with the standard shortcuts)
and the edited layer persists 2026-10-11 (`app/persistence.py`: a sidecar
`song.songlab.json` storing the engine base + the ordered commands, replayed
through `rebuild_stack()` on load with the same validation as a live push;
wired to the window as `Ctrl+S` + an auto-replay on `open_file`; a corrupt or
stale sidecar is reported and the engine layer kept). Lyric editing landed
2026-10-12 and closes the phase: four commands (`SetLyricText` /
`SetLyricTiming` / `DeleteLyric` / `InsertLyric`) over an immutable lyric
base, riding the **same** undo tape as the chords, so one `Ctrl+Z` walks back
through both layers in the order they were made. Lines are addressed by
their *display index* - a line may carry no timestamp at all - and
`effective_lyrics()` re-establishes display order after every command, so an
index always resolves against exactly the list it was validated against,
live and when a saved tape replays. The sidecar stores the engine lyric base
beside the chords (`edits_version` stays `"1"`: a pre-lyric sidecar loads
with an empty lyric layer, and a build that predates the commands rejects a
sidecar containing one loudly instead of dropping it). The timeline context
menu now offers all six chord commands (edit/split/trim-start/trim-end/
merge/delete/insert, each addressing the chord under the click) and the
lyrics view's context menu the five lyric ones (edit text/set start/set
end/insert line/delete line, addressed by the line under the click, with
enable states from the effective layer - "set end" waits for a start);
closing with unsaved edits offers Save/Cancel/Discard - the answer is exact,
since the tape is compared with the last save, so undoing back to the saved
state closes silently, and a lyric edit counts as unsaved like any chord
edit.

### Tasks

- [x] Editable document layer: user edits are a separate overlay over the
  engine output (raw engine results are never overwritten — provenance stays).
  `CommandStack.base` returns the engine layer untouched after any edit;
  user-produced events carry `source="user"`/`"user-merge"`
- [x] Chord editing: change label, split/merge/trim/delete/insert — six
  commands exist and are tested (vocabulary frozen 2026-10-11); all six are
  in the timeline context menu (2026-10-11), each addressed by the chord
  under the click, with enable states computed from the effective layer
- [x] Lyric editing: correct words and timings (`SetLyricText` replaces a
  line's words, `SetLyricTiming` moves a boundary or gives an untimed line a
  start, `DeleteLyric`/`InsertLyric` cover the structural fixes; the engine's
  word timestamps ride along as evidence and the engine layer itself is never
  touched. Lines are addressed by display index; the view's context menu
  offers every command. Per-word (re)editing is deliberately *not* in this
  vocabulary - it needs word addressing and would extend the schema, so it is
  a later, separate decision)
- [x] Undo/redo command stack (`CommandStack`: push/undo/redo, redo tape
  discarded on a new push, a failed push leaves the tape as it was)
- [x] Persistence of the edited document (`app/persistence.py`, 2026-10-11:
  `save_edits()`/`load_edits()`/`rebuild_stack()` over a sibling
  `song.songlab.json` that stores the engine chords + the ordered commands in
  canonical JSON; the engine layer is recoverable from the file untouched, a
  stale command fails loudly on replay, the edits format has its own
  `edits_version: "1"`. Wired into the window the same day: `Ctrl+S` /
  "Save Edits" writes the sidecar, `open_file` replays it automatically, and
  a corrupt or stale sidecar is reported with the engine layer kept)
- [x] GUI integration (edit from the timeline): the timeline's context menu
  offers "Edit chord here..."; Undo/Redo on `Ctrl+Z`/`Ctrl+Shift+Z`; the chord
  label and the strip redraw from the effective layer
- [x] Tests: command-level undo/redo, overlay round-trip, persistence —
  `tests/unit/test_editing.py` (82 tests, Qt-free: the chord vocabulary, the
  lyric vocabulary, the fold and the one-tape-both-layers behaviour),
  `tests/unit/test_persistence.py` (25 tests: round-trip of both layers,
  engine-layer recoverability, provenance, loud stale/corrupt rejection,
  pre-lyric sidecar compatibility), and the GUI flow in
  `tests/unit/test_gui_main_window.py::TestEditingTheChordLayer`,
  `TestPersistingTheEdits` and `TestEditingTheLyricsLayer` (14 tests: menu
  enable states, every lyric command, the mixed-layer undo order, the
  delete-refill gap flow, save/reopen of lyric edits, the widget-to-menu
  chain; offscreen, dialogs mocked) plus `tests/unit/test_gui_lyrics_view.py::TestTheRightClickNamesTheLine`
  (3 tests: the right-click to display-index mapping)

### Acceptance criteria

A user can correct a chord and a lyric line, undo and redo those edits, save,
reload, and the engine's original output is still recoverable.

### Dependencies / blockers

Phase C (document + session layer); GUI parts need Phase D.

### Must NOT be considered complete

In-place mutation of engine output; edits lost on reload; no undo.

---

## 9. Phase H — Transpose, Simplification and Export **[P]**

**Objective:** musically useful transformations and export of the analysis.

**Current status:** `[x]` — **Delivered 2026-10-13.** Library transposition plus
the whole-document `TransposeDocument` / `SimplifyDocument` commands in
`app/editing.py` (GUI "Transpose all chords..." / "Simplify all chords" and the
CLI's flag-first `songlab export --transpose/--simplify`, both riding the edit
tape), and the `export/` package with `songlab export` (JSON / ChordPro /
Markdown) that honours the saved sidecar so what is exported is what was
edited.

### Tasks

- [x] Library-level transposition (`normalization/chords.py`)
- [x] Transpose workflow: apply semitone offset to the whole document (CLI flag
  first, GUI control after); chords displayed/transposed, originals preserved
- [x] Chord simplification: reduce extensions/alterations to simpler voicings
  (define the reduction table, test it, expose as a workflow) — reduced on top
  of the documented `contract_chord_label()` table in `normalization/chords.py`
- [x] `songlab export` command with formats: canonical JSON (exists), ChordPro,
  simple Markdown/tabular; exporters live in `export/`, never in the model
- [x] Round-trip tests: export → parse → same data

### Acceptance criteria

From one analyzed song the user can transpose it, simplify its chords, and
export the result to at least JSON + ChordPro, with tests.

### Dependencies / blockers

Phase C for the document workflow; nothing else.

### Must NOT be considered complete

Exporters that write fields the model does not have; simplification without a
documented, tested rule table.

---

## 10. Phase I — Accuracy Improvements and Additional Engines **[P]→[R]**

**Objective:** improve chord recognition **after** the vertical slice works,
and only where measurement justifies it.

**Current status:** `[~]` — measured with the committed harness: **CSR 0.6312**
(raw) / **0.6384** (triad-reduced), segment overlap 0.8454, change-F1 0.8553 on
180 GuitarSet comping takes (2026-10-27, `docs/ENGINE_COMPARISON.md` §8). The
previous front end measured 0.6121 / 0.6183 (2026-10-20, §7), the first scoring
step measured 0.6283 / 0.6356 (2026-10-21), 0.6029 with the front-end default
before that (2026-10-19, §2), and the previously cited 0.4260 did not reproduce
and is retired. No second chord engine is registered. A
read-only audit of the implementation was completed on **2026-10-18** and its
prioritized plan is [`docs/CHORD_DETECTION_AUDIT.md`](docs/CHORD_DETECTION_AUDIT.md);
P1 (the measurement harness), P2 (per-chord confidence) and P3 (the front-end
sweep) are implemented, and the 2026-10-21 template/compression pass is the
measured continuation of P3. P4–P8 are not. The ceiling of this template
pipeline has been probed: a 109-class CRNN reference available only as
`external/` weights scored **0.2555 triad CSR** raw on 30 takes and was
rejected, a held-out MLP on chroma context added only ~0.03, and the open
pretrained chord models that do score well are non-commercial (BTC /
Isophonics-derived weights are CC-BY-NC-SA), so the next real step is a
licence-clean learned engine with its own held-out measurement, not another
template tweak.

### Tasks

- [x] Read-only chord-detection audit (2026-10-18): traced the real path from
  decode → CQT chroma → 24 triad templates → Viterbi → segments → GUI, mapped
  the tests, and recorded evidence-based proposals without changing code
  (`docs/CHORD_DETECTION_AUDIT.md`)
- [x] P1 — reproducible comparison harness and fixed reference set, so every
  later chord change reports before/after on the same audio (audit §10 P1):
  `scripts/chord_benchmark.py` + the SHA-256-pinned
  `tests/fixtures/guitarset_comp_manifest.json` (180 comp takes) + the scoring
  and corpus modules `evaluation/guitarset.py`, with the full audit §11 vector
  written to `per_take.jsonl` / `aggregate.json` / `aggregate.md`; the
  generated-fixture and synthetic-corpus paths are tested offline in
  `tests/unit/test_chord_benchmark_harness.py`
- [x] P2 — per-chord confidence from the score margin (the Phase B task),
  exposed in the existing panel/tooltip without inventing a probability
  (audit §10 P2). Implemented 2026-10-20: `segment_margins()` +
  `margin_confidence()` in the engine, the logistic fitted on 90 GuitarSet takes
  and measured on the other 90 (Brier 0.1436, ECE 0.0206), the full calibration
  and risk–coverage tables in `docs/ENGINE_COMPARISON.md` §6, the refit command
  `scripts/chord_benchmark.py --fit-confidence`, and the Viterbi run now records
  `match_threshold_used`/`smoothing_window_used` instead of implying either
  shaped the labels. The 180-take per-take vector is bit-for-bit unchanged
- [x] P3 — front-end robustness measured one variable at a time (tuning, HPSS,
  energy gate, CENS); no change is adopted without the P1 numbers
  (audit §10 P3). Implemented 2026-10-20: `front_end_settings()` /
  `compute_chroma()` expose four independent options, the harness gained
  `--option KEY=VALUE` and records what ran, and the full sweep is measured on
  the same 180 takes (`docs/ENGINE_COMPARISON.md` §7). `tuning=zero` gained
  +0.0092 CSR (paired, ±0.0033) against the old default and **was adopted**;
  HPSS (−0.0139, 6.7× the CPU) and CENS (−0.0554) were measured and rejected;
  the −40 dB energy gate is within noise and stays an option.
- [x] P3 continuation — **harmonic templates, sqrt chroma compression and a
  0.50 s minimum-duration merge**, measured 2026-10-21..27 on the same 180 takes
  (audit §10 P3/P6 groundwork). `frame_scores`/`decode_labels` gained
  `weighting`, `apply_feature_transform()` gained `sqrt`/`log`, and the
  engine gained `min_segment_seconds`. The adopted defaults are
  `weighting="harmonic"` (root/third/fifth 1.00/0.95/0.85, opposite third
  −0.35), `feature_transform="sqrt"`, `change_penalty=0.40` and
  `min_segment_seconds=0.5`: **CSR 0.6121 → 0.6312**, triad 0.6183 → 0.6384,
  overlap 0.8343 → 0.8454, change F1 0.8296 → 0.8553, median boundary error
  0.168 → 0.158 s. The paired CSR gain against the previous defaults is +0.0191
  (95 % CI +0.0052..+0.0329). The first scoring step used 0.30 s and measured
  0.6283 / 0.6356; moving to 0.50 s after the real-song chart check gained a
  further +0.0028 ± 0.0007 CSR and +0.0206 change F1 without losing a chart
  chord. The binary templates and raw chroma remain selectable, and the
  confidence logistic was refitted on the new margin scale (Brier 0.1485, ECE
  0.0363). The change penalty was re-swept, closing the 2026-10-20 open item.
- [ ] P4 — bass-aware feature and slash-chord output, reported separately from
  the triad label (audit §10 P4)
- [ ] P5 — duration-aware transition model (and metrical alignment once a beat
  engine exists), scored on boundary error and change F1 as well as CSR
  (audit §10 P5)
- [ ] P6 — vocabulary phase 2 (sevenths, suspensions, diminished/augmented)
  only after the triad baseline is measured; accept only if the triad-reduced
  view does not regress (audit §10 P6)
- [ ] P7 — share decode/chroma work between the chord and key engines; output
  equality first, latency/memory second (audit §10 P7)
- [ ] P8 — evaluate an alternative engine behind `ChordEngine` only after
  P1–P3 and a licence audit (audit §10 P8)

- [x] Keep `docs/ENGINE_COMPARISON.md` as the measurement record; every
  accuracy claim states environment + date. **Traceability gap found by the
  2026-10-18 audit** (the file began at section 4, so the chord measurement's
  method table was missing): sections 1–3 were restored on 2026-10-19 together
  with the method table, the three measured runs and the note that retired the
  0.4260
- [~] Baseline improvements with measured deltas — **partly delivered**
  2026-10-21 (harmonic templates, sqrt chroma, minimum-duration merge; above).
  Not delivered: bass templates/slash output (P4), duration-aware transitions
  (P5) and the phase-2 vocabulary (P6). The conservative seventh pass that was
  measured emitted sevenths on 21–53 % of the duration against a 13.4 %
  reference, so it was not adopted; a hierarchical decision needs the bass
  evidence first.
- [ ] Candidate engines (Chordino via Sonic Annotator, madmom, Guitariz-style
  ensembles, `external/` references) evaluated only with a **product reason**:
  "users need X and the baseline fails X". A first probe on 2026-10-21
  measured the 109-class ONNX reference under `external/Guitariz` at 0.2555
  triad CSR on 30 takes (raw argmax, no smoothing), which is far below the
  registered engine; it is **not** adopted and no `external/` code or weights
  are used by the package. The strong public BTC checkpoints are
  CC-BY-NC-SA and conflict with this project's licence, so they are out.
- [ ] **Learned chord engine, licence-clean and measured held out** — the
  measured next step for accuracy. Requirements: a dataset whose audio and
  annotations permit redistribution or local use, a training script that lives
  in `scripts/` (not the wheel), a compact inference path behind
  `ChordEngine` with an optional extra, the same 180-take (or better,
  multi-corpus) before/after vector, and a documented train/held-out split.
  Do not ship weights of unknown provenance and do not train and test on the
  same takes. GuitarSet (CC BY 4.0) is a legitimate start for the solo-guitar
  case; full-mix generalisation needs a second, licence-audited corpus.
- [ ] Fusion only if single-engine accuracy plateaus (`fusion/` is reserved)

### Acceptance criteria

Any accuracy change ships with before/after numbers on the same evaluation set;
engines ship behind `ChordEngine`, registered and selectable via `--engine`.

### Must NOT be considered complete

Unmeasured "improvements"; new engines that are not registered/tested;
benchmark growth that does not serve the product.

---

## 11. Phase J — Benchmarking and Validation **[S]**

**Objective:** keep validation as a **supporting** service for Phases B and I —
never as the main development path.

**Current status:** `[x]` (infrastructure) / `[~]` (coverage of the product path)

### Tasks

- [x] Metric suite (`metrics/`, `evaluation/`) with pinned oracles
- [x] `songlab benchmark` with kind-agnostic runner and `--engine`
- [x] Dataset policy + GuitarSet adoption (`docs/DATASET.md`)
- [ ] Benchmark case for the real-file product workflow (feeds Phase B/C tests)
- [x] Local hand-chart agreement check (2026-10-27): `evaluation/chart.py`
  parses the plain-text chart format and aligns chart chords to detected chords
  with Needleman–Wunsch on triads; `scripts/chord_chart_check.py` reports
  matches, substitutions, missing and extra chords (human and `--json`).
  Tests: `tests/unit/test_chart_agreement.py` (parser/alignment) and
  `tests/unit/test_chart_check_command.py` (command wiring). A private 5:27
  recording against an 86-chord hand chart matched 84 chart chords in order
  (97.7%), 2 substitutions, 15 extra detections, 2026-10-27; that is a local
  sequence check, not a timed benchmark, and the song/chart are not committed.
- [ ] Track accuracy on the same fixed evaluation set when engines change (Phase I)

### Must NOT be considered complete

New datasets/benchmarks added without a product-driven question.

---

## 12. Phase K — Performance and Cross-Platform Packaging **[P]**

**Objective:** the application runs on Linux, Windows and macOS and ships to
users.

**Current status:** `[~]` — portable code + platform-aware discovery exist and
CI runs on the gate; the long-song strategy landed 2026-10-14 (windowed chord
analysis + progress reporting); no packaging yet, and no Windows/macOS runtime
verification.

### Tasks

- [x] `pathlib`, platform-aware executable discovery, no hard-coded paths
- [x] Cross-platform CI for lint/type/tests
- [ ] Measure and record real-time factor for the full product path on a
  reference machine (§45 harness already exists)
- [x] Long-song strategy (chunked analysis, progress reporting) — landed
  2026-10-14, **opt-in and honest about its scope**:
  * `analysis/chunking.py` analyses the chord layer in windows
    (`--chord-chunk-seconds`, default off, `plan_chunks` reused from the
    lyrics windowing). The seam rules are the deliverable: an earlier window
    wins, coverage is never lost (a straddling chord keeps its part after the
    previous coverage, so no boundary is invented), a chord split by a seam is
    joined within one frame, and an engine that ignores the time range is
    reported instead of producing a duplicated timeline
  * only chords are windowed: key and tempo need the whole song, and the
    lyrics engine already chunks internally at 20 s
  * `analysis/progress.py`: `run_analysis(..., on_progress=...)` reports each
    step and each window, printed to *stderr* by `songlab analyze --progress`
    and `songlab play --progress`, so `--json` on stdout stays clean
  * the windowing is recorded in provenance (`chords_chunk_seconds`) and the
    run cost is the sum of the windows, never a partial sum
  * measured and recorded in `docs/ENGINE_COMPARISON.md` section 5
    (2026-10-14, environment + date stated): same chord labels and order as the
    whole-file pass on a 480 s fixture with one seam boundary moved by 94 ms;
    peak RSS 996 MB -> 309 MB on a 600 s file, runtime unchanged within noise
  * the GUI half landed 2026-10-14: `gui/analysis_worker.py` runs the
    session's own `open()` on a `QThread` (`ThreadedAnalysis`, the window's
    default runner; `ImmediateAnalysis` keeps the synchronous seam for tests
    and embedders). The window shows the service's `on_progress` events on a
    progress bar and the status line (a fraction only when a step reports
    one), disables every action while the worker owns the session, refuses a
    second song until it ends, and honours a close asked for mid-analysis
    when the analysis ends - the worker thread is joined in the slot that
    reports the outcome, so a window never dies with a running thread.
    Verified offscreen (`TestTheAnalysisRunsOffTheUiThread`) and against the
    real engine (`tests/integration/test_gui_integration.py`)
- [ ] Packaging: PyInstaller or briefcase builds per platform; optional extras
  (DSP, GUI) bundled or clearly reported by `songlab doctor`
- [ ] Smoke test of the packaged app on each target OS (honest matrix in README)

### Must NOT be considered complete

"Works on my machine"; unverified platform badges.

---

## 13. Research Backlog **[R]**

Subordinate to the product. Nothing here blocks Phases A–H. Each item needs a
**product reason** to be picked up. Valuable existing research (do not repeat):

* **Datasets** — search completed; GuitarSet (CC BY 4.0) adopted with
  annotation-only fixtures; IDMT/CASD blocked by NC/ND/SA; details in
  `docs/DATASET.md` and `docs/LICENSE_AUDIT.md`.
* **Licensing** — code/model/dataset audit done (`docs/LICENSE_AUDIT.md`,
  `docs/DEPENDENCY_MATRIX.md`); re-open only when a concrete new dependency
  requires it.
* **Lyrics ASR** — Parakeet vs faster-whisper measured (WER/CER/RTF, English vs
  Tagalog/Spanish, both MIT, chunking mandatory, stems not default); corpus
  cached in `.cache/` (gitignored); recorded in `docs/ENGINE_COMPARISON.md`.
* **Stem separation** — Demucs measured: hurts faster-whisper, marginal for
  Parakeet; not default. Revisit only for a user-facing stem feature.
* **Viterbi/chord decoding** — measured, shipped in the baseline engine.
* **Key/tempo** — Krumhansl (0.4278 exact / 0.1333 relative, 360 takes) and
  librosa tempo (22.63 BPM mean error, octave cases kept) measured and shipped.
* Candidate engines and tools investigated: Chordino/Sonic Annotator, madmom,
  beat_this, basic-pitch, Guitariz, musicpractice — all `external/`
  reference-only, never dependencies.
* Open questions: calibrated chord confidence; alignment of independent lyric
  streams; caching/reproducibility (old sections 60–62); i18n (English-first
  until the UI is stable).

---

## 14. Experimental Engines **[R]**

Engines **not** required for the first product. They exist to be read and
compared against, not to be built now:

* `external/` submodules: `chordify`, `Guitariz`, `orchidas-Chord-Recognition`,
  `basic-pitch`, `musicpractice`, `chordify-org/*` — **read-only reference
  material**, never imported, never dependencies (see `AGENTS.md`).
* Possible future in-repo experiments (only under Phase I justification):
  CNN/ONNX chord models, bass-aware decoding, ensemble/fusion decoders.

**Rule:** no experimental engine work before the First Product Milestone
(Phase C) is reached.

---

## 15. Long-Term Features **[F]**

After Phases A–K: song sections/structure detection, multiple display
languages (Qt Linguist), stems view and stem playback, practice features
(loop/speed — see `external/musicpractice` as reference), beat grid display,
additional export formats (MIDI, MusicXML), plugin-style third-party engines,
mobile/web distribution.

---

## 16. Parity Backlog — the features named in the Chordify / Chord AI comparison **[F]**

This is the product gap list, not the accuracy plan (that is Phase I) and not
the core milestone (Phases A–H). Each item is `[ ]` until it exists, runs and is
verified; none of them is a prerequisite for the chord chart or the measured
engine. The order is the order a user would notice the difference.

| Feature | Status | Why it is not done yet / what it needs |
| --- | --- | --- |
| File input, playback, seek, synchronized chords, chord-over-lyrics chart, key/tempo/lyrics, editing, undo/redo, transpose, simplify, export | `[x]` | delivered 2026-10-07..21; see Phases C–H |
| Import a user's plain-text chord chart (chords + lyrics) and align it to the song | `[~]` | implemented 2026-10-27: `app/chart_import.py` + Edit → Load chord chart... (`Ctrl+Shift+L`) anchor chart chords under the chart's chord columns, time lyric lines from the transcript's words, distribute instrumental runs, and save the base to the sidecar. Still open: section-aware timing, recording the chart path in provenance, beat-level placement, and manual correction of a badly aligned line |
| Transposition / capo-style display | `[~]` | transpose is implemented; an explicit capo setting that shifts what the player reads while the sounding chords stay fixed is a small presenter addition, not a new engine |
| Guitar / piano / ukulele chord diagrams | `[ ]` | needs a voicing table and an `app/` presenter; the chord label already exists, and the diagrams must not be generated by inventing finger positions |
| Loop playback (A/B) | `[ ]` | needs a player-side loop over the existing decoded buffer; the `Player` protocol already has `seek`/`play`/`pause` |
| Tempo slowdown without changing pitch | `[ ]` | needs a time-stretch backend behind the `Player` protocol; no dependency is audited yet, and the current `sounddevice` path plays the decoded samples at their own rate |
| Microphone / live input | `[ ]` | needs capture plus a streaming analysis path; `decode_audio()` is file-based today, and the accuracy of a short-window streaming decode is unmeasured |
| YouTube / SoundCloud import | `[ ]` | would be an optional downloader (`yt-dlp`-style) with its own licence, terms-of-service and failure surface; never a core dependency, and never redistributing the downloaded audio |
| 700+ chord vocabulary and slash chords | `[ ]` | Phase I P4/P6; the conservative seventh pass was measured and rejected, so this needs bass/root evidence and a measured triad-reduced non-regression |
| Offline mode (no network at analysis time) | `[~]` | the engines are local once installed; the lyrics model is pulled on first use (CC-BY-4.0) and the learned chord model does not exist yet. Packaging must make the model state explicit |
| Mobile / web clients | `[ ]` | out of scope for the desktop first product; the canonical JSON document is the integration seam if it is ever revisited |
| Translations | `[ ]` | the Language menu ships, no catalogue does; English is deliberately first until the UI is frozen |

**Rules for this backlog.** No item may be taken by copying an `external/`
repository or weights; a new dependency needs the licence audit first; an
accuracy feature needs the Phase I harness; a practice feature needs its own
tests and must not fork the playback clock. The desktop product stays the
priority.

---

## Appendix — Relationship to the old roadmap

The pre-reset roadmap (§1–§125) is archived at
[`docs/archive/ROADMAP-pre-product-reset.md`](docs/archive/ROADMAP-pre-product-reset.md).
Its technical knowledge (section numbers, measurements, decisions) remains
valid and is referenced from the docs listed in §1. Its **sequencing** — research
gates before product work — is obsolete. Use its `[*]`/`[x]`/`[ ]` markers only
as history; the markers in *this* file are the live status.
