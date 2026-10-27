# Working with an AI coding agent

This is the stable onboarding guide for a developer bringing an AI coding agent
to this repository. It is written for the agent as much as for the human. The
repository's binding rules are in [`AGENTS.md`](../AGENTS.md); this document
explains how to set up a working tree, where things live, and how to finish a
change without breaking the project's evidence and licensing rules.

> Superseded session notes live in Git history. Current status is
> [`ROADMAP.md`](../ROADMAP.md) §1 and `CHANGELOG.md`; this page is the setup and
> workflow guide, and `AGENTS.md` holds the binding rules.

## 1. Five-minute setup

Requirements: Python 3.10 or newer, `venv`, `pip`, and a Git checkout. FFmpeg is
needed only for non-WAV audio; `sounddevice` is needed only for live playback;
`PyQt6` is needed for the window and for the mypy gate.

Linux / macOS:

```bash
git clone https://github.com/song-chord-lyrics-analyzer/song-chord-lyrics-analyzer.git
cd song-chord-lyrics-analyzer

python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel

# The documented gate: lint, types, tests, window tests.
python -m pip install -e ".[dev,gui]"
```

Windows (PowerShell):

```powershell
git clone https://github.com/song-chord-lyrics-analyzer/song-chord-lyrics-analyzer.git
cd song-chord-lyrics-analyzer

py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev,gui]"
```

For the full local suite (real DSP engines, playback layer and window):

```bash
python -m pip install -e ".[dev,dsp,playback,gui]"
```

The `lyrics` extra is separate because it downloads the Parakeet model on first
use:

```bash
python -m pip install -e ".[dev,dsp,playback,gui,lyrics]"
```

Do not install it just to run the gate. Its integration tests are marked and
skip when the stack or model is absent; the normal suite never downloads a
model and never needs the network.

There is no required environment name. `.venv` is the convention in the docs;
the author's `.venv-chords` is a local name from earlier sessions and must not be
assumed to exist in a fresh clone. If you use several environments, name them
yourself and activate the one you mean.

## 2. The one gate command

```bash
python scripts/check.py
```

It runs, from the repository root, with the interpreter that invoked it:

1. `ruff check .`
2. `ruff format --check .`
3. `python -m mypy`
4. `python -m pytest -q`

On headless Linux it sets `QT_QPA_PLATFORM=offscreen` unless already set. It
does not install packages, download models or touch the network.

Useful modes:

```bash
python scripts/check.py --quick       # ruff + mypy, no pytest
python scripts/check.py --tests-only  # pytest only
```

If a tool is missing, the script prints the documented extras. The most common
mistake is installing only `.[dev]`: that leaves PyQt6 out, and the mypy gate
then fails on `gui/` even though "only types" were requested.

CI remains authoritative: `.github/workflows/ci.yml` runs lint/type checks on
Ubuntu with Python 3.12, the test matrix on Linux/Windows/macOS for Python
3.10–3.13, and the DSP/FFmpeg jobs. A green local gate is necessary, not a
substitute for CI.

## 3. Read order

Before writing code:

1. [`AGENTS.md`](../AGENTS.md) — hard rules, `external/`, markers, privacy.
2. [`ROADMAP.md`](../ROADMAP.md) §1 and the phase you are touching — the
   specification and current marker table.
3. [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — layers and dependency direction.
4. [`docs/DEVELOPMENT.md`](DEVELOPMENT.md) — setup, commands, conventions.
5. The tests next to the code (`tests/unit`, `tests/integration`,
   `tests/regression`) and the relevant `docs/` decision record.

## 4. Where the code lives

| Path | Responsibility |
| --- | --- |
| `src/.../models/` | Canonical typed data (`AnalysisResult`, `ChordEvent`, `LyricSegment`, confidence). Frozen after phase 14; change deliberately. |
| `src/.../engines/` | Engine protocols (`ChordEngine`, `LyricsEngine`, …), registry and implementations. Models are optional extras. |
| `src/.../analysis/` | Orchestration of the engines, progress and provenance. |
| `src/.../app/` | Plain-Python application presenters, session, timeline, display, editing, persistence, chart import. **New GUI logic belongs here.** |
| `src/.../gui/` | Thin PyQt6 widgets. Read `SongSession` and `app/` only; never call librosa or engine internals. |
| `src/.../evaluation/` | Scoring, benchmarks, chart parsing/agreement. |
| `src/.../metrics/`, `alignment/` | Standalone metric and timed-text alignment code. |
| `src/.../audio/`, `schema/` | Decode/playback/validation and the JSON codec. |
| `tests/` | Unit, integration, regression; fixtures generate audio and text. |
| `scripts/` | Developer tools, not shipped. `check.py` is the gate. |
| `docs/`, `ROADMAP.md` | Decisions, evidence, status. |
| `external/` | Third-party submodules: **reference only**, never imported, packaged, linted, installed or modified. |

The dependency direction is:

```text
CLI / GUI -> app/ -> analysis/ / engines/ -> models/
                 \-> evaluation/ / metrics/ / alignment/
```

Do not invert it. If a presenter needs a widget, it is not a presenter; if a
widget needs a decoder, it belongs behind `app/` or the session.

## 5. Anatomy of a good change

1. **Pick one roadmap deliverable.** State the section and marker you intend to
   move. If it is larger than one reviewable change, stop after the first
   vertical slice and leave the marker `[~]` with the remaining work named.
2. **Read the existing tests** before adding code. Add a failing regression test
   that names the behaviour, or explain in the commit why no new test is
   possible.
3. **Implement the smallest general change** in the right layer. Search the
   existing modules first, prefer a pure function or presenter over a new widget,
   and an existing seam over a new dependency.
4. **Update the record in the same change**: `ROADMAP.md` marker/status,
   `CHANGELOG.md` when user-visible, and the relevant `docs/` section. Do not
   invent numbers; if you measured something, record the environment and date.
5. **Run the gate** (`python scripts/check.py`) and paste the real result into
   the pull request. Do not claim a pass you did not run.
6. **Commit focused history.** Do not rewrite published history, force-push, or
   commit generated caches, virtual environments, model weights, private songs,
   lyrics, or screenshots of copyrighted text.

## 6. Definition of done

A change is done only when all of these are true:

- [ ] The roadmap section/task is marked `[x]` (fully implemented) or `[~]`
      (partly implemented, with the missing part stated).
- [ ] Tests cover the new behaviour, including a failure/edge case; optional
      dependencies are skipped, not failed.
- [ ] `python scripts/check.py` passes, or the remaining failure is reported
      honestly with its output.
- [ ] No `external/` code, weights, datasets or assets were imported, copied or
      added as a dependency.
- [ ] No private audio, user lyrics, model caches, `.venv*`, `.cache/`, results
      or generated benchmark files were committed.
- [ ] Any measurement has its environment, date, command and manifest; no
      proprietary-app parity is claimed.
- [ ] The GUI (if touched) was verified offscreen and the logic lives in
      `app/`, not in the widget.

## 7. Evidence and privacy rules

Before repeating a dataset, licensing, chord-decoding or engine comparison,
read [`ENGINE_COMPARISON.md`](ENGINE_COMPARISON.md), [`DATASET.md`](DATASET.md),
[`LICENSE_AUDIT.md`](LICENSE_AUDIT.md) and
[`DEPENDENCY_MATRIX.md`](DEPENDENCY_MATRIX.md). Those questions have measured
answers; do not re-open them without a concrete new dependency or product
reason. The product path comes first: research and benchmarks support it, they
do not replace it.

- **Never invent a number.** A benchmark or accuracy figure needs a committed
  script, a fixed input manifest, the environment and the date. `CSR 0.6312` is
  the current 180-take GuitarSet measurement; it is not a universal accuracy
  claim.
- **Do not tune on the test set.** Keep held-out takes out of feature or
  threshold selection.
- **No proprietary weights.** Public BTC weights and similar models may be
  non-commercial; check `docs/LICENSE_AUDIT.md` first.
- **`external/` is not a dependency.** Reading it is fine; importing, copying or
  adding it to the build is not.
- **Private material is not a fixture.** `mp3-library/`, the author's real song,
  its chart and the `images/A-quien-ire/` screenshot are private and
  intentionally untracked. Use `tests/fixtures/audio.py` and invented lyrics.
  Never add a commercial recording to a test or a commit.
- **Generated state stays out.** `.venv*`, `.cache/`, `results/`, `benchmark/`
  reports, `*.qm` unless intentionally shipped, model downloads and `:memory:`
  databases are ignored for a reason.

## 8. Common setup failures

| Symptom | Cause | Fix |
| --- | --- | --- |
| `mypy` reports missing `PyQt6` | installed `.[dev]`, not `gui` | `python -m pip install -e ".[dev,gui]"` |
| window tests are skipped | PyQt6 absent | install `gui`; `scripts/check.py` sets offscreen |
| DSP tests are skipped | numpy/librosa/soundfile absent | install `dsp` |
| playback tests are skipped | no output device or `sounddevice` absent | normal on headless machines; install `playback` if you need live audio |
| lyrics integration asks for a model or network | `lyrics` extra present/absent | normal; leave it out of the gate |
| `external/` is empty or submodules are uninitialised | private/reference checkout | do not run `git submodule update` for unrelated work; it is not needed to build or test |
| `mp3-library` is empty | private submodule | expected for outside contributors; never add a test that depends on it |
| Qt cannot connect to a display | headless Linux | `export QT_QPA_PLATFORM=offscreen` (the gate script does this) |

## 9. Prompt template for the human

Paste this into a new agent session, replacing the section:

```text
Work in /path/to/song-chord-lyrics-analyzer.

Read, in order: AGENTS.md, docs/AGENT_ONBOARDING.md, ROADMAP.md §1 and
the section for <phase/task>, docs/ARCHITECTURE.md, and the tests near the
code you will touch.

Goal: <one concrete roadmap deliverable>.

Constraints:
- Follow the layer rules (GUI -> app -> engines; no engine imports in gui/).
- Do not touch external/, don't add a dependency or weights without a licence
  audit, and don't commit private songs/lyrics/caches.
- Add or update tests. Mark the roadmap task [x] or [~] in the same change.
- Run `python scripts/check.py` before claiming done and report the real output.
- Don't commit or push unless I ask.
```

## 10. Tool entry points

Different agents look for different files. They all delegate to `AGENTS.md`:

- `AGENTS.md` — canonical instructions (Codex, Cursor, many tools).
- `CLAUDE.md` — Claude Code pointer.
- `GEMINI.md` — Gemini CLI pointer.
- `.github/copilot-instructions.md` — GitHub Copilot pointer.
- `.cursor/rules/repository.mdc` — Cursor rule pointer.

Edit `AGENTS.md` first; update the pointers only if a tool needs a different
path, and keep them short so they cannot drift.
