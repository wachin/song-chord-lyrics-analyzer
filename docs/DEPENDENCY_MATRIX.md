# Dependency Matrix

Status of the phase 1 dependency research (roadmap sections 55 and 83).

**How to read this document.** Nothing here may be added as a dependency before
its row is marked `verified` and its licence is reflected in
`docs/LICENSE_AUDIT.md`. Rows marked `unverified` are candidates only: they have
not been installed or benchmarked, and no quality claim is made about them.

Confidence markers:

* `verified` — confirmed from the upstream package/project page; source cited.
* `partial` — the package page was confirmed, but a key detail (platforms,
  weights licence, maintenance) still needs a check.
* `unverified` — not checked yet. **Do not rely on this row.**

## 1. Currently in use

| Package | Role | Pinned | Verified |
| --- | --- | --- | --- |
| *none* | The core package has zero runtime dependencies by design. | — | verified |

Python standard library only: `wave` (WAV metadata), `subprocess`, `hashlib`,
`argparse`, `logging`, `dataclasses`, `json`, `pathlib`, `tempfile`.

## 2. External executables

| Tool | Role | Licence | Status | Notes |
| --- | --- | --- | --- | --- |
| FFmpeg / ffprobe | decode, resample, transcode, probe | LGPL-2.1+ by default; GPL if built with `--enable-gpl` | partial | Not redistributed: the program only *executes* it. Distribution builds vary, so the audit documents the distinction. Docs: <https://ffmpeg.org/legal.html> |
| Sonic Annotator | runs Vamp plugins (Chordino) offline | GPL-2.0 (per upstream project) | unverified | Verify exact version (`-only` vs `-or-later`) before wiring it in. |
| Chordino / NNLS Chroma | chord estimation Vamp plugin | GPL-2.0 (per upstream project) | unverified | Verify before integrating; GPL-2.0-only would conflict with redistributing a combined GPL-3 work. |

## 3. Candidates for analysis engines

Each candidate must be evaluated on: technical purpose, quality, maintenance
status, Python compatibility, OS support, CPU/GPU needs, model requirements,
licence, **model licence**, installation complexity and performance.

### 3.1 Chords

| Candidate | Purpose | Licence (code) | Status | Known constraints |
| --- | --- | --- | --- | --- |
| chroma/template baseline (own code) | own CQT→chroma→templates→smoothing pipeline | GPL-3.0-or-later (this project) | planned | No third-party licence risk; provides explainability and a fallback. |
| Chordino / NNLS Chroma | chord estimation | GPL-2.0 | unverified | Requires Sonic Annotator or a Vamp host. |
| madmom | chords, beats, downbeats, tempo | see §4 | partial | Reported as limited to Python < 3.10 (`beat_this#9`, Jan 2025; `CPJKU/madmom#527`). Not installable on the Python versions this project targets without a fork. A `madmom-prebuilt` fork exists on PyPI. |
| PitchPerfect (`1ucas/chordify`) | CQT/chroma + templates + Viterbi + key/bass | unverified | unverified | Architectural reference first; use as an adapter only after licence review. |
| MOSS-Music | timestamps, lyrics, chords, key, tempo | unverified | unverified | Must be benchmarked against specialised engines; do not assume superiority. |

### 3.2 Lyrics (ASR / singing)

| Candidate | Purpose | Licence (code) | Status | Known constraints |
| --- | --- | --- | --- | --- |
| faster-whisper | fast Whisper inference (CTranslate2) | MIT (code); Whisper weights MIT | unverified | Verify current release and wheels. |
| openai-whisper | reference Whisper implementation | MIT | unverified | Slower; baseline for comparison. |
| Parakeet-based models | ASR alternative | unverified | unverified | Check model licence and hardware needs. |
| MOSS-Music | music-aware ASR | unverified | unverified | See above. |

### 3.3 Source separation

| Candidate | Purpose | Licence (code) | Status | Known constraints |
| --- | --- | --- | --- | --- |
| Demucs v4 | stems: vocals / drums / bass / other | MIT (code) | partial | Pre-trained **weights** licence has been questioned publicly (`facebookresearch/demucs#327`, 2022). Treat code and weights separately and verify before redistribution. |
| Spleeter / Open-Unmix / UVR models | alternatives | unverified | unverified | Compare quality and licence before choosing. |

### 3.4 Audio→MIDI, pitch, DSP, theory

| Candidate | Purpose | Licence (code) | Status | Known constraints |
| --- | --- | --- | --- | --- |
| Spotify Basic Pitch | polyphonic note transcription | Apache-2.0 | partial | Upstream README has a dated note about Python 3.10 support (notably on Apple Silicon) — verify against the current release before adopting. |
| TorchCREPE | monophonic pitch tracking | unverified (MIT reported) | unverified | Verify licence and model weights. |
| librosa | STFT/CQT/chroma/beat utilities | ISC (reported) | unverified | Confirm licence text; large `numba` dependency chain. |
| Essentia | key/tempo/feature extractors | **AGPL-3.0-only** (PyPI licence expression) | partial | AGPL is copyleft with a network clause. Verify compatibility and wheel availability for each target platform before use. |
| soundfile | libsndfile bindings | BSD-3-Clause (bindings), LGPL-2.1 (libsndfile) | unverified | Confirm bundling implications per platform. |
| scipy | signal processing primitives | BSD-3-Clause (reported) | unverified | Confirm before use. |
| music21 | chord parsing, transposition, MusicXML | unverified (BSD reported) | unverified | Keep strictly in the theory layer, never in raw audio inference. |
| numpy | arrays | BSD-3-Clause (reported) | unverified | Confirm. |

### 3.5 GUI (phase 15+)

| Candidate | Purpose | Licence | Status | Known constraints |
| --- | --- | --- | --- | --- |
| PyQt6 | GUI toolkit | GPL-3.0 or commercial (Riverbank) | partial | Compatible with this project's GPL-3.0-or-later licence. The LGPL alternative is PySide6; the choice must be recorded before GUI work starts. |

## 4. madmom — the first real blocker

Madmom is attractive because it covers beats, downbeats, tempo and chords in one
package, but the ecosystem reports it as restricted to Python < 3.10:

* `CPJKU/beat_this` issue #9 (Jan 2025): "installing madmom which is currently
  limited to Python < 3.10 because of CPJKU/madmom#527".
* PyPI still lists `madmom`, and a `madmom-prebuilt` fork (0.17.post1) exists.

Decision for now: **not adopted**. Options to evaluate in phase 5:

1. Use it only in a separate, documented environment (for example a Python 3.9
   sidecar run through a subprocess), clearly reported by `songlab doctor`.
2. Use a maintained fork, with the fork's provenance recorded.
3. Use alternative beat/tempo engines (librosa, Essentia, newer models) and treat
   madmom as optional.

Whichever path is chosen, `songlab doctor` must be able to report that the engine
is unavailable instead of crashing.

## 5. Verification checklist (phase 1 completion)

For every candidate above, before it becomes a dependency:

- [ ] Exact latest version and release date recorded.
- [ ] `Requires-Python` and the Python versions actually tested.
- [ ] Linux, Windows and macOS wheel availability (or build requirements).
- [ ] CPU/GPU requirements and CPU fallback behaviour.
- [ ] Code licence, model/weights licence and dataset licence recorded separately.
- [ ] Installation complexity and disk footprint measured.
- [ ] A minimal smoke test executed locally, with the result recorded here.
- [ ] Rejection reasons recorded for anything not adopted.

Until this checklist is complete for a candidate, no benchmark or accuracy claim
about it may appear in this repository (roadmap rules 4, 5 and 6).
