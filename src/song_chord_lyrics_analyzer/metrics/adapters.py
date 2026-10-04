"""Adapters from the canonical model to the metric inputs (roadmap section 44).

The metric functions in :mod:`song_chord_lyrics_analyzer.metrics.chords` and
:mod:`song_chord_lyrics_analyzer.metrics.segmentation` score *plain* sequences:
a list of labels for the timing-free views, a list of ``(start, end, label)``
triples for the boundary views. A real pipeline, however, carries canonical
:class:`~song_chord_lyrics_analyzer.models.music.ChordEvent` objects, which also
hold root, quality, bass, confidence and provenance.

These adapters are the single place that bridges the two, so no caller
re-implements the extraction:

* :func:`chord_labels` - the label sequence, in the order given;
* :func:`chord_segments` - the timed triples, completing each event's missing
  ``end`` from the next chord's ``start`` (or an explicit track end);
* :func:`key_labels` - the ``"C major"``-style strings
  :mod:`song_chord_lyrics_analyzer.metrics.key` scores, from
  :class:`~song_chord_lyrics_analyzer.models.music.KeyEstimate` objects;
* :func:`tempo_bpms` - the BPM values
  :mod:`song_chord_lyrics_analyzer.metrics.tempo` scores, from
  :class:`~song_chord_lyrics_analyzer.models.music.TempoEstimate` objects;
* :func:`lyric_text` - the transcript text
  :mod:`song_chord_lyrics_analyzer.metrics.lyrics` scores, from
  :class:`~song_chord_lyrics_analyzer.models.lyrics.LyricSegment` objects;
* :func:`timed_words` - the ``(text, start)`` pairs the word-timestamp metric
  scores, dropping words whose start was never reported.

Nothing is invented (roadmap section 43): a chord whose end cannot be
determined raises :class:`ValueError` instead of guessing a boundary, and an
overlapping or out-of-order sequence is rejected rather than silently
mis-scored.
"""

from __future__ import annotations

from collections.abc import Sequence

from song_chord_lyrics_analyzer.metrics.lyrics import TimedWord
from song_chord_lyrics_analyzer.metrics.segmentation import Segment
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricWord
from song_chord_lyrics_analyzer.models.music import ChordEvent, KeyEstimate, TempoEstimate

__all__ = [
    "chord_labels",
    "chord_segments",
    "key_labels",
    "lyric_text",
    "tempo_bpms",
    "timed_words",
]


def chord_labels(events: Sequence[ChordEvent]) -> list[str]:
    """The label sequence of chord events, preserving the given order.

    Every :class:`~song_chord_lyrics_analyzer.models.music.ChordEvent` carries a
    rendered ``label`` (``"N"`` for an explicit no-chord, ``"?"`` when no
    evidence was available), so the mapping is total and uncertainty survives.
    """
    return [event.label for event in events]


def chord_segments(
    events: Sequence[ChordEvent],
    *,
    end: float | None = None,
) -> list[Segment]:
    """Timed ``(start, end, label)`` triples from chord events.

    Each event's end is taken from ``event.end`` when present; otherwise the
    next event's ``start`` closes it, treating the annotations as contiguous.
    The final event falls back to ``end`` (a track duration or the end of the
    annotation window). If the last event has no end and ``end`` is not given,
    or if a resulting interval is empty/reversed, :class:`ValueError` is raised
    because a boundary would otherwise have to be invented.

    Events must be non-overlapping and in time order; a sequence that overlaps
    or goes backwards is rejected, since the boundary metrics assume a partition
    of the timeline rather than arbitrary intervals.
    """
    segments: list[Segment] = []
    for index, event in enumerate(events):
        start = float(event.start)
        if event.end is not None:
            stop = float(event.end)
        elif index + 1 < len(events):
            stop = float(events[index + 1].start)
        elif end is not None:
            stop = float(end)
        else:
            raise ValueError(
                "cannot determine the end of the last chord event: "
                "set ChordEvent.end or pass end= (the track duration)"
            )
        if stop < start:
            raise ValueError(f"chord interval is reversed: start {start!r} after end {stop!r}")
        if index + 1 < len(events) and float(events[index + 1].start) < stop:
            raise ValueError(
                f"chord intervals overlap: {start!r}-{stop!r} is followed by "
                f"{events[index + 1].start!r}"
            )
        segments.append((start, stop, event.label))
    return segments


def key_labels(estimates: Sequence[KeyEstimate]) -> list[str]:
    """The key labels of key estimates, preserving the given order.

    :attr:`~song_chord_lyrics_analyzer.models.music.KeyEstimate.label` renders
    ``"C major"`` or ``"unknown"``, exactly the vocabulary
    :mod:`song_chord_lyrics_analyzer.metrics.key` accepts, so an unresolved key
    survives as ``"unknown"`` instead of being dropped.
    """
    return [estimate.label for estimate in estimates]


def tempo_bpms(estimates: Sequence[TempoEstimate]) -> list[float]:
    """The BPM values of tempo estimates, preserving the given order.

    Only the primary reading is taken; competing half-time/double-time
    interpretations stay on the estimate's ``alternatives`` and are still
    reported by :func:`song_chord_lyrics_analyzer.metrics.tempo.tempo_error`.
    """
    return [float(estimate.bpm) for estimate in estimates]


def lyric_text(segments: Sequence[LyricSegment]) -> str:
    """The transcript text of lyric segments, joined in order.

    Segment text is concatenated with single spaces; the lyrics metric applies
    its own normalization, so punctuation and case survive here and are only
    folded at scoring time.
    """
    return " ".join(segment.text for segment in segments if segment.text)


def timed_words(words: Sequence[LyricWord]) -> list[TimedWord]:
    """The ``(text, start)`` pairs the word-timestamp metric scores.

    A word's start time is never invented: words without one are dropped rather
    than assigned a placeholder, so the metric only sees what the engine
    actually reported.
    """
    return [(word.text, float(word.start)) for word in words if word.start is not None]
