# Benchmark

**Status: planned for phase 11 — this command has not been implemented and no benchmark has been run
through it yet.** First *investigations* by temporary harnesses are recorded in
`docs/ENGINE_COMPARISON.md`: lyrics ASR on vocadito, on synthetic mixes and on real commercial
mixes, plus a chord-recognition baseline scored against a user chord chart on one song and its
Demucs stems. They are explicitly not `songlab benchmark` runs.

## Planned command

```bash
songlab benchmark samples/
```

## Planned reports

```text
benchmark/
├── benchmark.json
├── benchmark.csv
└── benchmark.md
```

Each row is expected to carry: engine, engine version, model, song, duration,
preprocessing strategy, processing time, peak memory, and the metrics that the
run can actually compute.

## Metrics (roadmap section 44)

Chord metrics: exact chord accuracy, root accuracy, quality accuracy, segment
overlap, timing error, chord-change detection accuracy. (A first timing-free pass — exact /
root / quality sequence F1, chord multiset and palette F1, and key, but no frame metrics — is
recorded in `docs/ENGINE_COMPARISON.md`, because its reference chart has no timestamps.)
All six chord metrics now exist as dependency-free library code in
`song_chord_lyrics_analyzer.metrics` (roadmap §44), pinned to recorded oracles; this
command still has to wire them into a per-engine report.

Lyric metrics: WER, CER, word timestamp error. All three now exist as
dependency-free library code (`metrics/lyrics.py`, roadmap §44), pinned to a `jiwer`
oracle; this command still has to wire them into a report.

Key metrics: exact key accuracy, relative-key error. Both now exist as
dependency-free library code in `song_chord_lyrics_analyzer.metrics` (roadmap §44),
pinned to a `mir_eval` oracle; this command still has to wire them into a report.

Tempo metrics: absolute BPM error, half-tempo error, double-tempo error. All three
exist as dependency-free library code (`metrics/tempo.py`), returned together so
metrical ambiguity is reported rather than normalised away.

## Performance metrics (roadmap section 45)

Processing time, seconds of audio per second of computation, peak RAM, VRAM,
model size, startup time, disk usage, and CPU versus GPU where applicable.

## Rules

* Never invent results. Every number must come from a stored report.
* Ground truth is explicit, licensed and versioned (see `docs/DATASET.md`).
* Comparisons must state the dataset, the sample count and the hardware.
* Tempo ambiguity (half-time/double-time) is reported as such instead of being
  silently normalised.
