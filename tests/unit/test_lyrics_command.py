"""``songlab lyrics`` (roadmap Phase E): the transcription command.

The command owns argument validation, engine selection and presentation, so
that is what these tests pin: the flags reach ``LyricsOptions`` (including the
window length, which travels in ``extra``), the report shows the timestamps a
user asked for, and a machine without the optional lyrics stack gets an honest
dependency error instead of a traceback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from song_chord_lyrics_analyzer.cli.commands import lyrics as command
from song_chord_lyrics_analyzer.cli.main import build_parser, main
from song_chord_lyrics_analyzer.engines import EngineKind
from song_chord_lyrics_analyzer.engines.base import LyricsOptions
from song_chord_lyrics_analyzer.models.analysis import EngineInfo, EngineResult
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricWord
from song_chord_lyrics_analyzer.utils.errors import (
    EXIT_DEPENDENCY_ERROR,
    DependencyError,
    EngineNotFoundError,
    InputError,
)


class FakeLyricsEngine:
    """A registered-engine stand-in that records what it was asked to do."""

    name = "fake-lyrics"
    kind = EngineKind.LYRICS

    def __init__(self, *, available: bool = True) -> None:
        self._available = available
        self.calls: list[tuple[Path, LyricsOptions]] = []

    def is_available(self) -> bool:
        return self._available

    def engine_info(self) -> EngineInfo:
        return EngineInfo(name=self.name, kind=self.kind.value, version="9.9.9")

    def transcribe(self, audio_path: Path, options: LyricsOptions) -> EngineResult:
        self.calls.append((Path(audio_path), options))
        return _result()


def _result() -> EngineResult:
    return EngineResult(
        engine="fake-lyrics",
        kind="lyrics",
        engine_version="9.9.9",
        audio_path=Path("song.wav"),
        lyrics=[
            LyricSegment(
                text="Hello world",
                start=0.0,
                end=20.0,
                words=[
                    LyricWord(text="Hello", start=1.0, end=1.5, source="fake-lyrics"),
                    LyricWord(text="world", start=1.5, source="fake-lyrics"),
                ],
                source="fake-lyrics",
            )
        ],
        processing_time_seconds=5.0,
        metadata={
            "performance": {"audio_seconds": 25.0, "peak_rss_bytes": 2048},
            "model": "nemo-parakeet-tdt-0.6b-v3",
            "quantization": "int8",
            "windows": 2,
            "windows_with_text": 1,
        },
        warnings=["1 of 2 windows produced no text; they are omitted."],
    )


class TestArguments:
    def test_the_defaults_are_the_measured_ones(self) -> None:
        args = build_parser().parse_args(["lyrics", "song.wav"])

        assert args.command == "lyrics"
        assert args.audio == Path("song.wav")
        assert args.engine is None
        assert args.chunk_seconds == 20.0
        assert args.overlap_seconds == 0.0
        assert args.start is None
        assert args.end is None
        assert args.language is None
        assert args.no_words is False
        assert args.json is False

    def test_the_flags_are_parsed(self) -> None:
        args = build_parser().parse_args(
            [
                "lyrics",
                "song.flac",
                "--engine",
                "parakeet-onnx",
                "--chunk-seconds",
                "8",
                "--overlap-seconds",
                "1.5",
                "--start",
                "2",
                "--end",
                "42",
                "--language",
                "es",
                "--no-words",
                "--json",
            ]
        )

        assert args.engine == "parakeet-onnx"
        assert args.chunk_seconds == 8.0
        assert args.overlap_seconds == 1.5
        assert args.start == 2.0
        assert args.end == 42.0
        assert args.language == "es"
        assert args.no_words is True
        assert args.json is True

    def test_the_command_is_listed(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(["--help"])

        assert exit_info.value.code == 0
        assert "lyrics" in capsys.readouterr().out

    def test_its_own_help_lists_the_window_flags(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(["lyrics", "--help"])

        assert exit_info.value.code == 0
        out = capsys.readouterr().out
        assert "--chunk-seconds" in out
        assert "--no-words" in out


class TestOptions:
    def _options(self, *argv: str) -> LyricsOptions:
        args = build_parser().parse_args(["lyrics", "song.wav", *argv])
        return command._options(args)

    def test_the_window_length_travels_in_extra(self) -> None:
        options = self._options("--chunk-seconds", "8", "--overlap-seconds", "2")

        assert options.extra == {"chunk_seconds": 8.0, "overlap_seconds": 2.0}

    def test_word_timestamps_follow_the_flag(self) -> None:
        assert self._options().word_timestamps is True
        assert self._options("--no-words").word_timestamps is False

    def test_the_language_and_range_are_passed_through(self) -> None:
        options = self._options("--language", "es", "--start", "1", "--end", "3")

        assert options.language == "es"
        assert options.start == 1.0
        assert options.end == 3.0

    def test_a_negative_start_is_refused(self) -> None:
        with pytest.raises(InputError, match="--start must not be negative"):
            self._options("--start", "-1")

    def test_a_negative_end_is_refused(self) -> None:
        with pytest.raises(InputError, match="--end must not be negative"):
            self._options("--end", "-1")

    def test_an_inverted_range_is_refused(self) -> None:
        with pytest.raises(InputError, match="--end must be greater than --start"):
            self._options("--start", "10", "--end", "5")

    def test_a_non_positive_window_is_refused(self) -> None:
        with pytest.raises(InputError, match="--chunk-seconds must be positive"):
            self._options("--chunk-seconds", "0")

    def test_a_negative_overlap_is_refused(self) -> None:
        with pytest.raises(InputError, match="--overlap-seconds must not be negative"):
            self._options("--overlap-seconds", "-1")

    def test_an_overlap_as_long_as_the_window_is_refused(self) -> None:
        with pytest.raises(InputError, match="must be smaller than --chunk-seconds"):
            self._options("--chunk-seconds", "10", "--overlap-seconds", "10")


class TestResolveEngine:
    def test_the_registered_parakeet_engine_is_the_default(self) -> None:
        engine = command.resolve_engine(None)

        assert engine.name == "parakeet-onnx"
        assert engine.kind is EngineKind.LYRICS

    def test_the_engine_can_be_named_explicitly(self) -> None:
        assert command.resolve_engine("parakeet-onnx").name == "parakeet-onnx"

    def test_an_unknown_name_is_an_engine_not_found(self) -> None:
        with pytest.raises(EngineNotFoundError):
            command.resolve_engine("does-not-exist")


class TestFormatReport:
    def test_the_report_shows_the_timestamps_a_user_asked_for(self) -> None:
        report = command.format_report(_result())

        assert "Lyrics" in report
        assert "File:     song.wav" in report
        assert "Engine:   fake-lyrics 9.9.9" in report
        assert "Model:    nemo-parakeet-tdt-0.6b-v3 (int8)" in report
        assert "Windows:  2, 1 with text" in report
        assert "Segments: 1" in report
        assert "Words:    2" in report
        assert "[00:00:00.000 - 00:00:20.000] Hello world" in report
        assert "00:00:01.000 00:00:01.500  Hello" in report
        assert "00:00:01.500 --:--  world" in report

    def test_the_run_cost_and_its_warnings_are_shown(self) -> None:
        report = command.format_report(_result())

        assert "Real-time factor" in report
        assert "Peak RSS" in report
        assert "1 of 2 windows produced no text" in report

    def test_an_empty_transcript_says_so(self) -> None:
        report = command.format_report(EngineResult(engine="fake-lyrics", kind="lyrics"))

        assert "No text was transcribed from this file." in report
        assert "Segments: 0" in report


class TestRun:
    def _patch(self, monkeypatch: pytest.MonkeyPatch, engine: FakeLyricsEngine) -> None:
        monkeypatch.setattr(command, "resolve_engine", lambda name: engine)

    def test_it_transcribes_through_the_registered_engine(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        engine = FakeLyricsEngine()
        self._patch(monkeypatch, engine)

        assert main(["lyrics", "song.wav", "--chunk-seconds", "8"]) == 0

        path, options = engine.calls[0]
        assert path == Path("song.wav")
        assert options.extra["chunk_seconds"] == 8.0
        assert "Hello world" in capsys.readouterr().out

    def test_json_prints_the_canonical_result(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._patch(monkeypatch, FakeLyricsEngine())

        assert main(["lyrics", "song.wav", "--json"]) == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload["engine"] == "fake-lyrics"
        assert payload["lyrics"][0]["text"] == "Hello world"
        assert payload["lyrics"][0]["words"][0]["start"] == 1.0

    def test_an_unavailable_engine_is_a_dependency_error(self, monkeypatch) -> None:
        self._patch(monkeypatch, FakeLyricsEngine(available=False))
        args = build_parser().parse_args(["lyrics", "song.wav"])

        with pytest.raises(DependencyError, match="fake-lyrics") as excinfo:
            command.run(args)

        assert "song-chord-lyrics-analyzer[lyrics]" in (excinfo.value.hint or "")

    def test_the_missing_stack_is_reported_instead_of_leaking_a_traceback(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def exploding(name: str | None) -> Any:
            raise DependencyError(
                "Engine 'parakeet-onnx' is not available in this environment.",
                hint="Install the optional lyrics stack.",
            )

        monkeypatch.setattr(command, "resolve_engine", exploding)

        assert main(["lyrics", "song.wav"]) == EXIT_DEPENDENCY_ERROR

        captured = capsys.readouterr()
        assert "not available" in captured.err
        assert "Traceback" not in captured.err
