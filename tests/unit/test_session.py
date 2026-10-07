"""The Phase C session: open, play, and know the chord under the playhead.

The synchronization logic is tested with a fake clock and a fake player, so the
assertions are exact instead of timing-dependent: at every boundary the right
event is returned, and ``N`` / ``?`` / "no chord" stay distinguishable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from fixtures.audio import write_sine_wav
from fixtures.clock import FakeClock
from fixtures.fake_player import FakePlayer
from song_chord_lyrics_analyzer import __version__
from song_chord_lyrics_analyzer.analysis import AnalysisOutcome
from song_chord_lyrics_analyzer.app import SessionSnapshot, SongSession
from song_chord_lyrics_analyzer.audio.playback import PlaybackState
from song_chord_lyrics_analyzer.models.analysis import (
    AnalysisResult,
    AnalysisRun,
    Provenance,
    RunStatus,
)
from song_chord_lyrics_analyzer.models.audio import AudioDocument
from song_chord_lyrics_analyzer.models.music import ChordEvent, ChordQuality
from song_chord_lyrics_analyzer.utils.errors import (
    AudioFileNotFoundError,
    DependencyError,
    InputError,
)

DURATION = 4.0

#: C, G, explicit silence, then an unclaimed chord - one event per second.
EVENTS: list[ChordEvent] = [
    ChordEvent(start=0.0, end=1.0, root="C", quality=ChordQuality.MAJOR, source="fake"),
    ChordEvent(start=1.0, end=2.0, root="G", quality=ChordQuality.MAJOR, source="fake"),
    ChordEvent.silence(2.0, 3.0, source="fake"),
    ChordEvent(start=3.0, end=4.0, source="fake"),
]


def _outcome(
    path: Path, chords: list[ChordEvent], *, duration: float = DURATION
) -> AnalysisOutcome:
    document = AnalysisResult(
        provenance=Provenance(application_version=__version__, input_path=str(path)),
        audio=AudioDocument(path=path, duration=duration),
        chords=list(chords),
        run=AnalysisRun(status=RunStatus.SUCCEEDED, started_at=datetime.now(timezone.utc)),
    )
    return AnalysisOutcome(result=document, steps=())


class _Recorder:
    """An ``analyze`` stand-in that records how the session called it."""

    def __init__(self, chords: list[ChordEvent] = EVENTS, *, duration: float = DURATION) -> None:
        self.chords = chords
        self.duration = duration
        self.calls: list[dict[str, Any]] = []

    def __call__(self, path: str | Path, **options: Any) -> AnalysisOutcome:
        self.calls.append({"path": Path(path), **options})
        return _outcome(Path(path), self.chords, duration=self.duration)


def _session(tmp_path: Path, **kwargs: Any) -> tuple[SongSession, FakePlayer, FakeClock, _Recorder]:
    clock = FakeClock()
    player = FakePlayer(clock=clock)
    recorder = kwargs.pop("analyze", _Recorder())
    session = SongSession(player=player, analyze=recorder, **kwargs)
    session.open(_wav(tmp_path))
    return session, player, clock, recorder


def _wav(tmp_path: Path) -> Path:
    return write_sine_wav(tmp_path / "song.wav", seconds=DURATION, channels=1)


class TestOpen:
    def test_open_returns_the_document_and_marks_the_session_open(self, tmp_path: Path) -> None:
        session, _player, _clock, _recorder = _session(tmp_path)

        assert session.is_open is True
        assert session.path == _wav(tmp_path).resolve()
        assert session.document is not None
        assert len(session.document.chords) == 4
        assert session.steps == ()

    def test_open_loads_the_file_into_the_player(self, tmp_path: Path) -> None:
        _, player, _, _ = _session(tmp_path)
        assert player.loaded == [_wav(tmp_path).resolve()]

    def test_open_forwards_the_engine_overrides(self, tmp_path: Path) -> None:
        clock = FakeClock()
        recorder = _Recorder()
        session = SongSession(player=FakePlayer(clock=clock), analyze=recorder)
        session.open(_wav(tmp_path), engines={"chords": "chroma-baseline"}, input_hash=False)

        assert recorder.calls == [
            {
                "path": _wav(tmp_path).resolve(),
                "engines": {"chords": "chroma-baseline"},
                "input_hash": False,
            }
        ]

    def test_opening_again_replaces_the_previous_song(self, tmp_path: Path) -> None:
        session, player, _clock, recorder = _session(tmp_path)
        second = write_sine_wav(tmp_path / "second.wav", seconds=1.0, channels=1)
        session.open(second)

        assert player.loaded == [_wav(tmp_path).resolve(), second.resolve()]
        assert len(recorder.calls) == 2
        assert session.path == second.resolve()

    def test_a_missing_file_is_reported_and_leaves_the_session_closed(self, tmp_path: Path) -> None:
        session = SongSession(player=FakePlayer(), analyze=_Recorder())
        with pytest.raises(AudioFileNotFoundError):
            session.open(tmp_path / "absent.wav")
        assert session.is_open is False

    def test_a_failing_analysis_closes_the_player(self, tmp_path: Path) -> None:
        player = FakePlayer()

        def _broken(path: str | Path, **options: Any) -> AnalysisOutcome:
            raise DependencyError("no engine could run", hint="pip install numpy librosa")

        session = SongSession(player=player, analyze=_broken)
        with pytest.raises(DependencyError):
            session.open(_wav(tmp_path))

        assert session.is_open is False
        assert player.closed is True

    def test_close_forgets_the_song_and_closes_the_player(self, tmp_path: Path) -> None:
        session, player, _clock, _recorder = _session(tmp_path)
        session.close()

        assert session.is_open is False
        assert session.document is None
        assert session.steps == ()
        assert session.chord_at(0.5) is None
        assert player.closed is True

    def test_a_snapshot_without_a_song_is_an_input_error(self) -> None:
        with pytest.raises(InputError, match="No song"):
            SongSession(player=FakePlayer()).snapshot()

    def test_the_session_creates_a_player_lazily(self, tmp_path: Path) -> None:
        session = SongSession(analyze=_Recorder())
        session.open(_wav(tmp_path))
        assert session.player is not None


class TestChordLookup:
    """``chord_at`` is the synchronization contract; its edges are pinned here."""

    def test_the_first_chord_covers_the_start(self, tmp_path: Path) -> None:
        session, _player, _clock, _recorder = _session(tmp_path)
        assert session.chord_at(0.0) is not None
        assert session.chord_at(0.0).label == "C"

    def test_each_event_is_returned_over_its_interval(self, tmp_path: Path) -> None:
        session, _player, _clock, _recorder = _session(tmp_path)
        assert [session.chord_at(t).label for t in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5)] == [
            "C",
            "C",
            "G",
            "G",
            "N",
            "N",
            "?",
            "?",
        ]

    def test_a_boundary_belongs_to_the_next_event(self, tmp_path: Path) -> None:
        session, _player, _clock, _recorder = _session(tmp_path)
        assert session.chord_at(0.999999).label == "C"
        assert session.chord_at(1.0).label == "G"

    def test_the_end_of_the_last_event_has_no_chord(self, tmp_path: Path) -> None:
        session, _player, _clock, _recorder = _session(tmp_path)
        assert session.chord_at(3.999999).label == "?"
        assert session.chord_at(4.0) is None
        assert session.chord_at(100.0) is None

    def test_before_the_first_event_has_no_chord(self, tmp_path: Path) -> None:
        recorder = _Recorder([ChordEvent(start=1.0, end=2.0, root="C")])
        session = SongSession(player=FakePlayer(), analyze=recorder)
        session.open(_wav(tmp_path))
        assert session.chord_at(0.0) is None
        assert session.chord_at(1.0).label == "C"

    def test_a_gap_between_events_has_no_chord(self, tmp_path: Path) -> None:
        recorder = _Recorder(
            [
                ChordEvent(start=0.0, end=1.0, root="C"),
                ChordEvent(start=2.0, end=3.0, root="G"),
            ]
        )
        session = SongSession(player=FakePlayer(), analyze=recorder)
        session.open(_wav(tmp_path))
        assert session.chord_at(1.5) is None
        assert session.chord_at(2.0).label == "G"

    def test_an_event_without_an_end_is_open_ended(self, tmp_path: Path) -> None:
        recorder = _Recorder([ChordEvent(start=0.0, end=None, root="C")])
        session = SongSession(player=FakePlayer(), analyze=recorder)
        session.open(_wav(tmp_path))
        assert session.chord_at(0.0).label == "C"
        assert session.chord_at(1000.0).label == "C"

    def test_no_events_means_no_chord(self, tmp_path: Path) -> None:
        recorder = _Recorder([])
        session = SongSession(player=FakePlayer(), analyze=recorder)
        session.open(_wav(tmp_path))
        assert session.chord_at(0.0) is None

    def test_a_negative_position_is_rejected(self, tmp_path: Path) -> None:
        session, _player, _clock, _recorder = _session(tmp_path)
        with pytest.raises(InputError, match="negative"):
            session.chord_at(-0.5)

    def test_silence_is_returned_rather_than_skipped(self, tmp_path: Path) -> None:
        """``N`` (a claim of silence) and ``None`` (no claim) are different."""
        session, _player, _clock, _recorder = _session(tmp_path)
        silence = session.chord_at(2.5)
        assert silence is not None
        assert silence.label == "N"
        assert silence.is_silence is True


class TestSynchronization:
    """The playhead drives the chord, deterministically, via the fake clock."""

    def test_current_chord_follows_the_playhead(self, tmp_path: Path) -> None:
        session, player, _clock, _recorder = _session(tmp_path)
        assert session.position() == 0.0
        assert session.current_chord().label == "C"

        session.play()
        player.advance(1.5)
        assert session.position() == pytest.approx(1.5)
        assert session.current_chord().label == "G"

    def test_the_display_updates_as_playback_advances(self, tmp_path: Path) -> None:
        session, player, _clock, _recorder = _session(tmp_path)
        session.play()

        seen: list[str] = [session.current_chord().label]
        for step, expected in ((1.0, "G"), (1.0, "N"), (1.0, "?")):
            player.advance(step)
            seen.append(session.current_chord().label)
            assert seen[-1] == expected
        assert seen == ["C", "G", "N", "?"]

    def test_pausing_freezes_the_chord(self, tmp_path: Path) -> None:
        session, player, _clock, _recorder = _session(tmp_path)
        session.play()
        player.advance(0.5)
        session.pause()
        player.advance(2.0)

        assert session.state is PlaybackState.PAUSED
        assert session.position() == pytest.approx(0.5)
        assert session.current_chord().label == "C"

    def test_seeking_moves_the_chord(self, tmp_path: Path) -> None:
        session, _player, _clock, _recorder = _session(tmp_path)
        session.seek(3.2)
        assert session.current_chord().label == "?"
        session.seek(1.1)
        assert session.current_chord().label == "G"

    def test_playback_calls_reach_the_player(self, tmp_path: Path) -> None:
        session, player, _clock, _recorder = _session(tmp_path)
        session.play()
        session.pause()
        session.seek(1.0)
        session.stop()
        # open() starts by releasing whatever was open before, hence the close.
        assert player.calls == ["close", "load", "play", "pause", "seek", "stop"]

    def test_a_snapshot_carries_the_timeline(self, tmp_path: Path) -> None:
        session, player, _clock, _recorder = _session(tmp_path)
        session.play()
        player.advance(1.25)

        snapshot = session.snapshot()
        assert isinstance(snapshot, SessionSnapshot)
        assert snapshot.path == _wav(tmp_path).resolve()
        assert snapshot.duration == pytest.approx(DURATION, abs=1e-3)
        assert snapshot.position == pytest.approx(1.25)
        assert snapshot.state is PlaybackState.PLAYING
        assert snapshot.chord is not None
        assert snapshot.chord.label == "G"
