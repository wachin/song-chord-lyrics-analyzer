# song-chord-lyrics-analyzer

[![CI](https://github.com/wachin/song-chord-lyrics-analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/wachin/song-chord-lyrics-analyzer/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](pyproject.toml)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows%20%7C%20macOS-lightgrey.svg)](#installation)
[![Offline-first](https://img.shields.io/badge/offline--first-yes-success.svg)](#design-principles)
[![Core dependencies](https://img.shields.io/badge/core%20dependencies-none-brightgreen.svg)](#design-principles)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Tests](https://img.shields.io/badge/tests-505%20passing-brightgreen.svg)](#development)

A cross-platform, offline-first laboratory that analyzes an audio song and
produces a synchronized representation of its **lyrics, chords, beats, tempo
and key** — with confidence and provenance attached to every inference.

* **Package:** `song_chord_lyrics_analyzer`
* **CLI:** `songlab`
* **Platforms:** Linux, Windows, macOS
* **Licence:** GPL-3.0-or-later
* **Status:** phase 0 complete and phase 1 dependency research done — repository,
  CLI, canonical model, engine interfaces, audio metadata, tests and CI. The
  chord metric suite already exists as dependency-free library code, and the
  **first chord engine is integrated**: `chroma-baseline` (CQT chroma matched
  against triad templates through an optional numpy/librosa front end) runs
  behind `songlab benchmark --engine`, which measures its own run cost.
  Candidates were resolved, licence-audited, adopted/deferred/rejected, and the
  adopted ones were smoke-tested in a throw-away environment on Linux (runtime
  verified on Linux only, no accuracy claim). The earlier measurements — the
  lyrics-ASR investigation and the chord measurements — were produced by a
  temporary, gitignored harness; see [`docs/ENGINE_COMPARISON.md`](docs/ENGINE_COMPARISON.md),
  the [roadmap](ROADMAP.md) for the order of work, and
  [`docs/DEPENDENCY_MATRIX.md`](docs/DEPENDENCY_MATRIX.md) for the findings.

## Why

Most tools hide a single model behind a single button. This project keeps the
analysis engine modular and inspectable, so a result is reported as:

```text
Chord: C
Confidence: 0.84
Time: 01:24.320–01:26.810

Evidence:
- Chordino: C
- Madmom: C
- Baseline: C/E
- Bass evidence: E
```

instead of pretending the algorithm is certain. Raw engine output is never
overwritten, and disagreement between engines is preserved rather than averaged
away.

## The problem we set out to solve: audio that already knows its chords

To know whether chord recognition is *right*, you need a reference: **song audio
paired with the name of the chord sounding at each moment** — audio segments
labelled with chords. Half of this project's research went into finding such a
resource, and the honest answer is that very few exist.

The search covered dozens of repositories, datasets and audio libraries. The
finding: **the resource we wanted already exists, and it is [GuitarSet](https://zenodo.org/records/3371780).**

| Source | Real song audio | Chord labels with timestamps | Licence | Verdict |
| --- | --- | --- | --- | --- |
| **GuitarSet** | yes — 360 real acoustic-guitar excerpts | yes — JAMS with chord (instructed *and* performed), beats, downbeats, tempo and key | **CC BY 4.0** | **adopted** — the one source with audio *and* timed chord boundaries under a permissive licence |
| Guitar-TECHS | yes — electric guitar, notes/scales/chords | chord/technique examples with per-string MIDI | CC BY 4.0 | candidate — note-level, not song progressions |
| isolated-guitar-chords | isolated single chords only | yes, one chord per clip | CC BY 4.0 | complementary — clean unit audio, not songs |
| EGFxSet | single notes through guitar effects | note-level | CC BY 4.0 | candidate — note-level |
| guitar-chord-mix | repack of the above | per-string note MIDI, not chord sequences | CC BY 4.0 / CC0 | redundant — its rows are already covered by GuitarSet |
| ChoCo | **no audio** | yes — 20,080 JAMS files | CC BY 4.0 (some partitions NC-SA) | annotations only — pair with audio you own |
| CASD | **no audio** | yes — 4 annotators per song | CC BY-NC-SA 4.0 | blocked — NC/SA, incompatible with GPL-3 |
| IDMT-SMT-Guitar / Chords / Chord-Sequences | synthetic or non-permissive | yes | CC BY-NC-ND 4.0 | blocked — NC/ND |
| chord-collection, frettler | **no audio** (fingering databases) | no | GPL / OLGA-derived | fingering reference only |

Two structural facts came out of this search, and both shaped the design:

1. **Audio rarely travels with the annotations.** Most timed chord references
   (ChoCo, CASD, Isophonics) ship labels only, because the recordings stay under
   their original copyright. GuitarSet is the exception.
2. **Permissive licences are the bottleneck.** The richest chord datasets
   (IDMT, CASD) are non-commercial or no-derivatives, so nothing from them may
   be committed into a GPL-3 repository.

GuitarSet's annotations were therefore pinned into **derived, annotation-only
fixtures** that tests and metrics run against, with the dataset licence and
provenance recorded inside the fixture itself:

* [`tests/fixtures/csr_oracle.json`](tests/fixtures/csr_oracle.json) — timed chord
  annotations for 22 comping takes plus the expected duration-weighted CSR.
* [`tests/fixtures/chord_metrics_oracle.json`](tests/fixtures/chord_metrics_oracle.json)
  — 143 pinned cases (alignment, evaluation and boundary metrics) cross-checked
  against NumPy and `mir_eval` reference implementations.

No audio is committed; only annotations and measured numbers. The full policy is
in [`docs/DATASET.md`](docs/DATASET.md).

## Design principles

1. **No GUI first.** The command-line laboratory is built and validated before
   any PyQt6 code exists.
2. **Engines behind interfaces.** Any chord or lyrics engine is an adapter; the
   CLI and GUI never import it directly.
3. **A canonical typed model.** Not Markdown, not ChordPro — those are exporters.
4. **Uncertainty survives.** `unknown` is not `0.0`, unknown is not "no chord",
   and tempo ambiguity is reported rather than normalised.
5. **No unnecessary dependencies.** The core package has none.
6. **Cross-platform from day one.** `pathlib`, platform-aware path discovery, and
   no hard-coded `/tmp` or `C:\Users\...`.
7. **English first.** Translations come only after the English UI is frozen.
8. **Never invent numbers.** A benchmark, timing or accuracy figure is written
   down only if it was measured, and it states its environment and date.

## Where the project is going

The roadmap is a phase plan, and the analysis engine is built behind interfaces
before the CLI is allowed to grow. Current state and direction:

| Area | State |
| --- | --- |
| Repository, CLI, canonical typed model, engine protocols, audio metadata | **implemented** |
| Dependency and licence research (candidates adopted/deferred/rejected) | **done** |
| Chord metrics — timing-free (align, exact/root/quality/MIREX views) and boundary-aware (segment overlap, change detection, timing error) | **library code, dependency-free** |
| Lyrics / key / tempo / beat engines behind the interfaces | next |
| `songlab benchmark` — `benchmark/{benchmark.json,csv,md}` over stored results | implemented; `--engine` runs a registered chord engine over cases with audio |
| `songlab chords` — first analysis command, on a selectable registered engine | implemented |
| `chroma-baseline` engine — template matching with a Viterbi decoder (roadmap 19/20) | implemented |
| `krumhansl` key engine — chroma profile vs the Krumhansl-Kessler profiles (roadmap 31/32) | implemented |
| `librosa-tempo` tempo engine — BPM with half/double readings kept (roadmap 33) | implemented |
| Stem separation, alignment, fusion, exports | later |
| GUI | last (phase 15) |

The metric definitions are already fixed in [`docs/BENCHMARK.md`](docs/BENCHMARK.md):
chord (exact/root/quality + segment overlap + timing error + change detection),
lyrics (WER/CER + word-timestamp error), key (exact + relative), tempo (absolute
and half/double BPM error, ambiguity reported not normalised). The order of work
lives in [`ROADMAP.md`](ROADMAP.md).

## Installation

Requires Python 3.10+ and `venv` + `pip`.

```bash
git clone https://github.com/wachin/song-chord-lyrics-analyzer
cd song-chord-lyrics-analyzer

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .         # add ".[dev]" for tests, linting, mypy
```

FFmpeg is optional but recommended: WAV files work out of the box, everything
else needs `ffmpeg` + `ffprobe` on your `PATH` (or in `SONGLAB_FFMPEG` /
`SONGLAB_FFPROBE`). See [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).

## First commands

```bash
songlab --help
songlab doctor                 # environment, FFmpeg status, caches, engines
songlab info song.mp3          # technical metadata
songlab info song.mp3 --json   # machine-readable
songlab info song.mp3 --hash   # add the SHA-256 used for caching/provenance
songlab chords song.wav        # chord detection with the first available engine
songlab chords song.wav --engine chroma-baseline --json   # select an engine, emit JSON
```

Example:

```text
$ songlab info song.wav
File:        /music/song.wav
Format:      wav
Codec:       pcm_s16le
Duration:   00:03:45.320 (225.320 s)
Sample rate: 44100 Hz
Channels:    stereo
Bit depth:   16 bit
Bitrate:     1411 kbit/s
File size:   37.95 MiB
Probed with: ffprobe
```

Planned commands, added phase by phase:

```text
songlab lyrics    song.mp3                    word-level lyric timestamps
songlab analyze   song.mp3 [--full]           the whole pipeline
songlab compare   song.mp3                    several engines side by side
songlab separate  song.mp3                    stem separation
songlab fuse      song.mp3                    consensus over engines
songlab export    song.mp3 --format chordpro  ChordPro, JSON, Markdown, ...
```

## What works today

| Capability | State |
| --- | --- |
| Canonical typed model (audio, lyrics, chords, beats, key, tempo, notes, stems, provenance) | implemented |
| Chord label parsing, rendering, transposition, uncertainty handling | implemented |
| Canonical JSON codec with schema version | implemented |
| Engine protocols + registry (`is_available`, `engine_info`) | implemented |
| Audio validation, FFmpeg discovery, metadata probing (WAV without FFmpeg) | implemented |
| `songlab info`, `songlab doctor`, error handling and exit codes | implemented |
| `songlab chords` — chord detection on a registry-selected engine (`--engine`, `--json`, time range) | implemented |
| Chord decoder — bulk majority smoothing or max-sum Viterbi with a measured change penalty and no-chord state | implemented |
| `krumhansl` key engine — key, mode and correlation confidence, scored by `songlab benchmark --engine` | implemented |
| `librosa-tempo` tempo engine — BPM scored as absolute, half-time and double-time error by `songlab benchmark --engine` | implemented |
| Chord metrics (`metrics/`) — timing-free and boundary-aware scoring views | implemented as library code |
| Key, tempo and lyrics metrics (`metrics/`) — WER/CER, key relation, half/double BPM | implemented as library code |
| Chord scoring semantics (`evaluation/`) — MIREX equality, duration-weighted CSR | implemented as library code |
| `songlab benchmark` — scores stored reference/hypothesis cases into `benchmark/{json,csv,md}` | implemented; `--engine chroma-baseline` fills cases from a real measured run |
| Further chord decoders, lyrics/key/tempo/beat engines, separation, alignment, fusion, exports, GUI | not started |

## Development

```bash
pytest                # 1146 tests + 9 environment-dependent skips, no network, no models
ruff check . && ruff format --check .
python -m mypy
```

Finished roadmap work must be marked in the same change: a new completion gets a
`[*]` marker with its date in [`ROADMAP.md`](ROADMAP.md); see
[`CONTRIBUTING.md`](CONTRIBUTING.md).

See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for setup conventions and how to
add an engine, [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the layering,
and [`docs/DEPENDENCY_MATRIX.md`](docs/DEPENDENCY_MATRIX.md) +
[`docs/LICENSE_AUDIT.md`](docs/LICENSE_AUDIT.md) for the research still pending
before any engine becomes a dependency.

## Research with AI coding agents

This repository is written to be worked on **together with an AI coding agent**,
and that is a deliberate part of the design. The ground rules an agent needs are
kept in [`AGENTS.md`](AGENTS.md), so anyone can point a fresh agent at the repo
and get correct, reproducible work — the faster developers join, the faster this
becomes something people rely on.

To start a parallel research effort with your own agent:

1. **Fork or clone** the repository and create the development environment above
   (`python -m pip install -e ".[dev]"`).
2. **Read the contract first.** Give your agent these files before it writes a
   line: [`AGENTS.md`](AGENTS.md) (agent rules), [`ROADMAP.md`](ROADMAP.md) (the
   specification and progress markers) and [`CONTRIBUTING.md`](CONTRIBUTING.md)
   (the human-facing rules).
3. **Pick a roadmap item** that is still `[ ]`, and treat its *Status* line as the
   definition of done.
4. **Keep the gate green** — the same four commands CI runs:
   `ruff check .`, `ruff format --check .`, `python -m mypy`, `pytest -q`.
5. **Record what you learned before you build.** New dependency or dataset
   findings go to [`docs/DEPENDENCY_MATRIX.md`](docs/DEPENDENCY_MATRIX.md) and
   [`docs/LICENSE_AUDIT.md`](docs/LICENSE_AUDIT.md); the roadmap marker is set in
   the same change.
6. **Measure, never invent.** Reproduce experiments in a throw-away, gitignored
   harness and commit only annotation-only fixtures and the numbers they pin,
   each with its environment and date.

A good first instruction to hand your agent:

> Read `AGENTS.md`, `ROADMAP.md` and `CONTRIBUTING.md`. Pick the first unstarted
> roadmap item that matches this area, implement it with tests, run the full
> gate, and update the roadmap marker and the relevant docs in the same change.
> Do not import, install or copy anything from `external/`.

Two rules keep parallel work mergeable: **`external/` is read-only reference
material** (never a dependency — see [`AGENTS.md`](AGENTS.md)), and **generated
state stays out of the repository** (caches, `.venv*`, model downloads,
temporary WAVs).

## Documentation

| Document | Contents |
| --- | --- |
| [`ROADMAP.md`](ROADMAP.md) | the specification, phase plan and live progress tracker (`[x]` / `[ ]` / `[*]` markers) |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | layering, model, error codes, status |
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | setup, conventions, adding an engine |
| [`AGENTS.md`](AGENTS.md) | rules for coding agents: `external/` is reference-only, roadmap markers |
| [`docs/DEPENDENCY_MATRIX.md`](docs/DEPENDENCY_MATRIX.md) | candidate dependencies and their verification status |
| [`docs/LICENSE_AUDIT.md`](docs/LICENSE_AUDIT.md) | code, model, dataset and tool licences |
| [`docs/DATASET.md`](docs/DATASET.md) | dataset policy, GuitarSet adoption, committed fixtures |
| [`docs/ENGINE_COMPARISON.md`](docs/ENGINE_COMPARISON.md) | measured engine comparisons and metric definitions |
| [`docs/BENCHMARK.md`](docs/BENCHMARK.md) | the metric specification and the planned `songlab benchmark` command |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | exit codes, FFmpeg, caches |
| [`docs/INTERNATIONALIZATION.md`](docs/INTERNATIONALIZATION.md) | English-first policy and Qt Linguist plan |
| [`docs/GUI_REQUIREMENTS.md`](docs/GUI_REQUIREMENTS.md) | planned GUI work, nothing claimed yet |

## Contributing

Contributions are welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md) for the
ground rules and [`AGENTS.md`](AGENTS.md) if you work with a coding agent. The
roadmap wins over convenience: research first, licence first, tests with every
change.

## Licence

GPL-3.0-or-later. Model weights, datasets and external tools have their own
licences; see [`docs/LICENSE_AUDIT.md`](docs/LICENSE_AUDIT.md) and
[`docs/DATASET.md`](docs/DATASET.md).
