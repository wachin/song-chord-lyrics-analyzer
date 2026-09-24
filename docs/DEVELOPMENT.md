# Development

## 1. Requirements

* Python 3.10 or newer (CI tests 3.10, 3.11, 3.12 and 3.13)
* `venv` + `pip` — Conda, Poetry and Pipenv are intentionally not required
* Optional: FFmpeg (`ffmpeg` + `ffprobe`) for anything that is not a WAV file

## 2. Setup

Linux / macOS:

```bash
git clone <repository>
cd song-chord-lyrics-analyzer

python -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

Windows (PowerShell):

```powershell
git clone <repository>
cd song-chord-lyrics-analyzer

python -m venv .venv
.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

The core package has **no** required dependencies. Analysis engines are opt-in
extras that are added phase by phase, with their licence and platform support
recorded in `docs/DEPENDENCY_MATRIX.md` first.

## 3. Everyday commands

```bash
pytest                       # full suite
pytest -q -m "not integration"   # skip tests that need FFmpeg
pytest -m integration        # only the FFmpeg integration tests
ruff check .                 # lint
ruff format --check .        # formatting (markdown is excluded on purpose)
python -m mypy               # type check
songlab --help               # CLI smoke check
songlab doctor               # environment report
songlab info samples/example.wav
```

## 4. Repository layout

```text
src/song_chord_lyrics_analyzer/   package (see docs/ARCHITECTURE.md)
tests/unit/                       fast, dependency-free tests
tests/integration/                tests that need FFmpeg or heavy models
tests/regression/                 fixture-driven behaviour locks
tests/fixtures/                   generated audio helpers + expectation JSON
docs/                             architecture, matrix, licence audit, this file
samples/                          small, licence-clear audio for experiments
benchmark/                        generated benchmark reports
results/                          generated analysis output (git-ignored)
scripts/                          one-off maintenance helpers
translations/                     Qt Linguist catalogues (phase 17)
```

## 5. Conventions

* English only: identifiers, CLI text, errors, logs, docs and test names.
* `pathlib.Path` everywhere; never hard-code `/tmp`, `/home/...` or `C:\...`.
* Timestamps are seconds as `float` in the model; formatting happens at the
  edges (`utils/time.py`).
* New canonical data goes into a typed dataclass in `models/`, never into a bare
  `dict`.
* Public functions are typed and validated; untyped `dict[str, Any]` is only
  acceptable for engine-specific payloads that are stored verbatim.
* Subprocesses: argument lists, `shell=False`, explicit timeouts.
* Anything model-driven must be optional and must report `is_available()`.
* Roadmap progress markers: finish work and mark it in the same change. A new
  completion gets `[*]` plus its date in `ROADMAP.md`; a section that is only
  partly done stays `[ ]` with an italic *Status* line. See `CONTRIBUTING.md`.

## 6. Adding an engine (target workflow)

1. Read `docs/DEPENDENCY_MATRIX.md` and add the licence findings to
   `docs/LICENSE_AUDIT.md` **before** writing code.
2. Create `engines/<name>.py` implementing `ChordEngine`, `LyricsEngine`, ...,
   including `engine_info()` and `is_available()`.
3. Register it in `engines/registry.py::create_default_registry()`.
4. Add unit tests with a fake payload plus an integration test that skips when
   the dependency is missing.
5. Document installation, platform support and known limitations.

## 7. Testing policy

* Tests never require network access and never download models.
* Tests must not commit copyrighted commercial songs; audio is generated
  (`tests/fixtures/audio.py`) or explicitly licensed (`samples/`).
* Optional tools are handled with `pytest.mark.skipif`, never by failing.
* Bug fixes come with a regression test; expectation-driven behaviour lives in
  `tests/fixtures/*.json` so changes show up as a reviewable diff.
* Never report accuracy numbers that were not measured (see `docs/BENCHMARK.md`
  once phase 11 lands).

## 8. Environment variables

| Variable | Purpose |
| --- | --- |
| `SONGLAB_FFMPEG` / `SONGLAB_FFPROBE` | explicit executable paths |
| `SONGLAB_CACHE_DIR` | analysis cache location |
| `SONGLAB_DATA_DIR` | application data (and default model) location |
| `SONGLAB_TEMP_DIR` | temporary file location |

Environment variables are advanced overrides only; user-facing configuration
belongs in explicit CLI options and (later) the settings dialog.
