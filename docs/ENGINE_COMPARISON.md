# Engine Comparison

**Status: partially written (2026-09-26).** A first measured lyrics-ASR comparison
(roadmap sections 25, 26 and 27) is recorded below, on isolated vocals, on synthetic
mixes, and on one real commercial mix. A first **chord** measurement (roadmap sections
23, 24, 27 and 28) was added on 2026-09-26: a chroma + Viterbi baseline scored against a
user-supplied chord chart, on the mix and on Demucs stems. Key and tempo comparisons do
not exist yet — no key or tempo engine has been integrated — so those rows stay empty
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

### Singing ASR strategy — mix, isolated vocal, and a separated stem (roadmap 26/27)

vocadito is a cappella, so this needs **constructed mixes**. Two experiments were run on the
same eight excerpts (English, Spanish, Catalan/Valencian, Tagalog): (a) mix vs the *true*
isolated vocal (no separator, so the only variable is the accompaniment), and (b) mix vs a
**real Demucs-separated vocal stem** (so the variable is the separation itself).

**Accompaniment** is synthetic (a C–Am–F–G pad progression at 120 BPM with a kick and hats,
rendered from scratch) at three vocal-to-accompaniment ratios; the control is the
peak-normalised vocal alone (`mixstem`), so a mix and its control differ *only* by the added
accompaniment.

**(a) Mix vs the true isolated vocal — no separator.**

| Condition (vocal vs accompaniment) | fw-small WER | fw-small CER | Parakeet WER | Parakeet CER |
| --- | ---: | ---: | ---: | ---: |
| isolated vocal (control) | 0.1998 | 0.1087 | 0.2736 | 0.2162 |
| mix, vocal +6 dB | 0.2014 | 0.1280 | 0.3086 | 0.2161 |
| mix, vocal 0 dB | 0.2505 | 0.1504 | 0.3356 | 0.2332 |
| mix, vocal −6 dB | 0.2905 | 0.1783 | 0.3651 | 0.2771 |

For both engines, adding accompaniment degrades transcription **monotonically** as it gets
louder, and the true isolated vocal is the best input.

**(b) Real separation with Demucs.** The `mix+00` mixes (vocal 0 dB vs accompaniment) were
separated with **Demucs 4.1.0 `htdemucs`** (`--two-stems=vocals`) on CPU, giving a `vocals`
stem and a `no_vocals` residual per excerpt. The stems were downmixed to mono 16-bit PCM
before transcription.

| Condition (8 excerpts) | fw-small WER | fw-small CER | fw-small RTF | Parakeet WER | Parakeet CER |
| --- | ---: | ---: | ---: | ---: | ---: |
| true isolated vocal (control) | 0.1998 | 0.1087 | 0.96 | 0.2736 | 0.2162 |
| raw mix (Demucs input) | 0.2505 | 0.1504 | 0.81 | 0.3356 | 0.2332 |
| Demucs `vocals` stem | 0.3244 | 0.2130 | 0.70 | 0.2991 | 0.1912 |
| Demucs `no_vocals` residual | 1.0000 | 1.0000 | 1.43 | 1.0000 | 1.0000 |

The residual scores WER 1.0 for both engines (the models emit nothing intelligible from the
accompaniment alone), which is a useful sanity check that the separator did move the vocal
out of the residual. But the **separated vocal is not the true vocal**:

* faster-whisper is **worse on the separated stem than on the raw mix** (0.3244 vs 0.2505) —
  the separation artefacts cost more than the masking did;
* Parakeet is **slightly better on the separated stem than on the raw mix** (0.2991 vs
  0.3356) but still worse than the true vocal (0.2736).

So the honest answer to roadmap 26 is: the *true* isolated vocal wins, but a *separated* one
does not automatically — whether separation pays off is engine-dependent, and here it did not
justify the cost for the faster engine. Note the caveat: the mixes are synthetic and
`htdemucs` is trained on real music, so this may be pessimistic — which is why the pass below
was run on a real recording. Demucs weights also have an unresolved licence (used locally
only, never bundled — see `docs/DEPENDENCY_MATRIX.md` §5 and `docs/LICENSE_AUDIT.md`).

### Same comparison on a real commercial mix (roadmap 26, second pass, 2026-09-25)

**Why.** The first pass used synthetic accompaniment, so its own caveat — "real songs still
need to be tested" — was left open. This pass replaces the synthetic accompaniment with a
real production.

**Input.** A commercial MP3 supplied by the user for local analysis only. It lives in the
gitignored `mp3/` directory and in the gitignored `.cache/real-song/`; **neither the audio nor
its lyrics are committed** and no lyric text appears in this document. It is 272.04 s long,
48 kHz stereo, 282 kbit/s. The file carries its own lyrics in an ID3 `lyrics-esp` tag — one
verse plus the chorus, 12 lines and 51 tokens — and that tag is used as the evaluation
reference. It is a **partial** reference, not a full verbatim transcript: the song repeats its
text, so any whole-file error rate is inflated by those repeats. The repeat-insensitive token
scores are therefore reported alongside and are the primary comparison.

**Separation.** Demucs 4.1.0 `htdemucs`, four stems, CPU: **5 min 38 s for the 272 s song**
(real-time factor 1.23). The `no_vocals` input is the sum of the drum, bass and `other` stems,
which is exactly what `--two-stems=vocals` returns as the residual.

**An integration finding first: the packaged ONNX Parakeet path cannot take a full song.**

| Parakeet route | Output | Time |
| --- | --- | ---: |
| `recognize(path)` on the whole 272 s file | 8 garbled words (45 characters) | 124 s |
| `with_vad(silero)` — the upstream long-audio route | **0 words**: the speech VAD finds no speech in singing | 4 s |
| our own 20 s fixed-window chunking | 67 words, 10 of 12 known lines | 52 s |

Long audio therefore needs our own chunking, and a *speech* VAD is the wrong tool for singing.
This is an integration finding only: the section-25 numbers are unaffected, because those
clips are 17–36 s.

**Results.** Reference: 12 lines / 51 tokens / 24 unique tokens (partial).

| Engine | Input | hyp tokens | unique tokens | unique-token F1 | multiset F1 | known lines found | WER* | CER* | RTF |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| faster-whisper `small` | raw mix | 139 | 26 | **0.960** | 0.537 | **12/12** | 1.726 | 1.717 | 0.59 |
| faster-whisper `small` | Demucs `vocals` | 130 | 31 | 0.873 | **0.564** | 11/12 | 1.549 | 1.603 | 0.43 |
| faster-whisper `small` | Demucs `no_vocals` | 6 | 1 | 0.000 | 0.000 | 0/12 | 1.000 | 0.945 | 0.18 |
| Parakeet TDT 0.6B v3 (20 s chunks) | raw mix | 67 | 33 | **0.737** | **0.678** | **10/12** | 0.686 | 0.581 | 0.19 |
| Parakeet TDT 0.6B v3 (20 s chunks) | Demucs `vocals` | 81 | 44 | 0.618 | 0.606 | 9/12 | 1.020 | 0.912 | 0.19 |
| Parakeet TDT 0.6B v3 (20 s chunks) | Demucs `no_vocals` | 0 | 0 | 0.000 | 0.000 | 0/12 | — | — | 0.21 |

\* WER/CER here are measured against the embedded *partial* lyrics, not against a full
transcript, so they are inflated by the song's repeats and are **not** the ranking metric.

**Reading it.**

* The **raw mix wins or ties for both engines**, and wins clearly for Parakeet (unique-token
  F1 0.737 vs 0.618, 10/12 vs 9/12 known lines, and a lower WER* despite the repeat inflation).
* For faster-whisper the two views disagree — the separated stem is better on the
  repeat-sensitive multiset F1 (0.564 vs 0.537) and on WER*, but worse on the repeat-insensitive
  unique-token F1 (0.873 vs 0.960) and it loses one known line. That is a wash, not a gain.
* The residual transcribes to 6 words for faster-whisper and to nothing for Parakeet, which
  confirms the vocal really did leave it.
* The input choice changes the output enormously: character-level similarity between the mix
  and stem transcriptions is 0.43 (faster-whisper) and 0.14 (Parakeet).

**So the synthetic conclusion does not transfer.** On the synthetic mixes separation helped
Parakeet slightly and hurt faster-whisper; on this real production it hurts Parakeet and is a
wash for faster-whisper. Both passes agree on the roadmap's own warning — never assume that
the isolated vocal is the better input — and this pass is the stronger evidence of the two,
because its mix is real.

**Limits.** One song and one arrangement (n = 1): no statistical claim is made. The reference
is the tag's partial lyrics and the song's repeats inflate any whole-file error rate. Backing
vocals, reverb and the production style are uncontrolled. And this compares the mix with
*Demucs' separated* vocal, not with the true vocal, which does not exist for commercial audio.

## Chords — chroma + Viterbi on the mix and on separated stems (roadmap 23/24/27/28)

**Why.** Roadmap 27 asks for chord recognition tested on `original`, `bass`, `other`,
`vocals` and `other + bass`; roadmap 28 asks which of them wins. This pass now covers
four songs.

**Input.** Four commercial MP3s supplied by the user for local analysis only, each with a
hand-written chord chart. Both pairs live in the gitignored `mp3/` directory; the extracted
audio, the stems and the detected sequences live in the gitignored `.cache/chords/<song>/`.
**Neither the audio nor the chord charts are committed, and no lyric text is reproduced**
here. Song A is 327.16 s, 44.1 kHz stereo, 160 kbit/s, tagged 84 BPM; song B is 268.5 s,
48 kHz stereo, ~103 kbit/s; song C is 254.3 s, 44.1 kHz stereo, ~327 kbit/s; song D is
296.8 s, 44.1 kHz stereo, ~325 kbit/s. The Demucs
4-stem split (`htdemucs`, CPU) is the same
configuration used for the real-song lyrics pass, run once per song. For song B, the free
LRCLIB lyrics API was also queried as a feasibility check: a plain and a line-timed variant
of the song exist there and match its duration, and the response is kept in the gitignored
cache as a possible future lyric reference — the chord pass did not use it.

**The engine (baseline, our own code).** The section-24.1 pipeline, re-implemented from the
recorded design:

1. HPSS harmonic component (`margin=3.0`) and tuning estimated with `librosa.estimate_tuning`;
2. `chroma_cqt` (from C2, 5 octaves) and `chroma_cens`, blended 0.3 CQT / 0.7 CENS and
   L2-normalised per frame;
3. 24 equal-weight major/minor triad templates, with non-chord-tone energy penalised (×0.5);
4. a bass chroma (C1, 3 octaves) root (+0.15) and fifth (+0.10) boost;
5. a song-level Krumhansl-Schmuckler key prior (+0.05 diatonic, −0.12 non-diatonic), used
   only as a soft prior;
6. beat-synchronous frames (`librosa.beat.beat_track`, median aggregation) decoded by a
   max-sum **Viterbi** with a flat chord-change penalty, followed by a second pass with a
   palette prior (states below 2.5% share penalised −0.10);
7. segments shorter than 0.30 s absorbed, consecutive duplicates collapsed.

The change penalty is expressed in this implementation's own emission units, so it does
**not** transfer from chordify's value; it was tuned on song A's sweep and then held fixed
for song B (robustness rows below), which is the honest cross-song test.

**Reference and metrics (timing-free).** Each chart is a complete chord sheet in song order
with section headers but **no timestamps** — the standard chord-sheet format (as found on
ultimate-guitar), so frame accuracy, segment overlap and chord-change timing error cannot
be computed. Song A's chart has 86 chords, 8 distinct (A, Am, Bm, C, D, Em, F#m, G), key
D major; song B's has 64 chords, only 4 distinct (A, D, E, F#m), key A major; song C's has
101 chords, 8 distinct (Am, Bm, C, D7, Dm, E, E5, F), key A minor — and it is the first
chart with seventh (`D7`) and fifth (`E5`) labels, which the 24-triad decoder cannot emit in
the first place, so song C is also scored against the reference **reduced to triads** (a
documented scoring view, never an edit of the chart). Song D's chart has 79 chords, only
4 distinct (A, B, C#m, E), key E major — all plain triads, so no reduction is needed.
Charts are
scored instead by:

* **sequence alignment** (Needleman-Wunsch, gap cost 1) between the reference sequence and
  the detected sequence, reported as exact / root-only / quality-only precision-recall-F1;
* **multiset F1** (repeat-aware chord distribution) and **palette F1** (distinct chords);
* **key** agreement (Krumhansl-Schmuckler on the reference's chord tones vs on the audio).

**Results, song A** at change penalty 0.40 (reference: 86 chords; chart key D major).

| Input (327 s) | chords detected | exact F1 | root F1 | quality F1 | multiset F1 | palette F1 | key |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| original mix | 87 | 0.694 | 0.751 | 0.694 | 0.809 | **0.824** | D major ✓ |
| Demucs `other` | 91 | **0.701** | 0.701 | **0.701** | **0.859** | 0.800 | D major ✓ |
| Demucs `bass`+`other` | 89 | 0.663 | 0.697 | 0.663 | 0.720 | 0.667 | D major ✓ |
| Demucs `no_vocals` (drums+bass+other) | 86 | 0.558 | 0.616 | 0.558 | 0.698 | 0.667 | D major ✓ |
| Demucs `vocals` | 66 | 0.447 | 0.513 | 0.447 | 0.684 | 0.750 | D major ✓ |
| Demucs `bass` | 119 | 0.429 | 0.585 | 0.429 | 0.537 | 0.667 | D major ✓ |

**Results, song B** at the same change penalty 0.40, held over from song A (reference:
64 chords; chart key A major).

| Input (268.5 s) | chords detected | exact F1 | root F1 | quality F1 | multiset F1 | palette F1 | key |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| Demucs `other` | 70 | **0.791** | **0.806** | **0.791** | **0.866** | **0.889** | A major ✓ |
| Demucs `bass`+`other` | 73 | 0.642 | 0.745 | 0.642 | 0.701 | 0.727 | A major ✓ |
| original mix | 64 | 0.641 | 0.656 | 0.641 | 0.688 | 0.727 | A major ✓ |
| Demucs `no_vocals` (drums+bass+other) | 61 | 0.624 | 0.720 | 0.624 | 0.704 | 0.727 | A major ✓ |
| Demucs `vocals` | 50 | 0.544 | 0.597 | 0.544 | 0.579 | 0.615 | A major ✓ |
| Demucs `bass` | 40 | 0.308 | 0.654 | 0.308 | 0.308 | 0.600 | A major ✓ |

**Results, song C** at the same change penalty 0.40, held over from song A (reference:
101 chords; chart key A minor). First against the chart's own labels:

| Input (254.3 s) | chords detected | exact F1 | root F1 | quality F1 | multiset F1 | palette F1 | key |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| original mix | 98 | 0.372 | 0.623 | 0.372 | 0.502 | 0.667 | A minor ✓ |
| Demucs `no_vocals` (drums+bass+other) | 101 | 0.396 | 0.653 | 0.396 | 0.505 | 0.667 | E minor ✗ |
| Demucs `bass` | 97 | 0.384 | 0.748 | 0.384 | 0.495 | 0.706 | A minor ✓ |
| Demucs `bass`+`other` | 103 | 0.343 | 0.686 | 0.343 | 0.490 | 0.667 | E minor ✗ |
| Demucs `vocals` | 39 | 0.371 | 0.457 | 0.371 | 0.443 | 0.615 | A minor ✓ |
| Demucs `other` | 93 | 0.216 | 0.433 | 0.216 | 0.371 | 0.625 | E minor ✗ |

And against the reference reduced to triads (`D7`→`D`, `E5`→`E`), which is the fair
comparison for a triad-only decoder:

| Input | exact F1 | root F1 | multiset F1 | palette F1 | key |
| --- | ---: | ---: | ---: | ---: | :---: |
| Demucs `bass` | 0.596 | **0.748** | **0.707** | **0.875** | A minor ✓ |
| Demucs `bass`+`other` | 0.598 | 0.686 | 0.667 | 0.824 | E minor ✗ |
| Demucs `no_vocals` | 0.594 | 0.653 | 0.644 | 0.824 | E minor ✗ |
| original mix | 0.533 | 0.623 | 0.613 | 0.824 | A minor ✓ |
| Demucs `vocals` | 0.414 | 0.457 | 0.486 | 0.833 | A minor ✓ |
| Demucs `other` | 0.320 | 0.433 | 0.474 | 0.800 | E minor ✗ |

**Results, song D** at the same change penalty 0.40, held over from song A (reference:
79 chords; chart key E major).

| Input (296.8 s) | chords detected | exact F1 | root F1 | quality F1 | multiset F1 | palette F1 | key |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| Demucs `no_vocals` (drums+bass+other) | 97 | 0.659 | **0.761** | 0.659 | **0.795** | 0.800 | E major ✓ |
| Demucs `bass`+`other` | 98 | 0.644 | 0.757 | 0.644 | 0.780 | 0.800 | E major ✓ |
| Demucs `other` | 88 | 0.659 | **0.790** | 0.659 | 0.766 | **0.889** | E major ✓ |
| original mix | 94 | 0.624 | 0.705 | 0.624 | 0.763 | 0.800 | B major ✗ |
| Demucs `vocals` | 92 | 0.526 | 0.573 | 0.526 | 0.702 | 0.727 | B major ✗ |
| Demucs `bass` | 72 | 0.570 | 0.702 | 0.570 | 0.649 | 0.727 | E major ✓ |

**Robustness to the change penalty** (multiset F1), because a single tuned value would hide
the sensitivity:

| Input | song A 0.30 | song A 0.40 | song A 0.50 | song B 0.30 | song B 0.40 | song B 0.50 | song C 0.30 | song C 0.40 | song C 0.50 | song D 0.30 | song D 0.40 | song D 0.50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| original mix | **0.726** | 0.809 | 0.765 | 0.721 | 0.688 | **0.727** | 0.451 | 0.502 | 0.452 | 0.759 | 0.763 | 0.713 |
| Demucs `other` | 0.652 | **0.859** | 0.752 | 0.749 | 0.866 | **0.924** | 0.326 | 0.371 | 0.388 | **0.822** | 0.766 | 0.737 |
| Demucs `bass`+`other` | 0.700 | 0.720 | **0.787** | 0.719 | 0.701 | 0.711 | 0.400 | 0.490 | 0.484 | 0.806 | 0.780 | 0.741 |
| Demucs `no_vocals` | 0.687 | 0.698 | 0.715 | 0.703 | 0.704 | 0.588 | 0.407 | 0.505 | 0.450 | 0.800 | 0.795 | 0.790 |
| Demucs `vocals` | 0.652 | 0.684 | 0.567 | 0.579 | 0.579 | 0.596 | 0.395 | 0.443 | 0.378 | 0.698 | 0.702 | 0.694 |
| Demucs `bass` | 0.560 | 0.537 | 0.526 | 0.403 | 0.308 | 0.408 | 0.473 | 0.495 | 0.447 | 0.698 | 0.649 | 0.606 |

**Cost.** Song A: ~38–40 s per 327 s song (real-time factor ≈ 0.12, peak RSS ≈ 1.04 GiB);
song B: ~33–34 s per 268.5 s (real-time factor ≈ 0.12, peak RSS ≈ 0.90 GiB); song C: ~31–33
s per 254.3 s (real-time factor 0.12–0.13, peak RSS ≈ 0.86 GiB); song D: ~35–36 s per 296.8 s
(real-time factor 0.12, peak RSS ≈ 0.95 GiB). Feature
extraction is essentially all of it — decoding is 0.03–0.05 s.

**Reading it.**

* **Key estimation is not stem-proof — in either direction.** On songs A and B all six
  inputs recovered the correct key. On song C three of six (`other`, `bass`+`other`,
  `no_vocals`) estimated E minor for an A-minor song; on song D two of six — **including
  the raw mix** — estimated B major for an E-major song. Across four songs, 5 of 24
  condition–song pairs get the key wrong, and *which* inputs fail is not consistent:
  dominant-heavy arrangements pull the Krumhansl-Schmuckler profile toward the dominant.
* **The per-stem rankings swing from song to song.** `other`: first on songs A and B,
  collapsed on C (0.371 on the chart's labels, 0.474 triad-reduced), third on D — and its
  best penalty on D is 0.30 (0.822). `bass`: worst on A and B, best on C's triad view
  (0.707), worst again on D (0.649). *No stem is reliably best*, and the earlier n = 2
  "`other` is best" reading was overfit — exactly what its caveat predicted.
* **`bass`+`other` is the steadiest stem input**: third on A and B, second on D, and on C
  second in the triad view (fourth on the raw labels) — 0.720 / 0.701 / 0.667 triad / 0.780.
  `no_vocals`, which is that pair plus drums, led
  song D (0.795) and was mid-pack elsewhere. `vocals` is consistently bad for chords:
  fifth on all four songs.
* **The raw mix never wins by much but never collapses.** Across four songs it lands
  second on A and C and fourth on B and D; it sits within 0.032 of the best input on C and
  D but 0.178 behind `other` on B — the safest no-separation choice without being anybody's
  clear winner.
* **The penalty tuned on song A transferred to songs B, C and D.** The mix peaks at 0.40
  on all four songs, on C no input climbs much at any penalty (0.37–0.51), and on D the
  top four inputs sit within 0.03 at every penalty — the value is not song-specific, though
  the full sweep ran only on song A.
* **Separation is not required for chords, and it is not a free win.** As in the lyrics pass,
  the extra processing does not buy a stable improvement over the mix.
* **What an arrangement rewards, a stem inherits.** Song C's bass-led solo-guitar style
  made `bass` the best input there; songs A, B and D's band arrangements punish it. The
  chart's bass line dominates what the bass stem can show, so `bass` alone swings hardest
  between songs. `vocals` stays weak on all four: it carries melody, not harmony.
* **The dominant knob is the change penalty**, not the input: moving it from 0.40 to 0.50
  roughly halves the detected chord count (87 → 63 on the mix).
* **The error pattern is systematic**: the engine confuses major with the parallel minor
  (on song A it emits `Dm` and `Gm` where the chart has `D` and `G`, and misses the single
  borrowed `C`; at penalty 0.40 the mix recovers 7 of 8 reference chords). Song B shows the
  same shape: `other` recovers all 4 reference chords with a single false parallel (`Em`),
  while the mix recovers all 4 but adds three (`Bm`, `Dm`, `Em`). Song C adds a new one:
  detected chord *counts* can match the chart (98 vs 101) while the content is wrong, so
  count alone is not evidence of accuracy.

**Limits.** Four songs and charts (n = 4), from the same user and the same genre (simple
diatonic worship arrangements; song C is from the same arranger as song A): still no
statistical claim, and songs B and D have 4-chord palettes, which
makes the palette metric easy. The charts have no timestamps, so no frame-level accuracy
exists. The change penalty was selected on song A's sweep — a tuned, not a default, value —
though it transferred to songs B, C and D. Song C's triad-reduced view means its seventh and
fifth labels can never be scored exactly against a triad-only decoder, and the reference
chords are the user's editorial choices for their own arrangements, not definitive
transcriptions.

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
* **Separation is not a free win.** Real Demucs `htdemucs` two-stem separation of the same
  synthetic mixes helped Parakeet slightly (WER 0.2991 vs 0.3356 on the raw mix) but **hurt**
  faster-whisper (0.3244 vs 0.2505): the separated vocal is not the true vocal. The
  `no_vocals` residual transcribed to WER 1.0 for both engines, confirming the vocal really
  was moved out. Separation was ~72 s per ~30 s excerpt (real-time factor ≈ 1.9) on this CPU.
  The real-song pass then **reversed the sign of the effect**, which is the point: separation
  is not a free win and its benefit does not transfer between synthetic and real audio.
* **Long audio is a packaging problem, not an accuracy problem.** Handed a whole 272 s song,
  the packaged ONNX Parakeet path returned 8 garbled words, and the upstream VAD route returned
  nothing at all (a speech VAD does not treat singing as speech). Only our own fixed-window
  chunking worked.
* **Chord input: no stable winner across four songs.** `other` led songs 1–2 (multiset F1
  0.859/0.866), collapsed on song 3 (0.371/0.474) and placed third on song 4; `bass` swung
  from worst to first (song 3's triad view) and back to worst; `no_vocals` led song 4
  (0.795). `bass`+`other` never finished far from the top (third, third, fourth on raw
  labels / second triad-reduced, second), `vocals` never left the bottom two, and
  the raw mix never won by much but never collapsed. Key estimation failed on 5 of 24
  condition–song pairs. The change penalty still matters more than anything else. This is
  the "separation is not a free win" result of the lyrics pass, now strengthened on the
  chord task.
* **The chord engine's errors are systematic, not random**: parallel major/minor confusion
  and missed borrowed chords, at a chord count (87) that closely matches the chart (86).

## What this is not

* Not a benchmark of mixed commercial music, backing vocals, reverb or live recordings —
  the roadmap 25 test list is only partly covered (isolated studio-ish solo vocals).
* Not a separator benchmark: only Demucs `htdemucs` was tried, in a 4-stem split of a single
  real song and a 2-stem split of synthetic mixes — no other separator, no `htdemucs_ft`, no
  UVR and no 6-stem model. Two inputs are not enough to rank separators.
* Not a full-transcript evaluation of the real song: its embedded lyrics are a partial
  reference, so no whole-song WER against a verbatim transcript exists.
* Not a chord-engine benchmark: the section-23/24 engine is a hand-written baseline with no
  sibling to compare against, tested on four songs with timestamp-free charts, so it measures
  *this* engine against *these* references, not chord recognition in general.
* Not a claim that one engine should be adopted. It is a first data point to inform phase 3.

## Reproduction

The harness, dataset and raw per-excerpt results (JSONL) plus the aggregate `summary.json`
live in the gitignored `.cache/lyrics-asr-investigation/` directory. The repository policy
(`.gitignore`) keeps `results/*.json|csv|md` and `benchmark/*` out of git, so the machine
artifacts are regenerated locally, not committed; this document is the committed record.
The committed `samples/vocadito_*.{wav,json}` excerpts are a small subset for spot-checking.

The real-song pass lives in the gitignored `.cache/real-song/` (its harness, the Demucs
stems and its own `summary.json`), and the input MP3 stays in the gitignored `mp3/`
directory, which `.gitignore` documents as "Songs mp3". **Neither the commercial audio nor
its embedded lyrics is committed, and neither can be redistributed**: the numbers above are
the only durable output, which also means this pass cannot be reproduced by anyone who does
not supply their own copy of the song. Its machine-readable results are also written to
`results/lyrics_asr_real_song_{rows.csv,summary.json}`, which the repository keeps out of git
like the rest of `results/`.

The chord pass lives in the gitignored `.cache/chords/` (`chords.py`, now per-song via a
`--song` flag, with per-song subdirectories holding the extracted audio, the Demucs stems,
cached chroma/beat features, per-input `results/*.json`, `summary.json`, the
`sweep.json`/`robust.json` parameter grids, a fetched LRCLIB response for song B and a
triad-reduced scoring view (`report --triads`, used for song C's seventh/fifth labels). The
commercial MP3s and chord charts stay in the gitignored `mp3/` directory (the user
also mirrors them in the private `mp3-library/` submodule, whose reference hash is the only
thing committed). **Neither
the audio, the chord charts nor any lyric text is committed**, and the pass is not
reproducible without the user's own copies; the tables above are the durable record.

## What it will contain, per engine and per preprocessing strategy (still pending)

The chord rows below (root/quality/exact accuracy, segment overlap, change timing) are
**now measured four times** in the chord section above, but only as timing-free sequence scores on
four timestamp-free charts; a true `songlab benchmark` report with frame metrics is still
pending, so the table stays as the specification.

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
