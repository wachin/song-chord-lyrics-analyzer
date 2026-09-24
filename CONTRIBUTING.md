# Contributing

Thanks for helping. This project follows [`ROADMAP.md`](ROADMAP.md) as its
specification; the roadmap wins over convenience.

## Ground rules

1. Do not build the GUI first. The CLI laboratory comes first.
2. Research a technology before integrating it: record findings in
   `docs/DEPENDENCY_MATRIX.md` and `docs/LICENSE_AUDIT.md`.
3. Do not assume a repository or a model is production-ready or free for
   commercial use. Check the licence, including the weights.
4. Never invent benchmark results. Only measured numbers may be written down.
5. Preserve raw engine output; never silently overwrite an analysis.
6. Keep engines behind interfaces and keep the GUI free of analysis algorithms.
7. English only for identifiers, CLI text, errors, logs, docs and test names.
8. Support Linux, Windows and macOS; use `pathlib`, never hard-coded paths.
9. Treat audio files as untrusted input: argument lists, `shell=False`,
   explicit timeouts.
10. Do not introduce a dependency that is not needed.

## Roadmap progress markers

[`ROADMAP.md`](ROADMAP.md) is both the specification and the progress tracker.
Every section, subsection and task carries a bracket marker:

* `[x]` — already achieved when the convention was introduced (2026-09-23).
* `[ ]` — not achieved yet. An italic *Status* line states what exists and what
  is still missing.
* `[*]` — **newly completed**. Anything finished after 2026-09-23 is marked with
  `[*]` plus the completion date, for example `[*] (2026-09-24)`.

Rules:

1. Work completed in a change must be marked in that same change. A change that
   advances a roadmap item but leaves its marker unset is incomplete, exactly
   like a change with no tests.
2. Newly finished work is marked `[*]`, never `[x]`. `[x]` records the state at
   the introduction of the convention; it is not a moving target.
3. Markers must be defensible against the code. Never mark something `[x]`
   because it looks close: only when the section's own deliverable is truly met.
4. A partially finished section stays `[ ]`; the *Status* line carries the
   detail. Do not invent a fourth marker.
5. Name the roadmap sections you changed in the pull-request description.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

## Before opening a pull request

```bash
ruff check .            # lint
ruff format --check .   # formatting (markdown is excluded on purpose)
python -m mypy          # types
pytest -q               # tests
songlab --help          # CLI still starts
```

All four must pass. CI runs them on Linux, Windows and macOS for Python 3.10 to
3.13.

Roadmap progress markers must be updated in the same change: mark what you
finished with `[*]` and its date, as described above.

## Adding an analysis engine

1. Add the licence and platform findings to `docs/LICENSE_AUDIT.md` and
   `docs/DEPENDENCY_MATRIX.md` first.
2. Implement the relevant protocol from `engines/base.py`
   (`ChordEngine`, `LyricsEngine`, ...) in `engines/<name>.py`, including
   `is_available()` and `engine_info()`.
3. Register it in `engines/registry.py::create_default_registry()`.
4. Add unit tests (fake payload, no network) and an integration test that skips
   when the dependency is missing.
5. Document installation, platform support and known limitations.

## Tests

* Never require network access, never download models.
* Never commit copyrighted commercial songs. Generate audio
  (`tests/fixtures/audio.py`) or use clearly licensed material in `samples/`.
* Bug fixes come with regression tests; expected behaviour lives in
  `tests/fixtures/*.json` so changes appear as reviewable diffs.

## Commits and reviews

Keep commits focused and explain *why* in the message. If a change alters the
canonical model, the engine interfaces or a CLI contract, say so explicitly -
those are frozen at phase 14 and change deliberately, not incidentally.
