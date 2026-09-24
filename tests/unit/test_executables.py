"""Unit tests for cross-platform executable discovery (roadmap sections 4, 17 and 16)."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from song_chord_lyrics_analyzer.utils.executables import (
    candidate_directories,
    find_executable,
    platform_summary,
    read_process_output,
    run_safely,
    version_of,
)


class TestFindExecutable:
    def test_explicit_env_override_wins(self, monkeypatch, tmp_path: Path) -> None:
        fake = tmp_path / "my-tool"
        fake.write_text("#!/bin/sh\nexit 0\n")
        fake.chmod(0o755)
        monkeypatch.setenv("MY_TOOL_PATH", str(fake))
        found = find_executable("anything", env_var="MY_TOOL_PATH")
        assert found == fake

    def test_env_override_may_point_at_a_directory(self, monkeypatch, tmp_path: Path) -> None:
        tool = tmp_path / "bin" / "my-tool"
        tool.parent.mkdir()
        tool.write_text("#!/bin/sh\nexit 0\n")
        monkeypatch.setenv("MY_TOOL_DIR", str(tool.parent))
        assert find_executable("my-tool", env_var="MY_TOOL_DIR") == tool

    def test_broken_env_override_falls_through(self, monkeypatch) -> None:
        monkeypatch.setenv("MY_TOOL_PATH", "/definitely/not/here")
        assert find_executable("songlab-definitely-missing-tool", env_var="MY_TOOL_PATH") is None

    def test_unknown_tool_returns_none(self) -> None:
        assert find_executable("songlab-definitely-missing-tool") is None

    def test_current_interpreter_is_discoverable(self) -> None:
        name = Path(sys.executable).name
        if shutil.which(name) is None:
            pytest.skip(f"{name} is not on PATH in this environment")
        assert find_executable(name) is not None

    def test_candidate_directories_exist(self) -> None:
        for directory in candidate_directories():
            assert directory.is_dir()


class TestRunSafely:
    def test_arguments_are_not_interpreted_by_a_shell(self) -> None:
        result = run_safely(
            [sys.executable, "-c", "import sys; print(sys.argv[1])", "a;b && rm -rf /"]
        )
        assert result.stdout.strip() == "a;b && rm -rf /"

    def test_missing_executable_raises_oserror(self) -> None:
        with pytest.raises(OSError):
            run_safely(["songlab-definitely-missing-tool"])

    def test_paths_with_spaces_are_handled(self, tmp_path: Path) -> None:
        spaced = tmp_path / "a directory"
        spaced.mkdir()
        script = spaced / "script.py"
        script.write_text("print('spaced ok')\n")
        assert run_safely([sys.executable, script]).stdout.strip() == "spaced ok"

    def test_read_process_output_combines_streams(self) -> None:
        script = "import sys; print('out'); print('err', file=sys.stderr)"
        output = read_process_output(run_safely([sys.executable, "-c", script]))
        assert "out" in output
        assert "err" in output


class TestVersion:
    def test_version_of_interpreter(self) -> None:
        version = version_of(Path(sys.executable), args=("--version",))
        assert version is not None
        assert version.startswith("Python")

    def test_platform_summary_mentions_machine(self) -> None:
        summary = platform_summary()
        assert "(" in summary and ")" in summary
