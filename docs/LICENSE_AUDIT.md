# Licence Audit

Roadmap section 56. This project's own source code is **GPL-3.0-or-later**
(see [`LICENSE`](../LICENSE)).

**Verified on 2026-09-23** on Linux x86_64 with CPython 3.13.5. Each row cites
where the fact came from: package metadata obtained through
`pip install --dry-run --report -`, the upstream `LICENSE`/`COPYING` file, the
model card, or the vendor's own licence page. Nothing here is legal advice, and
"not verified" is stated explicitly rather than guessed.

## 1. Layers that must stay separate

| Layer | Example | Why it matters |
| --- | --- | --- |
| Source code | `song_chord_lyrics_analyzer/` | GPL-3.0-or-later; distributing a combined work triggers copyleft obligations. |
| Python dependencies | librosa, music21 | Must be GPL-3.0-or-later compatible before being imported. |
| Model weights | Whisper, Demucs, madmom, Essentia, MOSS-Music | Frequently licensed differently from the code that loads them — verified separately below. |
| Datasets | benchmark and ground-truth audio | May not be redistributable at all. |
| External executables | FFmpeg, Sonic Annotator, Chordino | Executed, not bundled — unless an installer changes that. |

## 2. This project's code

| Component | Licence | Notes |
| --- | --- | --- |
| `song-chord-lyrics-analyzer` | **GPL-3.0-or-later** | Declared as an SPDX expression in `pyproject.toml` with `license-files = ["LICENSE"]`. |
| Dependencies of the core | none | The package imports only the standard library, so there is no licence surface at all in the core. |

## 3. Verified dependency licences (code)

| Package | Version | Licence | Source of the finding |
| --- | --- | --- | --- |
| numpy | 2.5.3 | BSD-3-Clause | `numpy/LICENSE.txt` |
| scipy | 1.18.1 | BSD-3-Clause | package metadata + bundled notices (see §6) |
| librosa | 1.0.0 | ISC | package metadata (`license = ISC`, ISC classifier) |
| soundfile | 0.14.0 | BSD-3-Clause | package metadata; wraps LGPL libsndfile (§6) |
| music21 | 10.5.0 | BSD | package classifier |
| ctranslate2 | 4.8.2 | MIT | `CTranslate2/LICENSE` |
| faster-whisper | 1.2.1 | MIT | package metadata |
| openai-whisper | 20250625 | MIT | `openai/whisper/LICENSE` |
| demucs | 4.1.0 | MIT (code only) | package metadata; `LICENSE` in the archived repo |
| basic-pitch | 0.4.0 | Apache-2.0 | `spotify/basic-pitch/LICENSE` |
| torchcrepe | 0.0.24 | MIT | package metadata |
| torch / torchaudio | 2.14.0 / 2.11.0 | BSD-3-Clause | `pytorch/LICENSE` (torchaudio: BSD classifier) |
| beat_this | 1.1.0 | MIT | `CPJKU/beat_this/LICENSE` |
| spleeter | 2.1.0 | MIT (code) | package metadata |
| audio-separator | 0.47.0 | MIT (wrapper) | package metadata |
| PyQt6 | 6.11.0 | GPL-3.0 or Riverbank Commercial | Riverbank: "PyQt is dual licensed ... under the GNU GPL v3 and the Riverbank Commercial License. Unlike Qt, PyQt is not available under the LGPL." |
| PySide6 | 6.11.2 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | package metadata |
| **essentia** | 2.1b6.dev1389 | **AGPL-3.0-only** | PyPI `license_expression`; `COPYING.txt` |
| **madmom** | 0.16.1 | **BSD (code) + CC BY-NC-SA (models)** | upstream project description |
| **1ucas/chordify** | — | MIT | `LICENSE`: "Copyright (c) 2026 Lucas Maciel" |

## 4. Verified model-weight licences

Weights are where the expensive mistakes live (roadmap rule 4).

| Model | Licence | Status |
| --- | --- | --- |
| Whisper (OpenAI) | MIT (upstream repository `LICENSE`) | verified for the reference release |
| `Systran/faster-whisper-large-v3` | `license:mit` tag on the Hugging Face model card | verified |
| MOSS-Music (`OpenMOSS-Team/MOSS-Music-8B-Instruct`) | `license:apache-2.0` tag on the model card, released 2026-05-01 | verified |
| Basic Pitch | Apache-2.0; the model file lives inside the same Apache-2.0 repository | verified |
| **madmom models/data files** | **CC BY-NC-SA 4.0** — "If you want to include any of these files ... in a commercial product, please contact Gerhard Widmer." | verified; **non-commercial, conflicts with redistribution inside a GPL-3 work** |
| **Essentia (MTG) models** | **CC BY-NC-SA 4.0**, proprietary licence on request | verified on essentia.upf.edu/models.html; **non-commercial** |
| **Demucs pre-trained models** | **unresolved** | issue `facebookresearch/demucs#327` (2022-05-05) is still open with label "Further information is requested"; the repository was archived 2025-01-01, so the question will not be answered upstream |
| torchcrepe weights (converted CREPE "tiny"/"full") | not individually verified; upstream CREPE is MIT | open |
| Spleeter pre-trained models | not verified | open |
| UVR model zoo (via `audio-separator`) | mixes licences, some non-commercial | open; verify per model |

Consequences already recorded in `docs/DEPENDENCY_MATRIX.md`: madmom and
Essentia are rejected for integration, and Demucs weights are never bundled — a
user may download them explicitly, with the unresolved status stated.

## 5. External executables (executed, not bundled)

| Tool | Licence (verified) | Position |
| --- | --- | --- |
| **FFmpeg / ffprobe** | ffmpeg.org/legal.html: "FFmpeg is licensed under the GNU Lesser General Public License (LGPL) version 2.1 or later. However, FFmpeg incorporates several optional parts and optimizations that are covered by the GNU General Public License (GPL) version 2 or later. If those parts get used the GPL applies to all of FFmpeg." | We locate and execute an installed binary; nothing is linked or redistributed. **Bundling it later is a new decision** that pulls in the page's compliance checklist (build without `--enable-gpl`/`--enable-nonfree`, dynamic linking, ship exactly matching source, about-box and EULA notices). |
| Sonic Annotator | GPL-2.0 (`COPYING` = GPLv2 text) | Separate program: executing it is unaffected. The `COPYING` file does not state "only" or "or later" — read the source headers before *combining* anything. |
| Chordino / NNLS Chroma | GPL-2.0 (`COPYING` = GPLv2 text) | Same as above. GPL-2.0-**only** would be incompatible with the GPL-3 work if it were linked or bundled, which is a further reason it stays an optional external tool. |

## 6. Bundled third-party code inside wheels we would ship

If this project ever ships binaries (an installer, a PyInstaller bundle), these
notices travel with the wheels:

| Wheel | Bundled component | Licence | Obligation |
| --- | --- | --- | --- |
| scipy | OpenBLAS | BSD-3-Clause | include notice |
| scipy | LAPACK | BSD-3-Clause-Open-MPI | include notice |
| scipy | libgfortran | **GPL-3.0-or-later WITH GCC-exception-3.1** | covered by the GCC Runtime Library Exception; do not strip the notices |
| scipy | libquadmath | LGPL-2.1-or-later | LGPL notice + relinking ability |
| soundfile | libsndfile | LGPL (per soundfile's own documentation) | LGPL notice + relinking ability |
| PyQt6 | Qt (the LGPL build, according to Riverbank) | LGPL | Qt notices; PyQt itself is GPL-3.0/commercial |

None of this blocks the current source distribution; it blocks careless binary
packaging, which is why it is written down now.

## 7. Compatibility conclusions

* **GPL-3.0-or-later** is our licence; PyQt6's GPL-3 option, and the permissive
  BSD/ISC/MIT/Apache-2.0 dependencies, are all fine.
* **AGPL-3.0-only (Essentia library)** can be combined with GPLv3 in principle,
  but the network clause and the non-commercial model licences make it a poor fit
  for what this project is trying to be. Rejected as a dependency.
* **CC BY-NC-SA 4.0 weights (madmom, Essentia)** impose a non-commercial further
  restriction that cannot be reconciled with shipping them inside a GPL-3 work.
  They are never bundled.
* **GPL-2.0-only external tools** (if that is what Chordino/NNLS Chroma turn out
  to be) stay separate executables that the user installs.
* **Demucs weights** stay unresolved and are therefore never redistributed.

## 8. Policy rules that follow

1. A licence question blocks **integration**, not documentation.
2. Weights are audited separately from code, every time, before automation
   downloads them.
3. Optional dependencies must degrade gracefully: `is_available()` returns false
   and the CLI explains what to install rather than failing to import.
4. Model management (roadmap section 52) must record, per model: name, version,
   source, **licence**, size, SHA-256 and hardware requirements, and must never
   download silently.
5. No copyrighted commercial music is committed to this repository; audio
   fixtures are generated, and `samples/README.md` records the licence and source
   of every file.

## 9. Datasets and samples

* Only original, public-domain, properly licensed or research-permitted material.
* Ground truth is explicit and documented; expected chords are never invented
  (roadmap section 43).
* `tests/fixtures/audio.py` generates WAV tones, so the test suite commits no
  audio at all.
