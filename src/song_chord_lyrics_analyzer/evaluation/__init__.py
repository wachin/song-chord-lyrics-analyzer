"""Chord evaluation (roadmap sections 44 and Phase I P1).

The scoring semantics verified against the CSR oracle fixture
(``tests/fixtures/csr_oracle.json``, derived from GuitarSet comping takes):
duration-weighted Chord Sequence Recall over MIREX-2010 equality, plus the
triad-reduced reference view. Ground truth is always explicit — the fixture
records its dataset provenance (GuitarSet, CC BY 4.0) and the recorded
expected values; nothing here invents numbers.

:mod:`song_chord_lyrics_analyzer.evaluation.guitarset` adds the reproducible
corpus side: a committed manifest of GuitarSet takes with SHA-256 digests, the
JAMS chord reader, and the full per-take comparison vector used by
``scripts/chord_benchmark.py``.
"""

from __future__ import annotations

from song_chord_lyrics_analyzer.evaluation.chords import (
    chord_pcs,
    duration_csr,
    harte_to_label,
    mirex_equal,
    reduce_ref_view,
    triad_reduce,
)
from song_chord_lyrics_analyzer.evaluation.guitarset import (
    GuitarSetManifest,
    GuitarSetTake,
    aggregate_scores,
    load_manifest,
    read_jams_chords,
    score_take,
    sha256_file,
    verify_take_files,
)

__all__ = [
    "GuitarSetManifest",
    "GuitarSetTake",
    "aggregate_scores",
    "chord_pcs",
    "duration_csr",
    "harte_to_label",
    "load_manifest",
    "mirex_equal",
    "read_jams_chords",
    "reduce_ref_view",
    "score_take",
    "sha256_file",
    "triad_reduce",
    "verify_take_files",
]
