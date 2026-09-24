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

| File | Source | Licence | Purpose |
| --- | --- | --- | --- |
| *(none yet)* | — | — | The first samples arrive with the phase 3/4 laboratories. |

## Adding a sample

1. Verify the licence allows redistribution **and** analysis for this project.
2. Add the file plus a sidecar JSON with ground truth and provenance.
3. Update the table above in the same commit.
4. Keep the total size of this directory small.
