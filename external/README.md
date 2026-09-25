# external/ — third-party reference repositories

This directory holds third-party Git repositories registered as **git submodules**.
They exist so that a developer (or an AI agent) can *read* a working implementation
while researching a roadmap area — the projects in [`ROADMAP.md`](../ROADMAP.md)
section 24 and related areas (instrument recognition, transcription, audio
identification).

**They are not part of this project.** They are not a library this project uses, not a
dependency, not a source to copy from, and not part of the build. Nothing in
`external/` is imported, packaged, installed, linted, type-checked or tested; the
exclusions are configured in `pyproject.toml` on purpose. The binding rules are in
[`AGENTS.md`](../AGENTS.md).

## Remove what does not survive the research

Nine repositories are registered (2026-09-24, down from a peak of 32). That is a
temporary research pool, not a permanent part of this repository, and submodules are
not free: every clone pays for them, every `git status` walks them, and every stale
pin is maintenance debt.

**This directory must shrink, not grow.** The workflow for every repository here is:

1. investigate it (architecture, licence, maintenance status, relevance to a roadmap
   area);
2. record the verdict in `docs/DEPENDENCY_MATRIX.md` (and in `docs/LICENSE_AUDIT.md`
   before anything is ever copied out of it);
3. **delete the submodule** unless it is still actively needed:

```bash
git submodule deinit -f external/<name>
git rm -f external/<name>
rm -rf .git/modules/external/<name>
```

A repository whose only justification is "might be useful someday" does not survive
step 3. This is not hypothetical: 23 of the original 32 were removed on 2026-09-24
exactly this way, right after their verdicts were recorded.

## Repositories

Licences below were read from each clone's `LICENSE` file (or README where noted) on
2026-09-24. That is an observation, **not** an audit: the audit record lives in
`docs/LICENSE_AUDIT.md`. "no licence file" means the clone contains no licence — treat
the code as fully reserved and never copy from it.

### Block 1 — chords and practice tools (4)

| Submodule | Upstream | What it is | Licence |
| --- | --- | --- | --- |
| `chordify` | <https://github.com/1ucas/chordify> | CQT/CENS chroma, triad templates, bass-aware Viterbi, key/palette priors (§24.1). **Investigated 2026-09-24** — kept as the primary architectural reference (`docs/DEPENDENCY_MATRIX.md` §13.1) | MIT (verified 2026-09-23) |
| `orchidas-Chord-Recognition` | <https://github.com/orchidas/Chord-Recognition> | automatic chord recognition via Pitch Class Profile features: hand-written CQT, JSON triad templates, Gaussian HMM + Viterbi (§24.5). **Investigated 2026-09-24** — kept for now as the research baseline (`docs/DEPENDENCY_MATRIX.md` §13.6) | no licence file |
| `musicpractice` | <https://github.com/atinm/musicpractice> | PySide6 desktop practice app on librosa: own maj/min/7th template + Viterbi chord engine, Krumhansl-Schmuckler key, Vamp/librosa beats, Demucs stems, Basic Pitch → LilyPond notation. **Investigated 2026-09-24 — kept** as the phase-15 GUI/integration blueprint (`docs/DEPENDENCY_MATRIX.md` §13.10) | MIT (LICENSE file) |
| `Guitariz` | <https://github.com/Guitariz/Guitariz> | React/FastAPI platform; its `ml/` holds a from-scratch 109-class chord CRNN, shared CQT-chroma features, a synthetic-data generator and an adaptive-self-transition Viterbi. **Investigated 2026-09-24 — kept** as a chord-engine reference (`docs/DEPENDENCY_MATRIX.md` §13.10) | MIT (LICENSE file) |

### Block 2 — instrument recognition (2)

Kept from an original 12 after investigation (2026-09-24, `docs/DEPENDENCY_MATRIX.md`
§13.8): these are the only two that are paper-backed, MIT-licensed, and technically
relevant to a possible future instrument/stem area of the roadmap.

| Submodule | Upstream | What it is | Licence |
| --- | --- | --- | --- |
| `instrument-prediction` | <https://github.com/biboamy/instrument-prediction> | frame-level instrument recognition by timbre and pitch (ISMIR 2018 paper code, MusicNet, 7 instruments) | MIT (LICENSE file) |
| `predominant-instrument-recognition` | <https://github.com/nii-yamagishilab/predominant-instrument-recognition> | NSynth-pretrained predominant instrument recognition in polyphonic music (APSIPA ASC 2023 paper code) | MIT (LICENSE.txt) |

### Block 4 — cross-cutting libraries (3)

Useful regardless of the analysis area being researched.

| Submodule | Upstream | What it is | Licence |
| --- | --- | --- | --- |
| `libcantus` | <https://github.com/libraz/libcantus> | pure-TypeScript music theory for MIDI note events: recover the harmony from notes and write new parts against it; no runtime dependencies | Apache-2.0 (LICENSE file, with NOTICE) |
| `basic-pitch` | <https://github.com/spotify/basic-pitch> | Spotify's Basic Pitch: lightweight-NN automatic music transcription (Python). Already researched as a dependency — adopted conditionally; see `docs/DEPENDENCY_MATRIX.md` | Apache-2.0 (LICENSE file, with NOTICE) |
| `basic-pitch-ts` | <https://github.com/spotify/basic-pitch-ts> | TypeScript/npm sibling of Basic Pitch for browser and Node transcription | Apache-2.0 (LICENSE file) |

Block 3 (transcription, audio identification and other) was removed entirely on
2026-09-24: its transcription candidate carries non-commercial weights, its
fingerprinting/cloud tools address a problem this project does not have, and the
LLM demo is not an analysis engine — see `docs/DEPENDENCY_MATRIX.md` §13.9.

## Commands

```bash
# add or refresh the repositories listed in scripts/add_external_repos.sh (shallow)
scripts/add_external_repos.sh
scripts/add_external_repos.sh --update

# add one that is missing (shallow is enough for reading)
git submodule add --depth 1 https://github.com/<owner>/<repo> external/<name>

# clone this project together with the references
git clone --recurse-submodules <this-repository-url>

# existing clone: fetch the pinned commits
git submodule update --init --depth 1

# remove one again (the normal outcome after investigation)
git submodule deinit -f external/<name>
git rm -f external/<name>
rm -rf .git/modules/external/<name>
```

Notes:

* `.gitmodules` is the authoritative list of registered paths and URLs; this README
  documents what each one is for.
* Some existing clones were added without `--depth 1`, so they carry full history;
  `scripts/add_external_repos.sh` adds missing ones shallowly.
* Submodules pin an exact commit. `git submodule update --remote` moves the pin, so it
  is a deliberate act, never something to slip into an unrelated change.
* `external/` is intentionally **not** in `.gitignore`: a gitignored path cannot be a
  submodule.
* A plain `git clone` leaves the submodules empty until
  `git submodule update --init` is run. That is fine — the project builds, tests and
  installs without them.
* `yuval-kahan/youchords-local` (formerly roadmap §24.2) was dropped on 2026-09-24: its
  URL no longer exists on GitHub (HTTP 404, checked 2026-09-23). The former
  `Esysc/magic-chords-project` entry is not registered either.
* Removed after investigation (2026-09-24), per the cleanup rule above — verdicts in
  `docs/DEPENDENCY_MATRIX.md` §13:
  * block 1: `chord-extractor` and `Chord-recognition` (superseded by chordify's
    cleaner native pipeline), `scales-chords` (an Obsidian plugin, off scope) and
    `chordscope` (its core beat/chord engine is madmom, already rejected; the
    worth-keeping ideas are recorded in §13.5);
  * §24.7 pass (§13.10): `Chords.py` (unlicensed 2021 MLP with 10 classes and
    `.h5` weights of undocumented provenance), `ChordVisualizer` (a Vue/WASM
    play-and-name theory toy — no audio analysis) and `ChordMiniApp` (cloud stack;
    its nested model submodules are uninitialized and its LFS checkpoints are absent
    because upstream exhausted its LFS budget);
  * §24.6 (§13.11): `MOSS-Music` — its ~18.1 GB of bf16 weights, missing quantization
    path and CUDA-only runtime make it unviable on this CPU-first project's target
    hardware;
  * block 2: ten course projects and notebooks, eight of them without any licence
    file, plus the GPL-3.0 thesis whose MedleyDB dependency is not redistributable
    (§13.8);
  * block 3: all five, including `muscriptor` (code MIT, **weights CC BY-NC 4.0**) —
    the same non-commercial-weights pattern that rejected madmom and Essentia (§13.9).
