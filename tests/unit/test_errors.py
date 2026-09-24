"""Unit tests for the error hierarchy (roadmap section 63)."""

from __future__ import annotations

from pathlib import Path

import pytest

from song_chord_lyrics_analyzer.utils.errors import (
    AudioFileNotFoundError,
    DependencyError,
    EngineNotFoundError,
    InputError,
    SongLabError,
    UnsupportedAudioError,
)


class TestMessages:
    def test_str_includes_the_hint(self) -> None:
        error = DependencyError("FFprobe was not found.", hint="Install FFmpeg.")
        assert str(error) == "FFprobe was not found.\n\nInstall FFmpeg."

    def test_str_without_hint(self) -> None:
        assert str(SongLabError("something failed")) == "something failed"

    def test_all_errors_expose_a_message(self) -> None:
        errors = [
            AudioFileNotFoundError(Path("/x/song.mp3")),
            UnsupportedAudioError(Path("/x/song.mp3"), reason="not audio"),
            EngineNotFoundError("chords", "madmom", ["baseline"]),
        ]
        for error in errors:
            assert isinstance(error, SongLabError)
            assert error.message
            assert str(error)


class TestExitCodes:
    def test_input_errors_exit_with_two(self) -> None:
        assert AudioFileNotFoundError(Path("/x/a.mp3")).exit_code == 2
        assert InputError("bad argument").exit_code == 2
        assert UnsupportedAudioError(Path("/x/a.mp3")).exit_code == 2

    def test_dependency_errors_exit_with_three(self) -> None:
        assert DependencyError("missing tool").exit_code == 3

    def test_engine_errors_list_the_alternatives(self) -> None:
        error = EngineNotFoundError("chords", "madmom", ["baseline", "chordino"])
        assert "madmom" in error.message
        assert "baseline, chordino" in (error.hint or "")

    def test_engine_error_without_alternatives(self) -> None:
        error = EngineNotFoundError("chords", "madmom", [])
        assert "(none registered)" in (error.hint or "")

    def test_unsupported_audio_error_mentions_the_reason(self) -> None:
        error = UnsupportedAudioError(Path("/x/a.mp3"), reason="no audio stream")
        assert "no audio stream" in error.message


class TestInheritance:
    @pytest.mark.parametrize(
        "error_class",
        [AudioFileNotFoundError, UnsupportedAudioError, DependencyError, InputError],
    )
    def test_specific_errors_are_catchable_as_songlab_errors(self, error_class: type) -> None:
        assert issubclass(error_class, SongLabError)
