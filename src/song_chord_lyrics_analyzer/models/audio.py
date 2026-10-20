"""Canonical audio metadata model (roadmap section 10).

Technical metadata (what the decoder reports) is strictly separated from
descriptive tags (what the file claims). Tags are never trusted: a wrong ID3
title must not influence analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from song_chord_lyrics_analyzer.utils.time import format_timestamp

__all__ = ["AudioDocument"]


@dataclass
class AudioDocument:
    """Technical description of a local audio file.

    Attributes:
        path: Absolute or relative path to the audio file.
        duration: Duration in seconds.
        sample_rate: Sample rate in Hz.
        channels: Number of audio channels.
        bit_depth: Bits per sample when the container exposes it.
        format: Container format (``wav``, ``mp3``, ``flac``, ...).
        codec: Codec name (``pcm_s16le``, ``mp3``, ...).
        bitrate: Bitrate in bits per second.
        file_size: File size in bytes.
        artist: Tag value, informational only.
        album: Tag value, informational only.
        title: Tag value, informational only.
        genre: Tag value, informational only.
        year: Tag value, informational only.
        extra_tags: Remaining container tags, unmodified.
        probe_backend: Tool that produced the metadata (``ffprobe``, ``wave``).
    """

    path: Path
    duration: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    bit_depth: int | None = None
    format: str | None = None
    codec: str | None = None
    bitrate: int | None = None
    file_size: int | None = None

    artist: str | None = None
    album: str | None = None
    title: str | None = None
    genre: str | None = None
    year: str | None = None

    extra_tags: dict[str, str] = field(default_factory=dict)
    probe_backend: str | None = None

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        if self.duration is not None and self.duration < 0:
            raise ValueError(f"duration must not be negative, got {self.duration!r}")
        if self.sample_rate is not None and self.sample_rate <= 0:
            raise ValueError(f"sample_rate must be positive, got {self.sample_rate!r}")
        if self.channels is not None and self.channels <= 0:
            raise ValueError(f"channels must be positive, got {self.channels!r}")
        if self.bitrate is not None and self.bitrate <= 0:
            raise ValueError(f"bitrate must be positive, got {self.bitrate!r}")
        if self.file_size is not None and self.file_size < 0:
            raise ValueError(f"file_size must not be negative, got {self.file_size!r}")

    @property
    def channels_label(self) -> str:
        """Human-readable channel description."""
        if self.channels is None:
            return "unknown"
        if self.channels == 1:
            return "mono"
        if self.channels == 2:
            return "stereo"
        return f"{self.channels} channels"

    @property
    def duration_label(self) -> str:
        """``HH:MM:SS.mmm`` representation of the duration."""
        return format_timestamp(self.duration)

    @property
    def bitrate_kbps(self) -> float | None:
        """Bitrate in kbit/s when known."""
        if self.bitrate is None:
            return None
        return self.bitrate / 1000.0

    def as_technical_dict(self) -> dict[str, object]:
        """Return only the technical fields, dropping untrusted tags."""
        return {
            "path": str(self.path),
            "duration": self.duration,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "bit_depth": self.bit_depth,
            "format": self.format,
            "codec": self.codec,
            "bitrate": self.bitrate,
            "file_size": self.file_size,
            "probe_backend": self.probe_backend,
        }
