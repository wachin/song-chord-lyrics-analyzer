"""Audio input validation (roadmap sections 16 and 105).

Audio files are untrusted input: paths are validated before any decoder runs,
and the source file is never opened for writing.
"""

from __future__ import annotations

from pathlib import Path

from song_chord_lyrics_analyzer.utils.errors import AudioFileNotFoundError, InputError
from song_chord_lyrics_analyzer.utils.logging import get_logger

__all__ = [
    "SUPPORTED_AUDIO_EXTENSIONS",
    "is_probably_audio",
    "validate_audio_file",
]

_logger = get_logger("audio.validation")

#: Extensions FFmpeg-based probing is expected to handle. Unknown extensions
#: are not rejected - they are only logged, because probing decides the truth.
SUPPORTED_AUDIO_EXTENSIONS = frozenset(
    {
        ".aac",
        ".aif",
        ".aiff",
        ".alac",
        ".amr",
        ".ape",
        ".caf",
        ".dsf",
        ".flac",
        ".m4a",
        ".mka",
        ".mp3",
        ".mp4",
        ".mpc",
        ".oga",
        ".ogg",
        ".opus",
        ".wav",
        ".webm",
        ".wma",
        ".wv",
    }
)


def is_probably_audio(path: Path) -> bool:
    """Whether the file extension suggests a supported audio container."""
    return Path(path).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS


def validate_audio_file(path: str | Path) -> Path:
    """Validate a user-supplied audio path and return its resolved form.

    Raises:
        AudioFileNotFoundError: The path does not exist.
        InputError: The path is a directory or an empty file.
    """
    candidate = Path(path).expanduser()
    if not candidate.exists():
        raise AudioFileNotFoundError(candidate)
    if candidate.is_dir():
        raise InputError(
            f"Expected an audio file but got a directory: {candidate}",
            hint="Pass the path of an audio file, for example: songlab info song.mp3",
        )
    if candidate.stat().st_size == 0:
        raise InputError(
            f"Audio file is empty: {candidate}",
            hint="The file contains no data; check that it was copied completely.",
        )
    if not is_probably_audio(candidate):
        _logger.warning(
            "unrecognised audio extension %r; probing the file anyway",
            candidate.suffix,
        )
    return candidate.resolve()
