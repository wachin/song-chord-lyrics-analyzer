"""Exception hierarchy for user-facing errors.

The CLI translates these exceptions into short, actionable messages instead of
raw tracebacks (roadmap section 63).
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "AudioFileNotFoundError",
    "ConfigError",
    "DuplicateEngineError",
    "DependencyError",
    "EngineNotFoundError",
    "InputError",
    "SchemaError",
    "SongLabError",
    "UnsupportedAudioError",
]

#: Exit code used when the user supplied something invalid.
EXIT_INPUT_ERROR = 2
#: Exit code used when an external tool or optional dependency is missing.
EXIT_DEPENDENCY_ERROR = 3
#: Exit code used for unexpected internal failures.
EXIT_INTERNAL_ERROR = 1


class SongLabError(Exception):
    """Base class for all expected, user-facing failures.

    Attributes:
        message: One-line explanation of what went wrong.
        hint: Optional instruction telling the user how to recover.
    """

    exit_code: int = EXIT_INTERNAL_ERROR

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        if self.hint:
            return f"{self.message}\n\n{self.hint}"
        return self.message


class InputError(SongLabError):
    """The user provided invalid input (missing file, bad argument, ...)."""

    exit_code = EXIT_INPUT_ERROR


class AudioFileNotFoundError(InputError):
    """The requested audio file does not exist."""

    def __init__(self, path: Path) -> None:
        super().__init__(
            f"Audio file not found: {path}",
            hint="Check the path and try again.",
        )
        self.path = path


class UnsupportedAudioError(InputError):
    """The file exists but does not look like usable audio."""

    def __init__(self, path: Path, *, reason: str | None = None) -> None:
        message = f"Unsupported or unreadable audio file: {path}"
        if reason:
            message = f"{message}\nReason: {reason}"
        super().__init__(
            message,
            hint=(
                "Supported container formats include WAV, MP3, FLAC, OGG, M4A, AAC "
                "and AIFF. Install FFmpeg to extend format support.\n"
                f"Requested file: {path}"
            ),
        )
        self.path = path


class DependencyError(SongLabError):
    """An external executable or optional Python dependency is missing."""

    exit_code = EXIT_DEPENDENCY_ERROR


class EngineNotFoundError(InputError):
    """The requested analysis engine is not registered."""

    def __init__(self, kind: str, name: str, available: list[str]) -> None:
        available_text = ", ".join(available) if available else "(none registered)"
        super().__init__(
            f"Unknown {kind} engine: {name}",
            hint=f"Available {kind} engines: {available_text}",
        )
        self.kind = kind
        self.name = name
        self.available = available


class DuplicateEngineError(SongLabError):
    """An engine with the same name is already registered for that kind."""

    def __init__(self, kind: str, name: str) -> None:
        super().__init__(f"A {kind} engine named {name!r} is already registered.")
        self.kind = kind
        self.name = name


class ConfigError(SongLabError):
    """The configuration is invalid or inconsistent."""

    exit_code = EXIT_INPUT_ERROR


class SchemaError(SongLabError):
    """A canonical document could not be (de)serialized."""

    exit_code = EXIT_INPUT_ERROR
