# Dataset

**Status: first samples added (2026-09-25).** Four CC-BY-4.0 `vocadito` excerpts with lyric
ground-truth sidecars are committed under `samples/` (`samples/README.md` has the provenance table).
The full 40-excerpt dataset and the synthetic mix conditions used by the lyrics-ASR investigation are
kept in the gitignored `.cache/lyrics-asr-investigation/` and described in `docs/ENGINE_COMPARISON.md`.
No commercial recording is committed, and the chord/key/tempo categories below are still uncollected.
The 2026-09-25 real-music pass of the lyrics-ASR investigation used one commercial MP3 supplied
by the user: it lives only in the gitignored `mp3/` directory (and the gitignored
`.cache/real-song/`), is never committed or redistributed, and is a local check rather than a
dataset entry — so it carries no sidecar and cannot be reproduced without the reader's own copy.

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
