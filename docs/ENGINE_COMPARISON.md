# Engine Comparison

**Status: not written yet — nothing has been benchmarked.**

This document will hold measured comparisons only. Writing it before the engines
exist would mean inventing numbers, which roadmap rule 6 forbids.

## What it will contain, per engine and per preprocessing strategy

| Field | Example |
| --- | --- |
| Engine and version | `chroma-baseline 0.1.0`, `chordino 1.1`, `madmom 0.17` |
| Preprocessing | `original`, `other`, `bass+other`, `vocals` |
| Dataset and size | `samples/` (n songs, listed in `docs/DATASET.md`) |
| Chord root accuracy | measured value |
| Chord quality accuracy | measured value |
| Exact chord accuracy | measured value |
| Segment overlap | measured value |
| Chord-change timing error | measured value |
| Lyric WER / CER | measured value |
| Key accuracy (exact / relative) | measured value |
| Tempo error (absolute / half / double) | measured value |
| Processing time and audio-seconds per second | measured value |
| Peak RAM | measured value |
| Hardware | CPU model, GPU model, RAM |

## Method rules

1. Same audio, same excerpt lengths, same ground truth for every engine.
2. Ground truth is explicit and stored with provenance (`docs/DATASET.md`).
3. Results are produced by `songlab benchmark`, which writes `benchmark/`
   reports; numbers are copied from those reports, never from memory.
4. Disagreement between engines is reported, not hidden — agreement rates are a
   result in their own right.
5. A missing or unavailable engine is recorded as unavailable, not as a failure.

## Until then

The honest current statement is: **no engine has been integrated, so no
comparison exists.** Chord *normalization* (parsing, rendering, transposition)
is implemented and unit-tested, which is not the same thing as chord
*recognition*.
