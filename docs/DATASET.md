# Dataset

**Status: first samples added (2026-09-25); timestamped-source search recorded
(2026-09-28); GitHub-free source measured (2026-09-29).** Four CC-BY-4.0
`vocadito` excerpts with lyric
ground-truth sidecars are committed under `samples/` (`samples/README.md` has the provenance table).
The full 40-excerpt dataset and the synthetic mix conditions used by the lyrics-ASR investigation are
kept in the gitignored `.cache/lyrics-asr-investigation/` and described in `docs/ENGINE_COMPARISON.md`.
No commercial recording is committed, and the chord/key/tempo categories below are still uncollected
as versioned, licensed dataset entries.
The 2026-09-25 real-music pass of the lyrics-ASR investigation used one commercial MP3 supplied
by the user: it lives only in the gitignored `mp3/` directory (and the gitignored
`.cache/real-song/`), is never committed or redistributed, and is a local check rather than a
dataset entry — so it carries no sidecar and cannot be reproduced without the reader's own copy.
Five user-supplied commercial MP3s with hand-written chord charts were used by the
2026-09-26 chord pass (`docs/ENGINE_COMPARISON.md`, "Chords"): all live only in the
gitignored `mp3/` directory, the chord charts are local references rather than dataset
entries (they have no timestamps and no sidecars), and none are committed or redistributable.
The user also keeps a private GitHub backup of the same files (mp3 plus chord charts),
mounted here as the private `mp3-library/` submodule: only the submodule reference hash is
committed — the audio and the chart text stay in that private repository and are never
committed here or redistributed.

## Timestamped annotation sources (searched 2026-09-28)

Roadmap 43 forbids manufactured ground truth, and the duration-weighted CSR
(`docs/ENGINE_COMPARISON.md`, roadmap 44) needs chord **boundaries** — not just a label
sequence — to score accuracy on real songs. The five user charts have no timestamps, so
sources of timed chord annotations were searched on 2026-09-28. The structural finding:
every source found ships **annotations only** — audio never travels with them, because
the recordings stay under their original copyright — so no source combines audio +
timestamps + a permissive licence.

| Source | Timed annotations | Audio | Licence (verified) | Verdict |
| --- | --- | --- | --- | --- |
| **GuitarSet** (Zenodo 10.5281/zenodo.3371780, v1.1.0) | **yes** — every excerpt ships a JAMS with 16 annotations: chord (instructed lead sheet *and* performed voicings), beats, downbeats, tempo, key, pitch contours | **yes** — 360 real acoustic-guitar excerpts (hexaphonic, pickup mix and reference-mic mono), 14–46 s each | **CC BY 4.0** (Zenodo record metadata; MD5s verified on download) | **adopted for local measurement (2026-09-29)** — the only source found that carries real audio *and* timed chord boundaries under a permissive licence. Audio + annotations stay in the gitignored `.cache/chords/guitarset/`; the licence would allow a committed `samples/` excerpt if one is ever wanted. First results in `docs/ENGINE_COMPARISON.md`, "Chords". |
| **CASD** (Chordify Annotator Subjectivity Dataset, mounted read-only at `external/chordify-org/CASD/`) | **yes, verified locally**: 50 `jams/*.jams` files, 4 annotator chord annotations each, real `time`/`duration` per Harte chord observation, song duration in `file_metadata` | **none** — only a `youtube_url` per song in `file_metadata.identifiers` | **CC BY-NC-SA 4.0** (`LICENSE.md`, read) | timestamps and format are exactly what the harness's `csr --ref` loader reads, but non-commercial + share-alike bars committing any of it into this GPL-3 repository (the same pattern that rejected madmom's and Essentia's weights, `docs/DEPENDENCY_MATRIX.md` §3.1), and the audio must come from the listener's own copy. Context + pending-licence evaluation candidate; never bundled, never committed. |
| **ChoCo** (`github.com/smashub/choco`, paper: Scientific Data 2023, DOI 10.1038/s41597-023-02896-3) | **yes**: 20,080 JAMS files — 2,283 from audio partitions (Isophonics 300, Billboard 890, CASD 50×4, Uspop 195, RWC-Pop 100, JAAH 113, Robbie Williams 61 …) — human-made, Harte notation, seconds for audio, with provenance metadata | **none** (annotations only) | **CC BY 4.0** for most partitions; CASD/JAAH/Mozart partitions re-licensed BY-NC-SA | the best index of timed ground truth under a GPL-compatible licence, and its Harte seconds are the format `csr --ref` already accepts. Still needs audio paired from a copy the user owns. |
| Isophonics / MIREX / `billboard-parser` | yes | **not distributed** (original CDs, purchase or research agreement) | mixed/restrictive | annotations without audio cannot feed the CSR's accuracy mode, which scores audio. |

**What was downloaded and checked (2026-09-29).**

* **GuitarSet** — `annotation.zip` (39.1 MB) and `audio_mono-mic.zip` (656.9 MB); the
  MD5s match the Zenodo record exactly (`b39b78e6…`, `275966d6…`).  360 `.jams` + 360
  `_mic.wav` files are extracted flat into `.cache/chords/guitarset/`. A 24-excerpt
  sample (6 players × 5 styles, the *comp* performances) was measured first, then the
  whole set: the chord vocabulary is 42 instructed labels, almost all major/minor triads
  plus a few `:7`/`:sus`, so a 24-triad decoder can be scored against it directly. All
  360 takes were decoded on 2026-09-29 (see `docs/ENGINE_COMPARISON.md`).
  A **derived fixture is committed** (2026-10-01):
  `tests/fixtures/csr_oracle.json` pins the chord-scoring semantics for pytest —
  for 22 comping takes it stores the timed chord annotations (both the instructed
  and the performed JAMS `chord` namespaces, as raw Harte observations), the recorded
  hypothesis segmentation and the expected duration-CSR numbers for four views. Only
  annotations and numbers travel, no audio, and the dataset licence (CC BY 4.0) and
  provenance are recorded inside the fixture's own `provenance` field; re-derivation
  from the downloaded source is documented in the fixture and in the harness that
  generated it.
* **ChoCo** — the `v1.0.0` release zip (179 MB; JAMS only, the knowledge graph was
  skipped). 20,086 JAMS files, 2,283 of them in the audio partitions. Intersecting its
  `meta.csv` titles/artists with the user's five charts gave **zero matches** (its audio
  partitions are Beatles, Billboard pop, jazz, Robbie Williams, Uspop, RWC-Pop and
  Schubert — no Spanish worship material), so ChoCo contributes annotations, not audio.
  The harness's `--ref` loader was run over real files from four partitions and the
  segment coverage matches the metadata duration in every case (Isophonics 127.7 s/55
  segments, Billboard 276.8 s/137, CASD 187.8 s/532, JAAH 185.0 s/98), which is the
  annotation half of the pipeline validated on the actual corpora.

**Conclusion and routes forward.** The CSR accuracy mode now has a real-audio source
(GuitarSet), so the blocker moved from "no timed ground truth at all" to "no timed
ground truth *for this project's own commercial songs*" — the five user charts still have
no timestamps and none of them exists in ChoCo. Routes to extend the measurement: pair a
permissively licensed timed chart (ChoCo) with an audio recording the user owns even if
that is not one of the five; or hand-annotate chord boundaries on one of our own charts
and record the provenance in its sidecar (roadmap 43 explicitly allows `chord boundaries`
as ground truth *when stored with provenance*; what is forbidden is inventing them). The
harness reads the interchange format for both: `csr --ref song.jams [--ref-index N]`
takes the `N`-th `chord`-namespace annotation (GuitarSet's 0 = instructed, 1 = performed)
and converts Harte labels (`Bb:min`, `F#:7/5`) to the canonical form, fixture-tested
alongside the metric itself.

## Guitar-dataset inventory (registered 2026-10-04)

The guitar chord/dataset search collected in
`research/repositorios_datasets_acordes_guitarra.txt` (13 entries) is registered
here with a licence and a verdict per source, so roadmap 42's "document every
dataset license" has one place to look. Licences marked *verified* were checked
against the primary record (Zenodo API, GitHub licence API, the project's own
site) on 2026-10-04; the rest are as recorded in the research file. The same
verdicts are mirrored as a short table in `docs/DEPENDENCY_MATRIX.md` §14.

| # | Source | What it holds | Licence (verified) | Verdict |
| --- | --- | --- | --- | --- |
| 1 | **T-vK/chord-collection** | guitar chord shapes as JSON/JS objects: finger positions and frets | *no licence file detected* via the GitHub API (2026-10-04) | fingering-representation reference only; no audio. All rights reserved until clarified — do not copy content into this repository. |
| 2+3 | **marl/GuitarSet** (GitHub + Zenodo 10.5281/zenodo.3371780) | 360 real acoustic-guitar excerpts with JAMS annotations: chords (instructed + performed), notes, strings, key, tempo, beats | **CC BY 4.0** (Zenodo metadata, MD5-verified 2026-09-29) | **adopted** — the only source found that combines real audio *and* timed chord boundaries under a permissive licence; used for local measurement since 2026-09-29, audio stays in the gitignored cache, annotations-only fixtures are committed. |
| 4 | **severyn-k/isolated-guitar-chords** (Hugging Face) | isolated major/minor chord recordings with strumming patterns and fingerings | **CC BY 4.0** (as recorded in the research file) | candidate for isolated-chord evaluation; not adopted. |
| 5+13 | **ryangowe/guitar-chord-mix** (Hugging Face) | unified WAV+JAMS clips (per-string `note_midi`) merged from GuitarSet, Guitar-TECHS, EGFxSet and Isolated Guitar Chords, plus SFZ libraries and DEMAND noise; 158 rows / 4.85 GB | per-source table on the dataset card: **CC BY 4.0** (GuitarSet, Guitar-Techs, EGFxSet, Isolated Guitar Chords, DEMAND), **CC0** (SFZ libraries) | integration resource; its licence follows its components, so audit whichever source a clip came from before reuse. Not adopted. |
| 6 | **Madhudorai/Guitar-TECHS** (GitHub → Zenodo 14963133) | electric-guitar techniques, scales, chords and excerpts across four capture modalities, with per-string/MIDI note labels | **CC BY 4.0** (project site `guitar-techs.github.io`, the ICASSP 2025 paper and the NLM dataset catalogue, 2026-10-04) | candidate for note- and chord-level guitar research; not adopted. |
| 7 | **philwhiles/frettler** | Java CLI + database of chord fingerings (OLGA-derived data) | **AGPL-3.0-or-later** (LICENSE file, 2026-10-04) | fingering reference only (no audio). AGPL code must never be bundled into this GPL-3.0-or-later project — same pattern as madmom/Essentia weights in `DEPENDENCY_MATRIX.md` §3.1. |
| 8+9 | **IDMT-SMT-Guitar** (Fraunhofer site + Zenodo 10.5281/zenodo.7544110) | real guitar recordings: techniques, playing styles, and a transcription/chord-rhythm subset | **CC BY-NC-ND 4.0** (recorded in the research file) | **blocked**: non-commercial *and* no-derivatives, which bars committing it into this GPL-3 repository or producing adapted fixtures. Never bundled, never committed. |
| 10 | **IDMT-SMT-Chords** (Zenodo 10.5281/zenodo.7544213) | 7,398 chord segments (2 s each) synthesized from MIDI; 273 guitar chord classes | **CC BY-NC-ND 4.0** (Zenodo API, 2026-10-04) | **blocked** for the same NC-ND reasons; the audio is synthesized rather than real playing anyway. |
| 11 | **IDMT-SMT-Chord-Sequences** (Zenodo 10.5281/zenodo.7544225) | 15,000 chord progressions (4–32 s) synthesized from MIDI with 45 instruments, with tempo/meter/instrument metadata | **CC BY 4.0** (Zenodo API, 2026-10-04) | licence is usable, but the audio is synthetic; candidate for sequence-level experiments only, not for real-guitar claims. Not adopted. |
| 12 | **Freesound** | marketplace of samples including isolated chord strums and guitar takes | **per item** (CC0 / CC BY variants; research file) | complementary source only; every item's own licence must be checked and recorded before use, and nothing is committed from it. |

**What this means.** GuitarSet stays the single adopted audio source (roadmap
43's ground truth); the IDMT-SMT-Guitar/Chords pair is hard-blocked by NC-ND;
frettler is AGPL and chord-collection has no detected licence, so both are
reading material for the fingering representation (roadmap 13) rather than
sources to copy from. Nothing in this table changes the policy below: no audio
from any of these sources is ever committed, and derived fixtures stay
annotation-only with their provenance inside the fixture.

## Policy

* No copyrighted commercial recordings are committed to this repository.
* Only original recordings, public-domain recordings, properly licensed material,
  or research datasets whose terms permit this use.
* Every file's licence and provenance is recorded in `samples/README.md`.
* Ground truth is explicit and never manufactured (roadmap section 43).
* Text fixtures are generated where possible: `tests/fixtures/audio.py` writes
  synthetic WAV tones, so tests need no committed audio at all.
* Committed derived fixtures stay annotation-only: `tests/fixtures/csr_oracle.json`
  (2026-10-01) carries GuitarSet chord annotations and expected metric values under
  the dataset's CC BY 4.0 terms, with the licence and provenance recorded inside the
  fixture; no audio, no commercial recording, nothing non-redistributable.

## Planned categories (roadmap section 42)

```text
simple_pop          acoustic_guitar     piano            full_band
live_recording      worship             spanish_vocals   english_vocals
male_vocal          female_vocal        dense_drums      bass_heavy
complex_harmony     modulation          multiple_instruments
```

## Ground truth format (planned)

Per song, a JSON sidecar with:

```text
lyrics              line text
word timestamps     start/end per word where known
chords              label + start + end
key                 tonic + mode
tempo               bpm (+ alternatives)
beats               timestamps
downbeats           timestamps
provenance          who annotated it, when, with which tool, and the licence
```

Absent values stay absent. "Not annotated" is different from "no chord here" and
from "silence", exactly as in the canonical model.

The `chords label + start + end` rows are the same tuple the JAMS `chord` namespace
stores (CASD, ChoCo and Isophonics all publish timed chords that way), so the planned
sidecar can be generated from — or exported to — JAMS without a format decision; the
gitignored harness's `csr --ref` loader already reads that form today.
