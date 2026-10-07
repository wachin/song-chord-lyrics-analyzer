# Architecture

This document describes the layered design of `song-chord-lyrics-analyzer` and
what is implemented today. The authoritative plan is
[`ROADMAP.md`](../ROADMAP.md) (reset on 2026-10-06 around the product path); this
file explains *how* the layers fit together, not what to build next.

## 1. Layering

```text
                 CLI (songlab)                PyQt6 GUI (Phase D)
                       │                              │
                       └──────────────┬───────────────┘
                                      ▼
                    app/  session + presenter   (no Qt, no ML)
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

`app/` is the layer both front ends share: `SongSession` (open → decode →
analyze → own the player → `chord_at(seconds)`) and `display.py` (the pure
presenter that turns a `SessionSnapshot` into a `DisplayFrame`). A front end
renders frames; it never re-implements synchronization. `songlab play` is the
terminal renderer, and the Phase D window renders the same frame with widgets.

Rules that keep this honest:

* The CLI and (later) the GUI contain **no** audio-analysis algorithm.
* No concrete engine (`madmom`, `librosa`, `demucs`, `faster-whisper`, ...) may
  be imported by the GUI or by `app/`, and none is a hard dependency of the package.
* The canonical document is never Markdown or ChordPro. Those are exporters.
* Raw engine output is preserved next to normalized output.

## 2. Package layout

```text
src/song_chord_lyrics_analyzer/
├── __init__.py           version and project constants (no heavy imports)
├── __main__.py           `python -m song_chord_lyrics_analyzer`
├── cli/                  argument parsing and command implementations
│   ├── main.py           parser, error translation, exit codes
│   └── commands/         info, doctor, chords, analyze, play, benchmark
├── app/                  session (open/analyze/play/chord_at) + display presenter
├── audio/                validation, FFmpeg discovery, metadata probing, shared decode, playback
├── engines/              engine protocols, options, registry, chord + key + tempo engines, decoding
├── schema/               canonical JSON codec
├── models/               canonical typed data model (dataclasses)
├── analysis/             runs the engines and assembles one AnalysisResult + Provenance
├── normalization/        chord parsing, rendering, transposition
├── evaluation/           chord scoring semantics (roadmap §44): MIREX equality, CSR
├── alignment/            (phase 9) shared timeline
├── fusion/               (phase 10) multi-engine consensus
├── metrics/              (phase 11) chord, key, tempo and lyrics metrics + model adapters
├── performance.py        (roadmap §45) run measurement: time, RAM, real-time factor
├── benchmark/            (phase 11) runs an optional engine over cases, scores them into reports
├── export/               (phase 12) JSON, CSV, TXT, ChordPro, MIDI, MusicXML
├── i18n/                 (phase 17) Qt Linguist catalogues
└── utils/                paths, executables, logging, errors, time
```

## 3. Data flow of one analysis (first stages implemented)

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

What exists today: `analysis/service.py` runs the chord, key and tempo engines and
assembles the `AnalysisResult` with `Provenance` and `AnalysisRun` (`songlab
analyze`, `--json` prints the document through the section 48 codec). Everything
below the "normalization" line — alignment, fusion, confidence aggregation and the
ChordPro/Markdown/MIDI/MusicXML exporters — is still an empty package.

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

## 5. Engine contract (implemented; first engine: chroma-baseline)

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

`songlab chords` (roadmap section 47) is the first command to use that registry:
`--engine NAME` selects a registered `chords` engine, and without it the first
*available* engine is chosen, so a missing optional dependency becomes a
`DependencyError` rather than a silent default. The command validates the
`--start`/`--end`/`--min-duration` flags, maps them to `ChordAnalysisOptions`
and formats the resulting `EngineResult`; the estimation stays entirely behind
the protocol.

`create_default_registry()` is the single place where engines become visible
to the rest of the application. It registers the first concrete adapter today,
the `chroma-baseline` chord engine (`engines/chroma_baseline.py`): an optional
numpy/librosa front end reports its availability honestly through
`is_available()`, while the template-matching half stays dependency-free and
is tested without it. `songlab benchmark --engine chroma-baseline` runs it on
every case that declares an audio file and records the measured section 45 run
cost alongside the score.

The second concrete adapter is the `krumhansl` key engine
(`engines/key_krumhansl.py`, roadmap 31/32): it reports key, mode, confidence and
source through the `KeyEngine` protocol, and its dependency-free correlation half
is similarly tested without the DSP stack. The third is `librosa-tempo`
(`engines/tempo_librosa.py`, roadmap 33), which reports BPM through the
`TempoEngine` protocol and keeps the half-time and double-time readings as
`TempoEstimate.alternatives` rather than resolving them; it reports no
confidence, because librosa produces none. `songlab benchmark --engine NAME` is
kind-agnostic — it dispatches on the engine's kind and fills that family's
hypothesis (chords, key, tempo, lyrics) — so a new engine whose output a section
44 metric family can score plugs into the benchmark without changing the runner.

Turning per-frame chord scores into a sequence is a separate concern, kept in
the dependency-free `engines/decoding.py` (`viterbi_decode`). The engine
exposes `frame_scores` (24 triad states plus a constant no-chord state) and
`decode_labels`, which selects either the roadmap 19 majority smoother or the
roadmap 20 max-sum Viterbi over a flat change penalty; the Viterbi decoder is
the default because it was measured to beat the smoother on real ground truth
(`docs/ENGINE_COMPARISON.md`). The decoder is selectable per run through
`ChordAnalysisOptions.extra` (`decoder`, `change_penalty`, `no_chord_score`),
so the experiment stays reproducible without a second engine.

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
| Area (this file) | Status |
| --- | --- |
| Model, codec, registry, audio metadata, CLI | implemented; the canonical model, the engine protocols and the commands `info`, `doctor`, `chords`, `analyze` and `play` all run |
| Audio decoding and playback | implemented as a shared service (`audio/decode.py`) and a tested `Player` with a real `sounddevice` backend (`audio/playback.py`). **Still open:** the DSP engines call `librosa.load` themselves instead of the shared decoder, and there is no waveform peak data yet |
| Chord engine | `chroma-baseline` registered, tested and measured (CSR 0.4260, 180 GuitarSet takes); per-chord confidence still reports `unknown` |
| Key and tempo engines | `krumhansl` and `librosa-tempo` registered, tested and measured; an engine for beats does not exist |
| Product slice (open → analyze → play → synchronized chord) | **reached** on 2026-10-07 as `songlab play` + `app/display.py`; the display is a terminal line |
| GUI | not started; the Phase D window renders the existing `DisplayFrame`/`SongSession` |
| Lyrics, beats, stems, alignment, fusion, export, packaging | not started; `metrics/`/`evaluation/` metrics and the `benchmark/` runner exist as library code, `export/`, `alignment/`, `fusion/` and `i18n/` are empty placeholders |

[`ROADMAP.md`](../ROADMAP.md) is the authoritative progress view, with `[x]` /
`[~]` / `[ ]` markers per task and per phase; this table summarises it and must
never disagree with it. The old `[*]` convention belongs to the archived
pre-reset roadmap and is history only.
