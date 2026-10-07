"""The Phase C display: one line showing the chord under the playhead.

The presenter is pure, so the assertions are exact strings; the refresh loop
runs on the fake clock, so "the chord changes while the song plays" is asserted
without waiting for real playback.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from fixtures.audio import write_sine_wav
from fixtures.clock import FakeClock
from fixtures.fake_player import FakePlayer
from song_chord_lyrics_analyzer import __version__
from song_chord_lyrics_analyzer.analysis import AnalysisOutcome
from song_chord_lyrics_analyzer.app import (
    ConsoleDisplay,
    DisplayFrame,
    SongSession,
    follow,
    frame_from,
    render_frame,
)
from song_chord_lyrics_analyzer.audio.playback import PlaybackState
from song_chord_lyrics_analyzer.models.analysis import (
    AnalysisResult,
    AnalysisRun,
    Provenance,
    RunStatus,
)
from song_chord_lyrics_analyzer.models.audio import AudioDocument
from song_chord_lyrics_analyzer.models.music import ChordEvent, ChordQuality
from song_chord_lyrics_analyzer.utils.errors import InputError

DURATION = 4.0


class _Tracking(ConsoleDisplay):
    """A console display that also records the frames it was asked to draw."""

    def __init__(self, stream: io.StringIO, *, inline: bool) -> None:
        super().__init__(stream, inline=inline)
        self.frames: list[DisplayFrame] = []

    @property
    def seen(self) -> list[str]:
        """The chord text of every frame drawn, in order."""
        return [frame.chord_text for frame in self.frames]

    def write(self, frame: DisplayFrame) -> None:
        self.frames.append(frame)
        super().write(frame)


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
    """An ``analyze`` stand-in that returns fixed chord events."""

    def __init__(self, chords: list[ChordEvent] = EVENTS, *, duration: float = DURATION) -> None:
        self.chords = chords
        self.duration = duration
        self.calls: list[dict[str, Any]] = []

    def __call__(self, path: str | Path, **options: Any) -> AnalysisOutcome:
        self.calls.append({"path": Path(path), **options})
        return _outcome(Path(path), self.chords, duration=self.duration)


def _wav(tmp_path: Path) -> Path:
    return write_sine_wav(tmp_path / "song.wav", seconds=DURATION, channels=1)


def _session(tmp_path: Path) -> tuple[SongSession, FakePlayer, FakeClock]:
    clock = FakeClock()
    player = FakePlayer(clock=clock)
    session = SongSession(player=player, analyze=_Recorder())
    session.open(_wav(tmp_path))
    return session, player, clock


class TestFrameFrom:
    def test_maps_the_snapshot_fields(self, tmp_path: Path) -> None:
        session, player, _clock = _session(tmp_path)
        session.play()
        player.advance(1.25)

        frame = frame_from(session.snapshot())
        assert frame.position == pytest.approx(1.25)
        assert frame.duration == pytest.approx(DURATION, abs=1e-3)
        assert frame.state is PlaybackState.PLAYING
        assert frame.chord is not None
        assert frame.chord.label == "G"

    def test_the_placeholder_means_no_chord_is_claimed(self, tmp_path: Path) -> None:
        session, _player, _clock = _session(tmp_path)
        frame = frame_from(session.snapshot())
        assert frame.chord_text == "C"
        session.seek(DURATION)
        assert frame_from(session.snapshot()).chord_text == "--"

    def test_silence_is_shown_as_n_rather_than_the_placeholder(self, tmp_path: Path) -> None:
        session, _player, _clock = _session(tmp_path)
        session.seek(2.5)
        assert frame_from(session.snapshot()).chord_text == "N"

    def test_an_uncertain_event_is_shown_as_a_question_mark(self, tmp_path: Path) -> None:
        session, _player, _clock = _session(tmp_path)
        session.seek(3.5)
        assert frame_from(session.snapshot()).chord_text == "?"


class TestFrameMeasurements:
    def _frame(self, position: float, duration: float = DURATION) -> DisplayFrame:
        return DisplayFrame(
            position=position, duration=duration, state=PlaybackState.PLAYING, chord=None
        )

    def test_progress_spans_the_track(self) -> None:
        assert self._frame(0.0).progress == 0.0
        assert self._frame(1.0).progress == pytest.approx(0.25)
        assert self._frame(4.0).progress == 1.0

    def test_progress_is_clamped_and_survives_a_missing_duration(self) -> None:
        assert self._frame(10.0).progress == 1.0
        assert self._frame(1.0, duration=0.0).progress == 0.0

    def test_time_text_formats_both_ends(self) -> None:
        assert self._frame(1.2).time_text == "00:00:01.200 / 00:00:04.000"

    def test_only_the_end_of_the_track_is_finished(self) -> None:
        assert self._frame(0.0).is_finished is False
        assert self._frame(3.999).is_finished is False
        assert self._frame(4.0).is_finished is True
        assert self._frame(1.0, duration=0.0).is_finished is False


class TestRenderFrame:
    def _frame(
        self, position: float, state: PlaybackState, chord: ChordEvent | None
    ) -> DisplayFrame:
        return DisplayFrame(position=position, duration=DURATION, state=state, chord=chord)

    def test_renders_one_line_with_position_bar_chord_and_state(self) -> None:
        chord = ChordEvent(start=1.0, end=2.0, root="G", quality=ChordQuality.MAJOR)
        line = render_frame(self._frame(1.2, PlaybackState.PLAYING, chord))
        assert line == "00:00:01.200 / 00:00:04.000  [#######-----------------]  G    playing"

    def test_pads_the_chord_so_the_line_does_not_jitter(self) -> None:
        long = ChordEvent(start=0.0, end=1.0, root="C", quality=ChordQuality.MAJOR7)
        assert render_frame(self._frame(0.0, PlaybackState.STOPPED, long)).endswith("Cmaj7 stopped")

    def test_no_chord_shows_the_placeholder(self) -> None:
        line = render_frame(self._frame(0.0, PlaybackState.STOPPED, None))
        assert "  [------------------------]  --   stopped" in line

    def test_the_bar_is_full_at_the_end(self) -> None:
        line = render_frame(self._frame(DURATION, PlaybackState.STOPPED, None))
        assert f"[{'#' * 24}]" in line

    def test_the_bar_width_is_configurable(self) -> None:
        line = render_frame(self._frame(2.0, PlaybackState.PAUSED, None), width=4)
        assert "[##--]" in line

    def test_a_zero_width_bar_is_rejected(self) -> None:
        with pytest.raises(InputError, match="progress bar"):
            render_frame(self._frame(0.0, PlaybackState.PAUSED, None), width=0)


def _snapshot(session: SongSession, position: float):
    """The snapshot the session would report with the playhead at ``position``."""
    session.seek(position)
    return session.snapshot()


class TestConsoleDisplay:
    def test_writes_one_line_per_frame_when_not_a_terminal(self, tmp_path: Path) -> None:
        session, _player, _clock = _session(tmp_path)
        stream = io.StringIO()
        display = ConsoleDisplay(stream, inline=False)

        first = display.show(_snapshot(session, 0.5))
        second = display.show(_snapshot(session, 1.5))

        assert display.inline is False
        assert first.chord_text == "C"
        assert second.chord_text == "G"
        lines = stream.getvalue().splitlines()
        assert len(lines) == 2
        assert lines[0].endswith("C    stopped")
        assert lines[1].endswith("G    stopped")

    def test_inline_mode_redraws_one_line_and_pads_it(self) -> None:
        stream = io.StringIO()
        display = ConsoleDisplay(stream, inline=True)
        display.write(DisplayFrame(1.0, DURATION, PlaybackState.PLAYING, None))
        display.write(DisplayFrame(2.0, DURATION, PlaybackState.PAUSED, None))
        display.close()

        written = stream.getvalue()
        assert written.startswith("\r")
        assert written.count("\r") == 2
        assert written.endswith("\n")

    def test_closing_without_drawing_writes_nothing(self) -> None:
        stream = io.StringIO()
        ConsoleDisplay(stream, inline=True).close()
        assert stream.getvalue() == ""

    def test_a_stream_without_isatty_defaults_to_one_line_per_frame(self) -> None:
        assert ConsoleDisplay(io.StringIO()).inline is False


class TestFollow:
    def test_draws_a_frame_per_refresh_and_follows_the_chords(self, tmp_path: Path) -> None:
        session, player, _clock = _session(tmp_path)
        display = _Tracking(io.StringIO(), inline=False)

        session.play()
        frames = follow(session, display, interval=0.5, sleep=player.advance, max_frames=5)

        assert frames == 5
        assert display.seen == ["C", "C", "G", "G", "N"]

    def test_a_paused_song_draws_once_and_never_sleeps(self, tmp_path: Path) -> None:
        session, player, _clock = _session(tmp_path)
        session.play()
        player.advance(1.5)
        session.pause()
        sleeps: list[float] = []

        frames = follow(
            session,
            ConsoleDisplay(io.StringIO(), inline=False),
            interval=0.5,
            sleep=sleeps.append,
        )

        assert frames == 1
        assert sleeps == []

    def test_the_last_frame_shows_the_finished_track(self, tmp_path: Path) -> None:
        session, player, _clock = _session(tmp_path)
        session.play()
        assert player.timeline is not None
        player.timeline.mark_finished()
        display = _Tracking(io.StringIO(), inline=False)

        frames = follow(session, display)

        assert frames == 1
        assert display.frames[0].is_finished is True
        assert display.frames[0].state is PlaybackState.STOPPED
        assert display.frames[0].progress == 1.0

    def test_the_display_is_closed_when_following_ends(self, tmp_path: Path) -> None:
        session, _player, _clock = _session(tmp_path)
        stream = io.StringIO()
        follow(session, ConsoleDisplay(stream, inline=True))
        # close() terminated the in-place line so later output starts fresh.
        assert stream.getvalue().endswith("\n")

    def test_a_non_positive_interval_is_rejected(self, tmp_path: Path) -> None:
        session, _player, _clock = _session(tmp_path)
        with pytest.raises(InputError, match="interval"):
            follow(session, ConsoleDisplay(io.StringIO()), interval=0.0)

    def test_max_frames_must_be_at_least_one(self, tmp_path: Path) -> None:
        session, _player, _clock = _session(tmp_path)
        with pytest.raises(InputError, match="max_frames"):
            follow(session, ConsoleDisplay(io.StringIO()), max_frames=0)
