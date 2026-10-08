"""``songlab gui`` (roadmap Phase D): the command that opens the window.

The command owns almost nothing - a file name, an engine override and a
dependency check - so the tests pin exactly that: the arguments, the help text
that must work on a Qt-free installation, and the honest error when the optional
GUI stack is missing (the same ``DependencyError`` the rest of the project raises
for an unavailable engine or decoder).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from song_chord_lyrics_analyzer.cli.commands import gui
from song_chord_lyrics_analyzer.cli.main import build_parser, main
from song_chord_lyrics_analyzer.utils.errors import EXIT_DEPENDENCY_ERROR, DependencyError

HAS_QT = importlib.util.find_spec("PyQt6") is not None


class TestArguments:
    def test_the_file_is_optional_because_the_window_can_open_one_too(self) -> None:
        args = build_parser().parse_args(["gui"])

        assert args.command == "gui"
        assert args.audio is None
        assert args.engine is None
        assert args.no_hash is False

    def test_a_file_and_engine_overrides_are_accepted(self) -> None:
        args = build_parser().parse_args(
            ["gui", "song.wav", "--engine", "chords=chroma-baseline", "--no-hash"]
        )

        assert args.audio == Path("song.wav")
        assert args.engine == ["chords=chroma-baseline"]
        assert args.no_hash is True

    def test_the_command_is_in_the_command_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(["--help"])

        assert exit_info.value.code == 0
        assert "gui" in capsys.readouterr().out

    def test_help_works_without_qt(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(["gui", "--help"])

        assert exit_info.value.code == 0
        assert "--no-hash" in capsys.readouterr().out


class TestDispatching:
    def test_the_command_hands_the_arguments_to_the_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, object] = {}

        def fake_run(audio: object, *, engines: object, input_hash: object) -> int:
            seen.update(audio=audio, engines=engines, input_hash=input_hash)
            return 0

        monkeypatch.setattr("song_chord_lyrics_analyzer.gui.run", fake_run)
        args = build_parser().parse_args(["gui", "song.wav", "--engine", "chords=chroma-baseline"])

        assert gui.run(args) == 0
        assert seen == {
            "audio": Path("song.wav"),
            "engines": {"chords": "chroma-baseline"},
            "input_hash": True,
        }

    def test_a_missing_gui_stack_is_reported_instead_of_leaking_a_traceback(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def exploding(*args: object, **kwargs: object) -> int:
            raise DependencyError(
                "The desktop window needs PyQt6, which is not installed.",
                hint="Install the optional GUI stack.",
            )

        monkeypatch.setattr("song_chord_lyrics_analyzer.gui.run", exploding)

        code = main(["gui"])
        printed = capsys.readouterr()

        assert code == EXIT_DEPENDENCY_ERROR
        assert "PyQt6" in printed.err
        assert "Install the optional GUI stack." in printed.err


@pytest.mark.skipif(HAS_QT, reason="PyQt6 is installed here, so there is nothing to report")
def test_without_qt_opening_a_window_explains_how_to_install_it() -> None:
    from song_chord_lyrics_analyzer.gui import require_qt

    with pytest.raises(DependencyError, match="PyQt6") as error:
        require_qt()

    assert "gui" in (error.value.hint or "")
