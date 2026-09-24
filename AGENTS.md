# AGENTS.md — instructions for AI coding agents

This file applies to automated coding agents, and to humans acting like one in this
repository. [`ROADMAP.md`](ROADMAP.md) is the specification and wins over
convenience; [`CONTRIBUTING.md`](CONTRIBUTING.md) holds the human-facing rules. Read
both before changing anything.

## What this repository is

`song-chord-lyrics-analyzer` is a **Python package plus a CLI** (`songlab`). It is in
phase 2 of the roadmap: canonical typed model, engine interfaces, audio metadata and
two console commands (`songlab info`, `songlab doctor`). **No analysis engine exists
yet**, so no accuracy claim about lyrics, chords, key, tempo or beats may be made
anywhere.

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

* `[x]` — already achieved when the convention was introduced (2026-09-23);
* `[ ]` — not achieved yet; an italic *Status* line states what exists and what is
  missing;
* `[*]` — **newly completed**, and it must carry the completion date, for example
  `[*] (2026-09-24)`.

Finish work and mark it in the same change. A change that advances a roadmap item but
leaves its marker unset is incomplete, exactly like a change with no tests. Never mark
a section `[x]` because it looks close, and never invent a fourth marker.

## Other rules that are easy to get wrong

* **Gate before claiming done.** All of these must pass:
  `ruff check .`, `ruff format --check .`, `python -m mypy`, `pytest -q`. Markdown is
  excluded from the formatter on purpose — do not "fix" the roadmap's formatting.
* **Never invent numbers.** No benchmark, timing or accuracy figure may appear in
  docs or commits unless it was measured, and a measurement must state the
  environment and the date.
* **English only** for identifiers, CLI text, errors, logs, docs and test names.
* **GUI last.** No PyQt6/GUI code before the analysis engine is stable (phase 15).
  Rule 1 of the roadmap.
* **Licences.** This project is GPL-3.0-or-later. Model weights, datasets and external
  tools have their own licences and several of the audited candidates are non-free for
  commercial use. Check `docs/LICENSE_AUDIT.md` before proposing anything.
* **Do not push generated state.** Results, caches, `.venv*`, model downloads and
  temporary WAVs stay out of the repository.
