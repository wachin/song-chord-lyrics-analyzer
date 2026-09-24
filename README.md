# song-chord-lyrics-analyzer

A cross-platform, offline-first laboratory that analyzes an audio song and
produces a synchronized representation of its **lyrics, chords, beats, tempo
and key** — with confidence and provenance attached to every inference.

* **Package:** `song_chord_lyrics_analyzer`
* **CLI:** `songlab`
* **Platforms:** Linux, Windows, macOS
* **Licence:** GPL-3.0-or-later
* **Status:** phase 0 complete and phase 1 dependency research done — repository,
  CLI, canonical model, engine interfaces, audio metadata, tests and CI. No
  analysis engine is integrated yet: candidates were resolved, licence-audited,
  adopted/deferred/rejected, and the adopted ones were smoke-tested in a
  throw-away environment on Linux (no real music, no accuracy numbers, and
  runtime verified on Linux only). See the [roadmap](ROADMAP.md) for the order of
  work and [`docs/DEPENDENCY_MATRIX.md`](docs/DEPENDENCY_MATRIX.md) for the
  findings.

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

## Installation

Requires Python 3.10+ and `venv` + `pip`.

```bash
git clone <repository>
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
songlab chords    song.mp3 --engine madmom    chord detection, selectable engine
songlab analyze   song.mp3 [--full]           the whole pipeline
songlab compare   song.mp3                    several engines side by side
songlab separate  song.mp3                    stem separation
songlab fuse      song.mp3                    consensus over engines
songlab export    song.mp3 --format chordpro  ChordPro, JSON, Markdown, ...
songlab benchmark samples/                    metrics + benchmark/ reports
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
| Lyrics/chords/key/tempo/beat engines, separation, alignment, fusion, exports, GUI | not started |

## Development

```bash
pytest                # 220 tests, no network, no models
ruff check . && ruff format --check .
python -m mypy
```

See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for setup conventions and how to
add an engine, [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the layering,
and [`docs/DEPENDENCY_MATRIX.md`](docs/DEPENDENCY_MATRIX.md) +
[`docs/LICENSE_AUDIT.md`](docs/LICENSE_AUDIT.md) for the research still pending
before any engine becomes a dependency.

## Documentation

| Document | Contents |
| --- | --- |
| [`ROADMAP.md`](ROADMAP.md) | the specification and phase plan |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | layering, model, error codes, status |
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | setup, conventions, adding an engine |
| [`docs/DEPENDENCY_MATRIX.md`](docs/DEPENDENCY_MATRIX.md) | candidate dependencies and their verification status |
| [`docs/LICENSE_AUDIT.md`](docs/LICENSE_AUDIT.md) | code, model, dataset and tool licences |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | exit codes, FFmpeg, caches |
| [`docs/INTERNATIONALIZATION.md`](docs/INTERNATIONALIZATION.md) | English-first policy and Qt Linguist plan |
| [`docs/ENGINE_COMPARISON.md`](docs/ENGINE_COMPARISON.md), [`docs/BENCHMARK.md`](docs/BENCHMARK.md), [`docs/DATASET.md`](docs/DATASET.md), [`docs/GUI_REQUIREMENTS.md`](docs/GUI_REQUIREMENTS.md) | planned work, nothing claimed yet |

## Licence

GPL-3.0-or-later. Model weights, datasets and external tools have their own
licences; see [`docs/LICENSE_AUDIT.md`](docs/LICENSE_AUDIT.md).
