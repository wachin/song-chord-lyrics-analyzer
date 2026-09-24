# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

### Research

* Completed the phase 1 dependency research for every candidate needed before the
  first analysis phases, with each fact sourced (package metadata, upstream
  `LICENSE`/`COPYING`, model card, or vendor licence page) and dated.
* **Adopted** (as optional extras, when their phase arrives): numpy, scipy,
  librosa, soundfile, music21, faster-whisper, beat_this. **PyQt6** confirmed
  compatible with GPL-3.0-or-later for phase 15, with PySide6 recorded as the
  permissive alternative. **basic-pitch** is adopted with a condition: it is
  Apache-2.0 and works, but its official install path is broken on Python 3.12+.
* **Rejected**: madmom (the PyPI release does not build on Python 3.13, and its
  model files are CC BY-NC-SA 4.0) and Essentia (AGPL-3.0-only library, MTG
  models CC BY-NC-SA 4.0, no Windows support).
* **Never bundle**: Demucs pre-trained weights (upstream licence question still
  open, repository archived 2025-01-01), Chordino and Sonic Annotator
  (GPL-2.0 external executables).
* Recorded that current numpy/scipy/librosa releases require Python >= 3.12, so
  DSP extras effectively raise the floor above the core's 3.10.
* Remaining open questions are listed explicitly: Windows/macOS runtime is
  unverified, no real music has been analysed, unverified weights (torchcrepe,
  Spleeter, UVR), and the GPL-2.0 "only" vs "or later" question for the Vamp
  plugins.

### Smoke-tested

Each adopted dependency was installed in a throw-away virtual environment and
exercised with generated audio (a tone, a C major triad and a 120 BPM click
track). Full detail: `docs/DEPENDENCY_MATRIX.md` §10.

* **soundfile 0.14.0** — metadata, read, and a sample-exact WAV->FLAC->read round
  trip in 8.9 ms.
* **librosa 1.0.0** — `chroma_cqt` ranks C/E/G correctly on a C major triad;
  `beat_track` reports 117.45 BPM on a 120 BPM click track. Cold calls carry a
  numba JIT cost (`chroma_cqt` 1524 ms cold vs ~110 ms warm).
* **beat_this 1.1.0** — exactly 120.00 BPM and 16/16 beats, 0.7-0.8 s of CPU for
  8 s of audio, on CPU-only torch. Its 81 MB checkpoint auto-downloads to
  `~/.cache/torch/hub`, so the adapter must redirect `TORCH_HOME` into our cache
  and announce the download.
* **basic-pitch 0.4.0** — the documented install **fails on Python 3.12/3.13**
  (`tensorflow<2.15.1` is unsatisfiable there). The model bundled in the wheel
  was run through ONNX instead (`--no-deps` + `onnxruntime`) and detected exactly
  C4/E4/G4.
* Cross-platform **wheel availability** for Python 3.13 was verified for Linux,
  Windows and macOS arm64; **runtime stays Linux-only** and is reported as such.
  No accuracy claim is made: a click track and a synthetic triad are not a
  benchmark.

### Reference repositories

* Added `external/`, holding third-party study references as read-only git submodules, plus
  `scripts/add_external_repos.sh` to add or refresh them. They are study material:
  never imported, packaged, installed, linted, type-checked or tested, which is now
  enforced by exclusions in `pyproject.toml` (verified by planting a lint-broken file
  and a failing test in `external/` and confirming the gates stay green).
* Added `AGENTS.md` and `external/README.md`, whose first rule is that `external/` is
  a set of reference repositories and not a library of this project.
* Expanded the pool to 32 repositories (2026-09-24) in four blocks — 12 chord,
  practice-tool and visualization projects, 12 instrument-recognition and detection
  projects, 5 transcription/audio identification projects and 3 cross-cutting music
  libraries — with `yuval-kahan/Chords.py` added after the first batch missed it.
  Licences were read from each clone's licence file and are recorded as observations
  (not audits) in `external/README.md`.
* Repaired the `ChordMiniApp` clone after its checkout failed: upstream's Git LFS
  budget is exhausted, so its model checkpoints cannot be downloaded. The code was
  checked out with `GIT_LFS_SKIP_SMUDGE=1` (checkpoints stay as pointer files) and the
  limitation is documented in `external/README.md`.
* Established the cleanup rule: `external/` is a temporary research pool that must
  shrink, not grow — after a repository is investigated and its verdict recorded, the
  submodule is deleted unless still needed.
* Recorded that the section 24.2 URL (`yuval-kahan/youchords-local`) returns HTTP 404,
  so it is deliberately not added; the section now references the author's other
  repositories registered under `external/`.
* Investigated the block 1 chord references against the section 24 bullets by reading
  the clones (2026-09-24); verdicts are recorded in `docs/DEPENDENCY_MATRIX.md` §13.
  `1ucas/chordify` is confirmed as the primary architectural reference, with its full
  pipeline documented bullet by bullet (HPSS + tuning-corrected CQT/CENS chroma blend,
  equal-weight triad templates, two-pass bass- and key-aware Viterbi, song-palette
  prior, conservative slash/extension display). The ideas worth keeping from
  `chordscope` (windowed modulation tracking, tempo-curve classification) and from the
  unlicensed `orchidas/Chord-Recognition` baseline (chroma → templates →
  Gaussian-emission HMM with Viterbi) are recorded as candidates to re-implement as
  original code.
* Applied the `external/` cleanup rule for the first time: removed `chord-extractor`
  (wraps the GPL-2.0 Chordino Vamp stack already classified as never-bundle),
  `Chord-recognition` (a superseded, unlicensed course project), `scales-chords`
  (an Obsidian plugin, off scope) and `chordscope` (its core beat/chord engine is
  madmom, already rejected). The pool went from 32 to 28 submodules.

### Documentation

* `ROADMAP.md` now tracks its own progress with bracket markers: `[x]` for work
  already achieved when the convention was introduced (2026-09-23), `[ ]` for
  work still open, and `[*]` for work completed afterwards, which must carry its
  completion date. Every section, subsection and task carries a marker.
* 25 sections whose work is partly done say so in an italic *Status* line rather
  than pretending to be finished, and the phase sections, both definition-of-done
  checklists and the 20 completion criteria are now ticked item by item.
* No roadmap item was finished by the marker-convention change itself; the first
  `[*]` markers appeared on 2026-09-24 (roadmap §24.4 and §24.5), and the date was
  recorded here so the first one could be checked against it.

## [0.1.0] - 2026-09-23

Phase 0 (repository bootstrap) plus the first tasks from the roadmap. No
analysis engine is integrated yet.

### Added

* `src/` package layout with the `songlab` console entry point.
* Canonical typed data model: `AudioDocument`, `LyricSegment`, `LyricWord`,
  `ChordEvent`, `BeatEvent`, `DownbeatEvent`, `BarEvent`, `KeyEstimate`,
  `TempoEstimate`, `NoteEvent`, `Stem`, `EngineInfo`, `EngineResult`,
  `AlignmentResult`, `AnalysisRun`, `AnalysisResult`, `Provenance` and
  `ConfidenceScore`.
* Engine protocols (`ChordEngine`, `LyricsEngine`, `BeatEngine`, `KeyEngine`,
  `TempoEngine`, `StemSeparationEngine`), options objects and an
  `EngineRegistry` that reports availability and provenance.
* Chord label parsing, rendering and transposition, with unrecognised labels kept
  as `OTHER`/`UNKNOWN` instead of being upgraded to false precision.
* Canonical JSON codec with a `schema_version` envelope and typed round trips.
* Audio foundation: input validation, cross-platform FFmpeg/ffprobe discovery,
  metadata probing through `ffprobe` with a standard-library WAV fallback, and
  SHA-256 hashing for caching and provenance.
* CLI: `songlab --help`, `--version`, `--verbose`, `--quiet`, `--debug`,
  `songlab info [--json] [--hash]` and `songlab doctor [--json]`, with
  actionable error messages and documented exit codes (2 = input, 3 = missing
  dependency).
* Cross-platform path helpers (cache, data, models, exports, temp) with
  `SONGLAB_*` overrides and no hard-coded system paths.
* Documentation: architecture, development guide, dependency matrix (with an
  explicit verification status per candidate), licence audit, internationalization
  plan, troubleshooting, and outlines for the comparison, benchmark, dataset and
  GUI documents.
* Tests: 220 tests covering models, chord normalization, the JSON codec, the
  registry, paths, timestamps, errors, audio validation and probing, the CLI
  contract, plus FFmpeg integration tests that skip when the tool is absent.
* GitHub Actions CI across Linux, Windows and macOS on Python 3.10-3.13, with
  linting, formatting, type checking and a dedicated FFmpeg integration job.

### Notes

* The core package has no runtime dependencies.
* Madmom is reported as restricted to Python < 3.10 and is therefore not adopted;
  see `docs/DEPENDENCY_MATRIX.md`.
* No accuracy claim is made anywhere: nothing has been benchmarked yet.
