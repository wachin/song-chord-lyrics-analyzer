"""Turn the session's timeline into something a human can watch (Phase C).

Roadmap link 7 - "synchronized chord display" - is the last missing piece of the
first product milestone, and this module is the smallest surface that closes it:
a *presenter* that maps one :class:`~song_chord_lyrics_analyzer.app.session.SessionSnapshot`
to a :class:`DisplayFrame` and renders it as one line of text showing the chord
under the playhead.

The split matters for Phase D. :func:`frame_from` and :func:`render_frame` are
pure functions over plain data, so the Qt window can render the same frame with
its own widgets while the logic stays covered by dependency-free tests;
:class:`ConsoleDisplay` only decides *where* the frame is written, and
:func:`follow` owns the refresh loop with the sleep function injected, so the
whole "chord changes as the song plays" behaviour is testable on a fake clock.

Nothing here knows about engines, decoding or Qt: the display renders what the
session already synchronized.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import IO

from song_chord_lyrics_analyzer.app.session import SessionSnapshot, SongSession
from song_chord_lyrics_analyzer.audio.playback import PlaybackState
from song_chord_lyrics_analyzer.models.music import ChordEvent
from song_chord_lyrics_analyzer.utils.errors import InputError
from song_chord_lyrics_analyzer.utils.time import format_timestamp

__all__ = [
    "BAR_WIDTH",
    "DEFAULT_REFRESH_INTERVAL",
    "NO_CHORD_TEXT",
    "ConsoleDisplay",
    "DisplayFrame",
    "follow",
    "frame_from",
    "render_frame",
]

#: Width of the progress bar in characters.
BAR_WIDTH = 24

#: Seconds between two refreshes of the live display.
DEFAULT_REFRESH_INTERVAL = 0.1

#: What to show when the session claims *no* chord at the playhead. Distinct
#: from ``N``, which is a chord event that states "the music is silent here".
NO_CHORD_TEXT = "--"

_BAR_FILL = "#"
_BAR_EMPTY = "-"


@dataclass(frozen=True)
class DisplayFrame:
    """One instant of the song, ready to render.

    Attributes:
        position: Playhead in seconds.
        duration: Track length in seconds (``0.0`` when unknown).
        state: Whether the player is stopped, playing or paused.
        chord: The event under the playhead, or ``None`` when no chord is
            claimed there (before the first event, in a gap, or past the end).
    """

    position: float
    duration: float
    state: PlaybackState
    chord: ChordEvent | None

    @property
    def chord_text(self) -> str:
        """The chord label to show: ``N`` for silence, ``--`` for no claim."""
        return self.chord.to_label() if self.chord is not None else NO_CHORD_TEXT

    @property
    def progress(self) -> float:
        """How far into the track the playhead is, clamped to ``[0.0, 1.0]``."""
        if self.duration <= 0.0:
            return 0.0
        return min(1.0, max(0.0, self.position / self.duration))

    @property
    def time_text(self) -> str:
        """Playhead and duration as ``HH:MM:SS.mmm`` timestamps."""
        return f"{format_timestamp(self.position)} / {format_timestamp(self.duration)}"

    @property
    def is_finished(self) -> bool:
        """Whether the playhead reached the end of the track."""
        return self.duration > 0.0 and self.progress >= 1.0


def frame_from(snapshot: SessionSnapshot) -> DisplayFrame:
    """Project a session snapshot onto the display model.

    Args:
        snapshot: A snapshot read from a :class:`SongSession`.

    Returns:
        The frame a front end should draw for that instant.
    """
    return DisplayFrame(
        position=snapshot.position,
        duration=snapshot.duration,
        state=snapshot.state,
        chord=snapshot.chord,
    )


def render_frame(frame: DisplayFrame, *, width: int = BAR_WIDTH) -> str:
    """Render one frame as a single line of text.

    Args:
        frame: The frame to render.
        width: Progress-bar width in characters.

    Returns:
        A line shaped like
        ``00:00:01.200 / 00:00:04.000  [#######-----------------]  G    playing``.
    """
    if width < 1:
        raise InputError(f"the progress bar needs at least one column, got {width!r}")
    filled = round(frame.progress * width)
    bar = _BAR_FILL * filled + _BAR_EMPTY * (width - filled)
    return f"{frame.time_text}  [{bar}]  {frame.chord_text:<4} {frame.state.value}"


class ConsoleDisplay:
    """Write frames to a text stream, redrawing one line when it is a terminal.

    On a terminal the line is rewritten in place with a carriage return, which
    is what makes the chord look like it changes *during* playback; when the
    stream is not a terminal (a pipe, a log file, a test buffer) every frame is
    printed on its own line, so the output stays a readable, assertable log.

    Args:
        stream: Where to write. Defaults to ``sys.stdout``.
        inline: Force in-place redrawing on or off. Defaults to "only when the
            stream is a terminal".
        width: Progress-bar width in characters.
    """

    def __init__(
        self,
        stream: IO[str] | None = None,
        *,
        inline: bool | None = None,
        width: int = BAR_WIDTH,
    ) -> None:
        self._stream: IO[str] = stream if stream is not None else sys.stdout
        if inline is None:
            isatty = getattr(self._stream, "isatty", None)
            inline = bool(isatty()) if callable(isatty) else False
        self._inline = inline
        self._width = width
        self._last_length = 0

    @property
    def inline(self) -> bool:
        """Whether frames are rewritten in place instead of printed per line."""
        return self._inline

    def show(self, snapshot: SessionSnapshot) -> DisplayFrame:
        """Render ``snapshot`` and write it; return the frame that was drawn."""
        frame = frame_from(snapshot)
        self.write(frame)
        return frame

    def write(self, frame: DisplayFrame) -> None:
        """Write one already-built frame."""
        line = render_frame(frame, width=self._width)
        if self._inline:
            padding = " " * max(0, self._last_length - len(line))
            self._stream.write("\r" + line + padding)
            self._last_length = len(line)
        else:
            self._stream.write(line + "\n")
        self._stream.flush()

    def close(self) -> None:
        """Finish the in-place line, so the next output starts on a new one."""
        if self._inline and self._last_length:
            self._stream.write("\n")
            self._last_length = 0
            self._stream.flush()


def follow(
    session: SongSession,
    display: ConsoleDisplay,
    *,
    interval: float = DEFAULT_REFRESH_INTERVAL,
    sleep: Callable[[float], None] = time.sleep,
    max_frames: int | None = None,
) -> int:
    """Draw the session while it keeps playing, and return the frames drawn.

    The loop draws once, then checks the *live* playback state rather than the
    clock: it keeps refreshing while the session is ``PLAYING`` and stops as
    soon as it is paused, stopped or finished - so it can never hang on a paused
    song. One last frame is drawn after the loop, which is what shows the final
    ``stopped`` state at the end of a track.

    Args:
        session: The session to watch.
        display: Where to write the frames.
        interval: Seconds to wait between refreshes.
        sleep: Waiter between two refreshes, injectable for tests.
        max_frames: Stop after this many frames (``None`` = until playback ends).

    Returns:
        How many frames were drawn.

    Raises:
        InputError: When ``interval`` is not positive or ``max_frames`` is not
            at least one.
    """
    if interval <= 0.0:
        raise InputError(f"the refresh interval must be positive, got {interval!r}")
    if max_frames is not None and max_frames < 1:
        raise InputError(f"max_frames must be at least 1, got {max_frames!r}")

    frames = 0
    while True:
        display.show(session.snapshot())
        frames += 1
        if session.state is not PlaybackState.PLAYING:
            break
        if max_frames is not None and frames >= max_frames:
            break
        sleep(interval)
    display.close()
    return frames
