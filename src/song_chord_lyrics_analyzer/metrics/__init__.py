"""Metrics stage (roadmap sections 44, 45 and 93).

Implemented: chord, key and tempo metrics (roadmap section 44).

* :func:`align` and :func:`evaluate` are the timing-free sequence views;
  :func:`duration_csr` (duration-weighted chord sequence recall) is re-exported
  from :mod:`song_chord_lyrics_analyzer.evaluation`, which owns the scoring
  semantics.
* :func:`segment_overlap`, :func:`chord_change_detection` and
  :func:`timing_error` are the timing-aware boundary views.
* :func:`chord_labels` and :func:`chord_segments` adapt canonical
  :class:`~song_chord_lyrics_analyzer.models.music.ChordEvent` objects to those
  input shapes, so a real pipeline never re-implements the extraction.
* Key metrics: :func:`exact_key_accuracy`, :func:`relative_key_error`,
  :func:`key_relation`, :func:`same_key` and :func:`weighted_key_score` (the
  MIREX-style heuristic view), pinned by ``tests/fixtures/key_oracle.json``.
* Tempo metrics: :func:`tempo_error` (absolute, half-time and double-time BPM
  error reported together) and :func:`tempo_interpretation`.
* :func:`key_labels` and :func:`tempo_bpms` adapt canonical
  :class:`~song_chord_lyrics_analyzer.models.music.KeyEstimate` and
  :class:`~song_chord_lyrics_analyzer.models.music.TempoEstimate` objects.

All of it is dependency-free Python and pinned by the fixture oracles.

Still pending: lyric metrics (WER, CER, timestamp error) and performance
measurements (processing time, RAM, model size).

Metrics must be computed from explicit ground truth (roadmap section 43);
invented numbers are never acceptable.
"""

from __future__ import annotations

from song_chord_lyrics_analyzer.evaluation import duration_csr
from song_chord_lyrics_analyzer.metrics.adapters import (
    chord_labels,
    chord_segments,
    key_labels,
    tempo_bpms,
)
from song_chord_lyrics_analyzer.metrics.chords import (
    align,
    evaluate,
    same_quality,
    same_root,
)
from song_chord_lyrics_analyzer.metrics.key import (
    exact_key_accuracy,
    key_relation,
    key_relation_counts,
    relative_key_error,
    same_key,
    weighted_key_score,
)
from song_chord_lyrics_analyzer.metrics.segmentation import (
    chord_change_detection,
    segment_overlap,
    timing_error,
)
from song_chord_lyrics_analyzer.metrics.tempo import (
    tempo_error,
    tempo_interpretation,
)

__all__ = [
    "align",
    "chord_change_detection",
    "chord_labels",
    "chord_segments",
    "duration_csr",
    "evaluate",
    "exact_key_accuracy",
    "key_labels",
    "key_relation",
    "key_relation_counts",
    "relative_key_error",
    "same_key",
    "same_quality",
    "same_root",
    "segment_overlap",
    "tempo_bpms",
    "tempo_error",
    "tempo_interpretation",
    "timing_error",
    "weighted_key_score",
]
