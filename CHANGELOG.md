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
  librosa, soundfile, music21, faster-whisper, basic-pitch, beat_this. **PyQt6**
  confirmed compatible with GPL-3.0-or-later for phase 15, with PySide6 recorded
  as the permissive alternative.
* **Rejected**: madmom (the PyPI release does not build on Python 3.13, and its
  model files are CC BY-NC-SA 4.0) and Essentia (AGPL-3.0-only library, MTG
  models CC BY-NC-SA 4.0, no Windows support).
* **Never bundle**: Demucs pre-trained weights (upstream licence question still
  open, repository archived 2025-01-01), Chordino and Sonic Annotator
  (GPL-2.0 external executables).
* Recorded that current numpy/scipy/librosa releases require Python >= 3.12, so
  DSP extras effectively raise the floor above the core's 3.10.
* Remaining open questions are listed explicitly: no smoke tests yet, unverified
  weights (torchcrepe, Spleeter, UVR), and the GPL-2.0 "only" vs "or later"
  question for the Vamp plugins.

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
