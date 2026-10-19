# Engine comparison

This file is the measurement record. Every number in it was produced by a run whose
environment and date are stated next to it, and every accuracy claim elsewhere in the
repository points back here. Sections 4 and 5 cover lyrics and the chunked-analysis
experiment. Sections 1–3 — the chord measurement — were lost in an earlier edit and
were **rebuilt on 2026-10-19** together with the harness that produces them
(`scripts/chord_benchmark.py`) and the committed corpus definition
(`tests/fixtures/guitarset_comp_manifest.json`).

## 1. Chord engines — method (2026-10-19)

**Corpus.** GuitarSet v1.1.0 (Zenodo <https://doi.org/10.5281/zenodo.3371780>,
CC BY 4.0): the 180 comping takes, `audio_mono-mic`, 461.3 MiB / 5,484.2 s of audio.
The manifest pins every take by the SHA-256 of its audio file *and* of its JAMS, and
the harness refuses a corpus whose bytes differ, so a run cannot quietly describe a
different corpus. Audio stays in the gitignored cache (`docs/DATASET.md`); only the
manifest (62 KiB: take names, file names, durations and digests) is committed.

**Reference.** One annotation view per run, never mixed in one number:
`--reference instructed` reads JAMS `chord` index 0 (the instructed lead sheet),
`--reference performed` reads index 1 (the performed voicings). Harte spellings are
converted by `evaluation.chords.harte_to_label`; observations with a non-positive
duration occupy no time and are dropped.

**Hypothesis.** The registered engine through its public call,
`ChromaBaselineEngine.analyze()` (`chroma-baseline` 0.1.0), with default options:
mono 22.05 kHz, CQT chroma, hop 2048 (92.879 ms), cosine similarity against the 24
major/minor triad templates plus an `N` state, Viterbi with a flat change penalty of
0.80. Hypothesis segments come from `metrics.adapters.chord_segments()`, which
completes a missing end from the next event or the measured duration and raises rather
than inventing one.

**Metrics** — the implemented definitions, not parallel ones (audit §11):

* `evaluation/chords.py:duration_csr` — duration-weighted CSR, raw and triad-reduced
  (the triad view reduces *both* sides);
* `metrics/segmentation.py:segment_overlap` — MIREX mean segmentation;
* `metrics/segmentation.py:chord_change_detection` — change-point P/R/F1, 0.5 s
  tolerance;
* `metrics/segmentation.py:timing_error` — median boundary distance in both
  directions;
* chord counts, engine wall time, real-time factor and peak RSS (the process
  high-water mark from `performance.py`).

**Protocol.** Same audio, same reference, same hop, one annotation view per run; both
decoders in separate processes; the whole vector is reported, not one number; no take
is excluded, and a hypothesis label with no counterpart still occupies time and is
scored as a miss (`N` included). Each run keeps `per_take.jsonl` (all hypothesis rows,
so a later default change can still be compared against these segmentations),
`aggregate.json` and `aggregate.md` under the gitignored `.cache/`.

**Reproducing it.**

```bash
python scripts/chord_benchmark.py --limit 180 --out .cache/chords/benchmark-viterbi-180
python scripts/chord_benchmark.py --limit 180 --decoder majority --out .cache/chords/benchmark-majority-180
python scripts/chord_benchmark.py --reference performed --out .cache/chords/benchmark-viterbi-180-performed
```

`scripts/chord_benchmark.py --write-manifest PATH` regenerates the pinned manifest from
a downloaded corpus.

**Environment (all three runs).** Linux x86_64, kernel 7.0.10-1-liquorix,
CPython 3.13.5, numpy 2.5.3, librosa 1.0.0, soundfile 0.14.0, `chroma-baseline` 0.1.0,
CPU only, commit `53ebb60`, **2026-10-19 (UTC)**.

## 2. Chord engines — measurement (2026-10-19)

Means over the 180 comping takes; per-take minima and maxima are in each run's
`aggregate.json`.

| Reference | Decoder | CSR | CSR (triad) | Segment overlap | Change F1 | Boundary err. ref→hyp | Boundary err. hyp→ref | Hyp chords | Ref chords |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| instructed | Viterbi, penalty 0.80 | **0.6029** | **0.6091** | **0.8298** | **0.8270** | 0.178 s | **0.187 s** | 12.89 | 12.00 |
| instructed | Majority smoother | 0.5300 | 0.5388 | 0.5428 | 0.4033 | **0.056 s** | 0.486 s | 56.86 | 12.00 |
| performed | Viterbi, penalty 0.80 | 0.5186 | 0.5954 | 0.8298 | 0.8270 | 0.178 s | 0.187 s | 12.89 | 12.00 |

Change precision / recall: Viterbi 0.8197 / 0.8585; majority 0.2694 / 0.9923. Summed
engine wall time over the takes was 73.7 s (Viterbi) and 66.6 s (majority) for 5,484.2 s
of audio; peak RSS 303 MiB in each process (the harness's own overhead is not in
either figure). The performed run has identical boundary metrics to the instructed
one because GuitarSet gives both annotation views the same change points — only the
labels differ, which is why the raw CSR drops while the triad view stays near the
instructed score.

**What the numbers say.**

* Viterbi wins on CSR (both views), segment overlap and change F1, and on the
  hypothesis→reference boundary error. The direction of the 2026-10-05 comparison is
  therefore reproduced by an independent run.
* The majority smoother's better reference→hypothesis boundary error is an artefact of
  over-segmentation: 56.86 chords per take against a 12.00-chord reference puts a
  boundary almost everywhere, so every reference boundary has one nearby. Its change
  precision (0.27) and segment overlap (0.54) price that in. This is the case the
  audit's "report the whole vector" rule was written for: a single timing figure would
  have made the worse decoder look better.
* The Viterbi hypothesis is close to the reference in size (12.89 vs 12.00 chords per
  take), which is the behaviour expected from a triad engine on clean solo-guitar
  audio, and it is the main reason CSR is as high as it is.

**Traceability note — the previously cited 0.4260 does not reproduce.**

The repository cited CSR 0.4260 on 180 GuitarSet takes (recorded 2026-10-05, described
as *Viterbi at penalty 0.80*). Running exactly that configuration through the
registered engine on the pinned corpus gives **0.6029**, and the difference is not the
metric: the scoring semantics are pinned by `tests/fixtures/csr_oracle.json`, and
re-scoring a stored hypothesis from the gitignored cache reproduced the old harness's
per-take values exactly (0.6709 instructed, 0.2621 performed for
`00_BN1-129-Eb_comp`). The difference is the hypothesis. The surviving 2026-09-29 sweep
(`.cache/chords/guitarset_all.jsonl`, still on disk) averages 0.4569 with 10.62 chords
per take, while the 2026-10-05 comparison records 17.06 (Viterbi) and 67.65 (majority)
chords per take — three different segmentations, only one of which (12.89) is produced
by the code in `engines/chroma_baseline.py`. The 0.4260 is therefore kept as a
historical measurement of a front end that is no longer in the tree, and **retired as
the registered engine's accuracy figure**. This is exactly the traceability gap the
2026-10-18 audit flagged; the harness and the manifest are what close it.

## 3. Chord engines — verdict

**The registered engine's measured accuracy is CSR 0.6029 (0.6091 triad-reduced) on
180 GuitarSet comping takes against the instructed lead sheet, 2026-10-19.** The
complete vector is in §2; quote the date and the reference view with the number.

What this result does **not** establish:

* accuracy on a mixed commercial recording — GuitarSet is one clean acoustic guitar
  with a permissive licence, and the user's ~75 % manual observation is still not a
  measurement (audit §9);
* robustness of the front end to reverb, tuning drift, compression or vocals — none of
  those variables is in this corpus (audit P3 is the proposal that measures them);
* per-chord confidence: `ChordEvent.confidence` is still `unknown` (audit P2).

**Consequence for the plan.** Audit P1 is satisfied: there is now a committed harness
(`scripts/chord_benchmark.py`), a fixed reference set
(`tests/fixtures/guitarset_comp_manifest.json`), a scoring path pinned by tests, and an
offline generated-fixture run in `tests/unit/test_chord_benchmark_harness.py`. Every
later chord proposal (P2–P8) reports a before/after vector on this audio instead of an
argument.

---

## 4. Lyrics engines — verdict

**Verdict: `onnx-asr` + Parakeet TDT 0.6B v3 (int8 ONNX) is the first lyrics
engine and was adopted in 2026-10-08 (roadmap Phase E).**

The representative implementation is ``src/song_chord_lyrics_analyzer/engines
/lyrics_parakeet.py`` behind the optional ``lyrics`` extra: it is the only
candidate that merged **accuracy on English (0.08 WER), CPU speed (real-time
factor 0.20), a verified licence and a decidable install**. The measured
quantities live in `docs/ENGINE_COMPARISON.md`s section 25/26 tables; this
section records only the decision and the rules the implementation follows.

* **Speed — the load-bearing requirement.** The bundled model cannot take a
  whole song (``recognize()`` on a 272 s file returned 8 garbled words) and the
  upstream speech VAD returns *nothing* on singing. Every implementation here
  therefore chunks long audio; the section 45 performance numbers belong to the
  engine, not to this table.
* **Weights never leave the cache.** The model is fetched by ``onnx-asr``
  itself, into the Hugging Face cache, and is never stored in this repository,
  never committed and never advertised as a dependency that can be reproduced
  offline.
* **No fake confidence.** The model reports no calibrated per-word confidence;
  ``LyricWord`` keeps ``ConfidenceScore.unknown``. Only a measured value belongs
  in the document, and a WER number only appears with its measurement artifact
  (file, reference, harness).
* **Word timestamps come from the model's own tokens.** A word's end is the next
  word's start; the last word of a window keeps ``end=None`` because the audio
  carries on past it and no boundary was reported.

### Remaining open questions (phase 4)

* **A second candidate is still untested end to end**: faster-whisper
  ``small`` (WER 0.3799, RTF 0.95) beats Parakeet on Tagalog and Spanish —
  whether that transfers to English is not established and would need a
  phase-3 measurement.
* **Chunk boundaries**: a word clipped at a window edge is attributed to the
  earlier window and can be lost; the `--overlap-seconds` option re-hears the
  seam but does not currently repair a clipped word. Whether overlap should be
  turned on by default is the only remaining implementation question.
* **Language detection** is not reported by this backend; a user-level tag can
  be recorded with the `--language` flag.

---

## 5. Chunked chord analysis — measurement (roadmap Phase K, 2026-10-14)

**Why measure at all:** windowing the chord layer (`analysis/chunking.py`,
`songlab analyze --chord-chunk-seconds`) changes what the engine is shown, so
the whole-file pass stays the default and the flag is opt-in until a measurement
says otherwise. These numbers are that measurement.

**Environment:** the machine this repository is developed on, Linux x86_64,
CPython 3.13.5, `chroma-baseline` 0.1.0, numpy 2.x/librosa from the `dsp`
extra, CPU only. Each row's wall time and `ru_maxrss` come from a **separate
process** measuring only the chord layer, so the two modes do not share a
high-water mark.

| Fixture | Mode | Chord call wall | Real-time factor | Peak RSS |
| --- | --- | --- | --- | --- |
| 180 s generated tone | whole file | 3.919 s | 45.93 | 448.2 MB |
| 180 s generated tone | 60 s windows (3) | 3.880 s | 46.40 | 309.3 MB |
| 600 s generated tone | whole file | 8.409 s | 71.35 | 996.2 MB |
| 600 s generated tone | 60 s windows (10) | 8.027 s | 74.75 | 309.3 MB |

**What the numbers say.** Window length, not song length, fixes the working
set: the 10-window run peaks at the same 309 MB as the 3-window one, while the
whole-file pass grows with the decode (448 MB at 3 minutes, 996 MB at 10
minutes — a 3.2x reduction at 10 minutes). Runtime is unchanged within noise,
so the memory is bought for free on these fixtures rather than traded against
speed.

**What it costs in output.** On a 480 s tonal fixture (C-Am-F-G, 8 s each,
generated by `tests/fixtures/audio.py`) a whole-file pass and a 60 s windowed
pass produced **the same 60 chords in the same order with the same labels**, and
one boundary of sixty moved by 94 ms — at a 60 s seam, because a change inside a
window's first frame is attributed to the window's own start. Both runs finished
`succeeded`; the windowed run records `chords_chunk_seconds: 60` in provenance
and `60 chords, 8 windows` in its step line. Timing for that pair was measured
in one process (windowed second, warm page cache), so its 8.8 s vs 5.7 s is
reported as *not slower*, not as a speed-up.

**Open question.** Whether a chord-heavy mix (rather than a synthetic triad
progression) shifts more than one boundary per seam is not established here:
the benchmark corpus in `benchmark/` is the place for that, and no accuracy
claim should be made from these three fixtures.
