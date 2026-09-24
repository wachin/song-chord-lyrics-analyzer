# ROADMAP — Song Chord Lyrics Analyzer

**Repository:** `song-chord-lyrics-analyzer`
**Python package:** `song_chord_lyrics_analyzer`
**CLI application:** `songlab`
**Primary language:** English
**GUI framework:** PyQt6
**Target platforms:** Linux, Windows, macOS
**Development environment:** Python `venv` + `pip`
**Development strategy:** CLI laboratory first → validated analysis engine → PyQt6 GUI → Qt Linguist translations

---

## Progress markers

Every section, subsection and task in this roadmap starts with a bracket marker.

| Marker | Meaning |
| --- | --- |
| `[x]` | Already achieved. Verified against the repository on 2026-09-23, the date this convention was introduced. |
| `[ ]` | Not achieved yet. Where some work already exists, an italic *Status* line under the heading states what is done and what remains. |
| `[*]` | Newly completed **after** this convention was introduced. The item must carry the completion date, for example `[*] (2026-09-24)`. |

Rules for keeping this roadmap honest:

* A task is finished only when its marker is set. A change that advances a roadmap item but leaves
  its marker unset is incomplete, exactly like a change without tests.
* Newly finished work gets `[*]`, never `[x]`. `[x]` records the state at the introduction of this
  convention and is never used for new work.
* Markers are updated in the same change that completes the work, and listed in the pull-request
  description (see `CONTRIBUTING.md`).
* Every marker must be defensible against the code. Never mark a section `[x]` because it looks
  close: use `[x]` only when the section's own deliverable or definition of done is truly met.
* On a policy, principle or instruction section, `[x]` means the policy is currently respected in the
  codebase, not that a feature exists.
* Partially finished sections stay `[ ]`; the *Status* line carries the detail. Do not invent a
  fourth marker.

---

# [x] 1. Project Vision

## [x] 1.1 Objective

Build a cross-platform application capable of analyzing an audio song and producing a synchronized representation containing:

* Lyrics
* Word-level or segment-level lyric timestamps
* Chords
* Chord changes
* Chord confidence
* Beats
* Downbeats
* Bars
* Tempo/BPM
* Musical key
* Optional bass information
* Optional note/MIDI information
* Alignment between lyrics, chords and musical time
* Exportable chord/lyrics formats

The eventual user workflow should be approximately:

```text
Open song
    ↓
Analyze
    ↓
Detect lyrics
    ↓
Detect chords
    ↓
Detect beat / tempo / key
    ↓
Align everything
    ↓
Review results
    ↓
Correct results if necessary
    ↓
Transpose / simplify
    ↓
Export
```

---

# [x] 2. Fundamental Development Principle

Do NOT begin by building the GUI.

The project must first become a reliable command-line research laboratory.

The development order is:

```text
Research
    ↓
CLI laboratory
    ↓
Audio infrastructure
    ↓
Lyrics experiments
    ↓
Chord experiments
    ↓
Beat/key/tempo experiments
    ↓
Stem separation experiments
    ↓
Alignment
    ↓
Fusion
    ↓
Benchmarking
    ↓
Export
    ↓
Stable analysis engine
    ↓
PyQt6 GUI
    ↓
English UI stabilization
    ↓
Qt Linguist translations
```

The GUI must be a client of the analysis engine.

The GUI must NOT contain the core audio-analysis algorithms.

---

# [x] 3. Language Policy

The application is English-first.

All initial development must use English for:

* Python identifiers
* Class names
* Function names
* CLI commands
* CLI help
* Error messages
* Logging
* Documentation
* Configuration
* Internal model names
* GUI text
* Test descriptions
* Reports
* Configuration keys

Do NOT introduce Spanish UI strings during the initial implementation.

Spanish and other languages will be added only after the English application is stable.

Internationalization will use Qt Linguist.

Planned system:

```text
English source strings
        ↓
Qt Linguist
        ↓
Spanish
Other languages
```

Expected files:

```text
translations/
├── song_chord_lyrics_analyzer_es.ts
├── song_chord_lyrics_analyzer_fr.ts
├── song_chord_lyrics_analyzer_de.ts
└── ...
```

Compiled translations:

```text
*.qm
```

Use:

* `QTranslator`
* `lupdate`
* `lrelease`

Do not hard-code translated strings throughout the application.

---

# [ ] 4. Cross-Platform Policy

*Status (2026-09-23): partial — `Path` and platform-aware executable discovery are implemented and
tested, and no code path assumes `/tmp` or `shell=True`; runtime behaviour is verified on Linux only.
Windows and macOS have wheel-level and CI-configuration evidence, not a runtime run.*

The application must target:

* Linux
* Windows
* macOS

from the beginning.

Do not build a Linux-only architecture and attempt to port it later.

Avoid assumptions such as:

```python
/home/user/
```

or:

```python
C:\Users\...
```

Use:

```python
from pathlib import Path
```

and platform-independent APIs whenever possible.

External executable discovery must work on all supported operating systems.

Potential external tools include:

* FFmpeg
* Sonic Annotator
* Chordino
* other optional engines

The architecture must distinguish between:

```text
Python package
External executable
Downloaded model
System dependency
Optional dependency
```

---

# [x] 5. Repository Naming

Repository:

```text
song-chord-lyrics-analyzer
```

Python package:

```text
song_chord_lyrics_analyzer
```

CLI:

```text
songlab
```

Do NOT shorten the Python package to an arbitrary abbreviation such as:

```text
scla
```

The descriptive package name is intentional.

---

# [x] 6. Initial Repository Structure

Create:

```text
song-chord-lyrics-analyzer/
├── .github/
│   └── workflows/
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT.md
│   ├── DEPENDENCY_MATRIX.md
│   ├── ENGINE_COMPARISON.md
│   ├── LICENSE_AUDIT.md
│   ├── BENCHMARK.md
│   ├── DATASET.md
│   ├── GUI_REQUIREMENTS.md
│   ├── INTERNATIONALIZATION.md
│   └── TROUBLESHOOTING.md
│
├── src/
│   └── song_chord_lyrics_analyzer/
│       ├── __init__.py
│       │
│       ├── cli/
│       ├── audio/
│       ├── engines/
│       ├── schema/
│       ├── models/
│       ├── normalization/
│       ├── alignment/
│       ├── fusion/
│       ├── metrics/
│       ├── export/
│       ├── i18n/
│       └── utils/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── regression/
│
├── samples/
├── benchmark/
├── results/
├── scripts/
├── translations/
│
├── pyproject.toml
├── README.md
├── ROADMAP.md
├── LICENSE
├── CONTRIBUTING.md
├── CHANGELOG.md
└── .gitignore
```

---

# [x] 7. Python Packaging

Use modern `pyproject.toml`.

Use the `src/` layout.

Create the environment with:

```bash
python -m venv .venv
```

Activate on Linux/macOS:

```bash
source .venv/bin/activate
```

Activate on Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Upgrade packaging tools:

```bash
python -m pip install --upgrade pip setuptools wheel
```

Install the project:

```bash
python -m pip install -e .
```

Development installation:

```bash
python -m pip install -e ".[dev]"
```

Do not require:

* Conda
* Poetry
* Pipenv

unless a concrete dependency makes one necessary.

The primary workflow must remain:

```text
venv + pip
```

---

# [x] 8. Core Architectural Rule

The architecture must be modular.

Never allow the GUI to directly depend on a specific AI/audio library.

For example, this is forbidden:

```text
GUI → Whisper
GUI → Demucs
GUI → librosa
GUI → Madmom
```

Instead:

```text
GUI
 ↓
Application Services
 ↓
Analysis Pipeline
 ↓
Engine Interfaces
 ↓
Concrete Engines
```

This allows different algorithms to be compared.

---

# [x] 9. Canonical Internal Data Model

The application must have a canonical typed representation.

Do NOT use Markdown as the internal representation.

Do NOT use ChordPro as the internal representation.

Markdown and ChordPro are output formats.

The canonical model should represent musical and linguistic information independently of any specific output format.

Potential models:

```text
AudioDocument
LyricSegment
LyricWord
ChordEvent
BeatEvent
DownbeatEvent
BarEvent
KeyEstimate
TempoEstimate
NoteEvent
Stem
AnalysisRun
AnalysisResult
EngineResult
ConfidenceScore
AlignmentResult
```

Use Python typing and preferably:

```python
@dataclass
```

or carefully designed Pydantic models if a concrete requirement justifies the dependency.

Do not introduce unnecessary frameworks.

---

# [x] 10. AudioDocument

Define a canonical audio metadata structure containing at least:

```text
path
duration
sample_rate
channels
bit_depth
format
codec
bitrate
file_size
```

Optional metadata:

```text
artist
album
title
genre
year
```

Never trust metadata to be correct.

Separate:

```text
technical metadata
```

from:

```text
musical analysis
```

---

# [x] 11. Lyric Model

Lyrics must support:

```text
segment-level timestamps
word-level timestamps
text
confidence
language
source
```

Example conceptual model:

```text
LyricSegment
    start
    end
    text
    confidence
    words[]
```

Each word can contain:

```text
word
start
end
confidence
```

The system must support engines that provide:

* segment timestamps
* word timestamps
* no timestamps

When no word timestamps are available, do not fabricate precision.

---

# [x] 12. Chord Model

Chord events must preserve more information than just:

```text
C
Am
F
G
```

A chord event should be capable of representing:

```text
start
end
root
quality
bass
extensions
label
confidence
source
metadata
```

Example:

```text
root = C
quality = major
bass = E
label = C/E
confidence = 0.84
```

The system must support uncertainty.

Do not convert an uncertain prediction into an apparently exact musical fact.

---

# [ ] 13. Initial Chord Vocabulary

*Status (2026-09-23): partial — the vocabulary, parser and renderer are implemented and
regression-tested (`normalization/chords.py`); no engine output has been validated against real music.*

Begin with a conservative vocabulary.

Phase 1:

```text
major
minor
N
```

Phase 2:

```text
7
maj7
m7
sus2
sus4
dim
aug
```

Phase 3:

```text
add9
6
m6
9
m9
slash chords
altered chords
```

Do not generate complex chord names merely because a model produces ambiguous pitch information.

The normalization layer must distinguish:

```text
detected evidence
```

from:

```text
interpreted chord label
```

---

# [x] 14. Chord Engine Interface

Create an abstract interface similar to:

```python
class ChordEngine(Protocol):
    name: str

    def analyze(
        self,
        audio_path: Path,
        options: ChordAnalysisOptions,
    ) -> EngineResult:
        ...
```

The concrete engines must be replaceable.

Potential engines:

* PitchPerfect
* Madmom
* Chordino/Sonic Annotator
* custom chroma/template baseline
* neural chord-recognition candidates
* other actively maintained projects discovered during research

---

# [x] 15. Lyrics Engine Interface

Create an abstraction similar to:

```python
class LyricsEngine(Protocol):
    name: str

    def transcribe(
        self,
        audio_path: Path,
        options: LyricsOptions,
    ) -> EngineResult:
        ...
```

Candidate engines include:

* Faster-Whisper
* Whisper
* Parakeet-based solutions
* MOSS-Music
* other appropriate music-aware ASR systems

Do not assume that a general speech recognizer is optimal for singing.

Benchmark singing separately.

---

# [ ] 16. Audio Preprocessing

*Status (2026-09-23): partial — validation, metadata probing and FFmpeg discovery are implemented and
tested; decoding, resampling, channel conversion and temporary-WAV generation remain (phase 2).*

Build an audio preprocessing subsystem.

Responsibilities:

```text
input validation
format detection
decoding
resampling
channel conversion
normalization
temporary WAV generation
silence handling
```

FFmpeg should be considered the primary compatibility layer.

The implementation must not assume FFmpeg is installed globally.

Research strategies for:

* Linux
* Windows
* macOS

Document:

* installation
* executable discovery
* version detection
* licensing
* redistribution considerations

---

# [x] 17. FFmpeg Safety

Never construct shell commands using unsafe string interpolation.

Prefer:

```python
subprocess.run(
    [
        ffmpeg,
        "-i",
        str(input_path),
        ...
    ],
    check=True,
)
```

Avoid:

```python
subprocess.run(command, shell=True)
```

unless there is an unavoidable and documented reason.

Audio files must be treated as untrusted input.

---

# [ ] 18. Audio Feature Laboratory

Before integrating sophisticated models, implement a basic feature laboratory.

Investigate:

* waveform
* RMS
* spectral centroid
* spectral bandwidth
* spectral contrast
* zero crossing rate
* STFT
* CQT
* chroma
* onset strength
* mel spectrogram

Libraries to investigate:

* librosa
* scipy
* soundfile
* Essentia

The goal is not to reinvent mature libraries.

The goal is to understand and benchmark their outputs.

---

# [ ] 19. Chroma Laboratory

Implement a baseline chord recognizer.

Pipeline:

```text
Audio
 ↓
STFT/CQT
 ↓
Chromagram
 ↓
Chord templates
 ↓
Similarity
 ↓
Candidate chords
 ↓
Temporal smoothing
 ↓
Chord events
```

Test:

```text
C
G
Am
F
```

and simple progressions.

Implement this baseline even if better engines will later be used.

It provides:

* debugging
* explainability
* regression testing
* fallback operation
* educational value

---

# [ ] 20. HMM / Viterbi Experiment

Investigate chord recognition using:

```text
chromagram
 ↓
chord likelihoods
 ↓
transition model
 ↓
Viterbi decoding
```

The system should test:

* self-transition probability
* chord-change penalties
* improbable transitions
* minimum duration

Do not hard-code musical assumptions without benchmarking them.

---

# [x] 21. Chordino / Sonic Annotator Investigation

Investigate Chordino/Sonic Annotator.

Determine:

* installation
* supported platforms
* output format
* chord vocabulary
* timestamp precision
* computational cost
* license
* maintenance state
* quality

Build an adapter if practical.

Preserve its original output before normalization.

---

# [x] 22. Madmom Investigation

Investigate Madmom for:

* beats
* downbeats
* tempo
* chord recognition
* onset detection

Document:

* Python compatibility
* operating-system support
* dependency issues
* maintenance state
* installation complexity
* licensing

Do not assume it will work unchanged on every current Python version.

---

# [ ] 23. PitchPerfect Investigation

Investigate:

```text
1ucas/chordify
```

and the PitchPerfect ecosystem/references found there.

Determine:

* architecture
* chord extraction method
* CQT/chroma processing
* chord templates
* Viterbi decoding
* key/song priors
* bass analysis
* integration possibilities
* license

Do not copy code blindly.

Extract architectural ideas and implement clean adapters where legally and technically appropriate.

---

# [ ] 24. GitHub Project Investigation

*Status (2026-09-23): partial — 24.1 (`chordify`) and 24.6 (MOSS-Music) were inventoried during phase 1;
24.2-24.5 have not been investigated yet.*

The agent MUST investigate these projects.

## [x] 24.1 chordify

Repository:

```text
https://github.com/1ucas/chordify
```

Investigate:

* chord extraction
* chroma/CQT
* chord templates
* temporal decoding
* key estimation
* bass analysis
* Demucs
* Whisper/Parakeet
* timestamp alignment
* offline processing
* licensing

---

## [ ] 24.2 youchords-local

Repository:

```text
https://github.com/yuval-kahan/youchords-local
```

Investigate:

* local-first architecture
* Madmom
* Chordino
* Sonic Annotator
* FFmpeg
* Demucs
* lyrics processing
* caching
* model handling
* licensing

---

## [ ] 24.3 magic-chords-project

Repository:

```text
https://github.com/Esysc/magic-chords-project
```

Investigate:

* chord detection
* lyrics
* transcription
* key
* tempo
* MIDI
* MusicXML
* Madmom
* Whisper
* Essentia
* architecture
* license

---

## [ ] 24.4 ChordScope

Repository:

```text
https://github.com/okamyuji/chordscope
```

Investigate:

* Madmom
* librosa
* music21
* chord analysis
* key
* beat
* tempo
* output representation

---

## [ ] 24.5 Research Chord Recognition

Repository:

```text
https://github.com/orchidas/Chord-Recognition
```

Investigate:

```text
CQT
 ↓
Chroma
 ↓
Chord templates
 ↓
HMM
 ↓
Viterbi
```

Use this as a research baseline.

---

## [ ] 24.6 MOSS-Music

*Status (2026-09-23): inventoried only — Apache-2.0 weights, 8B parameters, released 2026-05-01;
feasibility on commodity CPU hardware is untested.*

Repository:

```text
https://github.com/OpenMOSS/MOSS-Music
```

Investigate its capabilities for:

* singing ASR
* lyrics
* word timestamps
* key
* tempo
* beats
* downbeats
* chords
* timestamped chord transcription
* musical structure

Do not assume it is superior to specialized modular engines.

Benchmark it.

---

# [ ] 25. Lyrics Recognition

*Status (2026-09-23): partial — whisper, faster-whisper and ctranslate2 resolved and licence-checked;
no ASR engine has been run on audio yet.*

Start with Faster-Whisper or another practical ASR engine.

Investigate:

```text
Whisper
Faster-Whisper
Parakeet-based models
MOSS-Music
```

Test:

* English singing
* Spanish singing
* male vocals
* female vocals
* backing vocals
* reverberation
* live recordings
* music with heavy instrumentation

Record:

```text
WER
CER
timestamp error
processing time
RAM
VRAM
model size
```

---

# [ ] 26. Singing ASR Strategy

Compare:

```text
original mix
```

against:

```text
vocals stem
```

and potentially:

```text
vocals + selected accompaniment
```

Do not assume that isolated vocals always produce the best transcription.

Benchmark it.

---

# [ ] 27. Stem Separation

*Status (2026-09-23): partial — separation licences were audited and Demucs weights remain unresolved
(the repository was archived on 2025-01-01 with the question still open); no separation has been run.*

Investigate:

```text
Demucs
```

and appropriate alternatives.

Expected stems may include:

```text
vocals
drums
bass
other
```

Test chord recognition on:

```text
original
bass
other
vocals
other + bass
```

Compare results.

Do not automatically separate every song if the computational cost is unjustified.

Create a configurable strategy:

```text
fast
balanced
accurate
```

---

# [ ] 28. Stem Selection Strategy

For chord recognition, investigate whether:

```text
original
```

or:

```text
bass + other
```

or:

```text
other
```

produces the best results.

For lyrics:

```text
vocals
```

will normally be an important candidate.

However, this must be validated empirically.

---

# [ ] 29. Audio-to-MIDI

*Status (2026-09-23): partial — basic-pitch was smoke-tested through its bundled ONNX model (correct
C4/E4/G4 on a synthetic triad), but the supported install path fails on Python >= 3.12 and no musical
evaluation has been done.*

Investigate:

```text
Spotify Basic Pitch
```

Capabilities to test:

* note transcription
* polyphonic transcription
* guitar
* piano
* bass
* melodic instruments

Test:

```text
original
bass stem
other stem
```

Potential use:

```text
Audio
 ↓
MIDI
 ↓
Pitch evidence
 ↓
Chord interpretation
```

Basic Pitch is an auxiliary evidence source, not automatically the canonical chord engine.

---

# [ ] 30. Pitch Detection

*Status (2026-09-23): partial — torchcrepe resolved as MIT, but it was never executed and its model
weights are unverified.*

Investigate:

```text
TorchCREPE
```

or equivalent modern pitch trackers.

Potential uses:

* monophonic pitch
* bass tracking
* vocal pitch
* note evidence
* chord evidence

Do not introduce large machine-learning dependencies without demonstrating their value.

---

# [ ] 31. Music Theory Layer

*Status (2026-09-23): partial — chord parsing, normalization and transposition are implemented in this
repository; music21 was audited but is not integrated.*

Investigate:

```text
music21
```

for:

* chord parsing
* pitch-class manipulation
* key handling
* transposition
* Roman numerals
* MusicXML
* theoretical validation

The music-theory layer must remain separate from raw audio inference.

---

# [ ] 32. Key Detection

Implement multiple candidates.

Possible sources:

```text
Essentia
librosa
Madmom
chord-sequence inference
modern neural model
```

Return:

```text
key
mode
confidence
source
```

Example:

```text
C major
confidence: 0.87
source: essentia
```

If engines disagree, preserve the disagreement.

Do not silently choose one without documenting the decision.

---

# [ ] 33. Tempo Detection

*Status (2026-09-23): partial — one measurement only, on a synthetic click track (beat_this 120.00 BPM,
librosa 117.45 BPM); no real music evaluated and no engine adapter written.*

Implement:

```text
BPM
confidence
source
```

Handle:

* half-time
* double-time
* tempo ambiguity

Example:

```text
90 BPM
```

may correspond musically to:

```text
180 BPM
```

depending on beat interpretation.

Do not blindly normalize these cases.

---

# [ ] 34. Beat Detection

*Status (2026-09-23): partial — beat_this and librosa were smoke-tested on a synthetic click track;
downbeat quality was deliberately not assessed, since a click track has no meter.*

Detect:

```text
beat events
downbeats
bars
```

Each event should contain timestamps.

Potential engines:

* Madmom
* librosa
* Essentia
* other appropriate MIR libraries

---

# [ ] 35. Beat Grid

Create a normalized beat grid:

```text
Beat 1
Beat 2
Beat 3
Beat 4
...
```

Where possible, identify:

```text
bar start
```

and:

```text
downbeat
```

This becomes important for chord timing.

---

# [ ] 36. Alignment Engine

The alignment engine is one of the most important components.

It must align:

```text
lyrics
chords
beats
downbeats
bars
```

on a common timeline.

Conceptually:

```text
00:00 ─────────────────────────────── 03:45

Lyrics:  |---Hello---|------world------|
Chords:  | C | G | Am | F | C | G |
Beats:   |1|2|3|4|1|2|3|4|
Bars:    |-------bar-------|-------bar-------|
```

---

# [ ] 37. Chord/Lyric Alignment

The system must support:

```text
chord starts before lyric
chord changes during word
word spans chord change
multiple chords inside one lyric line
```

Do not force every lyric word to have exactly one chord.

The canonical timeline must permit overlapping semantic events.

---

# [ ] 38. Temporal Normalization

Implement configurable normalization.

Examples:

```text
merge adjacent identical chords
minimum chord duration
snap chord changes to beats
snap chord changes to subdivisions
quantize to bars
remove isolated improbable changes
```

Never destroy raw engine results.

Maintain:

```text
raw
normalized
final
```

as distinct representations.

---

# [x] 39. Confidence

Every inference should preserve confidence where the source provides it.

Potential levels:

```text
very_low
low
medium
high
very_high
```

But numerical confidence should remain available when supplied.

Do not convert:

```text
unknown
```

into:

```text
0.0
```

unless explicitly defined.

---

# [ ] 40. Fusion Engine

Eventually combine multiple engines.

Example:

```text
Chordino
Madmom
PitchPerfect
Chromagram baseline
Basic Pitch evidence
Bass analysis
```

The fusion engine should produce:

```text
candidate chords
evidence
agreement
confidence
selected result
```

Initial fusion should be deterministic.

Example:

```text
Engine A: C
Engine B: C
Engine C: Am
```

The system may identify:

```text
C
```

as the consensus candidate.

But the original disagreement must remain accessible.

---

# [ ] 41. Never Hide Engine Disagreement

*Status (2026-09-23): partial — the model can represent disagreement (`alternatives`, confidence and
provenance are mandatory fields), but no fusion step exists yet.*

The UI and exported reports should be able to show:

```text
Final: C
Confidence: 0.81

Evidence:
Chordino: C
Madmom: C
Baseline: Am
Basic Pitch: C/E evidence
```

This is preferable to pretending that the algorithm has absolute certainty.

---

# [ ] 42. Dataset Strategy

*Status (2026-09-23): partial — the policy is written down in `docs/DATASET.md`; no dataset exists.*

Create a small internal benchmark dataset.

Categories:

```text
simple_pop
acoustic_guitar
piano
full_band
live_recording
worship
spanish_vocals
english_vocals
male_vocal
female_vocal
dense_drums
bass_heavy
complex_harmony
modulation
multiple_instruments
```

Do not commit copyrighted commercial songs to the repository.

Use:

* original recordings
* public-domain recordings
* properly licensed recordings
* compatible research datasets

Document every dataset license.

---

# [ ] 43. Ground Truth

*Status (2026-09-23): partial — the intended format is documented in `docs/DATASET.md`; no annotations exist.*

Ground truth must be explicit.

Never manufacture expected chords.

Ground truth may contain:

```text
lyrics
word timestamps
chords
chord boundaries
key
tempo
beats
downbeats
```

Store provenance.

---

# [ ] 44. Metrics

## [ ] Chord metrics

Implement:

```text
exact chord accuracy
root accuracy
quality accuracy
segment overlap
timing error
chord-change detection accuracy
```

## [ ] Lyrics metrics

Implement:

```text
WER
CER
word timestamp error
```

## [ ] Key metrics

Implement:

```text
exact key accuracy
relative-key error
```

## [ ] Tempo metrics

Implement:

```text
absolute BPM error
half-tempo error
double-tempo error
```

---

# [ ] 45. Performance Metrics

*Status (2026-09-23): partial — install sizes and cold/warm timings were recorded once in
`docs/DEPENDENCY_MATRIX.md` section 11; no benchmark harness exists.*

Record:

```text
processing time
seconds of audio per second of computation
RAM
VRAM
model size
startup time
disk usage
```

Compare:

```text
CPU
GPU
```

where applicable.

---

# [ ] 46. Benchmark Command

Implement:

```bash
songlab benchmark samples/
```

Output:

```text
benchmark/
├── benchmark.json
├── benchmark.csv
└── benchmark.md
```

Include:

```text
engine
song
duration
processing_time
memory
result
metrics
```

---

# [ ] 47. CLI Design

*Status (2026-09-23): partial — `songlab info` and `songlab doctor` are implemented, tested and
verified end to end; every analysis command is still missing.*

The CLI should eventually support:

```bash
songlab info song.mp3
```

```bash
songlab lyrics song.mp3
```

```bash
songlab chords song.mp3
```

```bash
songlab chords song.mp3 --engine madmom
```

```bash
songlab chords song.mp3 --engine pitchperfect
```

```bash
songlab separate song.mp3
```

```bash
songlab analyze song.mp3
```

```bash
songlab analyze song.mp3 --full
```

```bash
songlab compare song.mp3
```

```bash
songlab benchmark samples/
```

```bash
songlab fuse song.mp3
```

```bash
songlab export song.mp3 --format chordpro
```

Eventually:

```bash
songlab models list
```

```bash
songlab models download ...
```

---

# [x] 48. JSON Export

*Note: the canonical JSON codec and its versioned envelope exist with round-trip tests; the
`songlab export` command that will expose them belongs to section 94.*

Implement complete machine-readable JSON.

Example conceptual structure:

```json
{
  "audio": {},
  "lyrics": [],
  "chords": [],
  "beats": [],
  "downbeats": [],
  "key": {},
  "tempo": {},
  "analysis": {},
  "engines": {},
  "provenance": {}
}
```

The JSON representation should preserve enough information to reproduce analysis reports.

---

# [ ] 49. ChordPro Export

Implement ChordPro export.

Example:

```text
[C]Hello [G]world
[Am]This is [F]my song
```

The exporter must use the canonical model.

Do not make ChordPro the canonical model.

---

# [ ] 50. Additional Export Formats

Investigate:

```text
JSON
CSV
TXT
ChordPro
MIDI
MusicXML
Markdown
```

Markdown is intended for human-readable reports.

---

# [ ] 51. Markdown Report

Generate reports such as:

```text
Song
Artist
Duration
Key
Tempo

Lyrics

[C]Hello [G]world
[Am]This is [F]my song
```

Include optional technical information:

```text
Chord engine
Lyrics engine
Confidence
Processing time
```

---

# [ ] 52. Model Management

Create a model manager.

Commands:

```bash
songlab models list
```

```bash
songlab models download MODEL
```

```bash
songlab models info MODEL
```

Record:

```text
model name
version
source
license
size
sha256
hardware requirements
```

Never silently download large models without informing the user.

---

# [ ] 53. Offline-First Principle

*Status (2026-09-23): partial — the core package never touches the network and has no dependencies;
the model manager that would distinguish online from offline dependencies does not exist yet.*

After models are downloaded, core analysis should work without an Internet connection whenever technically possible.

Internet access should not be required for every song.

The program should distinguish:

```text
online dependency
offline dependency
optional online service
```

---

# [ ] 54. GPU Strategy

*Status (2026-09-23): partial — CPU-only PyTorch is measured to work (1.4 GB, no CUDA stack); no
device-selection code exists yet.*

GPU acceleration should be optional.

The program must have a CPU fallback whenever feasible.

Do not make:

```text
CUDA
```

a mandatory requirement.

Potential hardware:

```text
NVIDIA CUDA
Apple Silicon / Metal where supported
CPU
```

Document actual support rather than assuming it.

---

# [x] 55. Dependency Matrix

Create:

```text
docs/DEPENDENCY_MATRIX.md
```

For every major dependency record:

```text
package
version tested
Python versions
Linux
Windows
macOS
CPU
GPU
license
model license
installation complexity
maintenance status
notes
```

Investigate at minimum:

```text
PyQt6
numpy
scipy
librosa
soundfile
essentia
madmom
pitchperfect
demucs
faster-whisper
basic-pitch
torch
torchaudio
torchcrepe
music21
```

Do not add all of them automatically.

Each dependency must justify its inclusion.

---

# [x] 56. License Audit

Create:

```text
docs/LICENSE_AUDIT.md
```

Separate:

```text
code license
model license
dataset license
weights license
external executable license
commercial-use restrictions
redistribution requirements
attribution requirements
```

A repository's source-code license does not automatically mean its downloaded models have the same license.

---

# [x] 57. Architecture Documentation

Create:

```text
docs/ARCHITECTURE.md
```

Document:

```text
GUI
 ↓
Application Services
 ↓
Analysis Pipeline
 ↓
Engine Interfaces
 ↓
Concrete Engines
 ↓
Canonical Data Model
 ↓
Normalization
 ↓
Alignment
 ↓
Fusion
 ↓
Metrics
 ↓
Export
```

---

# [x] 58. Engine Registry

Implement a registry.

Conceptually:

```python
registry.register(ChordinoEngine())
registry.register(MadmomChordEngine())
registry.register(PitchPerfectEngine())
```

The CLI can then use:

```bash
songlab chords --engine madmom song.mp3
```

without knowing implementation details.

---

# [ ] 59. Plugin-Like Architecture

*Status (2026-09-23): partial — the interface, the registry and its validation contract exist; no
concrete engine has been written against them yet.*

The engine layer should make future engines easy to add.

A new engine should ideally require:

```text
one adapter
one configuration
tests
documentation
```

without modifying the GUI.

---

# [ ] 60. Caching

Implement caching for expensive operations.

Cache candidates:

```text
decoded audio
resampled audio
stems
spectrograms
chroma
lyrics
chords
beats
models
```

Cache keys should depend on:

```text
input file hash
engine
engine version
configuration
model version
```

Avoid stale results.

---

# [ ] 61. Reproducibility

*Status (2026-09-23): partial — `Provenance` and content hashing exist; nothing yet reproduces a full
analysis run.*

Each analysis should record:

```text
application version
Python version
OS
engine versions
model versions
configuration
input hash
timestamp
```

This creates analysis provenance.

---

# [ ] 62. Provenance

*Status (2026-09-23): partial — the provenance dataclasses and `EngineInfo` exist; no engine writes
them yet.*

Every result should answer:

```text
Where did this result come from?
Which engine generated it?
Which model generated it?
Which preprocessing was used?
Which normalization was applied?
Which fusion rules were applied?
```

Do not lose provenance during transformation.

---

# [x] 63. Error Handling

Errors must be understandable.

Bad:

```text
Traceback...
```

for ordinary users.

Better:

```text
Unable to analyze the audio file.

Reason:
FFmpeg was not found.

Install FFmpeg and run the command again.
```

Debug mode may still expose the complete traceback.

---

# [x] 64. Logging

Implement structured logging.

Levels:

```text
DEBUG
INFO
WARNING
ERROR
```

The CLI should allow:

```bash
songlab analyze song.mp3 --verbose
```

and possibly:

```bash
songlab analyze song.mp3 --debug
```

---

# [ ] 65. Testing Strategy

*Status (2026-09-23): partial — unit, regression and skipped-if-missing FFmpeg integration tests run in
CI; engine tests cannot exist before engines do.*

Implement unit tests for:

```text
schemas
timestamps
chord parsing
chord normalization
transposition
alignment
fusion
confidence
exporters
configuration
path handling
```

Integration tests for:

```text
FFmpeg
lyrics engines
chord engines
Demucs
Basic Pitch
beat detection
```

Regression tests must use small fixtures.

---

# [x] 66. Cross-Platform CI

*Note: the workflow exists (Linux/Windows/macOS x Python 3.10-3.13, a lint job and an FFmpeg
integration job) but has never run on GitHub, because the repository has not been pushed.*

Configure GitHub Actions for:

```text
Linux
Windows
macOS
```

Test supported Python versions.

At minimum validate:

```text
installation
imports
CLI startup
unit tests
basic integration tests
```

Heavy AI tests may use a separate workflow.

---

# [ ] 67. GUI Requirements

Only after the analysis engine is sufficiently stable should PyQt6 development begin.

The GUI should provide:

```text
Open Audio
Analyze
Stop
Play
Pause
Seek
```

Main workspace:

```text
Waveform
Timeline
Lyrics
Chords
Beat grid
Playback cursor
```

---

# [ ] 68. GUI Timeline

The timeline should visually represent:

```text
lyrics
chords
beats
bars
```

Example:

```text
       C        G        Am       F
00:00 |--------|---------|---------|---------|
       Hello    world     this      song
       |   |   |   |     |   |   |
       1   2   3   4     1   2   3
```

The exact visual design may evolve.

---

# [ ] 69. GUI Editing

Allow the user to:

```text
edit lyrics
edit words
edit chord labels
move chord timestamps
add chord
delete chord
split chord
merge chord
transpose
simplify chords
```

All editing operations must work on the canonical model.

---

# [ ] 70. Undo / Redo

Implement:

```text
undo
redo
```

for editing operations.

Potential operations:

```text
EditLyric
EditChord
MoveChord
DeleteChord
InsertChord
Transpose
Quantize
```

---

# [x] 71. Chord Transposition

*Status (2026-09-23): the transposition primitives (`transpose_note_name`, `transpose_chord_label`) are
implemented and tested in `normalization/chords.py`; the GUI affordance belongs to phase 15.*

Implement transposition independently of the audio engine.

Example:

```text
C → D
Am → Bm
F → G
G → A
```

Support:

```text
semitone offset
key-based transposition
```

Preserve slash chords correctly.

---

# [ ] 72. Chord Simplification

Implement optional transformations:

```text
Cmaj7 → C
Am7 → Am
G7 → G
Dsus4 → D
```

These must be user-selectable.

Never overwrite the original analysis.

---

# [ ] 73. User Corrections

Manual corrections should be represented as a separate layer.

Conceptually:

```text
Raw Analysis
     ↓
Normalized Analysis
     ↓
User Corrections
     ↓
Final Document
```

This is important for preserving provenance.

---

# [ ] 74. GUI Playback

The audio player must synchronize:

```text
audio position
lyrics
chords
beats
cursor
```

When the user clicks a chord:

```text
jump to chord timestamp
```

When the user clicks a lyric:

```text
jump to lyric timestamp
```

---

# [ ] 75. GUI Confidence Visualization

The GUI should optionally show confidence.

Do not use only colors.

Provide accessible information such as:

```text
Confidence: 82%
Source: Madmom
```

---

# [ ] 76. GUI Engine Comparison

Provide an optional analysis/debug view showing:

```text
Final chord
Chordino
Madmom
PitchPerfect
Baseline
```

This is especially useful during development.

---

# [ ] 77. English UI Stabilization

Before translations:

* finalize terminology
* finalize menus
* finalize dialogs
* finalize errors
* finalize settings
* finalize CLI terminology
* finalize documentation terminology

Do not start translation while the UI is changing every day.

---

# [ ] 78. Qt Linguist

After English stabilization:

Generate translation sources with Qt tools.

Implement:

```text
QTranslator
```

and load language resources dynamically.

Initial translation:

```text
Spanish
```

Later:

```text
French
German
Portuguese
Italian
```

if there is demand.

---

# [x] 79. Internationalization Rules

*Note: the policy is respected — the canonical model is language-neutral and the package contains no
display strings. The `i18n` package is a placeholder until phase 17.*

Never write:

```python
label.setText("Analyze")
```

without making it translatable.

Use Qt translation mechanisms.

Avoid constructing sentences by concatenating translated fragments.

Prefer complete translatable strings.

---

# [ ] 80. Documentation

*Status (2026-09-23): partial — README, CONTRIBUTING, ARCHITECTURE, DEVELOPMENT, DEPENDENCY_MATRIX,
LICENSE_AUDIT, TROUBLESHOOTING, CHANGELOG and the remaining document skeletons exist; user-facing and
GUI documentation is still missing.*

Create:

```text
README.md
```

containing:

* project description
* screenshots eventually
* supported platforms
* installation
* first analysis
* CLI usage
* GUI usage
* dependencies
* models
* troubleshooting
* license

Create:

```text
docs/DEVELOPMENT.md
```

with developer setup.

---

# [ ] 81. User Documentation

Eventually document:

```text
How to analyze a song
How to install models
How to use GPU acceleration
How to correct chords
How to correct lyrics
How to transpose
How to export ChordPro
How to benchmark engines
```

---

# [x] 82. Phase 0 — Repository Bootstrap

Tasks:

* [x] Create repository
* [x] Create `src/` layout
* [x] Create `pyproject.toml`
* [x] Create package
* [x] Create CLI entry point
* [x] Create tests
* [x] Create README
* [x] Create ROADMAP
* [x] Configure Git
* [x] Configure `.gitignore`
* [x] Configure CI

Definition of done:

```bash
python -m pip install -e .
songlab --help
pytest
```

all work.

*Verified (2026-09-23): the three commands pass in a clean `venv` on CPython 3.13, with 219 tests
passing and one skipped (integration test requiring an external executable).*

---

# [x] 83. Phase 1 — Dependency Research

*Status (2026-09-23): research complete and reproducible (`pip --dry-run --report` plus upstream licence
sources), with Linux smoke tests recorded in `docs/DEPENDENCY_MATRIX.md` section 10. Windows and macOS
were not run, and no real music has been analysed.*

Before installing everything, investigate:

* [x] package availability
* [x] supported Python versions
* [x] operating systems
* [x] licenses
* [x] maintenance
* [x] GPU requirements
* [x] model requirements
* [x] installation complexity

Create:

```text
docs/DEPENDENCY_MATRIX.md
docs/LICENSE_AUDIT.md
```

Do not blindly install every candidate.

---

# [ ] 84. Phase 2 — Audio Foundation

*Status (2026-09-23): partial — audio metadata, validation, FFmpeg/ffprobe discovery and probing are
implemented and tested (`songlab info` works with zero third-party dependencies); resampling, channel
conversion and temporary-file generation remain.*

Implement:

```text
audio metadata
FFmpeg integration
resampling
channel conversion
temporary files
audio validation
```

CLI:

```bash
songlab info song.mp3
```

Definition of done:

The program can inspect common audio formats consistently on Linux, Windows and macOS.

---

# [ ] 85. Phase 3 — Lyrics Laboratory

Implement:

```bash
songlab lyrics song.mp3
```

Test:

* [ ] Faster-Whisper
* [ ] Whisper
* [ ] alternative music-aware models

Generate:

```text
TXT
JSON
SRT
```

where applicable.

Preserve word timestamps.

---

# [ ] 86. Phase 4 — Chord Laboratory

Implement:

```bash
songlab chords song.mp3
```

Integrate:

* [ ] baseline chroma recognizer
* [ ] Chordino
* [ ] Madmom
* [ ] PitchPerfect or equivalent
* [ ] other promising engines

Do not select a final engine before benchmarking.

---

# [ ] 87. Phase 5 — Musical Analysis

Implement:

```text
key
tempo
beats
downbeats
bars
```

Compare:

* [ ] Essentia
* [ ] librosa
* [ ] Madmom
* [ ] other candidates

---

# [ ] 88. Phase 6 — Stem Separation

Integrate Demucs or a suitable alternative.

Implement:

```bash
songlab separate song.mp3
```

Output:

```text
vocals
drums
bass
other
```

Test whether separation improves:

```text
lyrics
chords
tempo
key
```

---

# [ ] 89. Phase 7 — Audio-to-MIDI

Integrate Basic Pitch experimentally.

Command:

```bash
songlab midi song.mp3
```

Test:

```text
original
bass
other
```

Measure whether MIDI-derived evidence improves chord recognition.

---

# [ ] 90. Phase 8 — Normalization

Implement normalization pipeline:

```text
raw engine result
 ↓
canonical conversion
 ↓
validation
 ↓
normalization
```

Never modify the raw result.

---

# [ ] 91. Phase 9 — Alignment

Combine:

```text
lyrics
chords
beats
bars
```

into a shared timeline.

Validate difficult cases.

---

# [ ] 92. Phase 10 — Fusion

Implement multi-engine fusion.

Compare:

```text
engine agreement
engine disagreement
confidence
```

Generate final canonical analysis.

---

# [ ] 93. Phase 11 — Metrics

Build the benchmark infrastructure.

Every improvement should be measurable.

Avoid statements such as:

```text
This engine seems better.
```

Prefer:

```text
Chord root accuracy increased from X to Y on dataset Z.
```

Never invent metrics.

---

# [ ] 94. Phase 12 — Export

Implement:

```text
JSON
CSV
TXT
ChordPro
Markdown
MIDI
MusicXML
```

as feasible.

---

# [ ] 95. Phase 13 — Real-World Evaluation

Test songs with:

* [ ] clean studio production
* [ ] acoustic guitar
* [ ] piano
* [ ] full band
* [ ] worship music
* [ ] Spanish vocals
* [ ] English vocals
* [ ] live recordings
* [ ] background vocals
* [ ] heavy drums
* [ ] bass-heavy mixes
* [ ] modulation
* [ ] unusual chords

Document failures.

---

# [ ] 96. Phase 14 — Architecture Freeze

Before GUI:

* [ ] freeze canonical data model
* [ ] freeze engine interfaces
* [ ] freeze analysis services
* [ ] freeze CLI terminology
* [ ] stabilize exporters
* [ ] stabilize tests
* [ ] stabilize provenance

Only bug fixes and justified architectural changes should occur after this point.

---

# [ ] 97. Phase 15 — PyQt6 GUI

Build GUI on top of the stable engine.

Suggested modules:

```text
gui/
├── main_window.py
├── player.py
├── timeline.py
├── waveform.py
├── chord_editor.py
├── lyrics_editor.py
├── analysis_panel.py
├── engine_panel.py
├── settings_dialog.py
└── widgets/
```

Do not move analysis algorithms into these files.

---

# [ ] 98. Phase 16 — English GUI Stabilization

Complete:

* [ ] menus
* [ ] dialogs
* [ ] settings
* [ ] error messages
* [ ] keyboard shortcuts
* [ ] accessibility
* [ ] terminology

Test the English application thoroughly.

---

# [ ] 99. Phase 17 — Translation

Only now implement:

```text
Qt Linguist
Spanish
additional languages
```

The Spanish translation should be created from the stabilized English source.

---

# [x] 100. Suggested Development Commands

Linux/macOS:

```bash
git clone <repository>
cd song-chord-lyrics-analyzer

python -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

Windows:

```powershell
git clone <repository>
cd song-chord-lyrics-analyzer

python -m venv .venv
.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

Run CLI:

```bash
songlab --help
```

---

# [x] 101. Code Quality

Use:

```text
ruff
pytest
mypy or pyright where justified
```

Keep formatting and linting automated.

Avoid excessive abstraction.

Do not create classes simply because classes are possible.

---

# [x] 102. Type Checking

Use modern Python type hints.

Example:

```python
from pathlib import Path

def analyze_song(path: Path) -> AnalysisResult:
    ...
```

Avoid untyped dictionaries for canonical data.

Prefer typed structures.

---

# [ ] 103. Configuration

*Status (2026-09-23): partial — CLI flags are the explicit configuration surface and `SONGLAB_*`
variables exist only as documented advanced overrides; there is no settings file, and only a few of the
listed options exist.*

Configuration should be explicit.

Potential configuration:

```text
engine
model
device
sample rate
cache directory
temporary directory
language
output format
confidence threshold
```

Do not hide important configuration inside environment variables.

Environment variables may be used for advanced overrides.

---

# [x] 104. Temporary Files

Use:

```python
tempfile
```

and appropriate temporary directories.

Never assume:

```text
/tmp
```

on every platform.

---

# [x] 105. File Path Safety

Use:

```python
Path
```

throughout.

Validate input files.

Do not overwrite source audio accidentally.

Export to explicit output paths.

---

# [ ] 106. Large File Handling

*Status (2026-09-23): partial — file hashing streams in chunks so a whole file is never read into
memory; no analysis pipeline exists yet, so streaming analysis is untested.*

Songs may be long.

Avoid unnecessarily loading every representation into RAM simultaneously.

Consider:

```text
streaming
chunk processing
lazy loading
temporary files
memory limits
```

where appropriate.

---

# [ ] 107. Long Audio

Test:

```text
30 seconds
3 minutes
10 minutes
30 minutes
```

Do not optimize only for short laboratory samples.

---

# [ ] 108. Silence

Test:

* intro silence
* outro silence
* pauses
* instrumental sections

The system must not create arbitrary lyrics or chords during silence.

---

# [ ] 109. Instrumental Sections

*Note: `LyricSegmentKind.INSTRUMENTAL` is modelled so an engine can report it, but nothing detects it
yet.*

Lyrics may be absent.

Represent:

```text
instrumental
```

when appropriate.

Do not force empty lyrics into fake words.

---

# [ ] 110. Non-Lexical Vocals

*Note: `LyricSegmentKind.NON_LEXICAL` is modelled so an engine can report it, but nothing detects it
yet.*

Handle:

```text
oh
ah
hmm
la la
background vocals
```

appropriately.

Do not treat all vocal sounds as normal lexical words.

---

# [ ] 111. Multiple Languages

Eventually support multilingual lyrics.

At minimum test:

```text
English
Spanish
```

The architecture must not assume English phonology.

---

# [ ] 112. Musical Sections

Eventually investigate:

```text
intro
verse
pre-chorus
chorus
bridge
solo
outro
```

This may be added after the core pipeline works.

Do not block chord/lyrics analysis on automatic section detection.

---

# [ ] 113. Song Structure

If a suitable engine provides structural segmentation, preserve it as optional metadata:

```text
section
start
end
label
confidence
source
```

---

# [ ] 114. Future Features

Potential future capabilities:

```text
automatic section labels
Roman numeral analysis
Nashville numbers
scale degree analysis
lead-sheet generation
PDF lead sheet
MusicXML score
MIDI accompaniment
practice mode
loop selected section
slow down playback
pitch-preserving time stretch
metronome
karaoke mode
```

These are NOT prerequisites for the first stable version.

---

# [x] 115. Avoid Scope Explosion

The first stable target is:

```text
MP3
 ↓
Lyrics
 ↓
Chords
 ↓
Key
 ↓
Tempo
 ↓
Beats
 ↓
Alignment
 ↓
ChordPro/JSON export
```

Do not delay the first useful version by implementing every possible musical feature.

---

# [ ] 116. Definition of Done — CLI Laboratory

*Status (2026-09-23): 9 of 25 items met (repository, venv, pip, Linux, audio metadata, canonical model,
JSON export, documentation, licence audit). See the checklist below.*

The CLI laboratory is considered complete when:

* [x] repository works
* [x] `venv` installation works
* [x] pip installation works
* [x] Linux works
* [ ] Windows works
* [ ] macOS works
* [x] audio metadata works
* [ ] lyrics engine works
* [ ] chord engines can be compared
* [ ] key detection works
* [ ] BPM works
* [ ] beats work
* [ ] downbeats are evaluated
* [ ] Demucs is evaluated
* [ ] Basic Pitch is evaluated
* [x] canonical data model exists
* [ ] normalization exists
* [ ] alignment exists
* [ ] fusion exists
* [ ] benchmark exists
* [x] JSON export works
* [ ] ChordPro export works
* [x] documentation exists
* [x] license audit exists
* [ ] provenance is preserved

---

# [ ] 117. Definition of Done — GUI

*Status (2026-09-23): not started. No GUI code exists, by design (Rule 1).*

The GUI is considered ready when:

* [ ] audio opens
* [ ] analysis starts
* [ ] analysis can be cancelled
* [ ] playback works
* [ ] waveform/timeline works
* [ ] lyrics are displayed
* [ ] chords are displayed
* [ ] playback cursor is synchronized
* [ ] chords can be edited
* [ ] lyrics can be edited
* [ ] timestamps can be edited
* [ ] transpose works
* [ ] undo works
* [ ] redo works
* [ ] export works
* [ ] errors are understandable
* [ ] English terminology is stable
* [ ] translations can be loaded through Qt Linguist

---

# [x] 118. Master AI Coding-Agent Instructions

*Note: all 20 rules are currently respected. Rule 1 is the reason no GUI code exists yet.*

The coding agent must behave as a senior engineer specializing in:

```text
Python
audio DSP
music information retrieval
ASR
machine learning inference
PyQt6
cross-platform software
testing
packaging
open-source licensing
```

The agent must follow these rules.

## [x] Rule 1

Do not build the GUI first.

## [x] Rule 2

Research technologies before integrating them.

## [x] Rule 3

Do not assume a GitHub repository is production-ready.

## [x] Rule 4

Do not assume an AI model is free for commercial use.

## [x] Rule 5

Check licenses.

## [x] Rule 6

Do not invent benchmark results.

## [x] Rule 7

Preserve raw engine results.

## [x] Rule 8

Use a canonical typed internal model.

## [x] Rule 9

Keep engines behind interfaces.

## [x] Rule 10

Keep the GUI independent from specific analysis libraries.

## [x] Rule 11

Support CPU fallback wherever technically feasible.

## [x] Rule 12

Use `venv` + `pip`.

## [x] Rule 13

Keep Linux, Windows and macOS in scope.

## [x] Rule 14

English first.

## [x] Rule 15

Use Qt Linguist only after the English application stabilizes.

## [x] Rule 16

Do not introduce unnecessary dependencies.

## [x] Rule 17

Prefer mature libraries over reinventing complex algorithms.

## [x] Rule 18

Preserve uncertainty.

## [x] Rule 19

Never silently overwrite raw analysis.

## [x] Rule 20

Document important engineering decisions.

---

# [x] 119. Master Agent Prompt

*Note: standing instruction; in force for every change to this repository.*

The following prompt may be given to an autonomous coding agent:

> You are the senior software architect and implementation engineer for the `song-chord-lyrics-analyzer` project.
>
> Your task is to build a cross-platform Python application that analyzes songs and extracts synchronized lyrics, chords, tempo, beats, downbeats, key and related musical information.
>
> The target platforms are Linux, Windows and macOS.
>
> Use Python `venv` and `pip`.
>
> Use the `src/` package layout:
>
> `src/song_chord_lyrics_analyzer`
>
> The CLI executable should eventually be:
>
> `songlab`
>
> The project is English-first.
>
> Do not introduce Spanish or other translations until the English application is stable.
>
> Later internationalization must use Qt Linguist and `QTranslator`.
>
> The development strategy is:
>
> 1. repository bootstrap
> 2. dependency research
> 3. audio foundation
> 4. lyrics laboratory
> 5. chord laboratory
> 6. key/tempo/beat analysis
> 7. stem separation
> 8. audio-to-MIDI
> 9. normalization
> 10. alignment
> 11. fusion
> 12. metrics
> 13. export
> 14. real-world validation
> 15. architecture freeze
> 16. PyQt6 GUI
> 17. English GUI stabilization
> 18. Qt Linguist translations
>
> Do not skip directly to the GUI.
>
> First create a reliable CLI laboratory.
>
> Investigate the following projects and technologies:
>
> * `1ucas/chordify`
> * `yuval-kahan/youchords-local`
> * `Esysc/magic-chords-project`
> * `okamyuji/chordscope`
> * `orchidas/Chord-Recognition`
> * `OpenMOSS/MOSS-Music`
> * Chordino
> * Sonic Annotator
> * Madmom
> * PitchPerfect
> * librosa
> * Essentia
> * Faster-Whisper
> * Whisper
> * Demucs
> * Spotify Basic Pitch
> * TorchCREPE
> * music21
>
> Do not automatically depend on all of them.
>
> For each candidate determine:
>
> * technical purpose
> * quality
> * maintenance status
> * Python compatibility
> * operating-system compatibility
> * CPU/GPU requirements
> * model requirements
> * license
> * model license
> * installation complexity
> * performance
>
> Create `docs/DEPENDENCY_MATRIX.md` and `docs/LICENSE_AUDIT.md`.
>
> The project must have a canonical typed internal data model.
>
> At minimum investigate:
>
> * `AudioDocument`
> * `LyricSegment`
> * `LyricWord`
> * `ChordEvent`
> * `BeatEvent`
> * `DownbeatEvent`
> * `BarEvent`
> * `KeyEstimate`
> * `TempoEstimate`
> * `NoteEvent`
> * `Stem`
> * `AnalysisRun`
> * `AnalysisResult`
>
> The canonical model must not be Markdown or ChordPro.
>
> Markdown and ChordPro are exporters.
>
> Every analysis result must preserve provenance.
>
> Preserve:
>
> * raw engine output
> * normalized output
> * engine name
> * engine version
> * model version
> * configuration
> * preprocessing
> * timestamps
> * confidence
>
> Do not hide disagreement between engines.
>
> Build an engine abstraction so that multiple chord and lyrics engines can be compared.
>
> Build a baseline chord recognizer using:
>
> audio → CQT/chroma → chord templates → temporal smoothing
>
> and investigate an HMM/Viterbi extension.
>
> Implement experimental adapters for mature engines where practical.
>
> For lyrics, test original audio against separated vocals.
>
> For chord recognition, test:
>
> * original
> * vocals
> * bass
> * other
> * bass + other
>
> Do not assume that one preprocessing strategy is always best.
>
> Measure it.
>
> Implement benchmark metrics.
>
> Never invent benchmark results.
>
> Use explicit datasets and ground truth.
>
> Do not commit copyrighted commercial songs to the repository.
>
> Use public-domain, original or properly licensed material.
>
> Create:
>
> `songlab benchmark samples/`
>
> and generate JSON, CSV and Markdown reports.
>
> The CLI should eventually support:
>
> `songlab info song.mp3`
>
> `songlab lyrics song.mp3`
>
> `songlab chords song.mp3`
>
> `songlab analyze song.mp3`
>
> `songlab compare song.mp3`
>
> `songlab separate song.mp3`
>
> `songlab fuse song.mp3`
>
> `songlab benchmark samples/`
>
> `songlab export song.mp3 --format chordpro`
>
> and model-management commands.
>
> Implement JSON and ChordPro export before the GUI.
>
> The GUI must be written with PyQt6.
>
> The GUI must communicate with application services rather than directly calling Whisper, Demucs, Madmom, librosa, Essentia or other engines.
>
> The final GUI should provide:
>
> * audio playback
> * waveform/timeline
> * synchronized lyrics
> * synchronized chords
> * beat/downbeat information
> * key
> * tempo
> * confidence
> * engine information
> * editing
> * transpose
> * chord simplification
> * undo/redo
> * export
>
> Manual user corrections must remain separate from raw automatic analysis.
>
> Do not overwrite raw engine output.
>
> Use secure subprocess handling.
>
> Treat audio files as untrusted input.
>
> Avoid `shell=True`.
>
> Use `pathlib.Path`.
>
> Keep all important functionality cross-platform.
>
> Use GitHub Actions to test Linux, Windows and macOS.
>
> Write unit tests and integration tests continuously.
>
> Do not postpone all testing until the end.
>
> Keep the repository clean.
>
> Avoid unnecessary dependencies.
>
> Do not introduce heavyweight frameworks merely because they are popular.
>
> Prefer modular, testable components.
>
> At every phase:
>
> 1. inspect the current repository
> 2. understand the existing architecture
> 3. consult the roadmap
> 4. research uncertain dependencies
> 5. implement a small coherent change
> 6. run tests
> 7. update documentation
> 8. report what was implemented
> 9. report known limitations
> 10. propose the next concrete step
>
> Never claim that an engine works until it has actually been tested.
>
> Never claim cross-platform compatibility until the relevant platform has been tested or the limitation is explicitly documented.
>
> Never claim an algorithm is more accurate without benchmark evidence.
>
> Preserve uncertainty rather than producing false precision.
>
> Follow the roadmap as the primary project specification.

---

# [x] 120. First Tasks for the Agent

The agent should begin with these tasks only:

## [x] Task 1

Inspect the repository.

## [x] Task 2

Create or verify:

```text
pyproject.toml
src/song_chord_lyrics_analyzer/
tests/
docs/
```

## [x] Task 3

Create a minimal CLI:

```bash
songlab --help
```

## [x] Task 4

Implement:

```bash
songlab info song.mp3
```

## [x] Task 5

Create the initial canonical schemas.

## [x] Task 6

Create the engine interfaces.

## [x] Task 7

Create dependency research documentation.

## [x] Task 8

Create the first unit tests.

## [x] Task 9

Configure CI.

## [ ] Task 10

Only after those tasks succeed, begin the first audio-analysis experiments.

---

# [ ] 121. First Milestone

*Status (2026-09-23): partial — the package, CLI, typed models, audio metadata, tests, documentation and
CI exist; `songlab lyrics`, `songlab chords` and `songlab analyze` do not.*

The first meaningful milestone is:

```text
song-chord-lyrics-analyzer
        │
        ├── Python package
        ├── CLI
        ├── typed models
        ├── audio metadata
        ├── tests
        ├── documentation
        └── CI
```

The first command should eventually work:

```bash
songlab info song.mp3
```

Then:

```bash
songlab lyrics song.mp3
```

Then:

```bash
songlab chords song.mp3
```

Then:

```bash
songlab analyze song.mp3
```

Only when these foundations are reliable should PyQt6 become the main development focus.

---

# [ ] 122. Final Architecture Target

The intended long-term architecture is:

```text
                         ┌───────────────────┐
                         │     PyQt6 GUI     │
                         └─────────┬─────────┘
                                   │
                         ┌─────────▼─────────┐
                         │ Application Layer │
                         └─────────┬─────────┘
                                   │
                         ┌─────────▼─────────┐
                         │ Analysis Pipeline │
                         └─────────┬─────────┘
                                   │
             ┌─────────────────────┼─────────────────────┐
             │                     │                     │
      ┌──────▼──────┐      ┌──────▼──────┐      ┌──────▼──────┐
      │ Lyrics       │      │ Chord       │      │ Music       │
      │ Engines      │      │ Engines     │      │ Engines     │
      └──────┬──────┘      └──────┬──────┘      └──────┬──────┘
             │                     │                     │
             └─────────────────────┼─────────────────────┘
                                   │
                         ┌─────────▼─────────┐
                         │ Canonical Models │
                         └─────────┬─────────┘
                                   │
                         ┌─────────▼─────────┐
                         │  Normalization   │
                         └─────────┬─────────┘
                                   │
                         ┌─────────▼─────────┐
                         │    Alignment     │
                         └─────────┬─────────┘
                                   │
                         ┌─────────▼─────────┐
                         │      Fusion      │
                         └─────────┬─────────┘
                                   │
                         ┌─────────▼─────────┐
                         │ Metrics/Confidence│
                         └─────────┬─────────┘
                                   │
                   ┌───────────────┼───────────────┐
                   │               │               │
             ┌─────▼─────┐   ┌────▼────┐   ┌──────▼──────┐
             │  ChordPro │   │  JSON   │   │ MIDI/XML/etc│
             └───────────┘   └─────────┘   └─────────────┘
```

The central architectural principle is:

```text
ENGINE OUTPUT
      ↓
CANONICAL DATA
      ↓
ALIGNMENT
      ↓
FUSION
      ↓
USER EDITING
      ↓
EXPORT
```

not:

```text
AI MODEL → GUI
```

---

# [x] 123. Project Philosophy

The project should ultimately behave as a serious local music-analysis laboratory that happens to have a friendly GUI.

The GUI is not the foundation.

The analysis engine is the foundation.

The analysis engine is not tied to one AI model.

The canonical document is not tied to Markdown.

The final result should remain inspectable, reproducible, editable and exportable.

The application should tell the user not only:

```text
"C"
```

but, when appropriate:

```text
Chord: C
Confidence: 0.84
Time: 01:24.320–01:26.810

Evidence:
- Chord engine A: C
- Chord engine B: C
- Chord engine C: C/E
- Bass evidence: E
```

This makes the project useful not only as an end-user application but also as a research and experimentation platform.

---

# [ ] 124. Ultimate Goal

The finished application should allow a user to take:

```text
song.mp3
```

and obtain something conceptually equivalent to:

```text
Title: Example Song
Key: C major
Tempo: 92 BPM

[C]Hello [G]world
[Am]This is [F]my song

[C]Another [G]line
[Am]with the [F]chords
```

with synchronized playback, editable lyrics, editable chords, confidence information, provenance, transposition and export.

The system must achieve this through a scientifically testable and modular pipeline rather than relying on one opaque model.

---

# [ ] 125. Completion Criterion

*Status (2026-09-23): 1 of the 20 criteria is met (English first). Section 116 is the nearer, CLI-level
target.*

The project is considered mature when a user can:

1. [ ] Install it on Linux, Windows or macOS.
2. [ ] Open an MP3.
3. [ ] Analyze it locally.
4. [ ] Obtain lyrics.
5. [ ] Obtain synchronized chords.
6. [ ] Obtain key and tempo.
7. [ ] See beats/downbeats.
8. [ ] Play the song while the analysis follows the music.
9. [ ] Correct errors.
10. [ ] Transpose chords.
11. [ ] Simplify chords.
12. [ ] Export the result.
13. [ ] Re-run the same analysis reproducibly.
14. [ ] Inspect which engines produced the results.
15. [ ] Understand where the system is uncertain.
16. [ ] Work offline after required models have been downloaded.
17. [ ] Switch between supported analysis engines.
18. [ ] Add future engines without redesigning the GUI.
19. [x] Use English initially.
20. [ ] Later select Spanish or another language through Qt Linguist.

That is the target architecture for `song-chord-lyrics-analyzer`.
