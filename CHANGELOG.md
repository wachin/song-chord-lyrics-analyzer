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

### Lyrics ASR investigation (roadmap 25/26/27)

A first measured comparison of singing-voice recognition, run on the CPU-only
reference machine (Intel Core i3-7020U, 7.6 GiB RAM) and recorded in
`docs/ENGINE_COMPARISON.md`. It is an investigation by a temporary harness, not a
`songlab benchmark` run.

* Compared **Faster-Whisper 1.2.1** (`small`, int8) against **NVIDIA Parakeet TDT
  0.6B v3** through **onnx-asr 0.12.0** + onnxruntime (int8 ONNX). The ONNX path is
  the light CPU route and was chosen over `nemo_toolkit`; that resolves the open
  Parakeet-packaging question in `docs/DEPENDENCY_MATRIX.md` §12.
* Dataset: all 40 excerpts of **vocadito** (CC-BY-4.0, multilingual solo singing with
  annotated lyrics). Four excerpts and their lyric sidecars are committed under
  `samples/`; the rest stays in the gitignored `.cache/`.
* On isolated vocals Parakeet reached WER 0.3722 / CER 0.1857 at a real-time factor of
  0.20, versus Faster-Whisper `small` at WER 0.3799 / CER 0.2725 and a real-time factor
  of 0.95 (peak RSS ~1.3–1.4 GiB each). Per-language results differ sharply: Parakeet
  is far better on English, Faster-Whisper is better on Tagalog and the single Spanish
  excerpt, and both fail on Mandarin.
* Mix vs isolated vocal (roadmap 26): on eight excerpts with synthetic accompaniment at
  three ratios, both engines degraded monotonically as the accompaniment grew, and the
  true isolated vocal was best (no separation error is involved, by construction).
* Real separation with **Demucs 4.1.0 `htdemucs`** (`--two-stems=vocals`, CPU; roadmap
  26/27): repeating the same eight conditions on the separated `vocals` stem did *not*
  reproduce the true-vocal win. The separated stem was worse than the raw mix for
  Faster-Whisper (WER 0.3244 vs 0.2505) and only slightly better for Parakeet (0.2991 vs
  0.3356), while the `no_vocals` residual scored WER 1.0 for both engines. Separation is
  engine-dependent, not a free win, and the mixes are synthetic (a caveat, since
  `htdemucs` is trained on real music). Demucs weights were used locally only and never
  bundled — their licence is still unresolved.
* **Long audio is a packaging problem (roadmap 25).** Given a whole 272 s song, the packaged
  ONNX Parakeet path returned 8 garbled words and the upstream VAD route returned *nothing*,
  because a speech VAD does not treat singing as speech; only our own fixed 20 s window
  chunking produced a usable transcription. Faster-Whisper windows long audio itself.
* **Real commercial mix, second pass (roadmap 26).** A user-supplied commercial MP3 (4 min
  32 s, kept in the gitignored `mp3/` and never committed, with its embedded partial lyrics
  as the reference) was separated with Demucs `htdemucs` (4 stems, 5 min 38 s) and transcribed
  from the raw mix, the `vocals` stem and the `no_vocals` residual. The raw mix **won or tied
  for both engines** — clearly for Parakeet (unique-token F1 0.737 vs 0.618), a wash for
  Faster-Whisper — so the synthetic conclusion does not transfer to real audio. The residual
  transcribed to 6 words for Faster-Whisper and to nothing for Parakeet, confirming the vocal
  left it.
* Not covered, and recorded as such: backing vocals, reverb, live recordings, heavy
  instrumentation, word-timestamp error (vocadito has no word-level ground truth), a
  larger Whisper (medium needed ~66 s per 30 s clip on this CPU and was stopped), the
  `vocals + selected accompaniment` case, a full verbatim transcript for the real song, and
  6-stem separation or `htdemucs_ft`/UVR alternatives.

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
* Recorded that the section 24.2 URL (`yuval-kahan/youchords-local`) returns HTTP 404
  (checked 2026-09-23). On 2026-09-24 the section was dropped from the roadmap
  entirely: the repository no longer exists on GitHub, and section 24 now lists
  exactly the 13 repositories registered under `external/` — 24.1 (chordify), 24.5
  (research baseline), 24.6 (MOSS-Music) and a new compact 24.7 table for the
  remaining registered clones.
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
* Investigated blocks 2 (instrument recognition, 12 clones) and 3 (transcription,
  audio identification and other, 5 clones) with the same verdict-per-clone method.
  Block 2 kept only the two paper-backed MIT repositories (`instrument-prediction`,
  ISMIR 2018 frame-level recognition; `predominant-instrument-recognition`, APSIPA
  ASC 2023 NSynth-pretrained polyphonic recognition) — ten were course projects and
  notebooks without any licence file. Block 3 was removed entirely: `muscriptor`
  carries **CC BY-NC 4.0 weights** (the same non-commercial pattern that rejected
  madmom and Essentia), `presto`/`shazam-build`/`audd-go` address song
  identification this offline-first project does not have, and `Ear` is an LLM demo.
  The pool went from 28 to 13 submodules; every removed pin remains recoverable
  from git history.
* Closed roadmap §24.7 (2026-09-24) by investigating the last clones that still lacked
  a verdict and applying the cleanup rule once more; the verdicts are in
  `docs/DEPENDENCY_MATRIX.md` §13.10. **Kept** `musicpractice` (MIT, a PySide6 desktop
  app whose `chords.py` is a readable template + Viterbi chord engine with
  Krumhansl-Schmuckler key estimation, using Demucs and Basic Pitch — the closest
  blueprint for phase 15) and `Guitariz` (MIT, whose `ml/` package is a from-scratch
  109-class chord CRNN with a shared CQT-chroma extractor, a synthetic-data generator
  and an adaptive-self-transition Viterbi). **Removed** `Chords.py` (unlicensed 2021
  MLP, 10 classes, `.h5` weights of undocumented provenance), `ChordVisualizer` (a
  Vue/WASM play-and-name theory toy with no audio analysis) and `ChordMiniApp` (a
  cloud Next.js/Firebase stack whose nested model submodules are uninitialized and
  whose LFS checkpoints are absent upstream). The pool went from 13 to 10 submodules.
* Closed roadmap §24.6 (2026-09-24) with a **feasibility verdict instead of a benchmark**,
  because MOSS-Music cannot be run here. Reading the clone and the released weights (via the
  Hugging Face API) showed: ~9.1 B parameters (Qwen3-8B plus a 32-layer audio encoder), four
  bf16 shards totalling **18.11 GB**, no quantization path, a CUDA-only supported runtime and
  bandwidth-bound autoregressive decoding — so it is **not viable on commodity CPU** for this
  CPU-first project. Its code also has no root `LICENSE` (only the weights are Apache-2.0) and
  loading it requires `trust_remote_code=True`. The architecture ideas worth reading
  (DeepStack cross-layer injection, time-marker insertion) are recorded in
  `docs/DEPENDENCY_MATRIX.md` §13.11, and the submodule was removed. The pool went from 10 to
  9 submodules.

### Documentation

* `ROADMAP.md` now tracks its own progress with bracket markers: `[x]` for work
  already achieved when the convention was introduced (2026-09-23), `[ ]` for
  work still open, and `[*]` for work completed afterwards, which must carry its
  completion date. Every section, subsection and task carries a marker.
* 25 sections whose work is partly done say so in an italic *Status* line rather
  than pretending to be finished, and the phase sections, both definition-of-done
  checklists and the 20 completion criteria are now ticked item by item.
* No roadmap item was finished by the marker-convention change itself; the first
  `[*]` markers appeared on 2026-09-24 (roadmap §24.5, later followed by §24.7), and
  the date was recorded here so the first one could be checked against it.

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
