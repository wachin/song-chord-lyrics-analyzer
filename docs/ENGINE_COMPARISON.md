# Engine Comparison

**Status: partially written (2026-09-25).** A first measured lyrics-ASR comparison
(roadmap sections 25 and 26) is recorded below. Chords, key and tempo comparisons do
not exist yet — no chord/key/tempo engine has been integrated, so those rows stay empty
rather than invented (roadmap rule 6).

> **This is a pre-harness investigation, not `songlab benchmark`.** The phase-11 benchmark
> command does not exist yet; the numbers below come from a throwaway harness run on
> 2026-09-25 and stored in `results/` (which the repository intentionally keeps out of git —
> see the note in "Reproduction"). They are real measurements with the caveats stated below,
> and they are **not** a claim of production quality.

## Lyrics ASR — Faster-Whisper vs Parakeet on isolated vocals (roadmap 25)

**Dataset.** `vocadito` (Bittner et al., 2021), CC-BY-4.0: 40 short excerpts (17–36 s) of
solo, monophonic singing in 7 language labels, with lyrics annotated by trained musicians.
All 40 excerpts were used. Four of them are committed under `samples/` with sidecars.

**Engines.**

| Engine | Package | Checkpoint | Size on disk |
| --- | --- | --- | --- |
| faster-whisper 1.2.1 (ctranslate2 4.8.2) | `faster-whisper` (MIT) | `Systran/faster-whisper-small`, `compute_type=int8`, `beam_size=5`, language auto-detected | 464 MB |
| Parakeet TDT 0.6B v3 | `onnx-asr` 0.12.0 + `onnxruntime` 1.30.0 (MIT) | `istupakov/parakeet-tdt-0.6b-v3-onnx`, `quantization=int8` (weights CC-BY-4.0) | 640 MB |

**Ground truth** is the vocadito lyric text. Both reference and hypothesis are normalised
(NFKC, lower-cased, punctuation stripped, whitespace collapsed) before WER/CER. Each WER/CER
is computed per excerpt and then averaged (an unweighted mean of per-excerpt rates).

**Hardware.** Linux x86_64, CPython 3.13.5, CPU-only: Intel Core i3-7020U (2 cores / 4
threads, 2.30 GHz), 7.6 GiB RAM. `OMP_NUM_THREADS=8`. No GPU was used, so no VRAM figure.

### Overall (40 excerpts, isolated solo vocals)

| Engine | WER | CER | mean processing time | real-time factor | peak RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| faster-whisper `small` (int8) | 0.3799 | 0.2725 | 18.84 s | 0.95 | ≈ 1.29 GiB |
| Parakeet TDT 0.6B v3 (int8, ONNX) | **0.3722** | **0.1857** | **4.04 s** | **0.20** | ≈ 1.40 GiB |

Parakeet is ~4.7× faster (real-time factor 0.20 vs 0.95) at similar peak memory, and its
character error rate is clearly lower while the word error rate is essentially tied.

### By language label (40 excerpts, isolated solo vocals)

| Language (n) | fw-small WER | fw-small CER | Parakeet WER | Parakeet CER |
| --- | ---: | ---: | ---: | ---: |
| English (17) | 0.2314 | 0.1258 | **0.0770** | **0.0313** |
| French (9) | 0.3091 | 0.1517 | **0.2769** | **0.1101** |
| French+English (1) | 0.0294 | 0.0137 | 0.0294 | 0.0137 |
| Hawaiian+English (1) | 0.7917 | **0.1684** | **0.6667** | 0.4737 |
| Spanish (1) | **0.1429** | **0.0707** | 0.5714 | 0.4848 |
| Tagalog (6) | **0.4920** | **0.1428** | 0.8544 | 0.2397 |
| Catalan/Valencian (2) | **0.7812** | **0.5261** | 0.8594 | 0.5440 |
| Mandarin (2) | 1.0000 | 0.8749 | 1.0000 | **0.7129** |
| unlabelled (1) | 1.0000 | 3.4860 | **0.9722** | **0.9813** |

The picture is not "one engine wins": Parakeet is **much** better on English (WER 0.08 vs
0.23) and better on French, while faster-whisper is better on Tagalog and on the single
Spanish excerpt. Both fail on the Mandarin excerpts (WER 1.0). *n = 1 per language is not
evidence* — the individual-language rows are indicative, not conclusive.

### Singing ASR strategy — mix vs isolated vocal (roadmap 26)

vocadito is a cappella, so the comparison is done with **constructed mixes**: the same
vocal plus a synthetic accompaniment (a C–Am–F–G pad progression at 120 BPM with a kick and
hats, rendered from scratch) at three vocal-to-accompaniment ratios. The control is the
peak-normalised vocal alone (`mixstem`), so a mix and its control differ *only* by the added
accompaniment — there is **no separation error** in this experiment. Eight excerpts were
used (English, Spanish, Catalan/Valencian, Tagalog).

| Condition (vocal vs accompaniment) | fw-small WER | fw-small CER | Parakeet WER | Parakeet CER |
| --- | ---: | ---: | ---: | ---: |
| isolated vocal (control) | 0.1998 | 0.1087 | 0.2736 | 0.2162 |
| mix, vocal +6 dB | 0.2014 | 0.1280 | 0.3086 | 0.2161 |
| mix, vocal 0 dB | 0.2505 | 0.1504 | 0.3356 | 0.2332 |
| mix, vocal −6 dB | 0.2905 | 0.1783 | 0.3651 | 0.2771 |

For both engines, adding accompaniment degrades transcription **monotonically** as it gets
louder, and the isolated vocal is the best input. That supports isolating the vocal for
lyrics — but only for *synthetic* accompaniment; a real separator adds its own artefacts
(roadmap 27/28), which this experiment deliberately excludes.

## Observations

* **Speed.** On this CPU Parakeet's ONNX int8 path is ~4–5× faster than faster-whisper
  `small` int8 (real-time factor 0.20 vs 0.95). Both fit in roughly 1.3–1.4 GiB of RAM.
* **Accuracy is language-dependent.** Parakeet is far ahead on English; faster-whisper leads
  on Tagalog and Spanish here. Neither handles Mandarin singing.
* **Whisper repetition loops.** Non-lexical singing (e.g. sustained "la la la") triggered an
  82-second repetition loop in faster-whisper `small` on one excerpt — a real failure mode
  that inflates the mean time and produces garbage text. Parakeet did not do this.
* **Larger Whisper was not run.** `Systran/faster-whisper-medium` (1.5 GB) was downloaded and
  started, but on this 2-core CPU it needed ~66 s per 30 s excerpt (real-time factor ≈ 2.2),
  so the full grid would take over an hour; it was stopped and is **not** reported.
* **No timestamp error.** vocadito annotates lyrics at phrase level, not word level, so word
  timestamp error (roadmap 25) could not be computed and is left blank rather than faked.

## What this is not

* Not a benchmark of mixed commercial music, backing vocals, reverb or live recordings —
  the roadmap 25 test list is only partly covered (isolated studio-ish solo vocals).
* Not a separation comparison: no Demucs/UVR stem was produced (roadmap 27); the "mix" is
  synthetic and the "stem" is the true vocal.
* Not a claim that one engine should be adopted. It is a first data point to inform phase 3.

## Reproduction

The harness, dataset and raw per-excerpt results (JSONL) plus the aggregate `summary.json`
live in the gitignored `.cache/lyrics-asr-investigation/` directory. The repository policy
(`.gitignore`) keeps `results/*.json|csv|md` and `benchmark/*` out of git, so the machine
artifacts are regenerated locally, not committed; this document is the committed record.
The committed `samples/vocadito_*.{wav,json}` excerpts are a small subset for spot-checking.

## What it will contain, per engine and per preprocessing strategy (still pending)

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
| Lyric WER / CER | measured value (see above) |
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
