"""Audio metadata probing (roadmap section 10 and phase 2).

Metadata is read with ``ffprobe`` when available. WAV files can also be read
with the standard library, so ``songlab info`` works without installing
anything at all. Descriptive tags are kept separate from technical facts and
are never trusted.
"""

from __future__ import annotations

import hashlib
import json
import wave
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.audio.ffmpeg import (
    ffmpeg_install_hint,
    find_ffprobe,
    run_ffprobe,
)
from song_chord_lyrics_analyzer.audio.validation import validate_audio_file
from song_chord_lyrics_analyzer.models.audio import AudioDocument
from song_chord_lyrics_analyzer.utils.errors import DependencyError, UnsupportedAudioError
from song_chord_lyrics_analyzer.utils.logging import get_logger

__all__ = [
    "compute_file_hash",
    "probe_audio",
    "probe_audio_with_ffprobe",
    "probe_audio_with_wave",
]

_logger = get_logger("audio.probe")

_HASH_CHUNK_SIZE = 1024 * 1024

#: ffprobe tag names mapped onto canonical :class:`AudioDocument` fields.
_TAG_FIELDS = {
    "title": "title",
    "artist": "artist",
    "album": "album",
    "album_artist": "album_artist",
    "genre": "genre",
    "date": "year",
    "year": "year",
    "track": "track",
}


def compute_file_hash(path: Path, *, algorithm: str = "sha256") -> str:
    """Return the hex digest of a file, read in chunks.

    The digest is the cache key component that makes caching and provenance
    reproducible (roadmap sections 60 and 61).
    """
    digest = hashlib.new(algorithm)
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _first_audio_stream(payload: dict[str, Any]) -> dict[str, Any] | None:
    for stream in payload.get("streams", []):
        if stream.get("codec_type") == "audio":
            return stream
    return None


def _extract_tags(raw_tags: dict[str, Any] | None) -> dict[str, str]:
    """Normalize container tags to lower-case keys with string values."""
    if not isinstance(raw_tags, dict):
        return {}
    tags: dict[str, str] = {}
    for key, value in raw_tags.items():
        if value is None:
            continue
        tags[str(key).strip().lower()] = str(value)
    return tags


def probe_audio_with_ffprobe(path: Path) -> AudioDocument:
    """Probe a file with ``ffprobe`` and return a canonical document.

    Raises:
        DependencyError: When ``ffprobe`` is not installed.
        UnsupportedAudioError: When the file is not readable as audio.
    """
    result = run_ffprobe(
        [
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    if result.returncode != 0:
        reason = (result.stderr or result.stdout or "ffprobe returned an error").strip()
        raise UnsupportedAudioError(path, reason=reason.splitlines()[0] if reason else None)

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise UnsupportedAudioError(path, reason=f"ffprobe output was not JSON: {exc}") from exc

    stream = _first_audio_stream(payload)
    if stream is None:
        raise UnsupportedAudioError(path, reason="the file contains no audio stream")

    container = payload.get("format") or {}
    tags = _extract_tags(container.get("tags"))

    container_format = container.get("format_name")
    if isinstance(container_format, str):
        container_format = container_format.split(",")[0].strip() or None

    duration = _optional_float(container.get("duration"))
    if duration is None:
        duration = _optional_float(stream.get("duration"))

    document = AudioDocument(
        path=path,
        duration=duration,
        sample_rate=_optional_int(stream.get("sample_rate")),
        channels=_optional_int(stream.get("channels")),
        bit_depth=_optional_int(stream.get("bits_per_raw_sample"))
        or _optional_int(stream.get("bits_per_sample")),
        format=container_format,
        codec=stream.get("codec_name") or None,
        bitrate=_optional_int(container.get("bit_rate")) or _optional_int(stream.get("bit_rate")),
        file_size=_optional_int(container.get("size")) or path.stat().st_size,
        probe_backend="ffprobe",
        extra_tags=tags,
    )

    known = set(_TAG_FIELDS) | {"album_artist", "track"}
    for tag_key, value in tags.items():
        field_name = _TAG_FIELDS.get(tag_key)
        if field_name == "year" and document.year is None:
            document.year = value
        elif field_name in {"title", "artist", "album", "genre"}:
            setattr(document, field_name, value)
    document.extra_tags = {key: value for key, value in tags.items() if key not in known}
    return document


def probe_audio_with_wave(path: Path) -> AudioDocument:
    """Probe a WAV file using the standard library.

    Raises:
        UnsupportedAudioError: When the file is not a readable WAV container.
    """
    try:
        with wave.open(str(path), "rb") as reader:
            channels = reader.getnchannels()
            raw_sample_rate = reader.getframerate()
            sample_width = reader.getsampwidth()
            frame_count = reader.getnframes()
            compression = reader.getcomptype()
    except (wave.Error, EOFError, OSError) as exc:
        raise UnsupportedAudioError(path, reason=str(exc)) from exc

    sample_rate: int | None = raw_sample_rate if raw_sample_rate > 0 else None
    duration = frame_count / sample_rate if sample_rate else None
    codec = "pcm" if compression == "NONE" else compression.lower()

    return AudioDocument(
        path=path,
        duration=duration,
        sample_rate=sample_rate,
        channels=channels,
        bit_depth=sample_width * 8,
        format="wav",
        codec=codec,
        bitrate=sample_rate * channels * sample_width * 8 if sample_rate else None,
        file_size=path.stat().st_size,
        probe_backend="wave",
    )


def probe_audio(path: str | Path, *, use_ffprobe: bool = True) -> AudioDocument:
    """Probe an audio file and return its canonical metadata document.

    ``ffprobe`` is preferred because it reports the codec and container as
    decoded rather than guessed. WAV files fall back to the standard library so
    the tool remains useful on a machine without FFmpeg.

    Raises:
        AudioFileNotFoundError: The path does not exist.
        InputError: The path is a directory or an empty file.
        UnsupportedAudioError: The file could not be decoded as audio.
        DependencyError: A non-WAV file requires FFprobe, which is missing.
    """
    resolved = validate_audio_file(path)

    if use_ffprobe and find_ffprobe() is not None:
        try:
            document = probe_audio_with_ffprobe(resolved)
        except UnsupportedAudioError:
            if resolved.suffix.lower() != ".wav":
                raise
            _logger.debug("ffprobe could not read %s; falling back to wave", resolved)
        else:
            _logger.debug("probed %s with ffprobe", resolved)
            return document

    if resolved.suffix.lower() == ".wav":
        document = probe_audio_with_wave(resolved)
        _logger.debug("probed %s with wave", resolved)
        return document

    raise DependencyError(
        f"FFprobe is required to inspect {resolved.suffix or 'this'} files.",
        hint=("Only WAV files can be inspected without FFmpeg.\n\n" + ffmpeg_install_hint()),
    )
