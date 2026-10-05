# Benchmark

**Status (2026-10-04): `songlab benchmark` scores stored results and can run a
registered engine to produce them.** It reads a directory of case JSON files (a
reference/hypothesis pair per song), scores them with the section 44 metric family and
writes `benchmark/{benchmark.json,benchmark.csv,benchmark.md}`. With `--engine NAME`,
every case that declares an `audio` file is (re)run through that engine first: the
engine fills the hypothesis and its section 45 performance report fills duration,
processing time and peak memory — numbers measured on the machine doing the run,
never invented. Cases without `audio`, or runs without `--engine`, are scored exactly
as stored. The first engine behind the flag is `chroma-baseline` (see
`docs/ARCHITECTURE.md` §5); earlier *investigations* by temporary harnesses remain
recorded in `docs/ENGINE_COMPARISON.md` and are explicitly not `songlab benchmark`
runs.

## Command

```bash
songlab benchmark cases/ --output benchmark/
songlab benchmark cases/ --output benchmark/ --engine chroma-baseline
```

Reads every `*.json` case in `cases/`, scores it and writes the three reports. With
`--engine`, each case that declares `audio` is first run through that registered chord
engine (unknown names exit 2 listing the registered ones; an engine whose optional
dependencies are missing exits 3 before anything runs). `--json` prints the report
instead of writing the files (and prints nothing else, so the output stays valid JSON).

## Case format

One JSON object per song, pairing explicit ground truth with a hypothesis. Every metric
family is optional and independent; a family is scored only when both sides provide it.

```json
{
  "song": "vocadito_2",
  "engine": "faster-whisper-small",
  "engine_version": "1.2.1",
  "model": "Systran/faster-whisper-small",
  "duration_seconds": 35.208,
  "processing_time_seconds": 18.84,
  "peak_memory_bytes": 1385635840,
  "reference": {
    "lyrics_text": "cada vez que voy a arar",
    "lyrics_words": [{"text": "cada", "start": 0.0}],
    "chords": [{"start": 0.0, "end": 4.0, "label": "C"}],
    "chord_labels": ["C", "G"],
    "key": "C major",
    "tempo_bpm": 120.0
  },
  "hypothesis": { "lyrics_text": "cada ves que voy a arar", "key": "A minor" }
}
```

| Field | Metric family |
| --- | --- |
| `audio` (top level) | enables `--engine`: the recording the hypothesis is (re)produced from, relative to the case file |
| `lyrics_text` | WER, CER |
| `lyrics_words` | word timestamp error |
| `chords` | segment overlap, change detection, timing error |
| `chord_labels` | exact/root/quality/MIREX F1, multiset/palette F1 |
| `key` | relation, weighted score, exact accuracy, relative-key error |
| `tempo_bpm` | absolute, half-time and double-time BPM error |

Labels are canonical (the form `song_chord_lyrics_analyzer.evaluation.harte_to_label`
renders: `D#`, `A#m`, `N`). Convert Harte references such as `D#:maj` or `Bb:min` at
load time — the committed oracles and the harness loaders do exactly that — because
the exact view compares labels byte for byte.

## Reports

```text
benchmark/
├── benchmark.json
├── benchmark.csv
└── benchmark.md
```

Each case row carries engine, engine version, model, song, duration, processing time, peak
memory and the metrics that the case can actually compute; the summary averages every
numeric metric per engine (so the mean of `key.exact` is the exact key accuracy and the
mean of `key.relative` is the relative-key error). A hypothesis that declares an empty
chord timeline is a measured zero, not a missing family: an engine that found nothing
scores 0.0.

## Running an engine (sections 45 + 46)

With `--engine NAME`, the command runs the engine on each case's `audio` file before
scoring. The runner dispatches on the engine's kind and fills that family's hypothesis:
chords (`hypothesis.chords` / `chord_labels`), key (`key`, or `"unknown"` so a miss is
still scored), tempo (`tempo_bpm`) and lyrics (text plus timed words). An engine kind no
section 44 metric family can score (beats, stems, notes) is refused before any run. It
goes through `benchmark/runner.py`, which:

* fills the engine's own family fields, keeping stored fields the engine knows
  nothing about (such as lyrics when a chord engine runs);
* fills `duration_seconds`, `processing_time_seconds` and `peak_memory_bytes` from
  the engine's section 45 `PerformanceReport`, measured on this machine at run time;
* leaves the reference side and cases without `audio` untouched;
* reports one run line per case (chords, seconds, real-time factor) before the
  summary.

Example run: `chroma-baseline` on one 22.3 s GuitarSet comping excerpt reported 8
chords in 2.261 s (real-time factor 9.87) on this Linux x86_64 CPU — one smoke run of
a deliberately simple baseline, not an accuracy claim. (The engine's default Viterbi
decoder replaced the earlier majority smoother, which reported 55 chords on the same
excerpt; see `docs/ENGINE_COMPARISON.md`.) No case or number from it is committed;
reproduce it by pointing `--engine` at a case directory with audio.

## Metrics (roadmap section 44)

Chord metrics: exact chord accuracy, root accuracy, quality accuracy, segment
overlap, timing error, chord-change detection accuracy. (A first timing-free pass — exact /
root / quality sequence F1, chord multiset and palette F1, and key, but no frame metrics — is
recorded in `docs/ENGINE_COMPARISON.md`, because its reference chart has no timestamps.)
All six chord metrics now exist as dependency-free library code in
`song_chord_lyrics_analyzer.metrics` (roadmap §44), pinned to recorded oracles, and
`songlab benchmark` wires them into the per-engine report — directly for stored cases,
and from a measured engine run with `--engine`.Lyric metrics: WER, CER, word timestamp error. All three exist as dependency-free
library code (`metrics/lyrics.py`, roadmap §44), pinned to a `jiwer` oracle; this
command scores them for cases that provide the text on both sides (no lyrics engine
runs yet).Key metrics: exact key accuracy, relative-key error. Both exist as dependency-free
library code in `song_chord_lyrics_analyzer.metrics` (roadmap §44), pinned to a
`mir_eval` oracle; this command scores them for cases that provide the key on both
sides (no key engine runs yet).

Tempo metrics: absolute BPM error, half-tempo error, double-tempo error. All three
exist as dependency-free library code (`metrics/tempo.py`), returned together so
metrical ambiguity is reported rather than normalised away.

## Performance metrics (roadmap section 45)

Processing time, seconds of audio per second of computation, peak RAM, VRAM,
model size, startup time, disk usage, and CPU versus GPU where applicable.

A case that records both `duration_seconds` and `processing_time_seconds` is
scored with `performance.real_time_factor` — audio seconds divided by
processing seconds, so a value above 1.0 means the run was faster than real
time — and the summary averages it per engine like every other numeric metric.
The measurement behind those two fields lives in
`song_chord_lyrics_analyzer.performance` (roadmap section 45): a
`PerformanceProbe` brackets the run and returns a `PerformanceReport` whose
figures are read at run time on the machine that produced them. A figure the
platform cannot report stays `null` — VRAM on a CPU run, peak RSS on Windows —
and is never estimated.

## Rules

* Never invent results. Every number must come from a stored report.
* Ground truth is explicit, licensed and versioned (see `docs/DATASET.md`).
* Comparisons must state the dataset, the sample count and the hardware.
* Tempo ambiguity (half-time/double-time) is reported as such instead of being
  silently normalised.
