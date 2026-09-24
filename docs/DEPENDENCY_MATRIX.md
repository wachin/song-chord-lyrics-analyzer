# Dependency Matrix

Phase 1 dependency research (roadmap sections 55 and 83).

**Verified on 2026-09-23** on Linux x86_64 (Debian, glibc) with CPython **3.13.5**
and pip 26.2.1. Unless a row says otherwise, "verified" means:

* the latest release that resolves for this platform/Python was obtained from the
  package index via `pip install --dry-run --ignore-installed --no-deps --report -`,
  which reports the release version, `Requires-Python`, the licence field and the
  licence classifiers **and** the exact wheel that would be installed;
* the licence was cross-checked against the upstream `LICENSE`/`COPYING` file or
  the model card, cited in the row.

Reproducing the version/platform half of this table:

```bash
python -m pip install --dry-run --ignore-installed --no-deps --report - <package> \
  | python -m json.tool
```

**Scope warning.** These are *resolution and licence* findings. Nothing has been
installed into the project, smoke-tested or benchmarked, so no statement about
accuracy, speed or quality appears here. A wheel resolving is not the same as an
engine working.

## 0. Summary of decisions

| Verdict | Packages |
| --- | --- |
| **Adopt** (as optional extras, when their phase arrives) | numpy, scipy, librosa, soundfile, music21, faster-whisper, beat_this |
| **Adopt with a documented condition** | basic-pitch — Apache-2.0 and functionally verified, but its official install path is broken on Python >= 3.12 (see §6 and §10) |
| **Adopt for the GUI (phase 15)** | PyQt6 (GPL-3.0-or-later compatible); PySide6 recorded as the permissive alternative |
| **Candidate — measure before trusting** | MOSS-Music, torchcrepe, openai-whisper, spleeter, audio-separator |
| **Defer (heavy, only if a phase needs it)** | torch, torchaudio |
| **Reject for integration** | madmom (does not build on current Python; non-commercial weights), Essentia (AGPL library + non-commercial models + no Windows support) |
| **Never bundle, execute only** | FFmpeg/ffprobe, Sonic Annotator, Chordino/NNLS Chroma |
| **Never bundle weights** | Demucs (code MIT, weights licence unresolved) |
| **Reference clones investigated (2026-09-24, roadmap §24)** | 1ucas/chordify kept as the architectural reference; chordscope investigated and removed after recording; chord-extractor, Chord-recognition and scales-chords removed as superseded/off-scope; orchidas/Chord-Recognition investigated and kept for now — see §13 |

## 1. Core package

This project's own core has **zero runtime dependencies**: standard library only
(`wave`, `subprocess`, `hashlib`, `argparse`, `logging`, `dataclasses`, `json`,
`pathlib`, `tempfile`). Everything below is an opt-in extra.

## 2. Numerics, DSP and music theory

| Package | Latest resolved | Requires-Python | Licence (verified) | Platform | Verdict |
| --- | --- | --- | --- | --- | --- |
| numpy | 2.5.3 | `>=3.12` | BSD-3-Clause (`LICENSE.txt`: "Copyright (c) 2005-2025, NumPy Developers") | cp313 wheels; MacOS/POSIX/Unix/Windows | adopt |
| scipy | 1.18.1 | `>=3.12` | BSD-3-Clause. Wheels also bundle OpenBLAS (BSD-3-Clause), LAPACK (BSD-3-Clause-Open-MPI), **libgfortran (GPL-3.0-or-later WITH GCC-exception-3.1)** and libquadmath (LGPL-2.1-or-later) | cp313 wheels; Linux/MacOS/POSIX/Unix/Windows | adopt, see §7 |
| librosa | 1.0.0 | `>=3.12` | **ISC** (`license` metadata = "ISC", classifier "ISC License (ISCL)") | pure-Python wheel | adopt |
| soundfile | 0.14.0 | `>=3.10` | BSD-3-Clause; wraps **libsndfile (LGPL)**, bundled inside the platform wheels | OS Independent | adopt |
| music21 | 10.5.0 | `>=3.11` | BSD (classifier) | pure-Python wheel; MacOS/POSIX/Windows | adopt (theory layer only) |

**Python floor consequence.** Current numpy, scipy and librosa releases require
Python **≥ 3.12**. The package floor stays at 3.10 (the core needs nothing), but
any extra that pulls the modern DSP stack effectively needs 3.12+, or pip will
silently resolve older releases on 3.10/3.11. Those older resolutions are **not
verified here**; the CI matrix will surface them when the extras land.

## 3. Chord, beat, key and tempo engines

### 3.1 Rejected

| Candidate | Finding | Verdict |
| --- | --- | --- |
| **madmom** | PyPI's newest release is 0.16.1 and it **does not build** on Python 3.13: `ERROR: Failed to build 'madmom' when getting requirements to build wheel`. Its own project description separates licences: source code BSD, but "all model and data files are distributed under the **Creative Commons Attribution-NonCommercial-ShareAlike 4.0** license" and commercial use requires contacting the author. The GitHub main branch was modernised (`pyproject.toml` with `cython>=0.25`, `numpy>2`), but no matching release was published. | **Reject.** Non-commercial weights cannot be shipped inside a GPL-3 work, and there is no installable release for the Python versions this project targets. |
| **madmom-prebuilt** | Fork on PyPI, 0.17.post1, ships a `cp313` manylinux wheel and works around the build failure. Licence metadata is `"BSD, CC BY-NC-SA"` with the classifier `License :: Free for non-commercial use`. | **Reject** for the same licence reason. Recorded because it is the obvious workaround and the workaround does *not* solve the licensing problem. |
| **Essentia** | PyPI `license_expression` is **`AGPL-3.0-only`** (with `COPYING.txt`). The newest resolvable release is a **pre-release** (`2.1b6.dev1389`, needs `--pre`). Classifiers: Beta, `MacOS X` + `POSIX` only — **no Windows**. Its models are separately restricted: "All the models created by the MTG are licensed under **CC BY-NC-SA 4.0** and are also available under proprietary license upon request." | **Reject** as a dependency. AGPL + non-commercial models + no Windows support is three independent problems. Revisit only for an algorithm with no alternative, kept optional and *without* its models. |

### 3.2 Candidates

| Candidate | Latest resolved | Licence (verified) | Notes | Verdict |
| --- | --- | --- | --- | --- |
| **beat_this** (CPJKU) | 1.1.0 | **MIT** (`LICENSE`: "Copyright (c) 2024 Institute of Computational Perception, JKU Linz") | Pure wheel, `Requires-Python >=3`. Discovered while investigating why madmom is not usable; it is the natural replacement for the madmom role (beats/downbeats/tempo). The dependency is approved, but it must still be benchmarked before being selected as the default beat engine. | adopt for phase 5 (benchmark first) |
| **torchcrepe** | 0.0.24 | **MIT** (`license` metadata + classifier) | Pure wheel, no declared `Requires-Python`, depends on PyTorch. Weights are conversions of CREPE's "tiny"/"full" models; the CREPE repository is also MIT, but the converted weight files have **not** been individually verified. | candidate (phase 5/7) |
| **MOSS-Music** | `OpenMOSS-Team/MOSS-Music-8B-Instruct` | **`license:apache-2.0`** (Hugging Face model tag) | 8B audio-language model, released 2026-05-01, `pipeline_tag: audio-text-to-text`, `architectures: ["MossMusicModel"]`, Instruct + Thinking variants. Upstream lists "musical captioning, lyrics ASR, structural analysis, chord/key/tempo reasoning". | candidate (phases 3/10) — 8B inference cost, reasoning-style output; do not assume it beats specialised engines. |
| **Chordino / NNLS Chroma** | not a Python package | **GPL-2.0** (`COPYING` is the GPLv2 text). The COPYING file does not say "only" or "or later"; the source headers must be read before any *combining* | Vamp plugin. Repository `c4dm/nnls-chroma`, 175 commits; no recent release activity observed (the Arch AUR package was last updated 2020). Needs a Vamp host (`sonic-annotator` or Sonic Visualiser). | external executable only, **never bundled** |
| **Sonic Annotator** | not a Python package | **GPL-2.0** (`COPYING` verified: "GNU GENERAL PUBLIC LICENSE Version 2, June 1991") | Batch Vamp host, `vamp-plugins.org/sonic-annotator/`. Installed manually or from a distribution package; plugin discovery uses `VAMP_PATH`. | external executable only, **never bundled** |
| **1ucas/chordify** | not a Python package | **MIT** (`LICENSE`: "Copyright (c) 2026 Lucas Maciel") | Not the historical "chordify" demo: it is now a local CLI that does librosa CQT/CENS chroma + major/minor triad templates, adaptive bar aggregation, **bass-aware Viterbi decoding**, key + song-palette priors, conservative slash/extension display, optional Demucs `htdemucs_ft` isolation (`bass + other`), and Whisper/Parakeet lyrics with word timestamps. | **architectural reference** (roadmap section 23). Read and re-implement cleanly; do not copy blindly. Its YouTube downloader is out of scope for this project. |

## 4. Lyrics engines

| Candidate | Latest resolved | Requires-Python | Licence (verified) | Notes | Verdict |
| --- | --- | --- | --- | --- | --- |
| **faster-whisper** | 1.2.1 | `>=3.9` | **MIT** (`license` metadata + classifier) | Pure wheel. Native dependency **ctranslate2 4.8.2: MIT** (`LICENSE`: "Copyright (c) 2018- SYSTRAN"), classifiers Python 3.9-3.14, Production/Stable. Model `Systran/faster-whisper-large-v3` carries the **`license:mit`** tag on Hugging Face. | **primary candidate** (phase 3) |
| **openai-whisper** | 20250625 | `>=3.8` | **MIT** (`LICENSE`: "Copyright (c) 2022 OpenAI") | **sdist only, no wheel**, pulls PyTorch, needs FFmpeg. | baseline for comparison |
| **Parakeet-based** | not verified | — | — | `1ucas/chordify` reports using NVIDIA Parakeet with word-level timestamps; the specific packages (NeMo vs MLX ports) have not been researched. | unverified |
| **MOSS-Music** | see §3.2 | — | Apache-2.0 (weights) | Music-aware, but a reasoning model rather than a timestamped transcriber. | candidate |

## 5. Source separation

| Candidate | Latest resolved | Licence (verified) | Notes | Verdict |
| --- | --- | --- | --- | --- |
| **demucs** | 4.1.0 | **Code MIT** (`license` metadata "MIT License" + classifier). **Weights: unresolved** — issue `facebookresearch/demucs#327` ("License of pre-trained models", opened 2022-05-05) is still **open**, labelled "Further information is requested", and the repository was **archived on 2025-01-01** (read-only), so no maintainer answer is coming. | Pure wheel, `Requires-Python >=3.10`. Upstream archived ⇒ effectively unmaintained. | code usable, **weights must not be bundled**; treat weight download as an explicit user action with a licence warning |
| **spleeter** | 2.1.0 | Code **MIT**; **weights unverified** | `Requires-Python >=3.7,<4.0` — the upper bound will block future Python versions. | unverified |
| **audio-separator** | 0.47.0 | Wrapper **MIT**; the UVR model zoo mixes licences, some non-commercial | `Requires-Python >=3.10,!=3.14.1` | per-model verification required before use |

## 6. Audio→MIDI

| Candidate | Latest resolved | Licence (verified) | Notes | Verdict |
| --- | --- | --- | --- | --- |
| **basic-pitch** (Spotify) | 0.4.0 | **Apache-2.0** (`LICENSE`: "Copyright 2022 Spotify AB"). The model ships **inside the same wheel** (all four formats: `nmp.onnx`, `nmp.tflite`, `saved_model.pb`, `model.mlmodel`), so code and weights share one licence and no separate model download happens. | Pure `py2.py3-none-any` wheel, no declared `Requires-Python`. **Verified blocker:** it requires `tensorflow<2.15.1` for `python_version >= "3.11"` on non-Darwin, while PyPI only offers TensorFlow >= 2.20 for Python 3.13, so `pip install basic-pitch` **fails on Python 3.12 and 3.13**. See §10 for the verified ONNX workaround. | adopt with a condition (phase 7); see §10 |

## 7. Heavy ML runtimes

| Package | Latest resolved | Requires-Python | Licence | Notes | Verdict |
| --- | --- | --- | --- | --- | --- |
| torch | 2.14.0 | `>=3.10` | BSD-3-Clause (`LICENSE` begins "From PyTorch: Copyright (c) 2016- Facebook, Inc") | cp313 wheel. Verified by resolution: the default PyPI wheel drags in a full CUDA runtime (`cuda-toolkit`, `nvidia-cudnn-cu13`, `nvidia-cublas`, `nvidia-cufft`, `triton`, ...). CPU-only environments must install from the PyTorch CPU index; this matters for CI and for users without an NVIDIA GPU. | defer until a phase needs it |
| torchaudio | 2.11.0 | not declared | BSD (classifier) | cp313 wheel; MacOS X/POSIX/Windows | defer |
| ctranslate2 | 4.8.2 | `>=3.9` | MIT (verified) | transitive dependency of faster-whisper; Production/Stable; Python 3.9-3.14 | accepted transitively |

## 8. GUI toolkit

| Package | Latest resolved | Requires-Python | Licence (verified) | Verdict |
| --- | --- | --- | --- | --- |
| **PyQt6** | 6.11.0 | `>=3.10` | Riverbank's own page: "PyQt is dual licensed on all supported platforms under the **GNU GPL v3** and the Riverbank Commercial License. Unlike Qt, PyQt is **not** available under the LGPL", and the GPL-version binary wheels "include a copy of the corresponding **LGPL** version of Qt". | **adopt** — compatible with this project's GPL-3.0-or-later; record which Qt build the wheels carry if binaries are ever distributed |
| PySide6 | 6.11.2 | `<3.15,>=3.10` | Metadata `license`: `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` | documented alternative (permissive option if the licence position ever changes) |

## 9. External executables

| Tool | Licence (verified) | Notes |
| --- | --- | --- |
| **FFmpeg / ffprobe** | ffmpeg.org/legal.html: "FFmpeg is licensed under the GNU Lesser General Public License (LGPL) version 2.1 or later. However, FFmpeg incorporates several optional parts and optimizations that are covered by the GNU General Public License (GPL) version 2 or later. If those parts get used the GPL applies to all of FFmpeg." | The program only **executes** an already-installed binary. If a future installer ever bundles FFmpeg, the page's LGPL compliance checklist (configure without `--enable-gpl`/`--enable-nonfree`, dynamic linking, ship matching source, about-box and EULA notices) becomes mandatory. |

## 10. Smoke test results

Run on **2026-09-23**, Linux x86_64 (Debian, glibc), CPython **3.13.5**, pip
26.2.1, in a **throw-away virtual environment** (`.venv-smoke`) so the project's
own environment stayed dependency-free. All audio was generated in-process: the
project's `tests/fixtures/audio.py` for the plain tone, plus in-script generators
for a C major triad and a 120 BPM click track. No real music, no copyrighted
material, no GPU, no network except where noted.

### 10.1 Results

| Package | Install | Import | Functional check | Measured |
| --- | --- | --- | --- | --- |
| **soundfile 0.14.0** | OK — 5 packages (`cffi`, `numpy`, `pycparser`, `typing_extensions`) | OK | `sf.info`/`sf.read` on a generated WAV: 44100 Hz, 2 ch, 44100 frames, `WAV/PCM_16`; WAV→FLAC→read round trip is sample-exact (`np.allclose`) | 8.9 ms for info + read + write + read |
| **librosa 1.0.0** | OK — 26 packages (`numba`, `llvmlite`, `scikit-learn`, `scipy`, `soxr`, `pooch`, ...); environment 498 MB | OK | `chroma_cqt` on a C major triad ranks **C, E, G** as the three strongest pitch classes (C = 1.000); `beat_track` on a 120 BPM click track returns **117.45 BPM**, 14 of 16 beats | `chroma_cqt` 1524 ms cold → **107-119 ms warm**; `beat_track` 1849 ms cold → **48-55 ms warm** (numba JIT warm-up) |
| **beat_this 1.1.0** | OK — 3.7 s on top of CPU-only torch; environment 1.4 GB with torch | OK | On a 120 BPM click track: 16 beats, median interval exactly 0.5000 s → **120.00 BPM**; 0.70-0.83 s of CPU time for 8 s of audio (≈10× real time) | 81.1 MB checkpoint auto-downloaded to `~/.cache/torch/hub/checkpoints/beat_this-final0.ckpt`; 11.7 s on first use |
| **basic-pitch 0.4.0** | **FAILS**: `pip install basic-pitch` on Python 3.13 ends in `Failed to build 'numpy'` because `tensorflow<2.15.1` cannot be satisfied (PyPI offers TensorFlow >= 2.20 for 3.13). Workaround: `pip install --no-deps basic-pitch` plus `onnxruntime`, `resampy<0.4.3`, `pretty-midi`, `mir-eval` | OK (`ONNX_PRESENT=True`, `TF_PRESENT=False`) | `predict()` on the **bundled `nmp.onnx`** found exactly **C4/E4/G4** on a C major triad (6 note events: the three pitches plus repeats from the decay tail) | 0.31 s for 2 s of audio |

### 10.2 What the checks do and do not say

* The click track and the synthetic triad are self-written signals, not
  benchmarks. **No accuracy claim follows from them.**
* librosa's 117.45 BPM against a nominal 120 BPM is a recorded measurement, not a
  judgement; real music may differ.
* librosa emitted `n_fft=1024 is too large for input signal of length=690` on a
  very short segment. Engine adapters must treat warnings as diagnostics, not as
  failures.
* beat_this reported 12 "downbeats" for 16 beats. A uniform click track carries
  no real meter cue, so **downbeat quality is explicitly not assessed** here.
* basic-pitch's duplicate events on a decaying tone are normal model behaviour,
  not a defect claim.

### 10.3 Cross-platform availability (wheel level)

Metadata-only resolution for **CPython 3.13** (`--no-deps --only-binary :all:`),
so this is "an artifact exists", **not** "it runs there":

| Package | Linux | Windows | macOS arm64 |
| --- | --- | --- | --- |
| soundfile 0.14.0 | `manylinux_2_28_x86_64` | `win_amd64` | `macosx_11_0_arm64` |
| librosa 1.0.0 | `py3-none-any` | `py3-none-any` | `py3-none-any` |
| beat-this 1.1.0 | `py3-none-any` | `py3-none-any` | `py3-none-any` |
| basic-pitch 0.4.0 | `py2.py3-none-any` | `py2.py3-none-any` | `py2.py3-none-any` |
| numpy 2.5.3 / scipy 1.18.1 | cp313 manylinux | cp313 `win_amd64` | numpy `macosx_11_0_arm64`, scipy `macosx_14_0_arm64` |
| torch 2.14.0 (CPU index) | `manylinux_2_28_x86_64` | `2.14.0+cpu win_amd64` | `macosx_14_0_arm64` |

Runtime behaviour was verified **on Linux only**. Windows and macOS are
unverified beyond wheel availability, and must be re-checked on real machines
before any cross-platform claim (roadmap rule: never claim platform support that
was not tested).

### 10.4 Integration findings that change our design

1. **beat_this writes its checkpoint to `~/.cache/torch/hub/checkpoints`, not to
   our cache.** The adapter must redirect `TORCH_HOME` or pass an explicit
   checkpoint path so the file lands in `SONGLAB_CACHE_DIR` and can be listed and
   hashed by `songlab models` (roadmap section 52).
2. **That download is silent** apart from a progress bar. Our adapter must
   announce it, and record size + SHA-256 before use, since it is an 81 MB
   network fetch.
3. **`pip install beat-this` from the default index pulls the CUDA stack.** The
   CPU path is `--index-url https://download.pytorch.org/whl/cpu`, verified to
   serve Linux, Windows (`+cpu`) and macOS arm64 wheels.
4. **basic-pitch ships every model format inside the wheel**, so it needs no
   separate model download — genuinely offline-friendly *once the Python version
   conflict is solved*.
5. **Measured install sizes:** soundfile + librosa alone 498 MB
   (numba/llvmlite/scikit-learn dominate); adding CPU torch brings the
   environment to 1.4 GB. CPU torch installed in 95 s, and the PyTorch index did
   return transient connection resets before succeeding.

## 11. Installation complexity and hardware

| Package | Install | CPU/GPU | Notes on complexity |
| --- | --- | --- | --- |
| numpy / scipy / librosa / soundfile / music21 | `pip install <name>` | CPU | wheels for all three platforms; soundfile bundles libsndfile |
| faster-whisper | `pip install faster-whisper` | CPU or CUDA; CPU fallback exists | pulls ctranslate2 (native wheel); model files are downloaded separately and are not small |
| openai-whisper | `pip install openai-whisper` | CPU or CUDA | no wheel (sdist only), pulls PyTorch, needs FFmpeg |
| basic-pitch | `pip install basic-pitch` — **fails on Python >= 3.12**, see §10.1 | CPU-friendly | pure wheel; models bundled; `tensorflow<2.15.1` pin blocks 3.12/3.13 |
| beat_this | `pip install beat-this` | CPU or GPU | pure wheel, but verified resolution pulls **39 packages**: `torch 2.14.0`, `torchaudio 2.11.0`, `rotary-embedding-torch`, `soxr`, `numpy`, and the CUDA runtime packages from §7. Use the PyTorch CPU index for CPU-only installs. |
| torch / torchaudio | `pip install torch torchaudio` | CPU wheels exist; CUDA is opt-in | very large downloads; the default index pulls CUDA packages (§7), so pin the CPU build for CI |
| torchcrepe | `pip install torchcrepe` | CPU or CUDA | depends on the torch stack |
| demucs | `pip install demucs` | CPU slow, GPU recommended | weights must be fetched separately and are **not** bundled (see §5) |
| spleeter | `pip install spleeter` | CPU or GPU | `Requires-Python <4.0` upper bound; TF-era stack |
| audio-separator | `pip install audio-separator` | CPU or GPU | per-model licence checks required |
| MOSS-Music | `transformers` + Hugging Face model | GPU effectively required (8B) | feasibility not yet assessed |
| PyQt6 / PySide6 | `pip install PyQt6` | CPU | abi3 wheels for Linux/Windows/macOS |
| Sonic Annotator / Chordino | manual install, or a distribution package where it exists | CPU | plugin discovery via `VAMP_PATH`; no recent release activity observed |

Model downloads are never silent: the model manager (roadmap section 52) must
report name, version, source, licence, size, SHA-256 and hardware requirements
before anything is fetched.

## 12. Still open

These are the honest gaps remaining after the phase 1 research and the smoke
tests:

1. **Runtime verified on Linux only.** Windows and macOS have wheel-level
   evidence (see §10.3) but no runtime evidence. Anyone claiming cross-platform
   support for an engine must test it on that platform first.
2. **No real music has been analysed.** No accuracy, WER, key or tempo metric
   exists, and none may be quoted until `songlab benchmark` produces them
   (roadmap rules 6 and 13).
3. **The basic-pitch Python-version conflict needs a decision:** either pin that
   feature's extra to Python <= 3.11, ship the documented ONNX workaround
   (`--no-deps` + `onnxruntime`), or defer it to phase 7 and revisit. The ONNX
   path is verified to run, but it is *not* the upstream-supported install.
4. **Weights not individually verified** for torchcrepe/CREPE conversions,
   Spleeter, and the UVR model zoo used by `audio-separator`.
5. **beat_this checkpoint licence** is MIT per the project; the downloaded file
   itself has not been inspected, and its fetch must be routed through our cache
   and model manager.
6. **GPL-2.0 "only" vs "or later"** for NNLS Chroma and Sonic Annotator is not
   stated in `COPYING`; read the source headers before *combining* anything. This
   does not affect executing them as separate programs.
7. **Python 3.10/3.11 resolutions** of numpy/scipy/librosa were not verified (pip
   will select older releases; only 3.13 was exercised).
8. **Parakeet packaging** (NeMo vs MLX ports) has not been researched.
9. **MOSS-Music** needs a VRAM/CPU feasibility check before it can be considered
   an engine rather than a demo.
10. **No memory measurement** beyond environment disk size: peak RAM per engine
    belongs to `songlab benchmark` (roadmap section 45), not to this document.

Phase 1 is therefore **complete for the candidates needed by the first analysis
phases** (audio, lyrics, chords, beats; each has an installable, licence-cleared
option with Linux runtime evidence) and **deliberately still open** for the heavy
ML options and for every platform other than Linux.

## 13. Reference clone investigation — block 1 chords (roadmap section 24)

**Recorded on 2026-09-24**, reading the clones under `external/` (read-only
submodules; nothing was imported, executed or copied out). Licences were read from
each clone's `LICENSE` file. These are verdicts about *study repositories*, not
dependencies — none of them enters the dependency set, and per the `external/`
cleanup rule the submodule is deleted once its verdict is recorded.

### 13.1 1ucas/chordify — §24.1 (MIT, verified 2026-09-23)

**Verdict: keep. Primary architectural reference for the chord engine and the
lyrics-alignment formatter.** All eleven §24.1 bullets were answered by reading
`chordify/detector.py`, `transcriber.py`, `formatter.py`, `separation.py` and
`notation.py`:

| §24.1 bullet | What the code does |
| --- | --- |
| chord extraction | CQT/CENS chroma → equal-weight major/minor triad templates → Viterbi over beat-synchronous segments |
| chroma/CQT | harmonic component after HPSS (`margin=3.0`), tuning estimated with `librosa.estimate_tuning` and corrected; two `chroma_cqt` extractions (full range from C2 over 5 octaves, bass-focused over 3 octaves) plus `chroma_cens`, blended 0.7 CENS / 0.3 raw CQT and re-normalized per frame |
| chord templates | 24 triads (12 major + 12 minor with flat aliases) plus a no-chord "N" state; **equal root/third/fifth weights on purpose** — root-heavy templates mis-voted toward whichever chord matched the loudest (bass) pitch class; non-chord-tone energy penalized (weight 0.5) |
| temporal decoding | Viterbi over beat-synchronous segments (beat-tracked boundaries, short segments absorbed up to 0.25 s), chord-change penalty 0.18, extra penalty for entering/leaving "N"; a **second Viterbi pass** re-runs after a song-palette prior (chords below 2.5% share penalized) and isolated single-segment flickers are suppressed |
| key estimation | song-level chroma vs Krumhansl-Schmuckler major/minor profiles; used only as a **soft prior** (±0.05 diatonic bonus, −0.12 non-diatonic penalty), never as a hard rule; also drives flat/sharp respelling |
| bass analysis | separate low-octave chroma scores the root: +0.15 root boost, +0.10 prominence boost; a penalty applies **only when the bass favors a dominant non-chord tone** (pop bass alternates root and fifth, so a chord-tone bass is never evidence against the chord); slash chords displayed only above a 0.20 bass margin |
| Demucs | optional `--isolate-instrumental` (`htdemucs_ft`): keeps bass + other, drops vocals and drums before chroma analysis; opt-in dependency, significantly slower |
| Whisper/Parakeet | lyrics transcription with word-level timestamps, backend user-selectable (`transcriber.py`) |
| timestamp alignment | chords mapped onto words by character offsets within each lyric line (`formatter.py`); sharp/flat respelling and `--capo` transposition at display time |
| offline processing | everything runs locally except the YouTube downloader (yt-dlp), which is out of scope for this project |
| licensing | MIT (`LICENSE`: "Copyright (c) 2026 Lucas Maciel"), already recorded in §3.2 |

Upstream reports 0.98 mean frame accuracy on its own six-song **synthetically
rendered** benchmark suite; that is their measurement on their own generated
material and transfers nowhere — this project makes no accuracy claim from it.
The benchmark idea itself (render pop-style arrangements from known progressions
and score frame-by-frame) is worth reusing for our phase 12 metrics, with our own
implementation.

### 13.2 yuval-kahan/chord-extractor — removed

**Verdict: removed 2026-09-24 (superseded).** It orchestrates Chordino (the
GPL-2.0 Vamp plugin) through the `vamp` PyPI wrapper — the exact stack phase 1
already classified as *external executable only, never bundled*, with an
abandoned wrapper and platform-specific installation. It offers no technique
chordify does not cover with a cleaner native-Python pipeline. Licence recorded:
GPL-2.0 (`LICENSE` file).

### 13.3 yuval-kahan/Chord-recognition — removed

**Verdict: removed 2026-09-24 (superseded, unlicensed).** A university ML course
project (KNN/SVM/DecisionTree/AdaBoost over PCP features). No `LICENSE` file in
the clone — treat as fully reserved. Every technique it demonstrates is covered
better by chordify (templates + Viterbi) and orchidas (the §24.5 baseline).

### 13.4 yuval-kahan/scales-chords — removed

**Verdict: removed 2026-09-24 (off scope).** An Obsidian plugin that inserts
links to chord-diagram images from scales-chords.com for fenced tab blocks. It
could not be more tangential: rendering/embedding concern, zero audio analysis.
MIT (`LICENSE` file).

### 13.5 okamyuji/chordscope — §24.4 — investigated, then removed

**Verdict: §24.4 investigation complete 2026-09-24; submodule removed after
recording.** MIT (`LICENSE` file). A typer/rich CLI with a pydantic model layer
and per-area analyzers, built on librosa, music21, numpy, scipy, soundfile and
matplotlib:

* **beat/downbeat**: madmom `RNNBeatProcessor` + `DBNDownBeatTrackingProcessor`
  — exactly the madmom stack this project **rejected** in §3.1 (no Python 3.13
  build; CC BY-NC-SA weights). Its `_compat.py` monkey-patches madmom's
  inhomogeneous-shape bug on numpy ≥ 1.24, which confirms the maintenance
  situation rather than fixing it.
* **modulation**: re-applies Krumhansl-Schmuckler over a 16 s sliding window
  with 4 s hop, emitting key segments and from→to changes, with multi-pass
  smoothing and short-segment merging to suppress flap. **This windowed,
  smoothed key-segment idea is worth re-implementing in our own key engine.**
* **tempo curve**: local BPM from median beat-interval deltas, segments
  classified against the global tempo (±5%), linear regression for the trend
  (stable/accelerando/ritardando/variable).
* **chords**: also delegates to madmom's `DeepChromaChordRecognitionProcessor`.

The two ideas worth keeping (windowed modulation tracking; tempo-curve
classification) are now recorded here; the repository itself is not needed to
implement them, and its core engine is one we cannot adopt.

### 13.6 orchidas/Chord-Recognition — §24.5 — investigated, kept for now

**Verdict: §24.5 investigation complete 2026-09-24; submodule kept for now as the
§24.5 research baseline.** No `LICENSE` file — treat as fully reserved; never
copy from it. Since the verdict is recorded, it is also the next candidate for
the `external/` cleanup rule: the baseline idea lives here, not in the clone.
It implements precisely the §24.5 pipeline diagram, in six small files:

* `chromagram.py`: a hand-written constant-Q transform (spectral kernel built
  by FFT, per Kyogu Lee's *Enhanced Pitch Class Profile* paper) producing the
  12-dimensional chroma;
* `create_templates.py`: **binary** 24-triad templates (1.0 on the three chord
  tones) stored as JSON;
* `hmm.py`: HMM with multivariate-Gaussian emissions and a transition matrix
  derived from a nested circle-of-fifths layout, plus an explicit `viterbi()`;
* `main.py`: wires them together over WAV input.

As the research baseline §24.5 asked for, it has served its purpose: our own
implementation will follow the chroma → templates → HMM/Viterbi idea with
original code, informed more by chordify's refinements (§13.1) than by this
codebase.

### 13.7 Remaining block-1 clones

* **yuval-kahan/Chords.py**: kept for now — Keras CNN over PCP features with
  bundled `my_model.h5` weights of undocumented provenance (never copy the
  weights); tied to the §24.2 author ecosystem, whose correct target is still
  unresolved (HTTP 404). Revisit when §24.2 has a decision.
* **MOSS-Music**: unchanged — still the §3.2 candidate (phases 3/10), pending a
  feasibility check.
* **ChordVisualizer, musicpractice, Guitariz, ChordMiniApp**: outside §24 (they
  are apps/tools, not engines); kept as GUI/visualization reading for phase 15
  discussions. ChordMiniApp additionally embeds Beat-Transformer,
  Chord-CNN-LSTM and SongFormer models, which may deserve their own §24-style
  investigation if the roadmap grows a chord-model comparison area.

