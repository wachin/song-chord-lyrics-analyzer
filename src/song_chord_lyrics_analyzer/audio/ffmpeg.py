"""FFmpeg integration (roadmap sections 16 and 17).

FFmpeg is the primary compatibility layer for decoding audio, but it is *not*
assumed to be installed globally. Discovery is explicit, failures are reported
with platform-specific installation instructions, and every invocation passes
its arguments as a list - never through a shell.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from song_chord_lyrics_analyzer.utils.errors import DependencyError, InputError
from song_chord_lyrics_analyzer.utils.executables import (
    find_executable,
    read_process_output,
    run_safely,
)
from song_chord_lyrics_analyzer.utils.logging import get_logger

__all__ = [
    "FFMPEG_ENV_VAR",
    "FFPROBE_ENV_VAR",
    "FfmpegTools",
    "discover_ffmpeg_tools",
    "ffmpeg_install_hint",
    "find_ffmpeg",
    "find_ffprobe",
    "require_ffprobe",
    "tool_version",
]

_logger = get_logger("audio.ffmpeg")

FFMPEG_ENV_VAR = "SONGLAB_FFMPEG"
FFPROBE_ENV_VAR = "SONGLAB_FFPROBE"

_PROBE_TIMEOUT_SECONDS = 30.0


def ffmpeg_install_hint() -> str:
    """Return platform-specific installation instructions for FFmpeg."""
    if os.name == "nt":
        return (
            "Install FFmpeg on Windows with one of:\n"
            "  winget install --id Gyan.FFmpeg\n"
            "  choco install ffmpeg\n"
            "  scoop install ffmpeg\n"
            "or download a build from https://ffmpeg.org/download.html and add "
            "its 'bin' directory to PATH.\n"
            f"Alternatively set {FFMPEG_ENV_VAR} / {FFPROBE_ENV_VAR} to the full "
            "executable paths."
        )
    if sys.platform == "darwin":
        return (
            "Install FFmpeg on macOS with:\n"
            "  brew install ffmpeg\n"
            f"Alternatively set {FFMPEG_ENV_VAR} / {FFPROBE_ENV_VAR} to the full "
            "executable paths."
        )
    return (
        "Install FFmpeg on Linux with your package manager, for example:\n"
        "  sudo apt install ffmpeg\n"
        "  sudo dnf install ffmpeg\n"
        "  sudo pacman -S ffmpeg\n"
        f"Alternatively set {FFMPEG_ENV_VAR} / {FFPROBE_ENV_VAR} to the full "
        "executable paths."
    )


def find_ffmpeg() -> Path | None:
    """Locate the ``ffmpeg`` executable, or return ``None``."""
    return find_executable("ffmpeg", env_var=FFMPEG_ENV_VAR, extra_names=("ffmpeg",))


def find_ffprobe() -> Path | None:
    """Locate the ``ffprobe`` executable, or return ``None``."""
    return find_executable(
        "ffprobe",
        env_var=FFPROBE_ENV_VAR,
        extra_names=("ffprobe", "ffprobe64"),
    )


@dataclass(frozen=True)
class FfmpegTools:
    """Result of discovering the FFmpeg toolchain."""

    ffmpeg: Path | None = None
    ffprobe: Path | None = None

    @property
    def is_complete(self) -> bool:
        """Whether both binaries were found."""
        return self.ffmpeg is not None and self.ffprobe is not None


def discover_ffmpeg_tools() -> FfmpegTools:
    """Discover FFmpeg binaries without raising when they are absent."""
    tools = FfmpegTools(ffmpeg=find_ffmpeg(), ffprobe=find_ffprobe())
    _logger.debug("ffmpeg=%s ffprobe=%s", tools.ffmpeg, tools.ffprobe)
    return tools


def require_ffprobe() -> Path:
    """Return the ``ffprobe`` path or raise a helpful dependency error."""
    ffprobe = find_ffprobe()
    if ffprobe is None:
        raise DependencyError(
            "FFprobe was not found.",
            hint=(
                "FFprobe ships with FFmpeg and is required to inspect audio "
                "files other than WAV.\n\n" + ffmpeg_install_hint()
            ),
        )
    return ffprobe


def tool_version(executable: Path) -> str | None:
    """Return the first line of ``<tool> -version`` output, or ``None``."""
    try:
        result = run_safely([executable, "-version"], timeout=10.0)
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - env specific
        _logger.debug("could not read version of %s: %s", executable, exc)
        return None
    if result.returncode != 0:
        _logger.debug("%s -version exited with %s", executable, result.returncode)
    for line in read_process_output(result).splitlines():
        line = line.strip()
        if line:
            return line
    return None


def run_ffprobe(
    args: list[str | Path], *, timeout: float = _PROBE_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str]:
    """Run ``ffprobe`` with the given arguments, without a shell."""
    ffprobe = require_ffprobe()
    try:
        return run_safely([ffprobe, *args], timeout=timeout)
    except FileNotFoundError as exc:  # pragma: no cover - race with removal
        raise DependencyError(
            "FFprobe disappeared while running.", hint=ffmpeg_install_hint()
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise InputError(
            f"FFprobe timed out after {timeout:.0f}s while reading the audio file.",
            hint="The file may be corrupt or extremely large. Try a shorter excerpt.",
        ) from exc
    except subprocess.SubprocessError as exc:
        raise InputError(f"Could not run FFprobe: {exc}") from exc
