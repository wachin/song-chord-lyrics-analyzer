"""Generated audio fixtures.

Tests never commit copyrighted commercial songs (roadmap section 42). Tiny
synthetic WAV files are generated on the fly instead, which keeps the
repository small and the tests deterministic.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

__all__ = ["write_sine_wav", "write_wav_bytes"]


def write_sine_wav(
    path: Path,
    *,
    seconds: float = 1.0,
    sample_rate: int = 44100,
    channels: int = 2,
    frequency: float = 440.0,
    amplitude: float = 0.2,
    sample_width: int = 2,
) -> Path:
    """Write a sine tone to ``path`` as an uncompressed WAV file.

    Args:
        path: Destination path.
        seconds: Duration in seconds.
        sample_rate: Sample rate in Hz.
        channels: Number of channels (1 or 2).
        frequency: Tone frequency in Hz.
        amplitude: Peak amplitude in ``[0.0, 1.0]``.
        sample_width: Bytes per sample (2 = 16 bit PCM).

    Returns:
        The written path.
    """
    if sample_width != 2:
        raise ValueError("only 16-bit PCM fixtures are supported")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = max(1, round(seconds * sample_rate))
    peak = int(amplitude * 32767)
    peak = max(-32768, min(32767, peak))

    frames = bytearray()
    for index in range(frame_count):
        sample = int(peak * math.sin(2.0 * math.pi * frequency * index / sample_rate))
        frames.extend(struct.pack("<h", sample) * channels)

    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width)
        writer.setframerate(sample_rate)
        writer.writeframes(bytes(frames))
    return path


def write_wav_bytes(path: Path, payload: bytes = b"") -> Path:
    """Write arbitrary bytes to ``path`` - used for corrupt-input tests."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload or b"not-a-real-audio-stream")
    return path
