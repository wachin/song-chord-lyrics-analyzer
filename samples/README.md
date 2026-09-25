# Samples

Audio used for experiments, benchmarks and regression checks.

## Rules

* **No copyrighted commercial music.** Only original recordings, public-domain
  recordings, properly licensed material or research datasets whose terms permit
  this use (roadmap section 42).
* Every file added here must be listed in the table below with its source and
  licence. A file without a recorded licence is removed.
* Keep files short (a few seconds to ~30 seconds). Long songs bloat the
  repository and slow the test suite.
* Generated tones do not belong here: `tests/fixtures/audio.py` writes them at
  test time, so no binary fixture is committed.
* Ground truth sidecars (lyrics, chords, key, tempo, beats) are explicit and
  recorded with provenance; expected chords are never invented.

## Contents

Four excerpts from **vocadito** (Bittner et al., 2021), a CC-BY-4.0 dataset of 40 solo,
monophonic singing excerpts with lyric annotations. They are a small, checkable subset of the
40 used by the lyrics-ASR investigation documented in `docs/ENGINE_COMPARISON.md`; each has a
JSON sidecar with the annotated lyrics and provenance.

| File | Source | Licence | Purpose |
| --- | --- | --- | --- |
| `vocadito_6.wav` (+ `.json`) | vocadito, <https://zenodo.org/records/5578807> | CC-BY-4.0 | English solo singing; lyric ground truth |
| `vocadito_2.wav` (+ `.json`) | vocadito | CC-BY-4.0 | Spanish solo singing; lyric ground truth |
| `vocadito_5.wav` (+ `.json`) | vocadito | CC-BY-4.0 | Catalan/Valencian solo singing; lyric ground truth |
| `vocadito_16.wav` (+ `.json`) | vocadito | CC-BY-4.0 | Tagalog solo singing; lyric ground truth |

Attribution: Bittner, R., Pasalo, K., Bosch, J. J., Meseguer Brocal, G., & Rubinstein, D.
(2021). *vocadito: A dataset of solo vocals with f0, note, and lyric annotations* (Version 2)
[Data set]. Zenodo. <https://doi.org/10.5281/zenodo.5578807>. The excerpts are unmodified copies
from the archive; the hash of the archive is recorded in each sidecar. No instrumental mix is
committed — the mix conditions used in the investigation are generated locally and documented in
`docs/ENGINE_COMPARISON.md`.

## Adding a sample

1. Verify the licence allows redistribution **and** analysis for this project.
2. Add the file plus a sidecar JSON with ground truth and provenance.
3. Update the table above in the same commit.
4. Keep the total size of this directory small.
