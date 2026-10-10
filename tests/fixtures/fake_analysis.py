"""A canned analysis and a hardware-free session for the Phase D GUI tests.

The window must be testable without an engine, without a sound card and without
waiting for a real clock: it only consumes ``SongSession``, so a session with a
:class:`~fixtures.fake_player.FakePlayer` and a fixed
:class:`~song_chord_lyrics_analyzer.analysis.AnalysisOutcome` is enough to drive
every widget deterministically.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fixtures.clock import FakeClock
from fixtures.fake_player import FakePlayer
from song_chord_lyrics_analyzer import __version__
from song_chord_lyrics_analyzer.analysis import AnalysisOutcome, StepOutcome, StepStatus
from song_chord_lyrics_analyzer.app import SongSession
from song_chord_lyrics_analyzer.models.analysis import (
    AnalysisResult,
    AnalysisRun,
    Provenance,
    RunStatus,
)
from song_chord_lyrics_analyzer.models.audio import AudioDocument
from song_chord_lyrics_analyzer.models.confidence import ConfidenceScore
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricWord
from song_chord_lyrics_analyzer.models.music import (
    ChordEvent,
    ChordQuality,
    KeyEstimate,
    KeyMode,
    TempoEstimate,
)

__all__ = ["DURATION", "EVENTS", "STEPS", "AnalysisRecorder", "analysis_outcome", "opened_session"]

#: Length of the fake song, in seconds.
DURATION = 4.0

#: C, G, explicit silence, then F - one event per second, so every second of the
#: fake song has a different thing to show.
EVENTS: list[ChordEvent] = [
    ChordEvent(start=0.0, end=1.0, root="C", quality=ChordQuality.MAJOR, source="fake-chords"),
    ChordEvent(start=1.0, end=2.0, root="G", quality=ChordQuality.MAJOR, source="fake-chords"),
    ChordEvent.silence(2.0, 3.0, source="fake-chords"),
    ChordEvent(start=3.0, end=4.0, root="F", quality=ChordQuality.MAJOR, source="fake-chords"),
]

#: One lyric line per second, so the lyrics view has something active in every
#: second of the fake song, word timestamps included for the highlight.
LYRICS: list[LyricSegment] = [
    LyricSegment(
        text="hola mundo",
        start=0.0,
        end=1.0,
        words=[
            LyricWord(text="hola", start=0.0, end=0.5, confidence=ConfidenceScore.unknown()),
            LyricWord(text="mundo", start=0.5, end=1.0, confidence=ConfidenceScore.unknown()),
        ],
        source="fake-lyrics",
    ),
    LyricSegment(
        text="adios amor",
        start=2.0,
        end=3.0,
        words=[
            LyricWord(text="adios", start=2.0, end=2.5, confidence=ConfidenceScore.unknown()),
            LyricWord(text="amor", start=2.5, end=3.0, confidence=ConfidenceScore.unknown()),
        ],
        source="fake-lyrics",
    ),
]

#: One engine step per layer, as the analysis service would report them.
STEPS: tuple[StepOutcome, ...] = (
    StepOutcome("chords", "fake-chords", StepStatus.OK, "4 chords", 0.5),
    StepOutcome("key", "fake-key", StepStatus.OK, "key C major", 0.1),
    StepOutcome("tempo", "fake-tempo", StepStatus.SKIPPED, "not available"),
)


def analysis_outcome(
    path: str | Path,
    *,
    chords: list[ChordEvent] | None = None,
    duration: float = DURATION,
    steps: tuple[StepOutcome, ...] = STEPS,
    warnings: list[str] | None = None,
    lyrics: list[LyricSegment] | None = LYRICS,
) -> AnalysisOutcome:
    """Build a complete document for one song, as if the pipeline had run."""
    resolved = Path(path)
    document = AnalysisResult(
        provenance=Provenance(
            application_version=__version__,
            input_path=str(resolved),
            python_version="3.13.5",
            platform="Linux x86_64 / CPython 3.13.5",
            engines={},
            configuration={"chords": "fake-chords"},
        ),
        audio=AudioDocument(path=resolved, duration=duration),
        chords=list(EVENTS if chords is None else chords),
        lyrics=list(LYRICS if lyrics is None else lyrics),
        key=KeyEstimate(tonic="C", mode=KeyMode.MAJOR, source="fake-key"),
        tempo=TempoEstimate(bpm=120.0, source="fake-tempo"),
        run=AnalysisRun(
            status=RunStatus.SUCCEEDED,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        ),
        warnings=list(warnings or []),
    )
    return AnalysisOutcome(result=document, steps=steps)


class AnalysisRecorder:
    """An ``analyze`` stand-in that records its calls and returns a canned result."""

    def __init__(self, **options: Any) -> None:
        self.options = options
        self.calls: list[dict[str, Any]] = []

    def __call__(self, path: str | Path, **options: Any) -> AnalysisOutcome:
        self.calls.append({"path": Path(path), **options})
        return analysis_outcome(path, **self.options)


def opened_session(
    path: str | Path,
    *,
    clock: FakeClock | None = None,
    analyze: AnalysisRecorder | None = None,
) -> tuple[SongSession, FakePlayer, FakeClock]:
    """An open session on a fake player and frozen clock."""
    frozen = clock if clock is not None else FakeClock()
    player = FakePlayer(clock=frozen)
    session = SongSession(
        player=player, analyze=analyze if analyze is not None else AnalysisRecorder()
    )
    session.open(path)
    return session, player, frozen
