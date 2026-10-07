"""Decode an audio file to samples through one shared entry point (Phase A).

Until now every DSP engine decoded for itself, each with its own ``librosa.load``
call, and nothing could produce samples for playback. This module is the single
application-level decode service the roadmap asks for: given a path it returns
samples and the sample rate they are expressed at, so the analysis engines and
the playback layer can agree on one representation instead of three.

Two backends, in preference order:

* ``dsp`` - ``librosa.load`` (numpy/librosa/soundfile), the only path that reads
  compressed formats and can resample. Optional, like every heavy dependency in
  this project; without it the caller gets an honest
  :class:`~song_chord_lyrics_analyzer.utils.errors.DependencyError`.
* ``wave`` - the standard library, WAV files only, no resampling. This keeps a
  bare install useful for uncompressed audio (and keeps the tests CI-safe).

Samples are returned as one flat sequence of floats in ``[-1.0, 1.0]``, the
layout a raw audio buffer uses: mono, or channel-interleaved when ``channels``
is greater than one.
"""

from __future__ import annotations

import array
import importlib
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from song_chord_lyrics_analyzer.audio.validation import validate_audio_file
from song_chord_lyrics_analyzer.utils.errors import (
    DependencyError,
    InputError,
    UnsupportedAudioError,
)
from song_chord_lyrics_analyzer.utils.logging import get_logger

__all__ = [
    "BACKEND_AUTO",
    "BACKEND_DSP",
    "BACKEND_WAVE",
    "DecodedAudio",
    "decode_audio",
    "decode_with_wave",
]

_logger = get_logger("audio.decode")

#: Let the service pick: the DSP stack when importable, the stdlib for WAV.
BACKEND_AUTO = "auto"
#: Force the optional numpy/librosa front end.
BACKEND_DSP = "dsp"
#: Force the standard-library WAV reader.
BACKEND_WAVE = "wave"

_DSP_HINT = (
    "Install the optional DSP stack (pip install numpy librosa) to decode "
    "compressed audio or to resample. Only uncompressed WAV files can be "
    "decoded without it."
)

_BYTES_PER_SAMPLE = {1: 1, 2: 2, 3: 3, 4: 4}


@dataclass(frozen=True)
class DecodedAudio:
    """Samples decoded from one audio file.

    Attributes:
        path: The file the samples came from.
        samples: Flat samples in ``[-1.0, 1.0]`` - mono, or channel-interleaved
            when :attr:`channels` is greater than one. A numpy array with the
            DSP backend, a list of floats with the WAV backend.
        sample_rate: Sample rate in Hz of :attr:`samples`.
        channels: Number of channels interleaved in :attr:`samples`.
        backend: ``"dsp"`` or ``"wave"``, recorded so callers can explain
            which decoder ran.
    """

    path: Path
    samples: Any
    sample_rate: int
    channels: int
    backend: str

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError(f"sample_rate must be positive, got {self.sample_rate!r}")
        if self.channels <= 0:
            raise ValueError(f"channels must be positive, got {self.channels!r}")

    @property
    def frame_count(self) -> int:
        """Number of sample frames, i.e. samples per channel."""
        return len(self.samples) // self.channels

    @property
    def duration(self) -> float:
        """Duration of the decoded samples in seconds."""
        return self.frame_count / self.sample_rate

    @property
    def is_mono(self) -> bool:
        """Whether the samples carry a single channel."""
        return self.channels == 1


def _validate_window(offset: float, duration: float | None) -> None:
    if offset < 0:
        raise InputError(
            f"offset must not be negative, got {offset!r}",
            hint="Pass a start time in seconds of 0 or more.",
        )
    if duration is not None and duration <= 0:
        raise InputError(
            f"duration must be positive, got {duration!r}",
            hint="Pass a window length in seconds greater than 0, or None for the whole file.",
        )


def _import_dsp() -> tuple[Any, Any]:
    """Import numpy and librosa, or raise :class:`DependencyError`.

    Uses :func:`importlib.import_module` so the core package stays importable
    and type-checkable without the optional DSP stack installed.
    """
    try:
        librosa = importlib.import_module("librosa")
        numpy = importlib.import_module("numpy")
    except ImportError as error:
        raise DependencyError(
            "Decoding audio needs numpy and librosa, which are not installed.",
            hint=_DSP_HINT,
        ) from error
    return librosa, numpy


def _decode_with_dsp(
    path: Path,
    *,
    sample_rate: int | None,
    mono: bool,
    offset: float,
    duration: float | None,
) -> DecodedAudio:
    """Decode with ``librosa.load`` - every format soundfile supports."""
    librosa, numpy = _import_dsp()
    try:
        samples, rate = librosa.load(
            str(path),
            sr=sample_rate,
            mono=mono,
            offset=offset,
            duration=duration,
        )
    except Exception as error:
        raise UnsupportedAudioError(path, reason=str(error)) from error

    array_samples = numpy.asarray(samples)
    if array_samples.ndim > 1:
        channels = int(array_samples.shape[0])
        # (channels, frames) -> (frames, channels) -> flat interleaved buffer.
        interleaved = numpy.ascontiguousarray(array_samples.T).reshape(-1)
    else:
        channels = 1
        interleaved = array_samples.reshape(-1)
    interleaved = numpy.asarray(interleaved, dtype=numpy.float32)

    _logger.debug("decoded %s with librosa (%d ch, %d Hz)", path, channels, int(rate))
    return DecodedAudio(
        path=path,
        samples=interleaved,
        sample_rate=int(rate),
        channels=channels,
        backend=BACKEND_DSP,
    )


def _pcm_values(payload: bytes, sample_width: int) -> list[int]:
    """Signed integer PCM samples from little-endian bytes.

    ``sample_width`` must already have been validated by the caller.
    """
    if sample_width == 3:  # array has no 24-bit type
        return [
            int.from_bytes(payload[index : index + 3], "little", signed=True)
            for index in range(0, len(payload) - 2, 3)
        ]
    typecode = {1: "B", 2: "h", 4: "i"}[sample_width]
    values = array.array(typecode)
    values.frombytes(payload[: len(payload) - (len(payload) % sample_width)])
    if sys.byteorder == "big":
        values.byteswap()
    if sample_width == 1:  # 8-bit WAV is unsigned around 128
        return [value - 128 for value in values]
    return list(values)


def _downmix_mono(values: list[float], channels: int) -> list[float]:
    if channels == 1:
        return values
    frames = len(values) // channels
    return [
        sum(values[index * channels + channel] for channel in range(channels)) / channels
        for index in range(frames)
    ]


def _require_native_rate(sample_rate: int | None) -> None:
    """The WAV path cannot resample; refuse instead of reporting a wrong rate."""
    if sample_rate is not None:
        raise DependencyError(
            "Resampling audio needs the optional DSP stack.",
            hint=_DSP_HINT,
        )


def decode_with_wave(
    path: str | Path,
    *,
    mono: bool = True,
    offset: float = 0.0,
    duration: float | None = None,
) -> DecodedAudio:
    """Decode a WAV file with the standard library (no dependencies).

    Args:
        path: The WAV file to decode.
        mono: Downmix every channel to one.
        offset: Start time in seconds.
        duration: Window length in seconds, or ``None`` for the rest of the file.

    Raises:
        AudioFileNotFoundError: The path does not exist.
        InputError: The path is a directory, empty, or has an invalid window.
        UnsupportedAudioError: The file is not readable uncompressed PCM WAV.
    """
    _validate_window(offset, duration)
    resolved = validate_audio_file(path)

    try:
        with wave.open(str(resolved), "rb") as reader:
            channels = reader.getnchannels()
            sample_rate = reader.getframerate()
            sample_width = reader.getsampwidth()
            compression = reader.getcomptype()
            total_frames = reader.getnframes()
            first_frame = min(round(offset * sample_rate), total_frames)
            frame_span = (
                total_frames - first_frame
                if duration is None
                else min(round(duration * sample_rate), total_frames - first_frame)
            )
            reader.setpos(first_frame)
            payload = reader.readframes(frame_span)
    except (wave.Error, EOFError, OSError) as error:
        raise UnsupportedAudioError(resolved, reason=str(error)) from error

    if compression != "NONE":
        raise UnsupportedAudioError(
            resolved,
            reason=f"compressed WAV ({compression.lower()}) is not decodable without the DSP stack",
        )
    if sample_width not in _BYTES_PER_SAMPLE:
        raise UnsupportedAudioError(
            resolved,
            reason=f"unsupported sample width of {sample_width * 8} bits",
        )

    peak = float(1 << (8 * sample_width - 1))
    floats = [value / peak for value in _pcm_values(payload, sample_width)]
    if mono:
        floats = _downmix_mono(floats, channels)
        channels = 1

    _logger.debug(
        "decoded %s with the standard library (%d ch, %d Hz)", resolved, channels, sample_rate
    )
    return DecodedAudio(
        path=resolved,
        samples=floats,
        sample_rate=sample_rate,
        channels=channels,
        backend=BACKEND_WAVE,
    )


def decode_audio(
    path: str | Path,
    *,
    sample_rate: int | None = None,
    mono: bool = True,
    offset: float = 0.0,
    duration: float | None = None,
    backend: str = BACKEND_AUTO,
) -> DecodedAudio:
    """Decode ``path`` to samples through the shared decode service.

    Args:
        path: The audio file to decode.
        sample_rate: Target sample rate in Hz, or ``None`` to keep the file's
            own rate. Converting the rate needs the DSP backend.
        mono: Downmix every channel into one.
        offset: Start time in seconds.
        duration: Window length in seconds, or ``None`` for the rest of the file.
        backend: ``BACKEND_AUTO``, ``BACKEND_DSP`` or ``BACKEND_WAVE``.

    Raises:
        AudioFileNotFoundError: The path does not exist.
        InputError: The path is a directory, empty, or has an invalid window,
            or ``backend`` is unknown.
        UnsupportedAudioError: The file could not be decoded.
        DependencyError: No available backend can decode the request.
    """
    if backend not in {BACKEND_AUTO, BACKEND_DSP, BACKEND_WAVE}:
        raise InputError(
            f"Unknown decode backend: {backend!r}",
            hint=f"Use {BACKEND_AUTO!r}, {BACKEND_DSP!r} or {BACKEND_WAVE!r}.",
        )
    _validate_window(offset, duration)
    resolved = validate_audio_file(path)

    if backend == BACKEND_WAVE:
        _require_native_rate(sample_rate)
        return decode_with_wave(resolved, mono=mono, offset=offset, duration=duration)
    if backend == BACKEND_DSP:
        return _decode_with_dsp(
            resolved,
            sample_rate=sample_rate,
            mono=mono,
            offset=offset,
            duration=duration,
        )

    try:
        return _decode_with_dsp(
            resolved,
            sample_rate=sample_rate,
            mono=mono,
            offset=offset,
            duration=duration,
        )
    except DependencyError:
        if resolved.suffix.lower() != ".wav":
            raise
        _logger.debug("the DSP stack is unavailable; reading %s as WAV", resolved)

    _require_native_rate(sample_rate)
    return decode_with_wave(resolved, mono=mono, offset=offset, duration=duration)
