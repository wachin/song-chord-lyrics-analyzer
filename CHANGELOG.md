# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

### Research

* Completed the phase 1 dependency research for every candidate needed before the
  first analysis phases, with each fact sourced (package metadata, upstream
  `LICENSE`/`COPYING`, model card, or vendor licence page) and dated.
* **Adopted** (as optional extras, when their phase arrives): numpy, scipy,
  librosa, soundfile, music21, faster-whisper, beat_this. **PyQt6** confirmed
  compatible with GPL-3.0-or-later for phase 15, with PySide6 recorded as the
  permissive alternative. **basic-pitch** is adopted with a condition: it is
  Apache-2.0 and works, but its official install path is broken on Python 3.12+.
* **Rejected**: madmom (the PyPI release does not build on Python 3.13, and its
  model files are CC BY-NC-SA 4.0) and Essentia (AGPL-3.0-only library, MTG
  models CC BY-NC-SA 4.0, no Windows support).
* **Never bundle**: Demucs pre-trained weights (upstream licence question still
  open, repository archived 2025-01-01), Chordino and Sonic Annotator
  (GPL-2.0 external executables).
* Recorded that current numpy/scipy/librosa releases require Python >= 3.12, so
  DSP extras effectively raise the floor above the core's 3.10.
* Remaining open questions are listed explicitly: Windows/macOS runtime is
  unverified, no `songlab benchmark` report exists yet (only investigation harnesses,
  on synthetic material and on real music), unverified weights (torchcrepe, Spleeter,
  UVR), and the GPL-2.0 "only" vs "or later" question for the Vamp plugins.

### Smoke-tested

Each adopted dependency was installed in a throw-away virtual environment and
exercised with generated audio (a tone, a C major triad and a 120 BPM click
track). Full detail: `docs/DEPENDENCY_MATRIX.md` §10.

* **soundfile 0.14.0** — metadata, read, and a sample-exact WAV->FLAC->read round
  trip in 8.9 ms.
* **librosa 1.0.0** — `chroma_cqt` ranks C/E/G correctly on a C major triad;
  `beat_track` reports 117.45 BPM on a 120 BPM click track. Cold calls carry a
  numba JIT cost (`chroma_cqt` 1524 ms cold vs ~110 ms warm).
* **beat_this 1.1.0** — exactly 120.00 BPM and 16/16 beats, 0.7-0.8 s of CPU for
  8 s of audio, on CPU-only torch. Its 81 MB checkpoint auto-downloads to
  `~/.cache/torch/hub`, so the adapter must redirect `TORCH_HOME` into our cache
  and announce the download.
* **basic-pitch 0.4.0** — the documented install **fails on Python 3.12/3.13**
  (`tensorflow<2.15.1` is unsatisfiable there). The model bundled in the wheel
  was run through ONNX instead (`--no-deps` + `onnxruntime`) and detected exactly
  C4/E4/G4.
* Cross-platform **wheel availability** for Python 3.13 was verified for Linux,
  Windows and macOS arm64; **runtime stays Linux-only** and is reported as such.
  No accuracy claim is made: a click track and a synthetic triad are not a
  benchmark.

### Lyrics ASR investigation (roadmap 25/26/27)

A first measured comparison of singing-voice recognition, run on the CPU-only
reference machine (Intel Core i3-7020U, 7.6 GiB RAM) and recorded in
`docs/ENGINE_COMPARISON.md`. It is an investigation by a temporary harness, not a
`songlab benchmark` run.

* Compared **Faster-Whisper 1.2.1** (`small`, int8) against **NVIDIA Parakeet TDT
  0.6B v3** through **onnx-asr 0.12.0** + onnxruntime (int8 ONNX). The ONNX path is
  the light CPU route and was chosen over `nemo_toolkit`; that resolves the open
  Parakeet-packaging question in `docs/DEPENDENCY_MATRIX.md` §12.
* Dataset: all 40 excerpts of **vocadito** (CC-BY-4.0, multilingual solo singing with
  annotated lyrics). Four excerpts and their lyric sidecars are committed under
  `samples/`; the rest stays in the gitignored `.cache/`.
* On isolated vocals Parakeet reached WER 0.3722 / CER 0.1857 at a real-time factor of
  0.20, versus Faster-Whisper `small` at WER 0.3799 / CER 0.2725 and a real-time factor
  of 0.95 (peak RSS ~1.3–1.4 GiB each). Per-language results differ sharply: Parakeet
  is far better on English, Faster-Whisper is better on Tagalog and the single Spanish
  excerpt, and both fail on Mandarin.
* Mix vs isolated vocal (roadmap 26): on eight excerpts with synthetic accompaniment at
  three ratios, both engines degraded monotonically as the accompaniment grew, and the
  true isolated vocal was best (no separation error is involved, by construction).
* Real separation with **Demucs 4.1.0 `htdemucs`** (`--two-stems=vocals`, CPU; roadmap
  26/27): repeating the same eight conditions on the separated `vocals` stem did *not*
  reproduce the true-vocal win. The separated stem was worse than the raw mix for
  Faster-Whisper (WER 0.3244 vs 0.2505) and only slightly better for Parakeet (0.2991 vs
  0.3356), while the `no_vocals` residual scored WER 1.0 for both engines. Separation is
  engine-dependent, not a free win, and the mixes are synthetic (a caveat, since
  `htdemucs` is trained on real music). Demucs weights were used locally only and never
  bundled — their licence is still unresolved.
* **Long audio is a packaging problem (roadmap 25).** Given a whole 272 s song, the packaged
  ONNX Parakeet path returned 8 garbled words and the upstream VAD route returned *nothing*,
  because a speech VAD does not treat singing as speech; only our own fixed 20 s window
  chunking produced a usable transcription. Faster-Whisper windows long audio itself.
* **Real commercial mix, second pass (roadmap 26).** A user-supplied commercial MP3 (4 min
  32 s, kept in the gitignored `mp3/` and never committed, with its embedded partial lyrics
  as the reference) was separated with Demucs `htdemucs` (4 stems, 5 min 38 s) and transcribed
  from the raw mix, the `vocals` stem and the `no_vocals` residual. The raw mix **won or tied
  for both engines** — clearly for Parakeet (unique-token F1 0.737 vs 0.618), a wash for
  Faster-Whisper — so the synthetic conclusion does not transfer to real audio. The residual
  transcribed to 6 words for Faster-Whisper and to nothing for Parakeet, confirming the vocal
  left it.
* Not covered, and recorded as such: backing vocals, reverb, live recordings, heavy
  instrumentation, word-timestamp error (vocadito has no word-level ground truth), a
  larger Whisper (medium needed ~66 s per 30 s clip on this CPU and was stopped), the
  `vocals + selected accompaniment` case, a full verbatim transcript for the real song, and
  6-stem separation or `htdemucs_ft`/UVR alternatives.

### Chord recognition investigation (roadmap 23/24/27/28)

A first measured chord comparison, recorded in `docs/ENGINE_COMPARISON.md` ("Chords"). The
section-24.1 pipeline was re-implemented as our own baseline — HPSS + tuning-corrected
CQT/CENS chroma blend, 24 equal-weight triad templates, bass root/fifth boost, a
Krumhansl-Schmuckler key prior, beat-synchronous max-sum Viterbi and a palette-prior second
pass — running on **librosa 1.0.0** in a throwaway, gitignored environment. It is an
investigation, not a `songlab benchmark` run, and no chord adapter is registered in `src/` yet.

* The baseline was scored against a **user-supplied hand-written chord chart** (86 chords,
  8 distinct, key D major, no timestamps) for a second commercial MP3 supplied by the user
  (327 s, kept in the gitignored `mp3/`, never committed).
* Because the chart has no timestamps, scoring is **timing-free**: order-preserving sequence
  alignment (exact / root-only / quality-only precision-recall-F1), chord multiset and
  palette F1, and key agreement. No frame accuracy, segment overlap or change-timing error
  could be computed.
* Roadmap §27/§28 were exercised on the same Demucs 4-stem split: `original`, `vocals`,
  `other`, `bass`, `bass`+`other` and `drums`+`bass`+`other`. **All six recovered the
  correct key**, and **no stem was reliably best** — `other` led on multiset F1 at the tuned
  Viterbi change penalty (0.859 vs 0.809 for the mix), the raw mix led at a lower penalty and
  `bass`+`other` at a higher one. `bass` alone and `vocals` alone were clearly worst (bass
  recovers roots but not qualities). This repeats the lyrics pass's "separation is not a free
  win" finding on the chord task.
* Cost: ~38–40 s per 327 s song (real-time factor ≈ 0.12, peak RSS ≈ 1.04 GiB); the change
  penalty, not the input, was the dominant knob, and it was tuned on this same song — a
  recorded overfitting risk, so the stem ranking is indicative, not settled.
* **Second song (same day).** A third user-supplied commercial MP3 with its own hand-written
  chart (64 chords, only 4 distinct, key A major, no timestamps; 268.5 s, kept in the
  gitignored `mp3/`) was run through the unchanged pipeline at the penalty held over from
  the first song. All six inputs again recovered the correct key, and the ranking **repeated**:
  Demucs `other` first (multiset F1 0.866, palette 0.889; all 4 reference chords recovered
  with one false parallel `Em`), the raw mix second (0.688), `bass` (0.308) and `vocals`
  (0.579) last. At a higher penalty `other` reaches multiset F1 0.924 with a perfect palette
  match. Cost ~33–34 s per 268.5 s (RTF ≈ 0.12, peak RSS ≈ 0.90 GiB). With n = 2, `other`
  looks like the better chord input and the tuned penalty transferred across songs; a
  synced-lyrics check against the free LRCLIB API was also made for this song (both a plain
  and a line-timed variant exist and match its duration), recorded as an input option for
  future lyric passes, not as a result.
* **Third song (same day).** A fourth user-supplied commercial MP3 with its own hand-written
  chart (101 chords, 8 distinct, key A minor, 254.3 s; the first chart with seventh and
  fifth labels — `D7`, `E5` — which a triad-only decoder cannot emit, so scoring also uses
  a documented triad-reduced view of the reference). The held penalty transferred again,
  but **the n = 2 stem ranking inverted**: `other` (first twice) collapsed to
  second-to-last (multiset F1 0.371 on the chart's labels, 0.474 triad-reduced), while
  `bass` (last twice) led the triad view (0.707) — the song's bass-led solo-guitar style
  rewards the bass stem. For the first time **three of six inputs mis-estimated the key**
  (E minor for an A-minor song), and the raw mix was again the most consistent input.
  Conclusion back to *no stem is reliably best*, with the raw mix the safest
  no-separation choice; detected chord counts matching the reference (98 vs 101) proved no  guarantee of accuracy.
* **Fourth song (same day).** A fifth user-supplied commercial MP3 with its own hand-written
  chart (79 chords, only 4 distinct, key E major, plain triads; 296.8 s) — the first song
  taken from the user's private `mp3-library` submodule, which now feeds the harness
  directly. `no_vocals` led (multiset F1 0.795) with `bass`+`other` second (0.780), `bass`
  alone was worst again (0.649), and **the raw mix mis-estimated the key for the first time**
  (B major for an E-major song — the dominant-heavy chart pulled it; `vocals` failed the
  same way). With n = 4: `bass`+`other` is the steadiest stem input (second or third on
  three songs, fourth only on song 3's raw-label view), `vocals` never left the bottom two,
  and `other`'s best penalty on this song
  was 0.30 (0.822), not 0.40. Cost ~35–36 s per 296.8 s (RTF 0.12, peak RSS ≈ 0.95 GiB).
* **Fifth song (same days).** A sixth user-supplied commercial MP3 with its own hand-written
  chart (85 chords, 12 distinct — the richest vocabulary yet; first chart with an in-song
  modulation, D major → E major on the final chorus; `D7`/`E7` labels scored against a
  triad-reduced reference; 315.7 s). **The raw mix won for the first time** (multiset F1
  0.778, palette 0.857; 0.811/0.947 triad-reduced) with `bass`+`other` second (0.770) and
  `bass` worst (0.552) — five songs, four different winners. `vocals` mis-estimated the key
  to the relative (F# minor), and the modulating chart itself estimates A major (V of D,
  IV of E), softening key scoring for this song; 6 of 30 condition–song pairs get the key
  wrong overall. The 0.40 penalty transferred to songs B–D but song E's mix peaks at 0.50
  (0.829). Cost ~38–42 s per 315.7 s (RTF 0.12–0.13, peak RSS ≈ 0.98 GiB).
* **Engine v2 (2026-09-28), informed by Chordify's own repositories.** After all 35 public
  `github.com/chordify` repos were mounted as read-only references, the chord-relevant
  ones were read for **ideas only — no code copied**: `HarmTrace-Base` (LGPL-3.0)
  suggested rewarding the *fraction* of a chord's tones inside the estimated key instead
  of only its root (plus a conditional leading tone in minor keys), and `AceEval` and
  `tapcorrect` supplied metric/decoding ideas that stay recorded as candidates. The
  engine now also runs a **gated two-pass key estimate**: a legacy-prior probe, a
  duration-weighted chroma re-estimated with Krumhansl-Schmuckler, adopted only when the
  mode is unchanged and the correlation holds. Measured as a **nine-configuration
  ablation** over 5 songs × 6 inputs, the default v2 configuration raises the aggregate
  exact F1 **0.534 → 0.575** (triad-reduced **0.568 → 0.597**, multiset **0.655 → 0.691**)
  and key agreement **24/30 → 27/30** (the raw mix now gets all five keys right).
  Always-adopt/averaged key modes were measured worse (25/30), and the 12 optional
  dominant-seventh templates were measured and **rejected** (0.531 vs 0.534 on v1,
  0.570 vs 0.575 on v2). The hyper-parameters were selected on these same five songs, so
  the gain is recorded as in-sample. Every chord table in `docs/ENGINE_COMPARISON.md`
  was regenerated; the adoption record is in `docs/DEPENDENCY_MATRIX.md` §13.12.
* **tapcorrect's transition smoothing measured and rejected (2026-09-28).** The
  `tapcorrect` repo (ISMIR 2019) suggests Viterbi transitions that decay with state
  distance (`T[i,j] = exp(-λ|i-j|)`), implemented in the harness as
  `cost(i→j) = λ·d(i,j)` with `d` on the chromatic circle or the circle of fifths
  (+0.5 for a quality change, 1.0 for no-chord). 16 configurations (λ 0.40–2.00 × both
  metrics, plus flat 0.30/0.40/0.50) × 5 songs × 6 inputs: the best distance row
  (fifths, λ 0.40) reaches exact F1 **0.549 vs 0.575** for the shipped flat penalty,
  never closes the gap at chord-count-matched λ (0.531 vs 0.605), and only buys +2
  correct keys (25/30); chromatic is strictly worse than fifths. The run also exposed
  that the harness's legacy flat loop mutates `dp` in place while iterating states and
  **misses its own optimum** (brute-force verified): the corrected loop wins on
  exact/palette F1 but loses on multiset/key (where the gate and bonus were tuned on
  it), so the legacy loop stays the default — every recorded artifact reproduces
  byte-identically — and re-tuning the engine around the corrected loop is recorded as
  an open question. Tables in `docs/ENGINE_COMPARISON.md`, verdict in
  `docs/DEPENDENCY_MATRIX.md` §13.12.
* **AceEval's MIREX metrics implemented (roadmap 44, 2026-09-28).** `mirex2010` equality
  (pitch-class intersection ≥ 3, ≥ 2 for an augmented/diminished ground truth, +1 bass
  boosts, `N` only matches `N`) is re-implemented from the source we read and wired into
  the sequence alignment as a fourth scoring view: mean F1 **0.636** over 5 songs × 6
  inputs vs **0.575** for the historical exact view. The gain splits into +0.017 from the
  equality (`D7`/`E7` now match `D`/`E`; power chords like `E5` still cannot) and
  **+0.044 from a max-match tie-break** that the control measurement exposed —
  Needleman-Wunsch had been reconstructing arbitrary minimum-cost paths. Historical views
  keep their rule so every recorded number still reproduces and rankings are unaffected,
  but `songlab benchmark` should adopt the max-match rule. The duration-weighted **Chord
  Sequence Recall** (`crossSegment` + equal/not-equal durations) is also implemented and
  validated on a hand-computed fixture (11/16 = 0.6875), yet cannot run on real songs:
  the charts have no timestamps (roadmap 43) and reference timings will not be invented.
  Per-stem winners under MIREX change only on song C (`bass`+`other`, agreeing with the
  triad-reduced view). Tables in `docs/ENGINE_COMPARISON.md`, verdict in
  `docs/DEPENDENCY_MATRIX.md` §13.12, status in roadmap §44.
* **CSR runs on real songs; timestamped-source search recorded (roadmap 43/44,
  2026-09-28).** The duration-weighted Chord Sequence Recall left the fixture. In
  **agreement mode** — each Demucs stem's timed output against the raw mix's, no ground
  truth needed — it scored all five songs (`csr` command, per-song `csr.json`): mean CSR
  `no_vocals` **0.744** > `bass`+`other` 0.692 > `bass` 0.519 > `other` 0.515 > `vocals`
  **0.400**, with `no_vocals` first on 4 of 5 songs and `vocals` last on 4 of 5 — the
  separation-is-not-a-free-win result now holds on chord *timing* too (agreement, not
  accuracy: a stem can agree with a mix that is wrong the same way). The **accuracy
  mode** is implemented as well (`csr --ref song.jams`, with a JAMS loader that converts
  Harte labels like `Bb:min`/`F#:7/5` to the canonical form, fixture-tested) but has no
  input: the charts carry no timestamps. The search for timed sources found none with
  audio *and* a permissive licence — **CASD** has 50 songs × 4 annotators with real
  times (verified locally in `external/chordify-org/CASD/`) but is CC BY-NC-SA 4.0 and
  ships no audio (only `youtube_url`s), and **ChoCo** offers 20,080 timed JAMS files
  under CC BY 4.0 (most partitions) but also no audio. Both are recorded with their
  routes forward in `docs/DATASET.md`: pair a licensed timed chart with audio the user
  owns, or hand-annotate boundaries on one of our charts with provenance. Verdicts in
  `docs/DEPENDENCY_MATRIX.md` §13.12, statuses in roadmap §43/§44.
* **Duration CSR measured against real ground truth (roadmap 43/44, 2026-09-29).** The
  accuracy mode left the fixture. **ChoCo** v1.0.0 was fetched first (179 MB, 20,086
  JAMS) as an annotation index — its audio partitions are Beatles/Billboard/jazz/RWC-Pop/
  Schubert, its `meta.csv` intersects the user's five charts in **zero** songs — and its
  loader path was validated on real Isophonics/Billboard/CASD/JAAH files (segment
  coverage matches every metadata duration). Audio came from **GuitarSet** (Zenodo
  10.5281/zenodo.3371780, v1.1.0, **CC BY 4.0**, MD5s verified; 360 excerpts of real
  acoustic guitar with 16 timed JAMS annotations each) — the first source found with
  audio *and* chord boundaries under a permissive licence. A 24-excerpt sample (6 players
  × 5 styles, comping takes, 14–46 s, ~11 min of audio) gives the first duration CSR
  scored against real reference timings: **mean 0.476** against the instructed lead sheet
  and **0.465** against the triad-reduced performed voicings (raw performed 0.412, best
  median 0.511), with exact F1 0.577 and key agreement 17/24. Findings recorded: scoring
  the triad decoder against the *performed* jazz voicings costs ~0.06 CSR before
  triad-reduction; one excerpt collapses to a single chord (smeared chroma from
  `B7(13,*5)/A`-style voicings plus the flat change penalty, the same decoder weakness as
  the tapcorrect study); four more sit below 0.2; and four of the seven key misses are
  the documented relative major/minor confusion. Harness additions (gitignored):
  GuitarSet song entries, chart auto-derivation from the instructed annotation,
  `--ref-index`, and CSR rows for both annotation views. Tables in
  `docs/ENGINE_COMPARISON.md`, source records in `docs/DATASET.md`, verdict in
  `docs/DEPENDENCY_MATRIX.md` §13.12, statuses in roadmap §43/§44.
* **The CSR sweep was extended to all 360 GuitarSet excerpts (2026-09-29).** A
  resumable driver (`guitarset_all.py` → `guitarset_all.jsonl`, aggregated by
  `guitarset_aggregate.py`) decoded every take, 0 failures. The 24-excerpt sample turned
  out **mildly optimistic**: the other 156 comping takes move instructed CSR 0.476 →
  **0.457**, the performed-triad view 0.465 → 0.423 and exact F1 0.577 → 0.541, because
  the sample over-weighted the two strongest players. The comping takes (180) are the
  meaningful chord test; the **soloing** takes (180) are a negative control — the mic
  records a melody over headphones-only comping — and the CSR correctly collapses there
  (0.198, keys 33 %), which is evidence the metric measures the right thing. Style order
  tracks harmonic density (Singer-Songwriter 0.485 > Rock 0.378 > Bossa 0.314 > Jazz
  0.262 > Funk 0.197), 8 takes collapse to one chord and 26 score 0.000, and key
  agreement on comping takes is 58 % against 90 % on the five user songs. Full tables in
  `docs/ENGINE_COMPARISON.md`.
* **The 8 single-chord collapses were ablated — measured, fix identified, not adopted
  (2026-09-29).** Every take was re-decoded over a `change_penalty` (0.15–0.60) ×
  `palette_pass` × `viterbi_impl` grid (all 360 takes, plus the five songs × six inputs;
  `guitarset_ablation.py` / `song_ablation.py` in the gitignored harness). Verdict: the
collapses are a **penalty artefact of the legacy in-place Viterbi loop, not a decoder
  bug** — at the nominal 0.40 the *corrected* loop collapses more takes (28 vs 8) because
  it finally charges the penalty the legacy loop under-collects, and within each loop the
  collapse count is monotone in the penalty. The measured best combination is the
  corrected loop at flat penalty **0.20**: GuitarSet comping CSR 0.457 → **0.524**,
  collapses 8 → **3** (the worst take, one `G#m` for 14.4 s, moves 0.000 → 0.083),
  soloing negative control unchanged (0.198 → 0.191); on the five songs exact F1 0.575 →
  **0.610**, triad-reduced 0.597 → **0.640**, multiset 0.691 → **0.707**, palette 0.760 →
  0.797. The single regression is **key agreement 27/30 → 23/30**, because the two-pass
  key gate and the diatonic bonus were tuned on the legacy loop. The production default
  therefore stays `legacy + 0.40` (byte-reproducible artifacts); re-tuning the key gate
  around the corrected loop is the recorded next step before adoption. Tables in
  `docs/ENGINE_COMPARISON.md` ("Collapse ablation"), verdict in
  `docs/DEPENDENCY_MATRIX.md` §13.12, statuses in roadmap §43/§44.
* **The key gate was re-tuned around the corrected loop and engine default v3 was
  promoted (2026-10-01).** The collapse fix's one regression — five-song key agreement
  27/30 → 23/30 — turned out to be a *circularity*, not a tuning problem: stage 1 of
  the two-pass key gate probed with the segment decoder itself, so re-tuning that
  decoder moved the key estimate out from under the gate. The gate's probe now runs on
  the shipped v2 reference decoder (`legacy` loop, flat 0.40) while the segment decoder
  takes the corrected matrix loop at the re-tuned flat penalty **0.20**. Measured on the
  five songs × six inputs: exact F1 0.575 → **0.614**, triad-reduced 0.597 → **0.642**,
  multiset 0.691 → **0.716**, keys held at **27/30**; GuitarSet comping (180 takes)
  instructed CSR 0.457 → **0.521** and single-chord collapses **5 → 2**, soloing
  negative control flat. This was promoted as **engine default v3** in the harness; the
  legacy loop stays as the pinned probe and for byte-reproducibility of the v2
  artifacts. Before promoting anything, the harness's scoring semantics — chord
  pitch-class sets (bracket-voicing tuples replace the base voicing; out-of-vocabulary
  heads re-parse and fall back major/dominant), triad reduction (every quality
  collapses to its root or minor root; `E5`/`Ehdim7`/`A#m11` reduce to root), and
  MIREX equality (an intersection of 2 is rescued when the reference's non-root bass
  — a Harte degree slash like `D#/5` — sounds in the hypothesis) — were re-fitted to
  and verified against the pre-destruction oracle log: **88/88** duration-CSR targets
  (44 raw + 44 triad), the fixture case list extended with the rescue rules, and the
  instructed view of the 360-take sweep identical  (the performed view keeps 37
  documented per-take residuals on out-of-dictionary jazz voicings, without affecting
  any recorded mean beyond ±0.002). Tables in `docs/ENGINE_COMPARISON.md` ("Collapse
  ablation" and "Engine default v3"), verdict in `docs/DEPENDENCY_MATRIX.md` §13.12,
  statuses in roadmap §43/§44.
* **The verified scoring semantics moved into the package and the CSR oracle was
  committed as a pytest fixture (2026-10-01).** The harness's fitted implementations —
  `harte_to_label`, `chord_pcs`, `triad_reduce`, `mirex_equal`, `duration_csr` — now
  live in the new `song_chord_lyrics_analyzer.evaluation` subpackage (built only on the
  existing normalization/models modules), and the gitignored harness re-exports them as
  the single source of truth: re-running `song_ablation.py` and re-decoding all 360
  GuitarSet takes under v3 reproduced every recorded mean byte-for-byte. The oracle log
  itself became `tests/fixtures/csr_oracle.json`: 22 GuitarSet comping takes × both
  annotations × raw/triad views, each with the raw Harte reference observations, the
  v2-default hypothesis segmentation and the 88 expected duration-CSR targets, plus
  per-take tolerances, the label vocabulary and the dataset provenance (GuitarSet,
  CC BY 4.0, recorded inside the JSON; no audio is committed). The new
  `tests/unit/test_csr_oracle.py` (116 tests) re-scores every fixture target from the
  package implementation and pins the corner rules the oracle forced: the bass rescue
  and its failure modes (`F/1` denies, `C/E` vs `Cm` returns exactly 0.0), bracketed
  voicing tuples replacing the base voicing and opting out of the rescue, the
  augmented/diminished threshold of 2, triad reduction collapsing `A#m11` to its root,
  and the `E9(*1)/3` empty-voicing corner. Pytest's `pythonpath` now lists `tests/`
  explicitly so the fixture modules resolve deterministically. Full suite: 335 passed,
  1 skipped (environment-dependent executable test).
* **The chord metric suite is now library code (2026-10-03).** The new
  `song_chord_lyrics_analyzer.metrics` package (roadmap §44, phase 11) exposes the
  timing-free views — `align`, a dependency-free Python Needleman-Wunsch alignment, and
  `evaluate`, returning the exact/root/quality/MIREX F1 triples plus multiset F1,
  palette F1 and the hypothesis chord count — and the timing-aware boundary views —
  `segment_overlap` (MIREX `MeanSeg`), `chord_change_detection` (boundary hit-rate
  precision/recall/F at 0.5 s and 0.25 s) and `timing_error` (median change-point
  deviation). All re-use the scoring semantics already shipped in `evaluation/` (and
  re-export `duration_csr` for a single chord-metrics surface), and none adds a core
  dependency: the boundary metrics are re-implementations of published definitions, not
  new inventions. Nothing is wired to the engines or the CLI yet.
  `tests/fixtures/chord_metrics_oracle.json` records 11 hand alignment cases and 88
  evaluations produced by the original NumPy harness, plus 44 segmentation cases
  produced by `mir_eval` 0.8.2, all over the committed GuitarSet takes (labels/segments
  rebuilt from `csr_oracle.json`); the new `tests/unit/test_chord_metrics.py` (115 tests)
  and `tests/unit/test_chord_segmentation.py` (55 tests) reproduce every value. The
  canonical model is now wired to them too: `metrics/adapters.py` adds
  `chord_labels` (the label sequence from `ChordEvent` objects) and
  `chord_segments` (timed `(start, end, label)` triples, filling a missing end from
  the next chord's start), so a pipeline no longer re-implements the extraction.
  No boundary is invented (roadmap §43): an undetermined end, a reversed interval
  or overlapping events raise instead of being silently mis-scored. Covered by
  `tests/unit/test_chord_adapters.py` (16 tests). Full suite: 521 passed,
  1 skipped.

### Reference repositories

* Added `external/`, holding third-party study references as read-only git submodules, plus
  `scripts/add_external_repos.sh` to add or refresh them. They are study material:
  never imported, packaged, installed, linted, type-checked or tested, which is now
  enforced by exclusions in `pyproject.toml` (verified by planting a lint-broken file
  and a failing test in `external/` and confirming the gates stay green).
* Added `AGENTS.md` and `external/README.md`, whose first rule is that `external/` is
  a set of reference repositories and not a library of this project.
* Expanded the pool to 32 repositories (2026-09-24) in four blocks — 12 chord,
  practice-tool and visualization projects, 12 instrument-recognition and detection
  projects, 5 transcription/audio identification projects and 3 cross-cutting music
  libraries — with `yuval-kahan/Chords.py` added after the first batch missed it.
  Licences were read from each clone's licence file and are recorded as observations
  (not audits) in `external/README.md`.
* Repaired the `ChordMiniApp` clone after its checkout failed: upstream's Git LFS
  budget is exhausted, so its model checkpoints cannot be downloaded. The code was
  checked out with `GIT_LFS_SKIP_SMUDGE=1` (checkpoints stay as pointer files) and the
  limitation is documented in `external/README.md`.
* Established the cleanup rule: `external/` is a temporary research pool that must
  shrink, not grow — after a repository is investigated and its verdict recorded, the
  submodule is deleted unless still needed.
* Recorded that the section 24.2 URL (`yuval-kahan/youchords-local`) returns HTTP 404
  (checked 2026-09-23). On 2026-09-24 the section was dropped from the roadmap
  entirely: the repository no longer exists on GitHub, and section 24 now lists
  exactly the 13 repositories registered under `external/` — 24.1 (chordify), 24.5
  (research baseline), 24.6 (MOSS-Music) and a new compact 24.7 table for the
  remaining registered clones.
* Investigated the block 1 chord references against the section 24 bullets by reading
  the clones (2026-09-24); verdicts are recorded in `docs/DEPENDENCY_MATRIX.md` §13.
  `1ucas/chordify` is confirmed as the primary architectural reference, with its full
  pipeline documented bullet by bullet (HPSS + tuning-corrected CQT/CENS chroma blend,
  equal-weight triad templates, two-pass bass- and key-aware Viterbi, song-palette
  prior, conservative slash/extension display). The ideas worth keeping from
  `chordscope` (windowed modulation tracking, tempo-curve classification) and from the
  unlicensed `orchidas/Chord-Recognition` baseline (chroma → templates →
  Gaussian-emission HMM with Viterbi) are recorded as candidates to re-implement as
  original code.
* Applied the `external/` cleanup rule for the first time: removed `chord-extractor`
  (wraps the GPL-2.0 Chordino Vamp stack already classified as never-bundle),
  `Chord-recognition` (a superseded, unlicensed course project), `scales-chords`
  (an Obsidian plugin, off scope) and `chordscope` (its core beat/chord engine is
  madmom, already rejected). The pool went from 32 to 28 submodules.
* Investigated blocks 2 (instrument recognition, 12 clones) and 3 (transcription,
  audio identification and other, 5 clones) with the same verdict-per-clone method.
  Block 2 kept only the two paper-backed MIT repositories (`instrument-prediction`,
  ISMIR 2018 frame-level recognition; `predominant-instrument-recognition`, APSIPA
  ASC 2023 NSynth-pretrained polyphonic recognition) — ten were course projects and
  notebooks without any licence file. Block 3 was removed entirely: `muscriptor`
  carries **CC BY-NC 4.0 weights** (the same non-commercial pattern that rejected
  madmom and Essentia), `presto`/`shazam-build`/`audd-go` address song
  identification this offline-first project does not have, and `Ear` is an LLM demo.
  The pool went from 28 to 13 submodules; every removed pin remains recoverable
  from git history.
* Closed roadmap §24.7 (2026-09-24) by investigating the last clones that still lacked
  a verdict and applying the cleanup rule once more; the verdicts are in
  `docs/DEPENDENCY_MATRIX.md` §13.10. **Kept** `musicpractice` (MIT, a PySide6 desktop
  app whose `chords.py` is a readable template + Viterbi chord engine with
  Krumhansl-Schmuckler key estimation, using Demucs and Basic Pitch — the closest
  blueprint for phase 15) and `Guitariz` (MIT, whose `ml/` package is a from-scratch
  109-class chord CRNN with a shared CQT-chroma extractor, a synthetic-data generator
  and an adaptive-self-transition Viterbi). **Removed** `Chords.py` (unlicensed 2021
  MLP, 10 classes, `.h5` weights of undocumented provenance), `ChordVisualizer` (a
  Vue/WASM play-and-name theory toy with no audio analysis) and `ChordMiniApp` (a
  cloud Next.js/Firebase stack whose nested model submodules are uninitialized and
  whose LFS checkpoints are absent upstream). The pool went from 13 to 10 submodules.
* Closed roadmap §24.6 (2026-09-24) with a **feasibility verdict instead of a benchmark**,
  because MOSS-Music cannot be run here. Reading the clone and the released weights (via the
  Hugging Face API) showed: ~9.1 B parameters (Qwen3-8B plus a 32-layer audio encoder), four
  bf16 shards totalling **18.11 GB**, no quantization path, a CUDA-only supported runtime and
  bandwidth-bound autoregressive decoding — so it is **not viable on commodity CPU** for this
  CPU-first project. Its code also has no root `LICENSE` (only the weights are Apache-2.0) and
  loading it requires `trust_remote_code=True`. The architecture ideas worth reading
  (DeepStack cross-layer injection, time-marker insertion) are recorded in
  `docs/DEPENDENCY_MATRIX.md` §13.11, and the submodule was removed. The pool went from 10 to
  9 submodules.
* Mounted **all 35 public repositories of the Chordify organisation**
  (`github.com/chordify`) as shallow read-only submodules under `external/chordify-org/`
  (2026-09-27), the company's own source as study material for the chord engine. They are
  almost entirely Haskell plus two Python research repos; the chord-relevant ones
  (`HarmTrace-Base`, `AceEval`, `tapcorrect`, `CASD`) were read on 2026-09-28 and the
  ideas that survived measurement were implemented ourselves as engine v2 (see the chord
  investigation entry above); `docs/DEPENDENCY_MATRIX.md` §13.12 holds the per-repo
  verdicts. Same rules as every `external/` clone: never imported, executed or copied.

### Documentation

* `ROADMAP.md` now tracks its own progress with bracket markers: `[x]` for work
  already achieved when the convention was introduced (2026-09-23), `[ ]` for
  work still open, and `[*]` for work completed afterwards, which must carry its
  completion date. Every section, subsection and task carries a marker.
* 25 sections whose work is partly done say so in an italic *Status* line rather
  than pretending to be finished, and the phase sections, both definition-of-done
  checklists and the 20 completion criteria are now ticked item by item.
* No roadmap item was finished by the marker-convention change itself; the first
  `[*]` markers appeared on 2026-09-24 (roadmap §24.5, later followed by §24.7), and
  the date was recorded here so the first one could be checked against it.

## [0.1.0] - 2026-09-23

Phase 0 (repository bootstrap) plus the first tasks from the roadmap. No
analysis engine is integrated yet.

### Added

* `src/` package layout with the `songlab` console entry point.
* Canonical typed data model: `AudioDocument`, `LyricSegment`, `LyricWord`,
  `ChordEvent`, `BeatEvent`, `DownbeatEvent`, `BarEvent`, `KeyEstimate`,
  `TempoEstimate`, `NoteEvent`, `Stem`, `EngineInfo`, `EngineResult`,
  `AlignmentResult`, `AnalysisRun`, `AnalysisResult`, `Provenance` and
  `ConfidenceScore`.
* Engine protocols (`ChordEngine`, `LyricsEngine`, `BeatEngine`, `KeyEngine`,
  `TempoEngine`, `StemSeparationEngine`), options objects and an
  `EngineRegistry` that reports availability and provenance.
* Chord label parsing, rendering and transposition, with unrecognised labels kept
  as `OTHER`/`UNKNOWN` instead of being upgraded to false precision.
* Canonical JSON codec with a `schema_version` envelope and typed round trips.
* Audio foundation: input validation, cross-platform FFmpeg/ffprobe discovery,
  metadata probing through `ffprobe` with a standard-library WAV fallback, and
  SHA-256 hashing for caching and provenance.
* CLI: `songlab --help`, `--version`, `--verbose`, `--quiet`, `--debug`,
  `songlab info [--json] [--hash]` and `songlab doctor [--json]`, with
  actionable error messages and documented exit codes (2 = input, 3 = missing
  dependency).
* Cross-platform path helpers (cache, data, models, exports, temp) with
  `SONGLAB_*` overrides and no hard-coded system paths.
* Documentation: architecture, development guide, dependency matrix (with an
  explicit verification status per candidate), licence audit, internationalization
  plan, troubleshooting, and outlines for the comparison, benchmark, dataset and
  GUI documents.
* Tests: 220 tests covering models, chord normalization, the JSON codec, the
  registry, paths, timestamps, errors, audio validation and probing, the CLI
  contract, plus FFmpeg integration tests that skip when the tool is absent.
* GitHub Actions CI across Linux, Windows and macOS on Python 3.10-3.13, with
  linting, formatting, type checking and a dedicated FFmpeg integration job.

### Notes

* The core package has no runtime dependencies.
* Madmom is reported as restricted to Python < 3.10 and is therefore not adopted;
  see `docs/DEPENDENCY_MATRIX.md`.
* No accuracy claim is made anywhere: nothing has been benchmarked yet.
