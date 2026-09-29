# Dataset

**Status: first samples added (2026-09-25); timestamped-source search recorded
(2026-09-28).** Four CC-BY-4.0 `vocadito` excerpts with lyric
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
| **CASD** (Chordify Annotator Subjectivity Dataset, mounted read-only at `external/chordify-org/CASD/`) | **yes, verified locally**: 50 `jams/*.jams` files, 4 annotator chord annotations each, real `time`/`duration` per Harte chord observation, song duration in `file_metadata` | **none** — only a `youtube_url` per song in `file_metadata.identifiers` | **CC BY-NC-SA 4.0** (`LICENSE.md`, read) | timestamps and format are exactly what the harness's `csr --ref` loader reads, but non-commercial + share-alike bars committing any of it into this GPL-3 repository (the same pattern that rejected madmom's and Essentia's weights, `docs/DEPENDENCY_MATRIX.md` §3.1), and the audio must come from the listener's own copy. Context + pending-licence evaluation candidate; never bundled, never committed. |
| **ChoCo** (`github.com/smashub/choco`, paper: Scientific Data 2023, DOI 10.1038/s41597-023-02896-3) | **yes**: 20,080 JAMS files — 2,283 from audio partitions (Isophonics 300, Billboard 890, CASD 50×4, Uspop 195, RWC-Pop 100, JAAH 113, Robbie Williams 61 …) — human-made, Harte notation, seconds for audio, with provenance metadata | **none** (annotations only) | **CC BY 4.0** for most partitions; CASD/JAAH/Mozart partitions re-licensed BY-NC-SA | the best index of timed ground truth under a GPL-compatible licence, and its Harte seconds are the format `csr --ref` already accepts. Still needs audio paired from a copy the user owns. |
| Isophonics / MIREX / `billboard-parser` | yes | **not distributed** (original CDs, purchase or research agreement) | mixed/restrictive | annotations without audio cannot feed the CSR's accuracy mode, which scores audio. |

**Conclusion and routes forward.** The CSR accuracy mode stays blocked today; two honest
routes could unblock it — (a) pair a permissively licensed timed chart (ChoCo) with an
audio recording the user already owns, or (b) hand-annotate chord boundaries on one of
our own charts and record the provenance in its sidecar (roadmap 43 explicitly allows
`chord boundaries` as ground truth *when stored with provenance*; what is forbidden is
inventing them). The harness already reads the interchange format: `csr --ref song.jams`
takes the first `chord`-namespace annotation and converts Harte labels (`Bb:min`,
`F#:7/5`) to the canonical form, fixture-tested alongside the metric itself.

## Policy

* No copyrighted commercial recordings are committed to this repository.
* Only original recordings, public-domain recordings, properly licensed material,
  or research datasets whose terms permit this use.
* Every file's licence and provenance is recorded in `samples/README.md`.
* Ground truth is explicit and never manufactured (roadmap section 43).
* Text fixtures are generated where possible: `tests/fixtures/audio.py` writes
  synthetic WAV tones, so tests need no committed audio at all.

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
