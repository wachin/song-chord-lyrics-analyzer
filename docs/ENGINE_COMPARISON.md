## 4. Lyrics engines — verdict

**Verdict: `onnx-asr` + Parakeet TDT 0.6B v3 (int8 ONNX) is the first lyrics
engine and was adopted in 2026-10-08 (roadmap Phase E).**

The representative implementation is ``src/song_chord_lyrics_analyzer/engines
/lyrics_parakeet.py`` behind the optional ``lyrics`` extra: it is the only
candidate that merged **accuracy on English (0.08 WER), CPU speed (real-time
factor 0.20), a verified licence and a decidable install**. The measured
quantities live in `docs/ENGINE_COMPARISON.md`s section 25/26 tables; this
section records only the decision and the rules the implementation follows.

* **Speed — the load-bearing requirement.** The bundled model cannot take a
  whole song (``recognize()`` on a 272 s file returned 8 garbled words) and the
  upstream speech VAD returns *nothing* on singing. Every implementation here
  therefore chunks long audio; the section 45 performance numbers belong to the
  engine, not to this table.
* **Weights never leave the cache.** The model is fetched by ``onnx-asr``
  itself, into the Hugging Face cache, and is never stored in this repository,
  never committed and never advertised as a dependency that can be reproduced
  offline.
* **No fake confidence.** The model reports no calibrated per-word confidence;
  ``LyricWord`` keeps ``ConfidenceScore.unknown``. Only a measured value belongs
  in the document, and a WER number only appears with its measurement artifact
  (file, reference, harness).
* **Word timestamps come from the model's own tokens.** A word's end is the next
  word's start; the last word of a window keeps ``end=None`` because the audio
  carries on past it and no boundary was reported.

### Remaining open questions (phase 4)

* **A second candidate is still untested end to end**: faster-whisper
  ``small`` (WER 0.3799, RTF 0.95) beats Parakeet on Tagalog and Spanish —
  whether that transfers to English is not established and would need a
  phase-3 measurement.
* **Chunk boundaries**: a word clipped at a window edge is attributed to the
  earlier window and can be lost; the `--overlap-seconds` option re-hears the
  seam but does not currently repair a clipped word. Whether overlap should be
  turned on by default is the only remaining implementation question.
* **Language detection** is not reported by this backend; a user-level tag can
  be recorded with the `--language` flag.
