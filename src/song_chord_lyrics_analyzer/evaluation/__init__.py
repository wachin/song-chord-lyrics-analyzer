"""Chord evaluation (roadmap section 44).

The scoring semantics verified against the CSR oracle fixture
(``tests/fixtures/csr_oracle.json``, derived from GuitarSet comping takes):
duration-weighted Chord Sequence Recall over MIREX-2010 equality, plus the
triad-reduced reference view. Ground truth is always explicit — the fixture
records its dataset provenance (GuitarSet, CC BY 4.0) and the recorded
expected values; nothing here invents numbers.
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

__all__ = [
    "chord_pcs",
    "duration_csr",
    "harte_to_label",
    "mirex_equal",
    "reduce_ref_view",
    "triad_reduce",
]
