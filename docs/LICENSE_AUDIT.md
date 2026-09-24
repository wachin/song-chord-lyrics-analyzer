# Licence Audit

Roadmap sections 56 and 42. This project's own source code is
**GPL-3.0-or-later** (see [`LICENSE`](../LICENSE)).

A repository's source-code licence says nothing about the licences of the models
it downloads, the datasets it is tested with, or the external tools it executes.
They are audited separately below. Nothing in this document is legal advice.

## 1. Layers that must stay separate

| Layer | Example | Why it matters |
| --- | --- | --- |
| Source code | `song_chord_lyrics_analyzer/` | GPL-3.0-or-later; distributing a combined work triggers copyleft obligations. |
| Python dependencies | librosa, music21 | Their licences must be compatible with GPL-3.0-or-later before being imported. |
| Model weights | Whisper, Demucs, PitchPerfect models | Frequently licensed differently from the code that loads them. |
| Datasets | benchmark and ground-truth audio | May not be redistributable at all. |
| External executables | FFmpeg, Sonic Annotator, Chordino | Executed, not bundled — but redistribution of a bundle changes the analysis. |

## 2. Source code

| Component | Licence | Notes |
| --- | --- | --- |
| `song-chord-lyrics-analyzer` | GPL-3.0-or-later | Applies to `src/`, `tests/`, `scripts/` and this documentation. |
| Intended GUI toolkit | PyQt6 is GPL-3.0 or commercial | Compatible with GPL-3.0-or-later. PySide6 (LGPL) remains the alternative if the licence position ever changes. The decision must be recorded before phase 15. |

## 3. External executables (executed, not bundled)

| Tool | Licence | Position |
| --- | --- | --- |
| FFmpeg / ffprobe | LGPL-2.1+ for default builds; GPL for `--enable-gpl` builds | The program locates and executes an already-installed binary. No FFmpeg code is linked or redistributed. **If a future installer bundles FFmpeg, this section must be revisited** — the chosen build's configuration and licence texts then have to be shipped. |
| Sonic Annotator | GPL-2.0 (per upstream) | Unverified version (`-only` vs `-or-later`); resolve before integration. |
| Chordino / NNLS Chroma | GPL-2.0 (per upstream) | Unverified version. GPL-2.0-**only** code cannot be combined into a GPL-3 work, so the exact terms matter. |

## 4. Model weights

Rule 4 of the roadmap: do not assume a model is free for commercial use.

| Model family | Weights licence | Status |
| --- | --- | --- |
| Whisper (OpenAI) | MIT (reported) | verify before download automation |
| Demucs pre-trained models | questioned publicly (`facebookresearch/demucs#327`) | **verify before shipping**; code is MIT but weights have been discussed separately |
| PitchPerfect / Chordino models | unverified | verify |
| MOSS-Music | unverified | verify |

Model management (phase 13 of the roadmap ordering, `songlab models ...`) must
record, per model: name, version, source, licence, size, SHA-256, hardware
requirements. Models are never downloaded silently.

## 5. Datasets and samples

* No copyrighted commercial music may be committed to this repository.
* Only original recordings, public-domain recordings, properly licensed material
  or research datasets whose terms permit this use.
* Every sample added to `samples/` must be accompanied by its licence and source
  in `samples/README.md`.
* Ground truth is explicit and documented; expected chords are never invented
  (roadmap section 43).

## 6. Consequences for the code

* Engines that would force an incompatible copyleft licence onto the whole
  application are not integrated; they may still be compared through an
  optional, user-installed executable if that separation is legally sound.
* Optional dependencies must degrade gracefully: `is_available()` reports false
  and the CLI explains what to install, rather than failing to import.
* Any licence question that is unresolved blocks integration, not documentation.
