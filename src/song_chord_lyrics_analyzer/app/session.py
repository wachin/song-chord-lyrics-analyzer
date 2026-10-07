"""One song, from file to the chord under the playhead (roadmap Phase C).

The vertical slice the roadmap calls the first product milestone needs one place
that ties the pieces together: open a file, decode it, analyse it, own the
player, and answer "which chord is sounding at this instant?". That place is
:class:`SongSession`, and it is deliberately headless - no Qt, no display, no ML
imports - so both the CLI and the future GUI can drive the same object.

Two seams keep it testable without hardware or a DSP stack: the ``analyze``
callable and the ``Player``. With a fake player whose playhead runs on a fake
clock, the synchronization logic is exercised deterministically.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from song_chord_lyrics_analyzer.analysis import AnalysisOutcome, StepOutcome, run_analysis
from song_chord_lyrics_analyzer.audio.playback import PlaybackState, Player, create_player
from song_chord_lyrics_analyzer.audio.validation import validate_audio_file
from song_chord_lyrics_analyzer.models.analysis import AnalysisResult
from song_chord_lyrics_analyzer.models.music import ChordEvent
from song_chord_lyrics_analyzer.utils.errors import InputError
from song_chord_lyrics_analyzer.utils.logging import get_logger

__all__ = ["SessionSnapshot", "SongSession"]

_logger = get_logger("app.session")


@dataclass(frozen=True)
class SessionSnapshot:
    """What a display needs at one instant: the playback timeline model.

    Attributes:
        path: The open file.
        duration: Track length in seconds.
        position: Current playhead in seconds.
        state: Whether the player is stopped, playing or paused.
        chord: The chord event under the playhead, or ``None`` when no chord
            covers it (before the first event, in a gap, or past the end).
    """

    path: Path
    duration: float
    position: float
    state: PlaybackState
    chord: ChordEvent | None


class SongSession:
    """A song being analysed and played: the Phase C service layer.

    Typical use::

        session = SongSession()
        session.open(audio_file)         # any format the decoder supports
        session.play()
        session.current_chord()          # what is sounding right now
        session.chord_at(42.5)           # ...or anywhere on the timeline
        session.close()
    """

    def __init__(
        self,
        *,
        player: Player | None = None,
        analyze: Callable[..., AnalysisOutcome] = run_analysis,
    ) -> None:
        """Create a session.

        Args:
            player: Playback backend. Defaults to the installation's player,
                created on first use (so a machine without an audio device can
                still open and inspect a song).
            analyze: Analysis function, defaulting to
                :func:`~song_chord_lyrics_analyzer.analysis.run_analysis`.
        """
        self._player = player
        self._analyze = analyze
        self._path: Path | None = None
        self._outcome: AnalysisOutcome | None = None
        self._events: tuple[ChordEvent, ...] = ()
        self._starts: tuple[float, ...] = ()

    # -- lifecycle ---------------------------------------------------------

    def open(
        self,
        path: str | Path,
        *,
        engines: dict[str, str] | None = None,
        input_hash: bool = True,
    ) -> AnalysisResult:
        """Decode, analyse and load ``path``; return the canonical document.

        Args:
            path: The audio file to open.
            engines: Optional ``kind -> engine name`` overrides for the analysis.
            input_hash: Whether to record the input's SHA-256 in provenance.

        Raises:
            AudioFileNotFoundError: The path does not exist.
            UnsupportedAudioError: The file could not be decoded.
            DependencyError: No engine or decoder can run in this environment.
        """
        resolved = validate_audio_file(path)
        self.close()
        try:
            self.player.load(resolved)
            outcome = self._analyze(resolved, engines=engines, input_hash=input_hash)
        except Exception:
            self.close()
            raise

        events = tuple(sorted(outcome.result.chords, key=lambda event: event.start))
        self._path = resolved
        self._outcome = outcome
        self._events = events
        self._starts = tuple(event.start for event in events)
        _logger.debug("opened %s with %d chord events", resolved, len(events))
        return outcome.result

    def close(self) -> None:
        """Release the player and forget the open song."""
        if self._player is not None:
            self._player.close()
        self._path = None
        self._outcome = None
        self._events = ()
        self._starts = ()

    @property
    def is_open(self) -> bool:
        """Whether a song is currently open."""
        return self._path is not None

    # -- state -------------------------------------------------------------

    @property
    def player(self) -> Player:
        """The playback backend, created on first use."""
        if self._player is None:
            self._player = create_player()
        return self._player

    @property
    def path(self) -> Path | None:
        """The open file, or ``None``."""
        return self._path

    @property
    def document(self) -> AnalysisResult | None:
        """The canonical analysis document, or ``None`` when nothing is open."""
        return self._outcome.result if self._outcome is not None else None

    @property
    def steps(self) -> tuple[StepOutcome, ...]:
        """The per-engine step summary of the last analysis."""
        return self._outcome.steps if self._outcome is not None else ()

    @property
    def state(self) -> PlaybackState:
        """Whether the player is stopped, playing or paused."""
        return self._player.state if self._player is not None else PlaybackState.STOPPED

    def duration(self) -> float:
        """Track length in seconds - the player's timeline, then the document's."""
        if self._player is not None and self._player.duration() > 0:
            return self._player.duration()
        document = self.document
        if document is not None and document.audio is not None and document.audio.duration:
            return float(document.audio.duration)
        return 0.0

    def position(self) -> float:
        """Current playhead in seconds."""
        return self._player.position() if self._player is not None else 0.0

    def snapshot(self) -> SessionSnapshot:
        """The playback timeline model at this instant, for a display to render.

        Raises:
            InputError: When no song is open.
        """
        if self._path is None:
            raise InputError(
                "No song is open.",
                hint="Call session.open(path) before reading a snapshot.",
            )
        return SessionSnapshot(
            path=self._path,
            duration=self.duration(),
            position=self.position(),
            state=self.state,
            chord=self.current_chord(),
        )

    # -- playback ----------------------------------------------------------

    def play(self) -> None:
        """Start or resume playback."""
        self.player.play()

    def pause(self) -> None:
        """Pause playback."""
        self.player.pause()

    def stop(self) -> None:
        """Stop playback and return the playhead to the start."""
        self.player.stop()

    def seek(self, position: float) -> None:
        """Move the playhead to ``position`` seconds."""
        self.player.seek(position)

    # -- synchronization ---------------------------------------------------

    def chord_at(self, position: float) -> ChordEvent | None:
        """The chord sounding at ``position`` seconds, or ``None``.

        An event covers ``start <= position < end`` (half-open). ``None`` means
        *no chord is claimed there*: before the first event, inside a gap, or at
        and past the last event's end. An event without an ``end`` (only
        possible as the last one) is treated as open-ended. Explicit silence is
        an event of its own - it is returned, not skipped, so a caller can tell
        "no chord" (``N``) apart from "nothing to say" (``None``).

        The lookup is a binary search, so it stays cheap for long songs.

        Raises:
            InputError: When ``position`` is negative.
        """
        if position < 0:
            raise InputError(
                f"position must not be negative, got {position!r}",
                hint="Query the timeline with a playhead of 0 or more seconds.",
            )
        if not self._events:
            return None
        index = bisect_right(self._starts, float(position)) - 1
        if index < 0:
            return None
        event = self._events[index]
        if event.end is not None and position >= event.end:
            return None
        return event

    def current_chord(self) -> ChordEvent | None:
        """The chord at the current playhead, or ``None`` when none covers it."""
        return self.chord_at(self.position())
