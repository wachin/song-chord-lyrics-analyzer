# Engine comparison

This file is the measurement record. Every number in it was produced by a run whose
environment and date are stated next to it, and every accuracy claim elsewhere in the
repository points back here. Sections 4 and 5 cover lyrics and the chunked-analysis
experiment, §6 covers per-chord confidence and §7 the front-end sweep that moved the
default tuning handling. Sections 1–3 — the chord measurement — were lost in an
earlier edit and were **rebuilt on 2026-10-19** together with the harness that produces
them (`scripts/chord_benchmark.py`) and the committed corpus definition
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

The front end has one knob per measured variable (audit P3) and every run records the
ones it used: `tuning` (`zero` since 2026-10-20, `auto` or `estimate`), `feature`
(`cqt`/`cens`), `harmonic` (HPSS before chroma) and `energy_gate_db`. §7 is the
one-variable-at-a-time comparison that moved the tuning default, and it carries the
table for both settings.

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

# §7: one front-end variable at a time, then the adopted default
python scripts/chord_benchmark.py --option tuning=auto --out .cache/chords/p3-baseline
python scripts/chord_benchmark.py --option tuning=zero --out .cache/chords/p3-tuning-zero
python scripts/chord_benchmark.py --option harmonic=true --out .cache/chords/p3-harmonic
python scripts/chord_benchmark.py --option feature=cens --out .cache/chords/p3-cens
python scripts/chord_benchmark.py --option energy_gate_db=-40 --out .cache/chords/p3-energy-gate
python scripts/chord_benchmark.py --fit-confidence --out .cache/chords/benchmark-zero-tuning
```

`scripts/chord_benchmark.py --write-manifest PATH` regenerates the pinned manifest from
a downloaded corpus.

**Environment (the three runs above).** Linux x86_64, kernel 7.0.10-1-liquorix,
CPython 3.13.5, numpy 2.5.3, librosa 1.0.0, soundfile 0.14.0, `chroma-baseline` 0.1.0,
CPU only, commit `53ebb60`, **2026-10-19 (UTC)**. The §7 sweep was run on the same
machine on **2026-10-20** at commit `f72c8a9` and at the commit that carries the
front-end options; its own environment line is inside each run's `aggregate.md`.

## 2. Chord engines — measurement (2026-10-19)

Means over the 180 comping takes; per-take minima and maxima are in each run's
`aggregate.json`. These runs were made with the then-default front end
(`tuning=auto`, librosa's internal estimate); §7 moved the default to `tuning=zero`
and both tables are kept, because a default change is only believable if the
measurement behind it is reproducible.

| Reference | Decoder | CSR | CSR (triad) | Segment overlap | Change F1 | Boundary err. ref→hyp | Boundary err. hyp→ref | Hyp chords | Ref chords |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| instructed | Viterbi, penalty 0.80 | 0.6029 | 0.6091 | 0.8298 | 0.8270 | 0.178 s | 0.187 s | 12.89 | 12.00 |
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

**The registered engine's measured accuracy is CSR 0.6121 (0.6183 triad-reduced) on
180 GuitarSet comping takes against the instructed lead sheet, 2026-10-20** —
the default front end after the §7 sweep. The same engine measured 0.6029 / 0.6091
on 2026-10-19 with the previous default (`tuning=auto`); the difference is the
§7 measurement, not a different metric. The complete vector is in §7 and §2;
quote the date and the reference view with the number.

What this result does **not** establish:

* accuracy on a mixed commercial recording — GuitarSet is one clean acoustic guitar
  with a permissive licence, and the user's ~75 % manual observation is still not a
  measurement (audit §9);
* robustness to reverb, compression or vocals — none of those variables is in this
  corpus (audit P3's remaining proposals are what would measure them; the §7 sweep
  covers tuning, HPSS, CENS and an energy gate);
* that every chord comes with a trustworthy number: each event does carry a
  confidence (§6), but it is a probability *on GuitarSet*, not a guarantee
  elsewhere, and a `G` over `G7` still counts as a miss in the agreement it predicts.

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

---

## 6. Per-chord confidence — measurement (roadmap Phase I P2, 2026-10-20)

**What is reported.** `ChordEvent.confidence` is no longer `unknown`. For every
event the engine averages, over the frames the event covers, the **score margin**
of the label it emitted: that label's cosine similarity minus the best similarity
any other state reaches on the same frame, `N` included
(`engines/chroma_baseline.py:segment_margins`). A frame the Viterbi decoder kept
on its label against the frame's own preference contributes a *negative* margin,
so a smoothed boundary is visible in the number instead of hidden by it. The raw
margin is kept in `ChordEvent.metadata["score_margin"]`, so the derived number
can always be audited against its evidence.

**How a margin becomes a probability.** A logistic,
`p = sigmoid(23.4861 * margin + 0.1973)` (`margin_confidence`), fitted by
duration-weighted IRLS on the events of the **90 even-indexed takes** of the
committed manifest and measured on the **90 odd-indexed takes**, which never
influenced the constants. Agreement is the rule `duration_csr` applies: exact
label equality over the overlapping time, `N` only matching `N`.

**Reproducing it.**

```bash
python scripts/chord_benchmark.py --fit-confidence --out .cache/chords/benchmark-zero-tuning
```

**Fit and held-out result** (from `confidence_fit.json`; the same 90/90 split,
run over the §7 default front end):

| Split | Takes | Events | Duration | Accuracy | Brier | ECE |
| --- | --- | --- | --- | --- | --- | --- |
| fitted (even takes) | 90 | 1,163 | 2,738.7 s | 0.5736 | 0.1579 | 0.0227 |
| held out (odd takes) | 90 | 1,160 | 2,745.5 s | 0.5836 | 0.1420 | 0.0161 |

The fit converged in 6 Newton steps to slope 23.4861 / intercept 0.1973; the
engine carries exactly those. **The constants follow the front end:** the
§7 sweep moved the tuning default from `auto` to `zero`, which changed the
chroma and therefore the margins, so the logistic was refitted on the same
corpus. The pre-sweep fit (`tuning=auto`) was slope 24.2814 / intercept 0.1552
with held-out Brier 0.1436 / ECE 0.0206 — kept here so a reader can see the
two numbers describe two different front ends, not a re-tune of the same one.

**Calibration of the whole run** (all 180 takes, 2,323 events, 5,484.2 s; every
event reported a confidence, so no duration is unknown):

| Reported band | Events | Duration | Accuracy | Mean confidence |
| --- | --- | --- | --- | --- |
| very low (below 0.2) | 134 | 385.0 s | 0.100 | 0.154 |
| low (0.2–0.4) | 467 | 1,123.9 s | 0.340 | 0.310 |
| medium (0.4–0.6) | 674 | 1,423.8 s | 0.500 | 0.505 |
| high (0.6–0.8) | 596 | 1,362.9 s | 0.736 | 0.698 |
| very high (0.8–1.0) | 452 | 1,188.7 s | 0.873 | 0.885 |

Pooled accuracy 0.5786, Brier 0.1500, expected calibration error 0.0234. A band's
accuracy and its mean confidence track within about 0.04 everywhere, which is what
"calibrated" means here.

**Risk–coverage.** The useful question is not only "is the number calibrated?" but
"if the user ignores low-confidence chords, how much is left and how good is it?":

| Confidence at least | Coverage | Accuracy |
| --- | --- | --- |
| 0.50 | 0.608 | 0.734 |
| 0.60 | 0.465 | 0.800 |
| 0.70 | 0.339 | 0.843 |
| 0.80 | 0.217 | 0.873 |
| 0.90 | 0.083 | 0.890 |

Held out, the same thresholds give coverage 0.629 / 0.472 / 0.364 / 0.248 / 0.097 at
accuracy 0.732 / 0.808 / 0.861 / 0.881 / 0.887 — indistinguishable within the
sampling noise of 90 takes. Roughly half the duration can be shown with more than
four chords in five right; that is the user-facing value of the number.

**P2 changed no labels.** The confidence work alone (2026-10-20, before the §7
sweep) reproduced the §2 run's per-take scores, counts, boundaries and timing
exactly (0 differences over the ten scored fields, row by row against
`.cache/chords/benchmark-viterbi-180`). The §7 front-end change *does* move the
labels — it is a different chroma — which is why that sweep is measured, not
assumed.

**Two different ways to average, stated once.** §7's 0.6121 is the *mean of
per-take CSR*; the 0.5786 above pools every event's duration across the corpus,
so a long take weighs what it lasts. Neither replaces the other: the table
answers "how well does a run do on a typical take?", §6 answers "over this hour
of audio, how much is right?".

The harness's own wall clock around `analyze()` summed to 43.2 s for 5,484.2 s of
audio (decode included), with a 260.4 MiB process high-water mark across the 180
takes and no harness-side errors.

**Environment.** Linux x86_64, kernel 7.0.10-1-liquorix, CPython 3.13.5, numpy
2.5.3, librosa 1.0.0, soundfile 0.14.0, `chroma-baseline` 0.1.0, CPU only, commit
`f72c8a9` plus this change, **2026-10-20 17:11 UTC**. The manifest digest
was `de6338fb…` (the pinned corpus).

**Verdict.** The number is calibrated on the corpus it was fitted on, and its
risk–coverage curve is monotone and wide enough to be useful. What it is *not*:

* **Not transferable as a probability.** GuitarSet is one clean acoustic guitar; on a
  mixed commercial recording the ordering still holds, the probabilities do not.
* **Not measured for `N`.** GuitarSet has no notated silence, so an event claiming
  silence gets the same mapping by extrapolation, not by evidence.
* **Not a verdict on extension chords.** The reference is the exact label, so a `G`
  detected over a `G7` scores as a miss even though a player would accept it. The
  triad-reduced CSR (0.6183) shows how small that effect is on this corpus.
* **Not fused with the decoder.** The confidence is computed after decoding and never
  feeds back into it; a future change that uses it (automatic correction, fusion)
  must publish a new measurement on this harness, not just a claim.

---

## 7. Front-end robustness — one variable at a time (roadmap Phase I P3, 2026-10-20)

**Why this exists.** The audit's P3 asks whether the chroma front end — which until
2026-10-20 was just `librosa.feature.chroma_cqt(y, sr, hop_length=2048)` with no
explicit tuning, no harmonic attenuation and no energy gate — is throwing accuracy
away. Each option is measured alone, with everything else at its default, and each
run records what it used, so a reader can reproduce a row rather than trust it.

```bash
python scripts/chord_benchmark.py --option tuning=auto     --out .cache/chords/p3-baseline
python scripts/chord_benchmark.py --option tuning=zero     --out .cache/chords/p3-tuning-zero
python scripts/chord_benchmark.py --option tuning=estimate --out .cache/chords/p3-tuning-estimate
python scripts/chord_benchmark.py --option harmonic=true   --out .cache/chords/p3-harmonic
python scripts/chord_benchmark.py --option feature=cens    --out .cache/chords/p3-cens
python scripts/chord_benchmark.py --option energy_gate_db=-40 --out .cache/chords/p3-energy-gate
```

| Front end | CSR | CSR (triad) | Segment overlap | Change F1 | Boundary err. ref→hyp | Hyp chords | Wall | Peak RSS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `tuning=auto` (previous default) | 0.6029 | 0.6091 | 0.8298 | 0.8270 | 0.178 s | 12.89 | 69.5 s | 303.9 MB |
| **`tuning=zero` (new default)** | **0.6121** | **0.6183** | **0.8343** | **0.8296** | **0.168 s** | 12.91 | 55.2 s | 260.5 MB |
| `tuning=estimate` | 0.6062 | 0.6123 | 0.8313 | 0.8271 | 0.170 s | 12.93 | 60.8 s | 304.8 MB |
| `harmonic=true` (HPSS) | 0.5890 | 0.5953 | 0.8267 | 0.8103 | **0.139 s** | 13.74 | 464.1 s | 373.4 MB |
| `feature=cens` | 0.5475 | 0.5538 | 0.7228 | 0.7315 | 0.649 s | 8.91 | 58.2 s | 303.9 MB |
| `energy_gate_db=-40` | 0.6046 | 0.6107 | 0.8318 | 0.8284 | 0.178 s | 12.77 | 66.7 s | 304.6 MB |

All six runs: 180 comping takes, instructed lead sheet, Viterbi at penalty 0.80,
same manifest, same machine as §2 (Linux x86_64, CPython 3.13.5, numpy 2.5.3,
librosa 1.0.0, CPU only), **2026-10-20**, at the commits stated in each run's
`aggregate.md`.

**Paired deltas against `tuning=auto`.** Each row below is the mean of the 180
take-wise differences (the runs are paired by take, so the noise cancels) with
the standard error of that mean:

| Front end | Δ CSR (± SE) | Δ change F1 (± SE) | Takes with higher CSR |
| --- | --- | --- | --- |
| `tuning=zero` | **+0.0092 ± 0.0033** | +0.0027 ± 0.0028 | 65 / 180 |
| `tuning=estimate` | +0.0033 ± 0.0023 | +0.0001 ± 0.0014 | 24 / 180 |
| `energy_gate_db=-40` | +0.0017 ± 0.0010 | +0.0015 ± 0.0022 | 9 / 180 |
| `harmonic=true` | **−0.0139 ± 0.0051** | **−0.0167 ± 0.0055** | 64 / 180 |
| `feature=cens` | **−0.0554 ± 0.0094** | **−0.0955 ± 0.0122** | 54 / 180 |

The gate and HPSS win on more takes than they lose yet lose in duration: a few
takes suffer a large regression that a mean over takes hides and a duration
average surfaces. That is exactly the reason the audit asks for the whole vector
and not one number.

**What each row says.**

* **`tuning=zero` was adopted as the default.** In librosa 1.0,
  `chroma_cqt(tuning=None)` (what `tuning=auto` does) *estimates the recording's
  tuning from the signal* and shifts the CQT filters by that fraction of a bin,
  while `tuning=0.0` keeps the A440 grid. On GuitarSet — which measures 4–10
  cents sharp on every take checked — trusting A440 gains +0.0092 CSR with no
  metric worse, and it is also ~20 % less CPU and ~43 MB less memory because
  the tuning estimate is skipped. The mechanism is unproven; the measurement is.
* **`tuning=estimate` does not beat `zero` and barely beats `auto`.** It
  measures the deviation explicitly (`estimate_tuning`, recorded in cents as
  `tuning_cents`) and passes the same shift `auto` would have applied, so its
  +0.0033 over `auto` is within noise, and it stays 0.006 below `zero`.
  GuitarSet being in tune is the likely explanation, and no corpus here tests
  detuned audio.
* **HPSS is a loss, and a big cost.** The harmonic component costs 464 s of wall
  time for the same corpus (6.7× the default) and drops both CSR (−0.0139) and
  change F1 (−0.0167). On solo guitar the percussive component carries the
  attack the change detector uses; removing it blurs boundaries. Not adopted.
* **CENS is worse at everything except speed.** −0.0554 CSR and −0.0955 change
  F1, with the hypothesis collapsing to 8.91 chords per take against a 12.00
  reference: CENS's temporal smoothing swallows short chords. Its boundary error
  (0.649 s) is the worst in the table. Not adopted.
* **The −40 dB energy gate changes almost nothing** (+0.0017, within noise) and
  does not make GuitarSet emit a single `N`: there is no notated silence in it.
  It stays an option, because the audit's stated purpose — honest `N` in
  near-silence — cannot be measured on this corpus at all.

**Cross-check against the second annotation view.** Re-running the adopted default
on the `performed` voicings (JAMS `chord` index 1) and pairing it against the
recorded `tuning=auto` run for that view gives the same direction: CSR
0.5186 → **0.5250** (+0.0064 ± 0.0019), triad CSR 0.5954 → **0.6019** (+0.0064
± 0.0034), segment overlap +0.0045 ± 0.0020, change F1 +0.0027 ± 0.0028. The
improvement is a property of the front end, not of one reference view.

**What this does *not* establish.** That `tuning=zero` is better in general. Every
take in this corpus is played on a tuned instrument; a detuned recording is the
case where `auto` should win, and this corpus cannot express it. `tuning=auto`
stays one `--option` away for exactly that reason. The reverb, compression,
vocal-mix and onset variables of P3 are still unmeasured; the change penalty
itself (0.80) was fitted on the *old* front end and has not been re-swept.

**Consequence for the recorded numbers.** The default now produces CSR **0.6121**
/ **0.6183** triad / overlap **0.8343** / change F1 **0.8296** against the
instructed lead sheet, and the §6 confidence was refitted for it (Brier 0.1420,
ECE 0.0161 held out). The §2 numbers remain the record of the previous default;
both are in this file so that "what changed" is a diff between two measurements,
not a story.
