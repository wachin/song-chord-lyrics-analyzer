# external/ — third-party reference repositories

This directory holds third-party Git repositories registered as **git submodules**.
They exist so that a developer (or an AI agent) can *read* a working implementation
while researching a roadmap area — the projects listed in
[`ROADMAP.md`](../ROADMAP.md) section 24.

**They are not part of this project.** They are not a library this project uses, not a
dependency, not a source to copy from, and not part of the build. Nothing in
`external/` is imported, packaged, installed, linted, type-checked or tested; the
exclusions are configured in `pyproject.toml` on purpose. The binding rules are in
[`AGENTS.md`](../AGENTS.md).

## Repositories

| Submodule | Upstream | Why it is here | Licence |
| --- | --- | --- | --- |
| `chordify` | <https://github.com/1ucas/chordify> | CQT/CENS chroma, triad templates, bass-aware Viterbi, key/palette priors (§24.1) | MIT (verified) |
| `magic-chords-project` | <https://github.com/Esysc/magic-chords-project> | end-to-end web app: Madmom + Basic Pitch + Whisper + Essentia, exports (§24.3) | not audited yet |
| `chordscope` | <https://github.com/okamyuji/chordscope> | CLI: Madmom + librosa + music21, modulation and tempo-curve analysis (§24.4) | not audited yet |
| `Chord-Recognition` | <https://github.com/orchidas/Chord-Recognition> | PCP → CQT → templates → HMM/Viterbi research baseline (§24.5) | not audited yet |
| `MOSS-Music` | <https://github.com/OpenMOSS/MOSS-Music> | music/audio model, Apache-2.0, feasibility untested (§24.6) | Apache-2.0 (code; weights separate) |

`youchords-local` (§24.2) is deliberately absent: its URL returns **HTTP 404** (checked
2026-09-23). Add it once the roadmap points at the right repository.

## Commands

All of these are also wrapped by `scripts/add_external_repos.sh`.

```bash
# add or refresh every reference repository (shallow: --depth 1)
scripts/add_external_repos.sh
scripts/add_external_repos.sh --update

# clone this project together with the references
git clone --recurse-submodules <this-repository-url>

# existing clone: fetch just the reference repositories
git submodule update --init --depth 1

# one repository only
git submodule add --depth 1 https://github.com/1ucas/chordify external/chordify

# remove one again
git submodule deinit -f external/chordify
git rm -f external/chordify
rm -rf .git/modules/external/chordify
```

Notes:

* Submodules pin an exact commit. `git submodule update --remote` moves the pin, so it
  is a deliberate act, never something to slip into an unrelated change.
* `external/` is intentionally **not** in `.gitignore`: a gitignored path cannot be a
  submodule.
* A plain `git clone` leaves the submodules empty until
  `git submodule update --init` is run. That is fine — the project builds, tests and
  installs without them.
