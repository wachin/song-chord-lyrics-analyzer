# AGENTS.md — instructions for AI coding agents

This file applies to automated coding agents, and to humans acting like one in this
repository. [`ROADMAP.md`](ROADMAP.md) is the specification and wins over
convenience; [`CONTRIBUTING.md`](CONTRIBUTING.md) holds the human-facing rules. Read
both before changing anything.

## Start here

A fresh checkout needs Python 3.10+ and no private assets. The documented gate
environment installs the development tools **and** the window stubs:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev,gui]"
python scripts/check.py
```

For the full DSP/playback/window suite use
`python -m pip install -e ".[dev,dsp,playback,gui]"`. The `lyrics` extra is
separate because it downloads the Parakeet model; do not install it just to run
the gate. `python scripts/check.py` runs ruff, the format check, mypy and
pytest with the current interpreter and sets `QT_QPA_PLATFORM=offscreen` on
headless Linux. `--quick` runs only the static checks; `--tests-only` runs only
pytest.

There is no required virtual-environment name. `.venv` is the convention;
`.venv-chords` in old session notes is a local author environment and must not
be assumed to exist. `mp3-library/` is a private submodule: its absence is
normal for a contributor and no test may depend on it. `external/` may be empty
unless you explicitly initialised the reference submodules; neither the build
nor the tests need them.

Read [`docs/AGENT_ONBOARDING.md`](docs/AGENT_ONBOARDING.md) for the environment
matrix, repository map, common failures and a copy-paste prompt template.
`CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md` and
`.cursor/rules/repository.mdc` are short pointers to this file; edit this file
when a rule changes, not the pointers.

## What this repository is

`song-chord-lyrics-analyzer` is a **Python package plus a CLI** (`songlab`) and a
**desktop window**, on its way to a Chordify/Chord AI-style application. The
roadmap was reset on 2026-10-06 around the product path, and the *first product
milestone* (Phase C) is reached: canonical typed model, engine interfaces, audio
metadata and validation, a shared decode service, a tested playback layer, and
the commands `songlab info`, `doctor`, `chords`, `analyze` and `play` — the last
one plays a file and draws the chord under the playhead as it advances.
`songlab gui` adds the window: waveform, chord strip, transport, editing and
undo/redo, transpose/simplify, exports, external `.lrc`/`.srt` lyrics, a
**chord chart over the synchronized lyrics** (each chord above the timed word it
changes on, instrumental gaps included), and a **plain-text chart import** that
uses the chart's chords and lyrics, anchors the chords under the chart's own
columns, and times the words from the transcript. Registered engines: chords
`chroma-baseline`, lyrics `parakeet-onnx`, key `krumhansl`, tempo
`librosa-tempo`.

Two claims are allowed and no more: what was **measured** (always with its
environment and date) and what was **verified by running it**. Chord accuracy is
*measured* (CSR 0.6312, triad-reduced 0.6384, on 180 GuitarSet comping takes
against the instructed lead sheet, 2026-10-27, reproducible with
`scripts/chord_benchmark.py`; the previous front end measured 0.6121 / 0.6183
and the retired 0.4260 did not reproduce — `docs/ENGINE_COMPARISON.md` §2, §3,
§7, §8). Per-chord confidence is measured too (held-out Brier 0.1485, ECE
0.0363, accuracy 0.809 at coverage 0.476; `docs/ENGINE_COMPARISON.md` §8).
Lyrics are research with a registered engine but no accuracy claim; the display
now includes the synchronized chord-over-lyrics chart, verified offscreen and by
tests, but the project is not yet at the accuracy of the proprietary apps and
must not be described as matching their published numbers. The authoritative
status is the marker table in [`ROADMAP.md`](ROADMAP.md) §1.

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

## Agent workflow

1. Pick one roadmap deliverable that is `[ ]` or `[~]`; read its status line and
   the tests around it before writing code.
2. Add a failing regression test first where the behaviour is testable, then the
   smallest general implementation in the correct layer.
3. Update the roadmap marker/status and any user-facing changelog/docs in the
   same change.
4. Run `python scripts/check.py` and report the real result. A skipped optional
   test is not a failure; a skipped required test is not a pass.
5. Keep commits focused. Do not rewrite published history, force-push or push
   unless the maintainer asked; do not commit generated state.

A change is done only when the roadmap marker is honest, the tests cover the
new path, the gate passes, `external/` is untouched, and no private material or
invented measurement entered the tree.

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
* **Private material never becomes a fixture.** The author's `mp3-library/`
  submodule, the real song/chart used in local checks, and
  `images/A-quien-ire/` are intentionally untracked. Do not commit, quote or
  embed private audio, user lyrics or screenshots of copyrighted lyrics; use
  generated audio and invented text in tests and docs.
* **Do not push generated state.** Results, caches, `.venv*`, model downloads and
  temporary WAVs stay out of the repository.
