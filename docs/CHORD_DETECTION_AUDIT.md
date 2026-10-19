# Chord Detection Audit

**Status:** read-only audit, 2026-10-18. No engine, model, dependency, test or
configuration was changed to produce this report.

**Scope:** the chord path that runs today, from an audio file on disk to the
chord label drawn under the playhead, plus the tests that exercise it and a
prioritized plan for improving it.

**Method and limits.** Every statement below was checked by reading the
repository at commit `25643b0` and by running the targeted tests listed in
§8.2. The GUI session that prompted this audit was performed and reported by the
**user** on MX Linux 25; this audit did not run the GUI, play a song or listen to
its chords, so no accuracy observation here is the auditor's. Numbers attributed
to previous measurements are cited to the document that records them and were
**not** re-measured.

---

## 1. Executive summary

The chord path is a small, honest, fully inspectable baseline, not a learned
chord model:

1. decode to mono 22.05 kHz through the shared decode service;
2. one CQT chromagram (`librosa.feature.chroma_cqt`, hop 2048);
3. cosine similarity of every frame against **24 root-position triad
   templates** (12 major + 12 minor) plus one constant no-chord score;
4. max-sum Viterbi over 25 states with a **flat** change penalty (default
   `0.80`), or an optional majority smoother;
5. collapse equal-label runs into segments on the frame grid;
6. sort the events and let `SongSession.chord_at()` binary-search them for the
   GUI and the terminal display.

The confirmed consequences are:

* the engine can only ever emit `X`, `Xm` or `N` — no sevenths, suspensions,
  diminished/augmented triads, slash chords, inversions or bass notes, even
  though the canonical model and the label parser support them;
* there is no key conditioning, no bass/chroma split, no tuning estimation, no
  harmonic-percussive separation, no onset or beat alignment, no instrument
  modelling and no per-chord confidence;
* chord boundaries are quantised to one chroma frame (2048 / 22050 Hz ≈
  **92.9 ms**) and are derived only from label changes, never from onsets or
  beats;
* the committed tests pin template geometry, decoder mechanics, segmentation
  edges, canonical-label plumbing and timeline coverage. **No committed test
  asserts that the engine's label is musically correct on any audio**, and the
  end-to-end test only checks vocabulary and timestamp coverage.
* the one accuracy number that exists (CSR 0.4260 on 180 GuitarSet takes) is a
  recorded measurement from earlier work; it is low, it is cited in
  `ROADMAP.md`, `AGENTS.md` and `CHANGELOG.md`, and the user's manual "about
  75%" estimate does not replace it.

The audit therefore recommends measuring before changing anything, then making
small changes behind the existing `ChordEngine` interface, each with a
before/after comparison on the same fixed reference set. The proposals in §10
are **expected** benefits; none has been implemented or measured here.

---

## 2. The real code path

### 2.1 Entry points and call chain

All four chord entry points converge on the same service:

```text
songlab gui      gui/main_window.py:open_file()            (line 560)
songlab play     cli/commands/play.py
songlab analyze  cli/commands/analyze.py
songlab chords   cli/commands/chords.py
                     │
                     ▼
SongSession.open()                     app/session.py:106
  → player.load() (decodes for playback) audio/playback.py
  → run_analysis()                      analysis/service.py:310
       for kind in SUPPORTED_KINDS:     analysis/service.py:80, 368
         _resolve() → _call()           analysis/service.py:125, 137
         ChordEngine.analyze()          engines/chroma_baseline.py:397
       _merge()                         analysis/service.py:166
  → events sorted by start              app/session.py:153
  → chord_at() binary search            app/session.py:305
                     │
                     ▼
DisplayFrame / chord bands              app/display.py:111, app/timeline.py:60
Qt window refresh                       gui/main_window.py:1387
```

`gui/analysis_worker.py` only moves `SongSession.open()` onto a worker thread;
it does not add a second analysis path. The window reads only `SongSession` and
`app/` presenters, so the GUI cannot disagree with the CLI about which chord is
under the playhead — a structural property, not an accuracy claim.

### 2.2 Decoding

`ChromaBaselineEngine.analyze()` calls
`decode_audio(audio_path, sample_rate=22_050, mono=True, offset=…, duration=…)`
(`engines/chroma_baseline.py:433`). The shared service
(`audio/decode.py:291`) uses `librosa.load` (`audio/decode.py:152`) and returns
one flat interleaved float buffer plus its sample rate. The same service is used
by the key and tempo engines (`engines/key_krumhansl.py:223`,
`engines/tempo_librosa.py`), by `SoundDevicePlayer.load` and by the session's
waveform fallback, so decoding is consistent across the chord path, the display
and the other engines.

Confirmed properties: mono downmix, fixed 22.05 kHz for the chord engine, no
loudness normalisation, no silence trimming, no channel separation, no
resampling beyond the decoder's. A time range is decoded by `offset`/`duration`
and the returned event times are shifted by `offset`
(`engines/chroma_baseline.py:429-477`).

### 2.3 Feature extraction

```python
chroma = librosa.feature.chroma_cqt(y=samples, sr=int(sample_rate), hop_length=HOP_LENGTH)
frames = chroma.T.tolist()
frame_period = HOP_LENGTH / float(sample_rate)
```

`engines/chroma_baseline.py:445-451`, with `HOP_LENGTH = 2_048` and
`SAMPLE_RATE = 22_050` (lines 77-79). That is one 12-bin pitch-class vector
every 92.9 ms (≈ 10.8 frames per second). No arguments are passed for tuning,
octave weighting, harmonic attenuation or normalisation. The chroma is not
cached or shared with the key engine, which computes the same kind of
chromagram separately (`engines/key_krumhansl.py:233-240`).

### 2.4 Classification

`frame_scores()` (`engines/chroma_baseline.py:144`) builds, per frame, 24 cosine
similarities plus a constant no-chord score (0.06). The templates are bare
triads: 1.0 on the three triad pitch classes and 0.0 elsewhere
(`_triad_template` at line 108, `TEMPLATES` at line 122). Similarity is
`dot(frame, template) / (||frame|| * sqrt(3))`
(`_chord_scores` at line 130) — a geometric similarity, **not** a calibrated
probability or log-likelihood.

`match_frames()` (line 159) applies a 0.5 threshold and is used for the `raw`
payload and for the `"majority"` decoder only. The default `"viterbi"` decoder
(`decode_labels` at line 186) ignores `threshold` entirely: it runs
`viterbi_decode(frame_scores(...), change_penalty=...)`. The event metadata
still records `"match_threshold": DEFAULT_MATCH_THRESHOLD` (line 494) even when
that value had no effect on the run — a small honesty/metadata bug, not an
accuracy bug.

### 2.5 Temporal decoding and segmentation

`engines/decoding.py:viterbi_decode()` is a pure-Python max-sum Viterbi over the
25 states. Every transition between different states costs the same
`change_penalty`; staying costs nothing; the emission is the raw cosine score.
There is:

* no self-transition vs chord-change distinction beyond "different state";
* no duration model (nothing prefers a chord lasting a bar over one lasting a
  frame, except the flat penalty);
* no key- or vocabulary-dependent transition matrix;
* no beat, downbeat or onset information — no beat engine is registered
  (`engines/registry.py:179-182` registers only chords, key, tempo, lyrics);
* a tie rule that keeps the current state (documented at
  `engines/decoding.py:67-70`), which keeps boundaries stable.

`segments_from_labels()` (line 244) collapses equal-label runs and produces
`(start, end, label)` on the frame grid, clamping only the last end to the known
duration. `merge_short_segments()` (line 278) is opt-in through
`ChordAnalysisOptions.minimum_duration`; it moves boundaries to neighbours and
never invents a label. `events_from_segments()` (line 325) maps `root` /
`rootm` / `N` to `ChordEvent` with `ChordQuality.MAJOR/MINOR/NO_CHORD` and sets
`source="chroma-baseline"`. **No confidence is set**, so every event keeps
`ConfidenceScore.unknown()` (`models/confidence.py`).

### 2.6 Presentation

`SongSession.open()` sorts events by `start` (`app/session.py:153`).
`chord_at()` (`app/session.py:305`) implements half-open coverage
(`start <= t < end`), returns `None` before the first event, inside a gap and at
or past the last end, and returns an explicit `N` event as a claim of silence.
`chord_bands()` (`app/timeline.py:60`) clips overlapping engine output to one
label per instant, mirroring `chord_at()`. `DisplayFrame.chord_text`
(`app/display.py:77`) renders `N` for silence and `--` for "no claim", and
`chord_confidence_text` (line 82) renders the event's confidence — which is
always `unknown` today. The window draws the same frame in
`gui/main_window.py:refresh()` (line 1387) and the band labels in
`gui/timeline.py:_draw_bands()` (line 188). The analysis panel's "Chord
confidence" row comes from `app/summary.py:92-105` and honestly reads `unknown`
for this engine.

---

## 3. Chord representation and supported vocabulary

The **model** is richer than the engine. `ChordQuality`
(`models/music.py:67`) defines major, minor, no-chord, `7`, `maj7`, `m7`,
`sus2`, `sus4`, `dim`, `aug`, `add9`, `6`, `m6`, `9`, `m9`, plus `OTHER` and
`UNKNOWN`. `ChordEvent` carries `root`, `quality`, `bass`, `extensions` and a
rendered `label` (`models/music.py:132-165`), and `to_label()` renders slash
chords (`models/music.py:184-196`). `normalization/chords.py` parses all of
those suffixes, handles unicode accidentals, preserves unknown suffix text in
`OTHER`, and supports slash basses (`_split_slash_chord` at line 135,
`parse_chord_label` at line 149).

The **engine** supports exactly phase 1. `TEMPLATE_LABELS` is 12 major + 12
minor (`engines/chroma_baseline.py:103`); `events_from_segments()` has no path
that sets `bass` or `extensions`; `analyze()` refuses `vocabulary_phase > 1`
with an `InputError` (`engines/chroma_baseline.py:412-417`). Therefore:

| Quality | Model/parser | `chroma-baseline` output |
| --- | --- | --- |
| major | yes | `X` |
| minor | yes | `Xm` |
| no chord | yes | `N` |
| dominant/major/minor 7th | yes | never |
| sus2/sus4 | yes | never |
| diminished/augmented | yes | never |
| add9/6/m6/9/m9 | yes | never |
| slash chord / inversion | yes (`bass` field) | never |
| other/unknown | yes | never |

This is a deliberate phase-1 scope, not an accident, but it means the user's
observation of "chords" is made against a vocabulary that cannot represent the
harmony of most recorded music. A correct `G7` can only be reported as `G` or
`N`; a `C/E` can only be `C` or `N`.

---

## 4. What the algorithm accounts for

| Factor | Accounted for? | Evidence |
| --- | --- | --- |
| **Key** | **No** in the chord engine. A key is estimated independently, after the chords, by `krumhansl` (`analysis/service.py:80,368`), and the chord engine's only input is `ChordAnalysisOptions` (`engines/base.py`). There is no key-conditioned template or transition. |
| **Bass notes** | **No.** The engine has no bass feature, no low-band chroma and no inversion templates; it never sets `ChordEvent.bass`. The model and parser *can* represent a slash chord (`models/music.py:150,196`; `normalization/chords.py:135-146`), but nothing in the chord path produces one. |
| **Harmonic context** | **Partially, implicitly.** CQT chroma captures harmonics and `chroma_cqt` folds them into pitch classes, but there is no harmonic-percussive separation, no harmonic attenuation and no source model. A note's overtones can therefore reinforce a pitch class that is not in the sounding chord (e.g. the fifth harmonic of C is E, which biases C major over C minor). This is a **hypothesis to test**, not a measured effect. |
| **Tuning** | **No.** `chroma_cqt` is called without a `tuning=` argument (`engines/chroma_baseline.py:445-449`); nothing calls `librosa.estimate_tuning`. A recording not at A=440 equal temperament is analysed on a fixed grid. |
| **Transients / percussion** | **No.** No HPSS, no onset detection, no beat-synchronous aggregation. Drums contribute broadband energy to whatever 93 ms frame they hit; the flat Viterbi penalty is the only thing suppressing a one-frame excursion (and it only suppresses it if the excursion is not strongly favoured). |
| **Instrumentation changes** | **No.** Mono downmix, one global chroma, no stems, no instrument classifier. A guitar solo, a full band and an a-cappella section are all treated identically. |
| **Dynamics / loudness** | **No** explicit handling. `chroma_cqt` normalises each frame, which removes absolute level but not the relative balance between instruments. |
| **Stereo information** | **Discarded** by `mono=True`. |
| **Tempo / beat / bars** | **No.** Tempo is estimated separately (`librosa-tempo`); no beat or downbeat engine exists, and the chord boundaries are not aligned to any metrical grid. |
| **Vocals** | **No** handling; the vocal melody is mixed into the chroma and can pull the label towards the melody's notes rather than the accompaniment's harmony. |

Each "No" above is a confirmed code fact. The *size* of each effect on accuracy
is unknown and needs the comparison harness in §10.

---

## 5. How boundaries and timestamps are determined

1. The chroma frame grid is fixed by `hop_length=2048` at 22 050 Hz:
   **92.9 ms** per frame (`engines/chroma_baseline.py:451`). There is no
   sub-frame or onset-refined boundary.
2. A boundary exists only where the decoded label changes
   (`segments_from_labels`, line 244). There is no explicit change-point
   detector, no onset strength signal and no beat snapping.
3. Viterbi can move a boundary by whole frames only; the flat penalty sets how
   much evidence a short chord needs to survive. `0.80` is the recorded optimum
   from earlier GuitarSet work (cited in `ROADMAP.md` §1 and `CHANGELOG.md`).
4. The last segment's end is clamped to the decoded audio duration
   (`segments_from_labels` lines 267-272); events before that end at the next
   frame boundary. The first event starts at `0.0` (or at `offset` when a time
   range is analysed).
5. `minimum_duration` merging (`merge_short_segments`, line 278) is opt-in and
   only moves boundaries; it cannot create a boundary.

Consequence: a chord change that happens between two frames is reported up to
~93 ms late or early, and a change that is not accompanied by a clear
chroma change (same triad, different voicing/inversion) is not reported at all.

**Documentation inconsistency found.** `analysis/chunking.py:79-81` describes
`SEAM_TOLERANCE_SECONDS = 0.05` as "one analysis frame is ~23 ms at the shared
decoder's hop (512 / 22 050 Hz)". The chord engine's actual hop is 2048, i.e.
~92.9 ms, so the comment refers to a different frame size. The 50 ms tolerance
is still smaller than one chord frame, so it does not by itself merge unrelated
chords, but the justification is wrong and should be corrected when that file is
next touched. This is a documentation defect, not evidence of an output bug.

---

## 6. Consistency and duplication

**Consistent:** decoding is owned by `audio/decode.py` and used by the chord,
key and tempo engines, the player and the waveform fallback. The chord labels
flow through one canonical model and one presenter chain, so the CLI and the
window cannot disagree about the label at a given time. Windowed chord analysis
(`analysis/chunking.py`) reuses the engine's `start`/`end` contract and is
opt-in; the whole-file pass is the default and the one the recorded accuracy
number was measured with.

**Duplicated / wasteful:**

* the chord engine and the key engine both compute a CQT chromagram over the
  same decoded samples (`engines/chroma_baseline.py:445`,
  `engines/key_krumhansl.py:233`), with the same sample rate and hop, in two
  separate full decodes. Caching the decode is a product-level gain; caching
  the chroma would need a shared feature layer that does not exist yet.
* `run_analysis()` calls the engines sequentially; a song is therefore decoded
  once per DSP engine plus once for playback.
* `_chord_scores()` recomputes the frame norm for every template loop iteration
  (`engines/chroma_baseline.py:130-142`). It is pure-Python arithmetic over 12
  bins, so this is unlikely to dominate beside `chroma_cqt`, but it is O(24·12)
  per frame with avoidable work.
* the `raw` payload stores `match_frames()` labels even when the Viterbi decoder
  is active, so `raw["frame_labels"]` is not the sequence the events came from.
  It is documented as raw evidence, but a caller could mistake it for the
  decoded path.

**Not duplicated:** segment collapsing, minimum-duration merging, event
construction and timeline clipping each have exactly one implementation.

---

## 7. Weak heuristics, edge cases and likely false detections

Ordered roughly by expected impact. "Confirmed" means the code proves the
mechanism exists; "hypothesis" means the effect on accuracy needs a measurement.

1. **Triad-only vocabulary (confirmed).** Sevenths, suspensions, altered chords
   and inversions are forced onto the nearest major/minor triad or `N`. This is
   the single largest structural limitation and the most likely explanation for
   many of the user's perceived mistakes.
2. **Root-position templates only (confirmed).** An inverted chord (`C/E`,
   `G/B`) has the same pitch-class set as its root-position form, so the triad
   label may still be right, but the bass is never reported and a bass-driven
   listener will hear a different chord.
3. **Cosine score as emission (confirmed).** Viterbi sums cosine similarities
   and subtracts 0.80 per change. Cosine similarity depends on how many pitch
   classes carry energy: a noisy frame with all 12 bins populated can score
   moderately on many templates, while a clean triad scores near 1.0. The
   `0.80` penalty is therefore not on the same scale as a log-likelihood and its
   optimum is corpus-specific.
4. **Viterbi ignores the 0.5 threshold (confirmed).** A low-evidence frame can
   still win a state because the no-chord state is a constant 0.06 and the
   penalty is flat. The threshold exists but only affects the majority decoder
   and the raw labels, while metadata reports it as if it applied.
5. **No confidence (confirmed).** `ChordEvent.confidence` is always unknown; the
   frame scores that could yield a margin are discarded after decoding. The GUI
   therefore cannot distinguish a confident `C` from an arbitrary one.
6. **Fixed tuning (confirmed mechanism, hypothesis effect).** Off-pitch
   recordings smear energy across neighbouring bins and can flip major/minor
   thirds.
7. **Percussion and transients (confirmed mechanism, hypothesis effect).**
   Drum hits add broadband chroma energy; short spurious labels are possible
   where the penalty is outweighed by a strong transient.
8. **Vocal melody leakage (confirmed mechanism, hypothesis effect).** A melody
   note outside the accompaniment triad can pull the chroma towards a different
   template.
9. **Bass dominance (confirmed mechanism, hypothesis effect).** Chroma sums all
   octaves equally; a loud bass root can dominate the vector and hide the upper
   structure.
10. **Frame-grid boundaries (confirmed).** 92.9 ms resolution with no onset or
    beat snapping; changes are late/early by up to one frame, and changes within
    a sustained triad are invisible.
11. **Noise / silence threshold (confirmed edge case).** A fully silent frame
    scores 0 on every triad and falls to `N` by the no-chord score; a very quiet
    but non-silent frame can still produce a label. There is no energy gate.
12. **Short songs and empty frames (confirmed by tests).** Very short audio
    produces a chroma with one or two frames; `librosa` warns that the CQT
    window is longer than the signal (observed while running the tests), and the
    resulting labels are still emitted. This is acceptable for a baseline but
    worth an explicit minimum-duration test if the engine is changed.
13. **Misleading metadata (confirmed).** `match_threshold` is recorded on
    Viterbi runs where it was unused, and `raw.frame_labels` is the majority
    path even on Viterbi runs.
14. **Whole-file memory (confirmed).** A whole-file pass holds the decoded
    samples and the chroma. The opt-in windowing path exists to bound this; the
    GUI does not enable it by default.

---

## 8. Which tests exercise chord detection, and what they establish

### 8.1 The test map

| Test file | What it drives | What it actually establishes |
| --- | --- | --- |
| `tests/unit/test_chroma_baseline.py` | `_chord_scores`, `match_frames`, `decode_labels`, `smooth_labels`, `segments_from_labels`, `merge_short_segments`, `events_from_segments`, and full `analyze()` on generated tones | Template geometry (triads on the right bins), pure-triad and silent-frame classification, threshold behaviour, decoder selection, segment math, event mapping, file/phase errors, measured run cost, shared decode call, time-range shift, minimum duration. **No musical-correctness assertion.** |
| `tests/unit/test_decoding.py` | `viterbi_decode` | Tie-breaking, penalty effects, exhaustive-search equivalence on random matrices. The decoder is pinned; the emissions are not. |
| `tests/unit/test_chord_metrics.py` | `metrics/chords.py` | Alignment and exact/root/quality/MIREX views against hand-built cases. Tests the metric, not the engine. |
| `tests/unit/test_chord_segmentation.py` | `metrics/segmentation.py` | Segment overlap, change detection, timing error semantics. Tests the metric. |
| `tests/unit/test_csr_oracle.py` | `evaluation/chords.py` + `tests/fixtures/csr_oracle.json` | Duration-CSR and Harte parsing against 22 pinned GuitarSet takes. It pins **scoring semantics**, using a stored hypothesis segmentation; it does **not** re-run the engine. |
| `tests/unit/test_chord_adapters.py` | Model/normalisation adapters | Label parsing/rendering/transposition plumbing. |
| `tests/integration/test_analysis_e2e.py` | Real registry on a generated C–G–F–C WAV and an MP3 transcode | Events exist, start at 0, are ordered, have ends, reach the file duration, use phase-1 vocabulary, carry `source`, survive JSON. **It checks coverage and vocabulary, not which chord was detected.** |
| `tests/unit/test_chords_command.py`, `test_analyze`, `test_play_command`, `test_gui_*` | CLI/GUI plumbing with fake engines | Selection, flags, JSON, error paths, synchronization. No accuracy claim. |
| `tests/unit/test_timeline_presenter.py`, `test_session.py`, `test_display.py` | Timeline/session/display math | The chord under the playhead is the event `chord_at()` claims; band and label agree. Synchronization only. |

### 8.2 Results of the audit's own run

The following was executed on 2026-10-18 in `.venv-chords` (CPython 3.13.5,
numpy/librosa/sounddevice/PyQt6 importable, editable install):

```text
python -m pytest -q tests/unit/test_chroma_baseline.py tests/unit/test_decoding.py \
  tests/unit/test_chord_metrics.py tests/unit/test_chord_segmentation.py \
  tests/unit/test_csr_oracle.py tests/unit/test_chord_adapters.py
→ 381 passed, 5 warnings in 5.08s
```

`songlab gui --help` was also run to confirm the entry point and the installed
package. The GUI itself was **not** launched by the audit. The five warnings are
librosa CQT warnings on very short fixtures ("n_fft=1024 is too large for input
signal of length=…"), which are expected for sub-frame test tones and do not
fail the suite.

### 8.3 The gap

There is no committed test that:

* takes audio with **known** chords and asserts the engine's labels;
* runs the engine over a fixed reference corpus and records an accuracy number;
* checks boundary timing against onset or annotation times;
* checks confidence calibration (there is no confidence to calibrate).

`tests/fixtures/csr_oracle.json` is a strong scoring oracle, but its hypothesis
segments are pinned data, so improving the engine cannot be detected by the
current suite. Any improvement proposal must add that missing layer before it
can claim a gain.

---

## 9. Measurement status and traceability

* The recorded chord number is **CSR 0.4260** on 180 GuitarSet takes, with
  change-detection F1 0.6202, compared with 0.3676 / 0.3144 for the majority
  smoother. It is cited in `ROADMAP.md` §1 and §10, `AGENTS.md`, `CHANGELOG.md`
  and `AGENT_HANDOFF.md`.
* This audit did **not** reproduce that measurement: it needs the GuitarSet
  audio, which is not committed, and a harness that is not in the repository.
  The number is therefore treated as a prior recorded result, not as a fresh
  finding.
* **Traceability gap:** `docs/ENGINE_COMPARISON.md` in the current tree begins at
  "## 4. Lyrics engines" and contains only sections 4 and 5. The chord
  measurement's method table (corpus, split, decoder sweep, environment, date)
  is not in that file, so the number cited across the docs is not reproducible
  from the document that is supposed to record it. Fixing that is a
  documentation task, not an algorithm change, and should accompany the next
  measurement.
* The user's "about 75%" is a **manual, single-song, user-reported
  observation**. It is useful as a product signal (the app is usable and the
  chords are often right), not as an accuracy metric: no reference annotations,
  no defined matching rule, no repeatable procedure, no date-stamped
  environment beyond the machine description.

---

## 10. Prioritized improvement plan

Nothing here is implemented. Expected benefits are explicitly **not** measured
results. Every proposal keeps the existing `ChordEngine` contract and is
selectable through `--engine` / `ChordAnalysisOptions`, so a regression can be
reverted without touching the CLI or the GUI.

Each proposal uses this template:

* **Limitation and evidence**
* **Change**
* **Why it could help** (expected)
* **Trade-offs**
* **Validation**
* **Comparison protocol and metric**
* **Unmatched/ambiguous labels**
* **Order and risk**

### P1 — Build the comparison harness and reference set first

**Limitation and evidence.** §8.3: no committed test or harness compares engine
output to known chords. The recorded 0.4260 cannot be reproduced from the
repository, and the conductor of `docs/ENGINE_COMPARISON.md` is missing its
chord section.

**Change.** Add (in the next implementation change, not this audit) a
gitignored, reproducible harness that: reads a fixed manifest of GuitarSet takes
(permissively licensed audio fetched separately, never committed), runs the
registered chord engine through `ChromaBaselineEngine.analyze()`, converts Harte
annotations with the existing `evaluation.chords.harte_to_label`, and writes one
row per take with the same environment/date fields as §5 of
`ENGINE_COMPARISON.md`. Add a small committed benchmark case set that uses
generated fixtures with known triads (already possible through
`tests/fixtures/audio.py:write_chord_wav`) for fast regression checks.

**Why it could help.** It cannot improve accuracy by itself; it is what makes
every later claim checkable. Without it, P2-P6 are unfalsifiable.

**Trade-offs.** Some implementation time and a corpus download step for full
coverage; the generated-fixture subset runs offline. No new runtime dependency
(the metrics already exist).

**Validation.** The harness itself is validated by re-running the known
majority-vs-Viterbi comparison and checking that the direction of the recorded
difference reproduces; then by asserting that a deliberately broken hypothesis
lowers the score.

**Comparison protocol and metric.** Same audio, same time range, same reference
annotations, same hop, deterministic runs. Report duration-weighted CSR
(`evaluation/chords.py:duration_csr`) as the headline, with the raw and
triad-reduced views side by side; add segment overlap
(`metrics/segmentation.py:segment_overlap`), change-detection F1
(`chord_change_detection`) and median timing error (`timing_error`).

**Unmatched/ambiguous labels.** A hypothesis label stays in the denominator even
when it has no counterpart; it is scored as a miss, never dropped. `N` matches
only `N`. Enharmonic spellings are canonicalised by the existing parser.
Out-of-vocabulary reference labels are reduced with `triad_reduce` for the
triad view and kept raw for the exact view; both are reported, so a vocabulary
change cannot look better merely by shrinking the label set.

**Order and risk.** **First.** Low technical risk; medium effort.

### P2 — Report per-chord confidence from the score margin

**Limitation and evidence.** `ChordEvent.confidence` is never set by the engine
(`engines/chroma_baseline.py:325-345`, `events_from_segments`); the GUI's
confidence row and tooltip therefore read `unknown`
(`app/summary.py:92-105`, `app/display.py:82`). The Viterbi path also discards
the margin information it computed. `ROADMAP.md` Phase B lists this as an open
task.

**Change.** Compute a bounded, documented score for each event from evidence the
engine already has — for example the difference between the winning triad score
and the runner-up (and the no-chord score), aggregated over the event's frames;
or a normalised forward-backward posterior over the Viterbi states. Calibrate the
mapping on the P1 reference set before calling it a probability; until then label
it a heuristic margin. Set `ChordEvent.confidence` from it and expose it in the
existing UI surfaces. Also stop recording `match_threshold` on Viterbi runs, or
record that it was unused.

**Why it could help.** It does not change the labels; it lets the user and future
fusion/editing features see which chords are unreliable, and it gives the
comparison harness a risk-coverage signal. It is a prerequisite for sensible
automatic correction or ensemble fusion.

**Trade-offs.** A little CPU and memory per event (the frame scores are already
in memory); a calibration step; a risk of over-trusting an uncalibrated number,
which the naming and docs must prevent. No new dependency.

**Validation.** Unit tests: a pure triad scores higher than a noisy mixture; a
silent frame yields `N` with low confidence; confidence is monotonic in the
margin; an event boundary does not depend on confidence. Integration: the
reference-set run reports accuracy at coverage thresholds.

**Comparison protocol and metric.** Same P1 runs; report (a) label accuracy
unchanged, (b) risk-coverage curve / area under it, (c) calibration error if a
probability is claimed, (d) the fraction of events with `unknown` confidence
(should reach zero). Accuracy must not silently change; if it does, the change
is a bug in the aggregation.

**Unmatched/ambiguous labels.** Confidence is attached to whatever event the
engine emitted; a wrong low-confidence chord is still a miss in CSR. Report
accuracy separately for high- and low-confidence buckets rather than excluding
low-confidence events.

**Order and risk.** **Second.** Low risk.

### P3 — Measure front-end robustness one variable at a time

**Limitation and evidence.** The chroma call passes no tuning, no harmonic
attenuation and no normalisation options (`engines/chroma_baseline.py:445-449`).
There is no HPSS, no onset-synchronous aggregation and no energy gate. Each is a
plausible false-detection source (§7.6-7.9), but none has been measured.

**Change.** Treat this as a set of independent A/B experiments behind engine
options, not one "improved chroma" bundle:

1. `librosa.estimate_tuning` → pass `tuning=` to `chroma_cqt`;
2. harmonic-percussive separation (`librosa.effects.hpss`) before chroma, or
   harmonic-only chroma;
3. per-frame log compression / power normalisation and an energy threshold;
4. octave weighting (down-weight the lowest octave for bass-heavy mixes, or keep
   it and add a separate bass feature — see P4);
5. a comparison against `chroma_cens`, which is designed for robustness to
   dynamics and timbre.

Each option is recorded in `EngineResult.metadata` so the harness knows what
ran.

**Why it could help.** Tuning correction should reduce third/semitone smearing;
harmonic-only analysis should reduce drum-induced chroma; energy gating should
remove forced labels in near-silence. These are plausible mechanisms, not
demonstrated gains.

**Trade-offs.** HPSS roughly doubles the STFT work and adds memory; tuning
estimation is cheap; CENS changes the temporal resolution and may lag chord
changes. Every option adds a knob that must be documented and defaulted
deliberately.

**Validation.** P1 harness with one variable changed at a time; report CSR,
segment overlap, change F1 and boundary error. Unit tests for the energy gate
(silence → `N`) and for the metadata recording the option. Keep the current
defaults until a change wins on the same set and does not regress boundary
timing.

**Comparison protocol and metric.** Identical audio and annotations; report the
full metric vector per variant, not just the headline CSR. A variant that gains
CSR by inventing fewer boundaries must be visible in change F1.

**Unmatched/ambiguous labels.** Unchanged from P1: misses count, `N` only
matches `N`, reductions are reported explicitly.

**Order and risk.** **Third.** Low-to-medium risk if each variable is separate;
high risk if bundled.

### P4 — Bass-aware features and slash-chord output

**Limitation and evidence.** The engine never sets `ChordEvent.bass`
(`events_from_segments`, `engines/chroma_baseline.py:325-345`); the templates
are root-position triads with no inversion model
(`engines/chroma_baseline.py:108-124`); chroma sums all octaves, so the bass is
not separable. The canonical model and parser already support bass
(`models/music.py:150`, `normalization/chords.py:135-146`), and the CSR
implementation already has bass-rescue semantics (tested in
`tests/unit/test_csr_oracle.py`).

**Change.** Add a low-frequency chroma/spectral feature (e.g. a CQT chroma
restricted to the bass register, or a bass chroma from HPSS harmonics) and use
it to (a) choose among triad templates and (b) report the bass pitch class when
it differs from the root. Keep the triad label as the primary label, so a wrong
bass cannot make the chord unrecognisable. Optionally add inversion templates
(root, first, second) as separate states, but only after the bass feature alone
has been measured.

**Why it could help.** Bass notes carry harmonic information and are often the
most reliable low-frequency cue; modelling them can improve root detection and
allow slash chords, which the model already represents.

**Trade-offs.** More features and states (latency, memory, decoder cost); bass
extraction is unreliable on small speakers and bass-light recordings; extra
vocabulary increases confusion between `C`, `C/E` and `Am`. Confidence and
bass reporting must be separable.

**Validation.** Unit tests for bass extraction on generated triads with a
deliberately emphasised bass note; reference-set comparison of root accuracy,
exact accuracy and bass accuracy; a test that a bassless recording still yields
plain triads.

**Comparison protocol and metric.** Report root accuracy and exact accuracy
with and without the bass feature; count slash labels separately. Use the
existing CSR bass-rescue behaviour rather than inventing a second scoring rule.

**Unmatched/ambiguous labels.** A reference without a bass annotation must not be
penalised for a reported bass; score the no-bass view separately. A bass-only
difference counts as a root/exact mismatch under the chosen view and is reported
under the bass view, not silently discarded.

**Order and risk.** **Fourth.** Medium risk.

### P5 — Replace the flat transition model with a measured one

**Limitation and evidence.** `viterbi_decode` applies one flat penalty to every
state change (`engines/decoding.py`), with no duration model, no key prior and no
metrical information. There is no beat engine registered, and boundaries are
frame-grid only (§5). The current penalty 0.80 was tuned on GuitarSet and is
recorded, but it is a single global number.

**Change.** In order of cost:

1. a duration-aware self-transition (probability of staying grows with the
   current run length) or a minimum-duration cost, replacing the flat penalty;
2. a key-conditioned transition prior using the `krumhansl` estimate (already
   computed by `run_analysis`) — but only if the chord engine is given the key
   as an option, not by importing the key engine;
3. once a beat/downbeat engine exists, snap boundaries to the nearest beat or
   sub-beat, or aggregate chroma per beat.

**Why it could help.** Real chords last longer than one frame; a duration prior
should suppress flicker without suppressing genuine short chords. Beat alignment
should move boundaries from an arbitrary 93 ms grid to musically meaningful
positions. Neither is demonstrated yet.

**Trade-offs.** A duration model adds parameters that can overfit a small
corpus; key conditioning adds a dependency between two layers that are currently
independent (and must stay optional); beat snapping needs a new engine and its
own licence/dependency audit.

**Validation.** P1 harness; parameter sweeps recorded with their environment;
unit tests for the duration model on synthetic score sequences; boundary timing
error and change F1 must be reported alongside CSR, since smoothing can improve
CSR while worsening boundaries.

**Comparison protocol and metric.** Same runs; report change F1 and median
boundary error (`metrics/segmentation.py:timing_error`) as primary for this
proposal, with CSR as a guard against regressions.

**Unmatched/ambiguous labels.** Boundaries are only compared where both sides
have a change; unmatched changes count as false positives/negatives, not as
ignored. `N` boundaries are included (a drop to silence is a change).

**Order and risk.** **Fifth.** Medium risk; the key-conditioned variant should
wait for P1 evidence.

### P6 — Extend the vocabulary only after measuring the triad baseline

**Limitation and evidence.** The engine refuses `vocabulary_phase > 1`
(`engines/chroma_baseline.py:412-417`) although the model defines phase-2 and
phase-3 qualities (`models/music.py:67-95`) and the parser understands them
(`normalization/chords.py:80-110`). This is the largest source of "wrong" labels
for real songs.

**Change.** Add templates for the qualities the model already supports, in
increasing-risk order: dominant seventh, minor seventh, major seventh; then sus2
and sus4; then diminished and augmented. Keep them as additional states in the
same decoder and record the vocabulary phase in metadata/provenance. Consider a
hierarchical decision (triad first, then extension) if a flat 40-state model
confuses too much.

**Why it could help.** A `G7` reported as `G` is currently a miss under exact
scoring; representing it can only help *if* the additional states are separable
with the current chroma. That conditional is the experiment.

**Trade-offs.** More states mean more confusion, slower Viterbi and a larger
label set; the exact metric becomes harder to compare across vocabulary phases.
A richer vocabulary can lower triad accuracy while raising exact accuracy.

**Validation.** P1 harness with the same reference labels, reporting both the
raw and the triad-reduced views: a vocabulary extension is only accepted if the
triad-reduced view does not regress and the exact view improves. Unit tests per
template (pitch-class geometry) and a round-trip test that every emitted label
parses and renders back to itself.

**Comparison protocol and metric.** Exact accuracy, root accuracy and
triad-reduced CSR; plus per-quality precision/recall for the new labels. Report
vocabulary size with every number, so scores are never compared across
different label sets without the reduced view.

**Unmatched/ambiguous labels.** A reference `G7` and a hypothesis `G` are a miss
in the exact view and a match in the triad view; both must be reported. A
hypothesis label outside the reference vocabulary is a false positive, not
ignored.

**Order and risk.** **Sixth.** Medium-to-high risk; do not bundle with P3.

### P7 — Share feature computation between chord and key engines

**Limitation and evidence.** `ChromaBaselineEngine.analyze()` and
`KrumhanslKeyEngine.detect_key()` each decode the file and compute a CQT
chromagram with the same sample rate and hop
(`engines/chroma_baseline.py:433-449`, `engines/key_krumhansl.py:223-240`), and
`run_analysis()` runs them sequentially, so a song is decoded at least three
times (chords, key, tempo) plus once for playback.

**Change.** Introduce an application-level analysis cache keyed by path and
decode parameters (and later by a content hash), so engines can request decoded
samples or a chromagram instead of decoding privately. This is an `analysis/`
orchestration concern, not an engine algorithm change; the `ChordEngine`
protocol stays the same.

**Why it could help.** Faster opening and less peak memory, which matters for
the GUI's perceived responsiveness on long songs. It does not change accuracy.

**Trade-offs.** A cache lifecycle to design (invalidation, memory bounds,
thread safety with the GUI's worker thread); a refactor that could change
results if the feature parameters drift. Cache entries must never be committed.

**Validation.** Assert byte-identical (or numerically identical within a stated
tolerance) chord/key/tempo output before and after on the sample files; measure
wall time and peak RSS on the same machine and date, using
`performance.PerformanceProbe`. No accuracy claim.

**Comparison protocol and metric.** Same inputs, same environment, report
wall-clock and peak RSS with date; correctness is output equality, not a
metric.

**Unmatched/ambiguous labels.** Not applicable (no label change).

**Order and risk.** **After P1**, in parallel with P2 if desired. Low risk,
but it touches orchestration, so it should be its own change.

### P8 — Alternative engines: last, and only with a product reason

**Limitation and evidence.** The only registered chord engine is
`chroma-baseline` (`engines/registry.py:179-182`). Chordino and madmom are
mentioned in `ROADMAP.md` Phase I and are present under `external/` as
**read-only reference repositories**; they are explicitly not dependencies
(`AGENTS.md`). Learning-based models could beat a triad template matcher, but
they bring model weights, licences, CPU cost and a much larger failure surface.

**Change.** Only after P1-P3: evaluate one candidate behind `ChordEngine`, with
a licence audit first (`docs/LICENSE_AUDIT.md`), an optional extra, and the same
P1 comparison. Do not import anything from `external/`.

**Why it could help.** A learned model can capture timbre, voicing and
instrumentation that a 24-template matcher cannot. It is also the most likely
way to cross the ~0.43 CSR range if incremental front-end work plateaus.

**Trade-offs.** Weight downloads, model licences, latency, memory, a new
optional dependency and a much harder debugging story. It can also be *worse*
on guitar-only or sparse mixes; that is why it must be measured, not assumed.

**Validation.** The same reference set, the same metrics, a recorded environment
and date, and an honest `is_available()`/`engine_info()` implementation.

**Comparison protocol and metric.** Identical to P1; report CSR, segment
overlap, change F1, boundary error and run cost. A new engine is registered and
selectable, never a silent replacement.

**Unmatched/ambiguous labels.** Whatever vocabulary the engine emits is scored
through the same parser and reductions; no engine-specific scoring path.

**Order and risk.** **Last.** High risk and high dependency cost.

---

## 11. Comparison protocol (for every proposal)

1. **Freeze the inputs.** Same audio files, same time range, same decoder,
   same sample rate and hop. Record the file hashes.
2. **Freeze the reference.** One annotation view per run (instructed or
   performed for GuitarSet; never mix them in one number). Record which.
3. **Run both variants in separate processes** when measuring memory, as
   `docs/ENGINE_COMPARISON.md` §5 already does.
4. **Report the whole vector**, not one number: duration-weighted CSR (raw and
   triad-reduced), segment overlap, change-detection F1, median boundary error
   in both directions, chord count, wall time, peak RSS, environment and date.
5. **No cherry-picking.** A change is accepted only if it improves the target
   metric without a material regression in the others; a trade-off is stated as
   a trade-off, not as a win.
6. **Keep old output.** Store the previous run's hypothesis segments in the
   harness output so the comparison is reproducible even after the default
   changes.

**Label handling rule.** Every hypothesis event occupies time and therefore
counts. There is no "unmatched labels ignored" path. `N` is a label. Enharmonic
spellings are canonicalised. Labels outside the reference vocabulary are false
positives. Comparisons across different vocabularies use `triad_reduce` and say
so in the caption.

**Metric definitions.** Reuse the implemented ones; do not invent parallel
definitions:

* `evaluation/chords.py:duration_csr` — duration-weighted CSR;
* `evaluation/chords.py:mirex_equal` — MIREX equality (root, quality, bass
  semantics);
* `metrics/chords.py:evaluate` — exact/root/quality/MIREX precision/recall/F1;
* `metrics/segmentation.py:segment_overlap` — MIREX mean segmentation;
* `metrics/segmentation.py:chord_change_detection` — change-point P/R/F1;
* `metrics/segmentation.py:timing_error` — median boundary error, both
  directions.

---

## 12. Suggested order and risk

| Order | Proposal | Expected effect | Risk | Depends on |
| --- | --- | --- | --- | --- |
| 1 | P1 comparison harness | makes gains measurable | Low | — |
| 2 | P2 confidence margin | honesty/UI, enables fusion | Low | P1 for calibration |
| 3 | P3 front-end A/B (tuning, HPSS, energy, CENS) | fewer smeared/noisy labels | Low-medium (one variable at a time) | P1 |
| 4 | P4 bass feature / slash chords | better roots, inversions | Medium | P1, P3 |
| 5 | P5 duration/metrical model | fewer flickers, better boundaries | Medium | P1 |
| 6 | P6 vocabulary phase 2 | exact-match gains if separable | Medium-high | P1 |
| 7 | P7 shared decode/chroma | latency and memory only | Low | P1 for output equality |
| 8 | P8 alternative engine | potential step change | High | P1-P3, licence audit |

**Do not do first:** a learned model, a large vocabulary expansion, or a
beat-alignment layer. Each is expensive and unverifiable until P1 exists.

---

## 13. Open questions that need experiments

1. How much of the current error is *quality misclassification* (major vs minor,
   triad vs seventh) versus *boundary error* versus *no-chord confusion*? The
   metric vector can separate these; no one has.
2. Does tuning estimation change any labels on real GuitarSet takes, or is the
   corpus already well tuned?
3. Does HPSS help on guitar-only recordings, and does it hurt on dense mixes?
4. Is the `0.80` penalty still optimal once confidence and duration are added,
   or was it compensating for a weak emission model?
5. How much does the vocal melody contribute to wrong labels? Stem separation
   would answer it, but adds a large dependency; this is a research question,
   not a product change yet.
6. Is a 93 ms frame grid fine enough for the user-visible product, or does the
   perceived synchronization need onset-level boundaries even when the labels
   are unchanged? The user's manual session reported correct-looking
   synchronization, so this is a "nice to have" until measured.

---

## 14. What this audit did not do

* It did not modify any Python source, engine, dependency, version or
  configuration.
* It did not install packages or download models/datasets.
* It did not run the GUI, play audio, or listen to chords; the GUI observations
  belong to the user.
* It did not re-measure CSR, change F1, WER or any other number.
* It did not mark any proposal as implemented in `ROADMAP.md`.
