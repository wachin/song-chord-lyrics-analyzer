# Benchmark

**Status: planned for phase 11 — this command has not been implemented and no benchmark has been run
through it yet.** A first *investigation* by a temporary harness (lyrics ASR on vocadito) is recorded in
`docs/ENGINE_COMPARISON.md`; it is explicitly not a `songlab benchmark` run.

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
overlap, timing error, chord-change detection accuracy.

Lyric metrics: WER, CER, word timestamp error.

Key metrics: exact key accuracy, relative-key error.

Tempo metrics: absolute BPM error, half-tempo error, double-tempo error.

## Performance metrics (roadmap section 45)

Processing time, seconds of audio per second of computation, peak RAM, VRAM,
model size, startup time, disk usage, and CPU versus GPU where applicable.

## Rules

* Never invent results. Every number must come from a stored report.
* Ground truth is explicit, licensed and versioned (see `docs/DATASET.md`).
* Comparisons must state the dataset, the sample count and the hardware.
* Tempo ambiguity (half-time/double-time) is reported as such instead of being
  silently normalised.
