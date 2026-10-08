# AGENTS.md — instructions for AI coding agents

This file applies to automated coding agents, and to humans acting like one in this
repository. [`ROADMAP.md`](ROADMAP.md) is the specification and wins over
convenience; [`CONTRIBUTING.md`](CONTRIBUTING.md) holds the human-facing rules. Read
both before changing anything.

## What this repository is

`song-chord-lyrics-analyzer` is a **Python package plus a CLI** (`songlab`), on its
way to a desktop application. The roadmap was reset on 2026-10-06 around the product
path, and the *first product milestone* (Phase C) is reached: canonical typed model,
engine interfaces, audio metadata and validation, a shared decode service, a tested
playback layer, and the commands `songlab info`, `doctor`, `chords`, `analyze` and
`play` — the last one plays a file and draws the chord under the playhead as it
advances. Registered engines: chords `chroma-baseline`, key `krumhansl`, tempo
`librosa-tempo`.

Two claims are allowed and no more: what was **measured** (always with its
environment and date) and what was **verified by running it**. Chord accuracy is
*measured but low* (CSR 0.4260 on 180 GuitarSet takes), lyrics are still research
with no engine registered, and the display is a terminal line — so the project is
not yet a Chordify-style desktop application, and it must not be described as one.
The authoritative status is the marker table in [`ROADMAP.md`](ROADMAP.md) §1.

| Path | What it is |
| --- | --- |
| `src/song_chord_lyrics_analyzer/` | the package and the code that ships |
| `tests/` | unit, regression and integration tests |
| `docs/` | the decision and research record |
| `scripts/` | developer scripts, not shipped |
| `external/` | **third-party reference repositories — not code of this project** |

## Hard rule: `external/` is reference material, not a library

`external/` contains third-party Git repositories registered as **git submodules**.
They are kept so that a human or an agent can *read* implementations while
researching a roadmap area (section 24, plus adjacent study areas such as instrument
recognition and audio transcription). They are **not** a library this project uses,
**not** a dependency, and **not** part of the build.

An agent working here MUST NOT:

1. import anything from `external/`, or put it on `sys.path`, `PYTHONPATH`,
   `pythonpath` or `testpaths`;
2. add it to `dependencies` or `optional-dependencies`, install it with `pip`, or
   call its code at runtime;
3. include it in the wheel, the sdist or any release artefact;
4. lint, format, type-check or test it — `external/` is deliberately excluded in
   `pyproject.toml` (ruff, mypy, pytest) for exactly this reason;
5. copy code, weights, datasets or assets out of it without recording the licence in
   `docs/LICENSE_AUDIT.md` and the findings in `docs/DEPENDENCY_MATRIX.md` **first**;
6. modify it: no commits, branches, stashes or edits inside a submodule, and no
   `git submodule update --remote` as part of an unrelated change;
7. describe it, in code, docs, comments or commit messages, as a dependency of this
   project.

Correct uses of `external/`: reading how another project structured chroma extraction,
Viterbi decoding, caching, model handling or timestamp alignment — and then writing
original code in `src/`.

If a reference repository is genuinely worth adopting, follow
[`CONTRIBUTING.md`](CONTRIBUTING.md) ("Adding an analysis engine"): licence audit
first, then an optional extra, then an engine behind the interface, with tests. The
submodule is never the integration path.

## Roadmap progress markers

`ROADMAP.md` tracks its own progress. Every section, subsection and task carries a
bracket marker:

* `[x]` — **implemented**: the requirement exists in the repository, runs, and was
  verified by executing it (not by documentation or partial tests);
* `[~]` — **partially implemented**: the missing part is stated in the phase;
* `[ ]` — **not implemented**.

Finish work and mark it in the same change. A change that advances a roadmap item but
leaves its marker unset is incomplete, exactly like a change with no tests. Never mark
a section `[x]` because it looks close, and never invent a fourth marker. (The old
`[*]` convention belongs to the archived pre-reset roadmap.)

## Other rules that are easy to get wrong

* **Gate before claiming done.** All of these must pass:
  `ruff check .`, `ruff format --check .`, `python -m mypy`, `pytest -q`. Markdown is
  excluded from the formatter on purpose — do not "fix" the roadmap's formatting.
  `mypy` type-checks `gui/` against the real PyQt6 stubs, so the development venv
  installs the `gui` extra (`pip install -e ".[dev,gui]"`); that is a dev-environment
  requirement, not a dependency of the installed package.
* **Never invent numbers.** No benchmark, timing or accuracy figure may appear in
  docs or commits unless it was measured, and a measurement must state the
  environment and the date.
* **English only** for identifiers, CLI text, errors, logs, docs and test names.
* **GUI after the product slice, and always through `app/`.** The headless slice
  (Phase C) exists and so does the minimal window (Phase D, `songlab gui`, behind
  the optional `gui` extra). Widgets read `SongSession` and the `app/` presenters
  only: GUI → `app/` → engines, never GUI → librosa, and new logic goes into
  plain-Python presenters so it stays testable offscreen. `gui/` imports Qt
  lazily, so the core install and the test matrix stay Qt-free.
* **Licences.** This project is GPL-3.0-or-later. Model weights, datasets and external
  tools have their own licences and several of the audited candidates are non-free for
  commercial use. Check `docs/LICENSE_AUDIT.md` before proposing anything.
* **Do not push generated state.** Results, caches, `.venv*`, model downloads and
  temporary WAVs stay out of the repository.
