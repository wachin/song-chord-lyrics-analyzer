"""Metrics stage (roadmap sections 44, 45 and 93).

Implemented: chord metrics (roadmap section 44).

* :func:`align` and :func:`evaluate` are the timing-free sequence views;
  :func:`duration_csr` (duration-weighted chord sequence recall) is re-exported
  from :mod:`song_chord_lyrics_analyzer.evaluation`, which owns the scoring
  semantics.
* :func:`segment_overlap`, :func:`chord_change_detection` and
  :func:`timing_error` are the timing-aware boundary views.
* :func:`chord_labels` and :func:`chord_segments` adapt canonical
  :class:`~song_chord_lyrics_analyzer.models.music.ChordEvent` objects to those
  input shapes, so a real pipeline never re-implements the extraction.

All of it is dependency-free Python and pinned by
``tests/fixtures/chord_metrics_oracle.json``.

Still pending: lyric metrics (WER, CER, timestamp error), key metrics (exact,
relative) and tempo metrics (absolute, half-time, double-time error), plus
performance measurements (processing time, RAM, model size).

Metrics must be computed from explicit ground truth (roadmap section 43);
invented numbers are never acceptable.
"""

from __future__ import annotations

from song_chord_lyrics_analyzer.evaluation import duration_csr
from song_chord_lyrics_analyzer.metrics.adapters import (
    chord_labels,
    chord_segments,
)
from song_chord_lyrics_analyzer.metrics.chords import (
    align,
    evaluate,
    same_quality,
    same_root,
)
from song_chord_lyrics_analyzer.metrics.segmentation import (
    chord_change_detection,
    segment_overlap,
    timing_error,
)

__all__ = [
    "align",
    "chord_change_detection",
    "chord_labels",
    "chord_segments",
    "duration_csr",
    "evaluate",
    "same_quality",
    "same_root",
    "segment_overlap",
    "timing_error",
]
