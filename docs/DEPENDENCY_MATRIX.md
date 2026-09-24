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
| **Adopt** (as optional extras, when their phase arrives) | numpy, scipy, librosa, soundfile, music21, faster-whisper, basic-pitch, beat_this |
| **Adopt for the GUI (phase 15)** | PyQt6 (GPL-3.0-or-later compatible); PySide6 recorded as the permissive alternative |
| **Candidate — measure before trusting** | MOSS-Music, torchcrepe, openai-whisper, spleeter, audio-separator |
| **Defer (heavy, only if a phase needs it)** | torch, torchaudio |
| **Reject for integration** | madmom (does not build on current Python; non-commercial weights), Essentia (AGPL library + non-commercial models + no Windows support) |
| **Never bundle, execute only** | FFmpeg/ffprobe, Sonic Annotator, Chordino/NNLS Chroma |
| **Never bundle weights** | Demucs (code MIT, weights licence unresolved) |

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
| **basic-pitch** (Spotify) | 0.4.0 | **Apache-2.0** (`LICENSE`: "Copyright 2022 Spotify AB"). The model ships inside the same Apache-2.0 repository, so code and weights share one licence. | Pure `py2.py3-none-any` wheel, no declared `Requires-Python`; classifiers still list only Python 3.8-3.11 (metadata is stale relative to 0.4.0) and Linux/MacOS X/Windows. The upstream README's Python-3.10 note is not a hard limit for 0.4.0, but this must be smoke-tested before adoption. | adopt (phase 7), measured against no-MIDI |

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

## 10. Installation complexity and hardware

| Package | Install | CPU/GPU | Notes on complexity |
| --- | --- | --- | --- |
| numpy / scipy / librosa / soundfile / music21 | `pip install <name>` | CPU | wheels for all three platforms; soundfile bundles libsndfile |
| faster-whisper | `pip install faster-whisper` | CPU or CUDA; CPU fallback exists | pulls ctranslate2 (native wheel); model files are downloaded separately and are not small |
| openai-whisper | `pip install openai-whisper` | CPU or CUDA | no wheel (sdist only), pulls PyTorch, needs FFmpeg |
| basic-pitch | `pip install basic-pitch` | CPU-friendly | pure wheel, no declared Python floor |
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

## 11. Still open

These are the honest gaps in this research:

1. **No smoke test has been run.** Only resolution, licence and wheel availability
   were verified. `pip download`-level confidence is not "it works".
2. **Weights not individually verified** for torchcrepe/CREPE conversions,
   Spleeter, and the UVR model zoo used by `audio-separator`.
3. **GPL-2.0 "only" vs "or later"** for NNLS Chroma and Sonic Annotator is not
   stated in `COPYING`; read the source headers before *combining* anything. This
   does not affect executing them as separate programs.
4. **Python 3.10/3.11 resolutions** of numpy/scipy/librosa were not verified (pip
   will select older releases).
5. **Parakeet packaging** (NeMo vs MLX ports) has not been researched.
6. **MOSS-Music** needs a VRAM/CPU feasibility check before it can be considered
   an engine rather than a demo.

Phase 1 is therefore **complete for the candidates needed before the first
analysis phases** (audio, lyrics, chords, beats) and **deliberately still open**
for the heavy ML options that later phases may or may not need.
