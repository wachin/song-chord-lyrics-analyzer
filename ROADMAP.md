# Product Roadmap — song-chord-lyrics-analyzer

**Repository:** `song-chord-lyrics-analyzer`
**Python package:** `song_chord_lyrics_analyzer`
**CLI:** `songlab`
**Planned GUI:** PyQt6
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
Gate at the time of audit: `ruff check` clean, `ruff format --check` 84 files
clean, `mypy` 57 files clean, `pytest` **1165 passed / 9 skipped** (core venv)
and **1173 passed / 1 skipped** (DSP venv with numpy/librosa).

### The product path, link by link

| # | Link | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Real audio file input | `[x]` | `audio/validation.py` + `audio/probe.py` (ffprobe; WAV via stdlib). Verified on a real song file (296.8 s, MP3, 324 kbit/s). |
| 2 | Decoding to samples | `[~]` | Works: each DSP engine calls `librosa.load` itself (`engines/chroma_baseline.py`, `key_krumhansl.py`, `tempo_librosa.py`; soundfile backend decodes MP3). **Missing:** no shared application-level decode service, and nothing decodes audio for playback. |
| 3 | Chord engine on real audio | `[x]` | `ChromaBaselineEngine` registered, tested, measured (CSR 0.4260 with Viterbi 0.80 on 180 GuitarSet takes — `docs/ENGINE_COMPARISON.md`). Ran on a real song during the audit. |
| 4 | Timestamped ChordEvent sequence | `[x]` | `songlab chords` printed 76 events with `start`/`end`/`label` on a real song; `songlab analyze --json` emitted the same inside the canonical document with provenance (schema version 1, `schema/codec.py`). |
| 5 | Audio playback | `[ ]` | **No playback code exists in `src/`.** The only playback implementations in the repository are inside `external/` (read-only third-party reference submodules). |
| 6 | Current playback timestamp | `[ ]` | Follows from 5: there is no player, so no position query exists. |
| 7 | Synchronized chord display | `[ ]` | **No GUI and no display code exists in `src/`** (no Qt import anywhere in the package). `docs/GUI_REQUIREMENTS.md` is a plan only. |

**Conclusion:** links 1–4 exist and are verified on real audio; links 5–7 do
not exist at all. Until 5–7 work, this project is an **analysis laboratory /
development system**, not yet a functional Chordify/Chord AI-style application.

### What is genuinely implemented today

* `[x]` Canonical typed model: `models/` (AudioDocument, ChordEvent with
  start/end/label/confidence, KeyEstimate, TempoEstimate, LyricSegment/Word,
  AnalysisResult, Provenance, AnalysisRun).
* `[x]` Canonical JSON codec with `SCHEMA_VERSION = 1` (`schema/codec.py`).
* `[x]` Engine protocols + registry (`engines/base.py`, `engines/registry.py`).
  Registered engines: **chords** `chroma-baseline`, **key** `krumhansl`,
  **tempo** `librosa-tempo`. Kinds `LYRICS`, `BEATS`, `STEMS`, `NOTES` have **no**
  registered engine.
* `[x]` Chord engine: CQT chroma → 24 triad templates → majority or Viterbi
  decoding (`engines/chroma_baseline.py`, `engines/decoding.py`), with the
  change penalty measured (0.80) on GuitarSet.
* `[x]` Application service `run_analysis()` (`analysis/service.py`): runs
  chords/key/tempo, skips unavailable engines honestly, assembles provenance
  (version, SHA-256, python, platform, engines, configuration).
* `[x]` CLI: `songlab info`, `doctor`, `chords`, `analyze` (incl. `--json`),
  `benchmark`.
* `[x]` Audio metadata probing, FFmpeg discovery with platform install hints,
  input validation (`audio/`).
* `[x]` Metrics as library code: chord (CSR, boundary/change, timing), key,
  tempo (half/double kept), lyrics WER/CER (`metrics/`, `evaluation/`).
* `[x]` Benchmark infrastructure, kind-agnostic runner (`benchmark/`).
* `[x]` Tests: 1165 core + DSP-dependent tests, fixtures with annotation-only
  GuitarSet oracles, CI workflow.
* `[x]` Documentation of decisions: `docs/ARCHITECTURE.md`,
  `DEPENDENCY_MATRIX.md`, `LICENSE_AUDIT.md`, `DATASET.md`,
  `ENGINE_COMPARISON.md`, `BENCHMARK.md`, `TROUBLESHOOTING.md`.
* `[~]` Chord confidence: `ChordEvent.confidence` exists but the baseline
  engine reports `unknown` (honestly — it has no calibrated confidence yet).
* `[x]` Real-file E2E: `tests/integration/test_analysis_e2e.py` runs the real
  default registry (chroma-baseline + krumhansl + librosa-tempo) over a
  deterministic generated WAV and, with FFmpeg, over its MP3 transcode, and
  asserts timestamped chord events cover the file. It skips without the
  optional DSP stack.
* `[~]` Transposition: `transpose_chord_label()` /
  `transpose_note_name()` exist and are tested as library functions; there is
  no user-facing transpose workflow (CLI or GUI).
* `[ ]` Playback, waveform/timeline data, GUI, lyrics engine, beats engine,
  stem separation, alignment, fusion, editing, undo/redo, ChordPro/Markdown
  export, packaging.
* Empty packages (placeholders only, `__init__.py`): `export/`, `alignment/`,
  `fusion/`, `i18n/`.

### Known documentation drift (fix opportunistically, not a phase)

* `README.md` badge says "505 tests"; actual count is 1165+.
* `README.md` / `AGENTS.md` still describe the old `[*]` marker convention and
  "no analysis engine exists yet"; the marker rules of *this* file apply.

---

## 2. Phase A — Audio Input and Playback Foundation **[P]**

**Objective:** load an audio file, decode it to samples, play it, and answer
"what is the current playback position?" — the substrate for everything after.

**Current status:** `[~]`

### Tasks

- [x] Input validation and safe path handling (`audio/validation.py`)
- [x] Metadata probing: ffprobe + WAV fallback (`audio/probe.py`)
- [x] FFmpeg discovery, no-shell invocation, install hints (`audio/ffmpeg.py`)
- [~] Decoding to samples for **analysis** — works, but only inside each engine
  via `librosa.load`; there is no shared decode entry point
- [ ] Shared application-level decode service (path → mono/stereo samples +
  sample rate) reused by analysis *and* playback, so engines stop owning decoding
- [ ] Playback abstraction: player interface with `load`, `play`, `pause`,
  `seek`, `position()`, `duration()`, `state` callbacks (no Qt types in it)
- [ ] Playback backend decision (candidate: `sounddevice`; alternative: Qt
  Multimedia in Phase D) — small dependency research, license noted in
  `docs/DEPENDENCY_MATRIX.md`, then implement
- [ ] Waveform peak data extraction for the timeline (downsampled min/max per pixel bucket)
- [ ] Tests: unit tests with committed WAV fixtures; integration test that
  plays/seeks a short file headlessly (CI-safe: no audio device → mock/skip)
- [ ] Works with a real MP3 file, not only WAV

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
on real audio during the audit; the gaps are automation and honesty of the
output, not the algorithm.

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
- [ ] Per-chord confidence from the baseline (score margin), so `confidence` is
  a measured number instead of always `unknown`
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

**Current status:** `[ ]`

This is the **first product milestone**. It is deliberately small: the first
version does not need perfect chord recognition — it needs to be real,
executable, testable, understandable, integrated, synchronized, and replaceable
by better engines later. Accuracy work happens in Phase I, **after** this works.

### Tasks

- [ ] A single application session/service: open file → decode → analyze →
  player → `chord_at(position_seconds)` lookup (binary search over events)
- [ ] Playback timeline model: song duration, playhead position, current event
- [ ] Deterministic test of the synchronization logic (fake clock: at t=0..n the
  right chord is returned; boundary and `N`/`?` handling defined)
- [ ] Minimal display surface showing the current chord, updating with
  playback (this may be the first slice of the Phase D window — either way,
  the milestone is not declared until a user can *see* it change)
- [ ] One scripted demo path: real song file in → chord list + playback + live
  chord out, documented in the README with honest wording

### Files / modules

New `src/song_chord_lyrics_analyzer/app/` (session/service layer — no Qt, no
ML imports), `audio/playback.py` (Phase A), `analysis/service.py`, tests.

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

**Current status:** `[ ]`

### Tasks

- [ ] PyQt6 dependency (optional extra; core stays dependency-free) — license
  noted in `docs/LICENSE_AUDIT.md` (GPL compatible)
- [ ] Main window consuming the **application session layer only**
  (hard rule: GUI never imports librosa, engines, numpy, or `analysis/` internals)
- [ ] Minimal Viable GUI, exactly:
  - [ ] open an audio file
  - [ ] play / pause
  - [ ] seek (click/drag on timeline)
  - [ ] show current time
  - [ ] show detected chords
  - [ ] synchronize chord display with playback
- [ ] Show key, tempo, engine name and provenance summary (cheap, already available)
- [ ] Waveform/timeline rendering from Phase A peak data
- [ ] Headless test strategy for GUI logic (logic in plain-Python presenters;
  Qt widgets thin and tested with `QT_QPA_PLATFORM=offscreen`)

### Files / modules

New `src/song_chord_lyrics_analyzer/gui/` (`main_window.py`, `player.py`,
`timeline.py`, `waveform.py`, `analysis_panel.py` as in
`docs/GUI_REQUIREMENTS.md`), plus `app/` from Phase C.

### Acceptance criteria

A user can launch the app, open a song, see its waveform timeline, play it,
seek, and always see the chord for the current position.

### Dependencies / blockers

Phases A + C. Nothing else.

### Must NOT be considered complete

A window that only loads files; widgets importing engines directly; the full
feature list below — that is `[F]` work, added after the minimal GUI works.

### Later GUI features (progressive, `[F]`)

lyrics display → chord/lyric editing with undo/redo → transpose → chord
simplification → export dialogs → confidence/engine panels → translations.

---

## 6. Phase E — Lyrics Integration **[P]**

**Objective:** turn the existing lyrics research into a real, registered lyrics
engine that produces timestamped words from real audio.

**Current status:** `[~]` — research measured, models/libraries known, metrics
and `LyricSegment`/`LyricWord` models exist; **no engine is registered**
(`LYRICS -> []`).

### Tasks

- [x] Lyrics models (`models/lyrics.py`) and WER/CER + word-timestamp metrics (`metrics/lyrics.py`)
- [x] Research already done (see §13 — do not repeat): Parakeet-1B-v3 via
  `onnx-asr` beats faster-whisper small on English (WER 0.3722 vs 0.3799);
  both are MIT; **long-audio chunking (~20 s windows) is mandatory**;
  stems do **not** improve transcription by default
- [ ] Lyrics engine adapter implementing `LyricsEngine` (start with the measured
  best option: Parakeet via `onnx-asr`, optional extra)
- [ ] Chunked transcription pipeline (windowing, overlap handling, reassembly)
- [ ] Register the engine; `songlab lyrics` command; `run_analysis()` gains a
  lyrics step with the same honest skipped/failed status handling
- [ ] Integration test on committed fixture audio (short, license-clean)
- [ ] Honest output: word timestamps carry `unknown` confidence unless measured

### Files / modules

New `engines/lyrics_*.py`, `cli/commands/lyrics.py`, `analysis/service.py`,
`pyproject.toml` (optional extra), `tests/`.

### Acceptance criteria

A real audio file produces timestamped lyric words through the same application
service and CLI pattern as chords, with model provenance (name, license,
version) recorded in the document.

### Dependencies / blockers

Optional DSP extra (onnxruntime ~GB download) — must stay optional; core and
its tests never require it. No dataset research required.

### Must NOT be considered complete

WER numbers from the old harness; an adapter that only runs on one machine;
un-timestamped transcripts.

---

## 7. Phase F — Synchronized Lyrics + Chords **[P]**

**Objective:** show lyrics and chords together on the same playback clock.

**Current status:** `[ ]`

### Tasks

- [ ] Lyric timeline model aligned to the same position clock as chords
- [ ] `lyrics_at(position)` alongside `chord_at(position)` in the session layer
- [ ] GUI: lyric line display synchronized with playback (active word
  highlighted when word timestamps exist)
- [ ] Alignment rules when lyrics come from an external timed-text file
  (`.lrc`/sidecar) — reuse `alignment/` (currently empty) instead of a new
  duplicate module
- [ ] Tests: fake-clock synchronization for both streams; boundary cases

### Acceptance criteria

While a song plays, both the current chord and the current lyric line update in
sync, from one timestamped source of truth.

### Dependencies / blockers

Phases C + D + E.

### Must NOT be considered complete

Lyrics shown without timestamps; two unsynchronized position clocks.

---

## 8. Phase G — Editing and User Corrections **[P]**

**Objective:** the user can fix what the engines got wrong, without losing the
original analysis.

**Current status:** `[ ]`

### Tasks

- [ ] Editable document layer: user edits are a separate overlay over the
  engine output (raw engine results are never overwritten — provenance stays)
- [ ] Chord editing: change label, split/merge/trim segments
- [ ] Lyric editing: correct words and timings
- [ ] Undo/redo command stack
- [ ] Persistence of the edited document (canonical JSON, schema bump if needed)
- [ ] GUI integration (edit from the timeline)
- [ ] Tests: command-level undo/redo, overlay round-trip, schema stability

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

**Current status:** `[~]` — `transpose_chord_label()` /
`transpose_note_name()` already exist as tested library functions; nothing
user-facing uses them; `export/` is an empty package; JSON export exists only
as `analyze --json`.

### Tasks

- [x] Library-level transposition (`normalization/chords.py`)
- [ ] Transpose workflow: apply semitone offset to the whole document (CLI flag
  first, GUI control after); chords displayed/transposed, originals preserved
- [ ] Chord simplification: reduce extensions/alterations to simpler voicings
  (define the reduction table, test it, expose as a workflow) — check
  `evaluation/chords.py` `triad_reduce` before writing anything new
- [ ] `songlab export` command with formats: canonical JSON (exists), ChordPro,
  simple Markdown/tabular; exporters live in `export/`, never in the model
- [ ] Round-trip tests: export → parse → same data

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

**Current status:** `[~]` — baseline measured (CSR 0.4260, change-F1 0.6202 on
180 GuitarSet takes); no second chord engine registered.

### Tasks

- [ ] Keep `docs/ENGINE_COMPARISON.md` as the measurement record; every
  accuracy claim states environment + date
- [ ] Baseline improvements with measured deltas (confidence margins, bass
  templates, phase-2 vocabulary) — each behind the existing engine interface
- [ ] Candidate engines (Chordino via Sonic Annotator, madmom, Guitariz-style
  ensembles, `external/` references) evaluated only with a **product reason**:
  "users need X and the baseline fails X"
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
- [ ] Track accuracy on the same fixed evaluation set when engines change (Phase I)

### Must NOT be considered complete

New datasets/benchmarks added without a product-driven question.

---

## 12. Phase K — Performance and Cross-Platform Packaging **[P]**

**Objective:** the application runs on Linux, Windows and macOS and ships to
users.

**Current status:** `[~]` — portable code + platform-aware discovery exist and
CI runs on the gate; no packaging, no Windows/macOS runtime verification.

### Tasks

- [x] `pathlib`, platform-aware executable discovery, no hard-coded paths
- [x] Cross-platform CI for lint/type/tests
- [ ] Measure and record real-time factor for the full product path on a
  reference machine (§45 harness already exists)
- [ ] Long-song strategy (chunked analysis, progress reporting)
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

## Appendix — Relationship to the old roadmap

The pre-reset roadmap (§1–§125) is archived at
[`docs/archive/ROADMAP-pre-product-reset.md`](docs/archive/ROADMAP-pre-product-reset.md).
Its technical knowledge (section numbers, measurements, decisions) remains
valid and is referenced from the docs listed in §1. Its **sequencing** — research
gates before product work — is obsolete. Use its `[*]`/`[x]`/`[ ]` markers only
as history; the markers in *this* file are the live status.
