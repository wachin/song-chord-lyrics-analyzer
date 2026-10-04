# Benchmark

**Status (2026-10-03): `songlab benchmark` is implemented for *stored results*.** It reads a
directory of case JSON files (a reference/hypothesis pair per song), scores them with the
section 44 metric family and writes `benchmark/{benchmark.json,benchmark.csv,benchmark.md}`.
No engine runs yet, so a metric is reported only when both sides of a case provide what it
needs — nothing is invented. Running an engine on audio and filling `processing_time`/`memory`
from the run is the remaining piece. First *investigations* by temporary harnesses are recorded in
`docs/ENGINE_COMPARISON.md`: lyrics ASR on vocadito, on synthetic mixes and on real commercial
mixes, plus a chord-recognition baseline scored against a user chord chart on one song and its
Demucs stems. They are explicitly not `songlab benchmark` runs.

## Command

```bash
songlab benchmark cases/ --output benchmark/
```

Reads every `*.json` case in `cases/`, scores it and writes the three reports. `--json`
prints the report instead of writing the files.

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
| `lyrics_text` | WER, CER |
| `lyrics_words` | word timestamp error |
| `chords` | segment overlap, change detection, timing error |
| `chord_labels` | exact/root/quality/MIREX F1, multiset/palette F1 |
| `key` | relation, weighted score, exact accuracy, relative-key error |
| `tempo_bpm` | absolute, half-time and double-time BPM error |

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
mean of `key.relative` is the relative-key error).

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
