"""Project the lyrics layer onto the song's clock (roadmap ``[F]`` item 1).

The lyrics view is presenter work, not widget work, exactly like the chord
bands in :mod:`song_chord_lyrics_analyzer.app.timeline`: a widget that decides
which lyric line is sounding *now* is a widget that cannot be tested without a
display, and a second clock the window could drift away from. This module owns
that decision as pure functions over the canonical
:class:`~song_chord_lyrics_analyzer.models.lyrics.LyricSegment`:

* :func:`lyric_lines` puts the document's segments in display order - the timed
  ones first, in playback order; a segment without timestamps is never active
  on the clock, so it is drawn after them, dimmed, in document order.
* :func:`lyric_at` answers "which line is sounding at this instant?" and
  mirrors ``SongSession.chord_at`` exactly: an active segment covers
  ``start <= position < end``, a missing ``end`` runs open-ended, and ``None``
  means *no line is claimed there* - silence, not an error. Since Phase F,
  ``SongSession.lyric_at`` and ``SongSession.word_at`` expose exactly these
  answers on the session itself, so both front ends read the lyrics layer the
  way they read the chords layer.
* :func:`word_at` narrows that to the word whose own timestamps cover the
  instant. A word the engine left without a start never becomes active: the
  view invents nothing the model did not report.

Everything here is plain data and arithmetic: no Qt, no audio, no numpy.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Sequence

from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricWord
from song_chord_lyrics_analyzer.utils.errors import InputError

__all__ = ["lyric_at", "lyric_lines", "word_at"]


def lyric_lines(segments: Iterable[LyricSegment]) -> tuple[LyricSegment, ...]:
    """The segments of a document in display order.

    Timed segments come first in playback order (a stable sort, so segments
    that start together keep their document order); a segment without any
    timestamp is never active on the clock, so it is drawn after them, in
    document order.

    Args:
        segments: The lyric segments of a canonical document, in any order.

    Returns:
        The display-ordered segments.
    """
    timed: list[LyricSegment] = []
    untimed: list[LyricSegment] = []
    for segment in segments:
        (timed if segment.start is not None else untimed).append(segment)
    timed.sort(key=lambda segment: segment.start if segment.start is not None else 0.0)
    return tuple(timed + untimed)


def lyric_at(lines: Sequence[LyricSegment], position: float) -> LyricSegment | None:
    """The segment sounding at ``position`` seconds, or ``None``.

    The lookup mirrors :meth:`~song_chord_lyrics_analyzer.app.session.SongSession.
    chord_at`: a binary search over the timed segments, ``start <= position <
    end``, half-open; a segment without an ``end`` is treated as open-ended,
    which is what the last transcribed window needs. ``None`` means *no line
    is claimed there*, which a view shows as silence rather than emptiness.

    Args:
        lines: The display-ordered segments (see :func:`lyric_lines`).
        position: Playhead in seconds.

    Returns:
        The active segment, or ``None`` before the first line, in a gap or
        past the last one - and when every line is untimed.

    Raises:
        InputError: When ``position`` is negative.
    """
    if position < 0:
        raise InputError(
            f"position must not be negative, got {position!r}",
            hint="Query the lyrics view with a playhead of 0 or more seconds.",
        )
    timed: list[LyricSegment] = []
    starts: list[float] = []
    for segment in lines:
        if segment.start is not None:
            timed.append(segment)
            starts.append(segment.start)
    index = bisect_right(starts, position) - 1
    if index < 0:
        return None
    segment = timed[index]
    if segment.end is not None and position >= segment.end:
        return None
    return segment


def word_at(segment: LyricSegment | None, position: float) -> LyricWord | None:
    """The word inside ``segment`` whose timestamps cover ``position``.

    A word covers ``start <= position < end``. When the engine left the word's
    end open - the last word of a transcribed window, whose end is the next
    hearing's - it stays active until the next word starts, or to the end of
    the segment, whichever comes first. A word without a start timestamp is
    never active, and neither is a segment without words: the model reported
    nothing, and the view invents nothing.

    Args:
        segment: The active segment from :func:`lyric_at`, or ``None``.
        position: Playhead in seconds.

    Returns:
        The active word, or ``None`` when nothing is claimed there.

    Raises:
        InputError: When ``position`` is negative.
    """
    if position < 0:
        raise InputError(f"position must not be negative, got {position!r}")
    if segment is None or not segment.words:
        return None
    timed: list[LyricWord] = []
    starts: list[float] = []
    for word in segment.words:
        if word.start is not None:
            timed.append(word)
            starts.append(word.start)
    if not timed:
        return None
    index = bisect_right(starts, position) - 1
    if index < 0:
        return None
    word = timed[index]
    if word.end is not None and position >= word.end:
        return None
    if word.end is None:
        following = timed[index + 1].start if index + 1 < len(timed) else None
        limit = following if following is not None else segment.end
        if limit is not None and position >= limit:
            return None
    return word
