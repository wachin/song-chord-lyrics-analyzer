# Architecture

This document describes the layered design of `song-chord-lyrics-analyzer` and
what is implemented today. It follows the roadmap ordering: the analysis engine
is built and validated before any GUI exists.

## 1. Layering

```text
                 CLI (songlab)                PyQt6 GUI (phase 15)
                       │                              │
                       └──────────────┬───────────────┘
                                      ▼
                            Application services
                                      ▼
                            Analysis pipeline
                                      ▼
                            Engine interfaces          (Protocols)
                                      ▼
                            Concrete engines           (adapters)
                                      ▼
                            Canonical data model
                                      ▼
        normalization → alignment → fusion → metrics → export
```

Rules that keep this honest:

* The CLI and (later) the GUI contain **no** audio-analysis algorithm.
* No concrete engine (`madmom`, `librosa`, `demucs`, `faster-whisper`, ...) may
  be imported by the GUI, and none is a hard dependency of the package.
* The canonical document is never Markdown or ChordPro. Those are exporters.
* Raw engine output is preserved next to normalized output.

## 2. Package layout

```text
src/song_chord_lyrics_analyzer/
├── __init__.py           version and project constants (no heavy imports)
├── __main__.py           `python -m song_chord_lyrics_analyzer`
├── cli/                  argument parsing and command implementations
│   ├── main.py           parser, error translation, exit codes
│   └── commands/         info, doctor
├── audio/                validation, FFmpeg discovery, metadata probing
├── engines/              engine protocols, options, registry
├── schema/               canonical JSON codec
├── models/               canonical typed data model (dataclasses)
├── normalization/        chord parsing, rendering, transposition
├── alignment/            (phase 9) shared timeline
├── fusion/               (phase 10) multi-engine consensus
├── metrics/              (phase 11) accuracy and performance metrics
├── export/               (phase 12) JSON, CSV, TXT, ChordPro, MIDI, MusicXML
├── i18n/                 (phase 17) Qt Linguist catalogues
└── utils/                paths, executables, logging, errors, time
```

## 3. Data flow of one analysis (target)

```text
audio file
   │  audio/probe.py            technical metadata (AudioDocument)
   ▼
preprocessing (phase 2/6)        decoded, resampled, optional stems
   │
   ├─ lyrics engines (phase 3)   EngineResult.lyrics
   ├─ chord engines  (phase 4)   EngineResult.chords
   ├─ beat/key/tempo (phase 5)   EngineResult.beats/downbeats/bars/key/tempo
   └─ audio→MIDI     (phase 7)   EngineResult.notes
   ▼
normalization (phase 8)          canonical events + preserved raw payloads
   ▼
alignment (phase 9)              AlignmentResult on one timeline
   ▼
fusion (phase 10)                consensus + visible disagreement
   ▼
metrics / confidence (phase 11)
   ▼
export (phase 12)                JSON, ChordPro, Markdown, MIDI, MusicXML
```

## 4. Canonical model (implemented)

All models are `@dataclass` types in
[`models/`](../src/song_chord_lyrics_analyzer/models), validated in
`__post_init__` so malformed engine output fails loudly at the boundary.

| Model | Purpose |
| --- | --- |
| `AudioDocument` | technical metadata + untrusted tags, kept separate |
| `LyricSegment`, `LyricWord` | segment/word timestamps, optional and never fabricated |
| `ChordEvent` | `start`, `end`, `root`, `quality`, `bass`, `extensions`, `label`, `confidence`, `source`, `metadata` |
| `BeatEvent`, `DownbeatEvent`, `BarEvent` | rhythmic grid |
| `KeyEstimate`, `TempoEstimate` | key/mode and BPM, including tempo ambiguity |
| `NoteEvent` | pitch/MIDI evidence |
| `Stem` | separated audio and its provenance |
| `ConfidenceScore` | numeric value **plus** a band; `unknown ≠ 0.0` |
| `EngineInfo`, `EngineResult` | engine identity and raw+canonical output |
| `AlignmentResult`, `AnalysisRun`, `AnalysisResult`, `Provenance` | assembled document and reproducibility record |

Deliberate design decisions:

* `ChordEvent.label` is always populated, so raw engine text survives; the
  structured parts are what later stages operate on.
* An event with no evidence renders as `?`, an explicitly silent region as `N`.
  Unknown is never reported as "no chord".
* Unrecognised chord suffixes become `ChordQuality.OTHER` with the original
  suffix preserved; transposition leaves them untouched.
* Confidence is optional: `None` means "the engine did not say", not "zero".

## 5. Engine contract (implemented, no concrete engines yet)

```python
class ChordEngine(Protocol):
    name: str
    kind: EngineKind

    def is_available(self) -> bool: ...
    def engine_info(self) -> EngineInfo: ...
    def analyze(self, audio_path: Path, options: ChordAnalysisOptions) -> EngineResult: ...
```

Engines are registered in `EngineRegistry` by kind and name, which is what makes
`songlab chords song.mp3 --engine madmom` possible without the CLI knowing
anything about Madmom. Adding an engine requires one adapter, one configuration
entry, tests and documentation - never a change in the CLI or the GUI.

`create_default_registry()` is intentionally empty in phase 0. It is the single
place where engines become visible to the rest of the application.

## 6. Audio foundation (implemented)

* `audio/validation.py` validates untrusted input paths (existence, directory,
  empty file) and warns about unfamiliar extensions instead of rejecting them.
* `audio/ffmpeg.py` discovers `ffmpeg`/`ffprobe` cross-platform (`PATH`, then
  Homebrew/winget/Chocolatey/Scoop locations, then `SONGLAB_FFMPEG` /
  `SONGLAB_FFPROBE` overrides) and reports install instructions when missing.
  Every invocation passes arguments as a list; `shell=True` is never used.
* `audio/probe.py` prefers `ffprobe` and falls back to the standard library for
  WAV, so `songlab info` works on a machine without FFmpeg. It also computes the
  SHA-256 digest used later as a cache key and provenance field.

## 7. Error handling and exit codes

Expected failures raise subclasses of `SongLabError` carrying a message and a
hint. The CLI prints them without a traceback:

```text
Error: FFprobe is required to inspect .mp3 files.

Only WAV files can be inspected without FFmpeg.
...
```

| Exit code | Meaning |
| --- | --- |
| `0` | success |
| `1` | unexpected internal error (use `--debug` for the traceback) |
| `2` | invalid input (missing file, bad argument) |
| `3` | missing external dependency (FFmpeg, optional model) |
| `130` | interrupted by the user |

## 8. Serialization

`schema/codec.py` provides one generic codec (`encode`, `decode`, `to_json`,
`from_json`) for every canonical dataclass, so there is no per-model
`to_dict`/`from_dict` duplication. Documents are wrapped with a
`schema_version` envelope to make future migrations explicit.

## 9. Status of each roadmap area

| Area | Status |
| --- | --- |
| Phase 0 repository bootstrap | done |
| Phase 1 dependency research | done for the pre-analysis candidates, including smoke tests of the adopted ones on Linux; heavy ML options and Windows/macOS runtime deliberately still open (see `DEPENDENCY_MATRIX.md` §10, `LICENSE_AUDIT.md`) |
| Phase 2 audio foundation | metadata + FFmpeg discovery done; resampling/decoding pending |
| Phase 3 lyrics laboratory | not started |
| Phase 4 chord laboratory | chord normalization done; engines pending |
| Phase 5 key/tempo/beats | models done; engines pending |
| Phases 6-14 | not started |
| Phase 15+ GUI | not started (by design) |

`ROADMAP.md` is the authoritative progress view: every section carries a bracket
marker (`[x]` achieved on 2026-09-23, `[ ]` open, `[*]` finished afterwards with
its date), and sections whose work is partly done carry an italic *Status* line.
This table summarises that state and must never disagree with it.
