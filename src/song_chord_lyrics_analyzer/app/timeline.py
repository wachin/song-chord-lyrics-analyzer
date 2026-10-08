"""Project the canonical timeline onto something drawn (roadmap Phase D).

The roadmap asks for a second display surface - a window instead of a terminal -
and the way to keep it cheap is to keep the *geometry* out of the widgets.
:mod:`song_chord_lyrics_analyzer.app.display` already turns a snapshot into a
:class:`~song_chord_lyrics_analyzer.app.display.DisplayFrame`; this module adds
the two things a drawn timeline needs and a terminal does not:

* :func:`chord_bands` lays the chord events out over the whole track in seconds,
  so a widget only has to map seconds to pixels. It mirrors ``SongSession.chord_at``
  exactly - an event covers ``start <= t < end`` and the latest event that started
  wins - so the band drawn under the playhead is the band the session reports.
* :func:`x_for_position` / :func:`position_for_x` are the two directions of that
  mapping, clamped to the track, which is what makes "click the timeline to seek"
  a pure function instead of widget arithmetic.

Everything here is plain data and arithmetic: no Qt, no audio, no numpy. Phase D
tests it without a display, and the window renders the result.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from song_chord_lyrics_analyzer.models.music import ChordEvent
from song_chord_lyrics_analyzer.utils.errors import InputError

__all__ = [
    "ChordBand",
    "chord_bands",
    "position_for_x",
    "x_for_position",
]


@dataclass(frozen=True)
class ChordBand:
    """One chord event projected onto the whole track.

    Attributes:
        start: Start time in seconds.
        end: End time in seconds, never before :attr:`start`.
        label: The label to draw (``to_label()``: ``N`` for silence, ``?`` when
            the event carries no evidence).
        is_silence: Whether the band is explicit silence.
    """

    start: float
    end: float
    label: str
    is_silence: bool

    @property
    def duration(self) -> float:
        """Length of the band in seconds."""
        return self.end - self.start


def chord_bands(events: Iterable[ChordEvent], *, duration: float) -> tuple[ChordBand, ...]:
    """Lay chord events out over a track of ``duration`` seconds.

    The rules come from the session, not from the engine:

    * An event with no ``end`` runs until the next event starts, or to the end of
      the track.
    * A band never crosses the next one's start and never runs past ``duration``,
      so overlapping engine output still paints one label per instant - the same
      one ``chord_at()`` would return.
    * A band that would be empty (an event that ends where the next begins, a
      zero-length event, or an event starting at or after the end of the track)
      is dropped: there is nothing to draw and nothing to seek to.

    Args:
        events: The chord events of a document, in any order.
        duration: Track length in seconds; ``0.0`` means "unknown", in which case
            the last band is left open-ended at its own end.

    Returns:
        The bands in time order.
    """
    ordered = sorted(events, key=lambda event: event.start)
    bands: list[ChordBand] = []
    for index, event in enumerate(ordered):
        if duration > 0.0 and event.start >= duration:
            continue
        next_start = ordered[index + 1].start if index + 1 < len(ordered) else None
        end = event.end
        if next_start is not None:
            end = next_start if end is None else min(end, next_start)
        elif end is None:
            end = duration if duration > 0.0 else event.start
        if duration > 0.0:
            end = min(end, duration)
        if end <= event.start:
            continue
        bands.append(
            ChordBand(
                start=event.start,
                end=end,
                label=event.to_label(),
                is_silence=event.is_silence,
            )
        )
    return tuple(bands)


def _validate_geometry(duration: float, width: float) -> None:
    if duration < 0.0:
        raise InputError(f"duration must not be negative, got {duration!r}")
    if width <= 0.0:
        raise InputError(f"width must be positive, got {width!r}")


def x_for_position(position: float, *, duration: float, width: float) -> float:
    """Where ``position`` seconds sits on a timeline ``width`` wide.

    Args:
        position: Playhead in seconds; values outside the track are clamped, so a
            drawing routine never paints outside its own widget.
        duration: Track length in seconds; ``0.0`` means "unknown" and maps to
            the start of the timeline.
        width: Width of the drawn timeline, in whole pixels or any other unit.

    Returns:
        The offset from the left edge, within ``[0.0, width]``.

    Raises:
        InputError: When ``duration`` is negative or ``width`` is not positive.
    """
    _validate_geometry(duration, width)
    if duration == 0.0:
        return 0.0
    return min(width, max(0.0, position / duration * width))


def position_for_x(x: float, *, duration: float, width: float) -> float:
    """The playback position under an offset of ``x`` on a timeline.

    The inverse of :func:`x_for_position`: this is what turns a click or a drag
    into ``session.seek(seconds)``.

    Args:
        x: Offset from the left edge, clamped to the timeline.
        duration: Track length in seconds; ``0.0`` means "unknown" and maps to
            the start of the track.
        width: Width of the drawn timeline, in the same unit the caller measures
            the click in.

    Returns:
        Seconds from the start of the track, within ``[0.0, duration]``.

    Raises:
        InputError: When ``duration`` is negative or ``width`` is not positive.
    """
    _validate_geometry(duration, width)
    if duration == 0.0:
        return 0.0
    return min(duration, max(0.0, x / width * duration))
