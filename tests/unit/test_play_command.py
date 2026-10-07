"""``songlab play`` (roadmap Phase C): the first product command.

The command is thin, so the tests pin what it owns: the flag validation, the
header, the one-frame ``--at`` mode and the fact that it drives the display from
a real :class:`SongSession` (here with a fake player, so no device is needed).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from fixtures.audio import write_sine_wav
from fixtures.fake_player import FakePlayer
from song_chord_lyrics_analyzer import __version__
from song_chord_lyrics_analyzer.analysis import AnalysisOutcome
from song_chord_lyrics_analyzer.app import SongSession
from song_chord_lyrics_analyzer.cli.main import main
from song_chord_lyrics_analyzer.models.analysis import (
    AnalysisResult,
    AnalysisRun,
    Provenance,
    RunStatus,
)
from song_chord_lyrics_analyzer.models.audio import AudioDocument
from song_chord_lyrics_analyzer.models.music import ChordEvent, ChordQuality
from song_chord_lyrics_analyzer.utils.errors import DependencyError

DURATION = 4.0

#: C, G, explicit silence, then an unclaimed chord - one event per second.
EVENTS: list[ChordEvent] = [
    ChordEvent(start=0.0, end=1.0, root="C", quality=ChordQuality.MAJOR, source="fake"),
    ChordEvent(start=1.0, end=2.0, root="G", quality=ChordQuality.MAJOR, source="fake"),
    ChordEvent.silence(2.0, 3.0, source="fake"),
    ChordEvent(start=3.0, end=4.0, source="fake"),
]


class _Recorder:
    """An ``analyze`` stand-in that records how the command called it."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, path: str | Path, **options: Any) -> AnalysisOutcome:
        self.calls.append({"path": Path(path), **options})
        document = AnalysisResult(
            provenance=Provenance(application_version=__version__, input_path=str(path)),
            audio=AudioDocument(path=Path(path), duration=DURATION),
            chords=list(EVENTS),
            run=AnalysisRun(status=RunStatus.SUCCEEDED, started_at=datetime.now(timezone.utc)),
        )
        return AnalysisOutcome(result=document, steps=())


def _patch_session(monkeypatch, player: FakePlayer, recorder: _Recorder) -> SongSession:
    """Make ``songlab play`` build the faked session instead of a real one."""
    session = SongSession(player=player, analyze=recorder)
    monkeypatch.setattr(
        "song_chord_lyrics_analyzer.cli.commands.play.SongSession",
        lambda: session,
    )
    return session


def _wav(tmp_path: Path) -> Path:
    return write_sine_wav(tmp_path / "song.wav", seconds=DURATION, channels=1)


class TestAtMode:
    def test_prints_the_chord_at_one_position_without_playing(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        player = FakePlayer()
        _patch_session(monkeypatch, player, _Recorder())

        assert main(["play", str(_wav(tmp_path)), "--at", "1.2"]) == 0

        out = capsys.readouterr().out
        assert "00:00:01.200 / 00:00:04.000" in out
        assert "G" in out
        assert "playing" not in out and "stopped" in out
        assert "play" not in player.calls

    def test_a_position_past_the_end_shows_no_chord(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        _patch_session(monkeypatch, FakePlayer(), _Recorder())

        assert main(["play", str(_wav(tmp_path)), "--at", "99"]) == 0

        out = capsys.readouterr().out
        assert "00:00:04.000 / 00:00:04.000" in out
        assert "--" in out

    def test_silence_is_shown_as_n(self, tmp_path: Path, capsys, monkeypatch) -> None:
        _patch_session(monkeypatch, FakePlayer(), _Recorder())

        assert main(["play", str(_wav(tmp_path)), "--at", "2.5"]) == 0
        assert "N" in capsys.readouterr().out


class TestPlaybackMode:
    def test_prints_a_header_and_one_line_per_frame(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        player = FakePlayer()
        recorder = _Recorder()
        _patch_session(monkeypatch, player, recorder)

        assert (
            main(
                [
                    "play",
                    str(_wav(tmp_path)),
                    "--frames",
                    "3",
                    "--interval",
                    "0.001",
                    "--no-hash",
                ]
            )
            == 0
        )

        out = capsys.readouterr().out
        assert "Playing" in out
        assert f"File:     {_wav(tmp_path).resolve()}" in out
        assert "Duration: 00:00:04.000" in out
        assert "Chords:   4 events from fake" in out
        assert sum(1 for line in out.splitlines() if line.startswith("00:0")) == 3
        assert "play" in player.calls
        assert recorder.calls[0]["input_hash"] is False

    def test_the_engine_overrides_reach_the_analysis(self, tmp_path: Path, monkeypatch) -> None:
        recorder = _Recorder()
        _patch_session(monkeypatch, FakePlayer(), recorder)

        assert (
            main(
                [
                    "play",
                    str(_wav(tmp_path)),
                    "--engine",
                    "chords=chroma-baseline",
                    "--frames",
                    "1",
                    "--interval",
                    "0.001",
                ]
            )
            == 0
        )
        assert recorder.calls[0]["engines"] == {"chords": "chroma-baseline"}

    def test_no_playback_backend_is_a_dependency_error(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        session = _patch_session(monkeypatch, FakePlayer(), _Recorder())

        def _no_device() -> None:
            raise DependencyError(
                "Audio playback needs sounddevice and numpy, which are not available.",
                hint="pip install sounddevice numpy",
            )

        monkeypatch.setattr(session, "play", _no_device)

        assert main(["play", str(_wav(tmp_path))]) == 3
        err = capsys.readouterr().err
        assert "sounddevice" in err
        assert "pip install sounddevice numpy" in err

    def test_the_session_is_closed_even_when_playback_fails(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        player = FakePlayer()
        session = _patch_session(monkeypatch, player, _Recorder())
        monkeypatch.setattr(
            session,
            "play",
            lambda: (_ for _ in ()).throw(DependencyError("no device")),
        )

        assert main(["play", str(_wav(tmp_path))]) == 3
        assert player.closed is True


class TestValidation:
    def test_a_missing_file_is_an_input_error(self, tmp_path: Path, capsys, monkeypatch) -> None:
        _patch_session(monkeypatch, FakePlayer(), _Recorder())

        assert main(["play", str(tmp_path / "nope.wav")]) == 2
        assert "not found" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "flags",
        [
            ["--at", "-1"],
            ["--interval", "0"],
            ["--frames", "0"],
        ],
    )
    def test_impossible_flags_are_rejected(
        self, tmp_path: Path, capsys, monkeypatch, flags: list[str]
    ) -> None:
        _patch_session(monkeypatch, FakePlayer(), _Recorder())

        assert main(["play", str(_wav(tmp_path)), *flags]) == 2
        err = capsys.readouterr().err
        assert flags[0] in err

    def test_an_unknown_layer_is_rejected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        _patch_session(monkeypatch, FakePlayer(), _Recorder())

        assert main(["play", str(_wav(tmp_path)), "--engine", "nope=x"]) == 2
        assert "Unknown analysis layer" in capsys.readouterr().err

    def test_help_documents_the_display_flags(self, capsys) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["play", "--help"])
        assert excinfo.value.code == 0
        out = capsys.readouterr().out
        for flag in ("--at", "--interval", "--frames", "--no-inline"):
            assert flag in out
