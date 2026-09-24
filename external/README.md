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

Twenty-four repositories are registered (2026-09-24). That is a temporary research
pool, not a permanent part of this repository — it is too many to keep, and submodules
are not free: every clone pays for them, every `git status` walks them, and every stale
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
step 3.

## Repositories

Licences below were read from each clone's `LICENSE` file (or README where noted) on
2026-09-24. That is an observation, **not** an audit: the audit record lives in
`docs/LICENSE_AUDIT.md`. "no licence file" means the clone contains no licence — treat
the code as fully reserved and never copy from it.

### Block 1 — chords (8)

| Submodule | Upstream | What it is | Licence |
| --- | --- | --- | --- |
| `Chords.py` | <https://github.com/yuval-kahan/Chords.py> | chord recognition experiments (Python, Keras models, jim2012Chords features) with a Windows C# demo app | no licence file |
| `chord-extractor` | <https://github.com/yuval-kahan/chord-extractor> | Python library that extracts chord sequences from sound files, with multiprocessing for batch extraction | GPL-2.0 (LICENSE file) |
| `Chord-recognition` | <https://github.com/yuval-kahan/Chord-recognition> | university ML course project: chord decoding from WAV files with machine learning | no licence file |
| `chordify` | <https://github.com/1ucas/chordify> | CQT/CENS chroma, triad templates, bass-aware Viterbi, key/palette priors (§24.1) | MIT (verified 2026-09-23) |
| `MOSS-Music` | <https://github.com/OpenMOSS/MOSS-Music> | music/audio foundation model; feasibility on commodity CPU untested (§24.6) | Apache-2.0 per README (models); no top-level LICENSE file |
| `scales-chords` | <https://github.com/yuval-kahan/scales-chords> | plugin that embeds guitar/piano chord diagrams (images from scales-chords.com) in fenced code blocks | MIT (LICENSE file) |
| `chordscope` | <https://github.com/okamyuji/chordscope> | CLI: Madmom + librosa + music21, modulation and tempo-curve analysis (§24.4) | MIT (LICENSE file) |
| `orchidas-Chord-Recognition` | <https://github.com/orchidas/Chord-Recognition> | automatic chord recognition from monophonic/polyphonic audio via Pitch Class Profile features (§24.5) | no licence file |

### Block 2 — instrument recognition (11)

Extra study material: none of these is a target of section 24; they inform a possible
future instrument/stem area of the roadmap.

| Submodule | Upstream | What it is | Licence |
| --- | --- | --- | --- |
| `Music-Instrument-Recognition` | <https://github.com/dhivyasreedhar/Music-Instrument-Recognition> | CNN (mel spectrograms) vs kNN (MFCCs) on the London Philharmonic dataset; monophonic only | no licence file |
| `music-instrument-classifier` | <https://github.com/IvyZX/music-instrument-classifier> | single-note classifier for cello, clarinet, flute, violin and piano (4th octave) | no licence file |
| `Musical-Instrument-Recognition-by-XGBoost` | <https://github.com/Jay-Codeman/Musical-Instrument-Recognition-by-XGBoost> | team project on Medley-solos-DB using XGBoost over audio features | no licence file |
| `babaktr-musical-instrument-recognition` | <https://github.com/babaktr/musical-instrument-recognition> | musical instrument recognition system using artificial neural networks | no licence file |
| `instrument-prediction` | <https://github.com/biboamy/instrument-prediction> | frame-level instrument recognition by timbre and pitch (ISMIR 2018 paper code) | MIT (LICENSE file) |
| `Instrument-Recognition-with-CNNs` | <https://github.com/bt-s/Instrument-Recognition-with-CNNs> | KTH DT2119 course project: instrument recognition with CNNs | no licence file |
| `predominant-instrument-recognition` | <https://github.com/nii-yamagishilab/predominant-instrument-recognition> | NSynth-pretrained predominant instrument recognition (APSIPA ASC 2023 paper code) | MIT (LICENSE.txt) |
| `bronzelion-musical-instrument-recognition` | <https://github.com/bronzelion/musical-instrument-recognition> | app that detects the instrument of an audio clip (four instruments covered) | no licence file |
| `instrument-recognition-polyphonic` | <https://github.com/vskadandale/instrument-recognition-polyphonic> | master's thesis (UPF SMC): polyphonic instrument recognition trained on MedleyDB | GPL-3.0 (LICENSE file) |
| `instrument-recogniton` | <https://github.com/vk-mittal14/instrument-recogniton> | string-instrument classification with machine learning | no licence file |
| `instrument-classifier` | <https://github.com/LMicol/instrument-classifier> | instrument sound classification from mel spectrogram features | MIT (LICENSE file) |

### Block 3 — transcription, audio identification and other (5)

Extra study material outside the current scope of section 24.

| Submodule | Upstream | What it is | Licence |
| --- | --- | --- | --- |
| `muscriptor` | <https://github.com/muscriptor/muscriptor> | MuScriptor (Kyutai + Mirelo): multi-instrument transcription of a recording into MIDI and sheet music | MIT (LICENSE file) |
| `presto` | <https://github.com/skulklabs/presto> | Go: identifies a song from a short clip by matching compact fingerprints against a persistent library | MIT (LICENSE file) |
| `shazam-build` | <https://github.com/Danztee/shazam-build> | from-scratch Shazam audio fingerprinting in Go (DSP pipeline, PostgreSQL fingerprint store, React frontend) | MIT (LICENSE file) |
| `audd-go` | <https://github.com/AudDMusic/audd-go> | Go client for the AudD cloud music recognition API | MIT (LICENSE file) |
| `Ear` | <https://github.com/Kaidorespy/Ear> | audio perception for LLMs: analyses a song and has an LLM write a grounded description of it | MIT (LICENSE file) |

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
* The existing clones were added without `--depth 1`, so they carry full history;
  `scripts/add_external_repos.sh` adds missing ones shallowly.
* Submodules pin an exact commit. `git submodule update --remote` moves the pin, so it
  is a deliberate act, never something to slip into an unrelated change.
* `external/` is intentionally **not** in `.gitignore`: a gitignored path cannot be a
  submodule.
* A plain `git clone` leaves the submodules empty until
  `git submodule update --init` is run. That is fine — the project builds, tests and
  installs without them.
* The section 24.2 target `yuval-kahan/youchords-local` is deliberately absent: its URL
  returns **HTTP 404** (checked 2026-09-23). The former `Esysc/magic-chords-project`
  entry is not registered either.
