"""Cross-platform discovery of external executables (roadmap section 4 and 16).

External tools such as FFmpeg, Sonic Annotator and Chordino are optional. Their
absence must never produce a traceback; it must produce a clear message telling
the user how to install the tool.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from song_chord_lyrics_analyzer.utils.logging import get_logger

__all__ = [
    "candidate_directories",
    "find_executable",
    "read_process_output",
    "run_safely",
    "version_of",
]

_logger = get_logger("utils.executables")

_VERSION_TIMEOUT_SECONDS = 10.0


def candidate_directories() -> list[Path]:
    """Return extra directories that commonly hold external tools.

    ``shutil.which`` already covers ``PATH``; these candidates help on macOS
    (Homebrew) and Windows (winget / Chocolatey / Scoop) where a GUI process
    may have an incomplete environment.
    """
    directories: list[Path] = []
    home = Path.home()
    directories.extend([home / ".local" / "bin", home / "bin"])

    if os.name == "nt":
        # Windows environment variable lookup is case-insensitive, so the
        # canonical upper-case names are used everywhere.
        local_appdata = os.environ.get("LOCALAPPDATA")
        program_files = os.environ.get("PROGRAMFILES")
        program_data = os.environ.get("PROGRAMDATA")
        if local_appdata:
            local = Path(local_appdata)
            directories.extend(
                [
                    local / "Microsoft" / "WinGet" / "Links",
                    local / "Programs",
                ]
            )
        if program_files:
            pf = Path(program_files)
            directories.extend([pf / "ffmpeg" / "bin", pf / "FFmpeg" / "bin"])
        if program_data:
            directories.append(Path(program_data) / "chocolatey" / "bin")
        directories.append(home / "scoop" / "shims")
    elif sys.platform == "darwin":  # pragma: no cover - macOS only
        directories.extend(
            [
                Path("/opt/homebrew/bin"),
                Path("/usr/local/bin"),
                Path("/opt/local/bin"),
            ]
        )
    else:
        directories.extend(
            [
                Path("/usr/local/bin"),
                Path("/usr/bin"),
                Path("/bin"),
                Path("/snap/bin"),
            ]
        )

    return [directory for directory in directories if directory.is_dir()]


def _with_executable_suffix(name: str) -> list[str]:
    if os.name == "nt" and not name.lower().endswith((".exe", ".cmd", ".bat")):
        return [name, f"{name}.exe"]
    return [name]


def find_executable(
    name: str,
    *,
    env_var: str | None = None,
    extra_names: tuple[str, ...] = (),
) -> Path | None:
    """Locate an executable without relying on a fully populated environment.

    Args:
        name: Executable name (for example ``"ffmpeg"``).
        env_var: Optional environment variable holding an explicit path. When
            set, it takes precedence over every other strategy.
        extra_names: Alternative names to try (for example ``"ffprobe64"``).

    Returns:
        The resolved path to an executable file, or ``None`` when not found.
    """
    if env_var:
        override = os.environ.get(env_var)
        if override:
            candidate = Path(override).expanduser()
            if candidate.is_dir():
                candidate = candidate / name
            if candidate.is_file():
                return candidate
            _logger.debug("%s set to %s but no such file exists", env_var, override)

    for candidate_name in (name, *extra_names):
        for lookup in _with_executable_suffix(candidate_name):
            found = shutil.which(lookup)
            if found:
                return Path(found)

    for directory in candidate_directories():
        for lookup in _with_executable_suffix(name):
            candidate = directory / lookup
            if candidate.is_file():
                return candidate
    return None


def run_safely(
    args: list[str | Path],
    *,
    timeout: float = _VERSION_TIMEOUT_SECONDS,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run an external command without a shell.

    Audio filesystem paths and engine output are untrusted input, so
    ``shell=True`` is never used and every argument is passed as a list element
    (roadmap section 17).
    """
    command = [str(part) for part in args]
    _logger.debug("running: %s", " ".join(command))
    # Arguments are always passed as a list and shell=False is explicit, so no
    # untrusted path can ever be interpreted by a shell (roadmap section 17).
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
        shell=False,
    )


def read_process_output(result: subprocess.CompletedProcess[str]) -> str:
    """Return combined stdout/stderr of a completed process, stripped."""
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    return output.strip()


def version_of(executable: Path, *, args: tuple[str, ...] = ("-version",)) -> str | None:
    """Return the first line of a tool's version output, or ``None``."""
    try:
        result = run_safely([executable, *args])
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - env specific
        _logger.debug("could not read version of %s: %s", executable, exc)
        return None
    for line in read_process_output(result).splitlines():
        line = line.strip()
        if line:
            return line
    return None


@lru_cache(maxsize=1)
def platform_summary() -> str:
    """Return a short human-readable platform description."""
    return f"{platform.system()} {platform.release()} ({platform.machine()})"
