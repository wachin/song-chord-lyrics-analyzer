"""Reduce decoded samples to waveform peaks, one bucket per drawn column.

A waveform view does not need every sample: it needs the lowest and the highest
value inside each column it is about to paint. This module turns the flat,
optionally interleaved samples of
:class:`~song_chord_lyrics_analyzer.audio.decode.DecodedAudio` into that
reduction - the "downsampled min/max per pixel bucket" of roadmap Phase A, and
the data the Phase D timeline renders.

Two properties make it useful in this project:

* **No dependency.** It never imports numpy. A bucket is a slice of the decoded
  sequence and its extremes are either ``min()``/``max()`` (a list, the standard
  library WAV backend) or the array's own ``.min()``/``.max()`` methods (the DSP
  backend), so the same code is fast with numpy and correct without it.
* **Frame aligned.** Buckets are cut in *frames*, not samples, so an interleaved
  stereo file reduces each column from both channels of the same instant.

Nothing here knows about Qt, playback or chord analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from song_chord_lyrics_analyzer.audio.decode import DecodedAudio
from song_chord_lyrics_analyzer.utils.errors import InputError

__all__ = [
    "DEFAULT_PEAK_BUCKETS",
    "WaveformPeaks",
    "peaks_of",
    "waveform_peaks",
]

#: Buckets used when a caller does not ask for a specific resolution. Wide
#: enough for a full-screen timeline, small enough to stay cheap to compute.
DEFAULT_PEAK_BUCKETS = 1024


@dataclass(frozen=True)
class WaveformPeaks:
    """The waveform of one track, reduced to one bucket per drawn column.

    Attributes:
        minimums: Lowest sample value in each bucket, in ``[-1.0, 1.0]``.
        maximums: Highest sample value in each bucket, in ``[-1.0, 1.0]``.
            ``maximums[i]`` and ``minimums[i]`` belong to the same bucket, so a
            view draws bucket ``i`` as the vertical segment between them.
    """

    minimums: tuple[float, ...]
    maximums: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.minimums) != len(self.maximums):
            raise ValueError(
                "minimums and maximums must have the same length, got "
                f"{len(self.minimums)} and {len(self.maximums)}"
            )

    def __len__(self) -> int:
        """Number of buckets."""
        return len(self.minimums)

    @property
    def bucket_count(self) -> int:
        """Number of buckets, i.e. how many columns this waveform has."""
        return len(self.minimums)

    @property
    def is_empty(self) -> bool:
        """Whether the reduction produced no bucket at all."""
        return not self.minimums

    def at(self, index: int) -> tuple[float, float]:
        """The ``(low, high)`` pair of one bucket.

        Raises:
            IndexError: When ``index`` is outside the buckets.
        """
        return self.minimums[index], self.maximums[index]


def _extremes(block: Any) -> tuple[float, float]:
    """Lowest and highest value of one bucket.

    Works on a numpy array (its own ``min``/``max`` are C loops) and on a plain
    sequence (the builtins), without importing either.
    """
    low = getattr(block, "min", None)
    high = getattr(block, "max", None)
    if callable(low) and callable(high):
        return float(low()), float(high())
    return float(min(block)), float(max(block))


def waveform_peaks(
    samples: Any,
    *,
    channels: int = 1,
    buckets: int = DEFAULT_PEAK_BUCKETS,
) -> WaveformPeaks:
    """Reduce ``samples`` to at most ``buckets`` min/max pairs.

    Args:
        samples: Flat samples in ``[-1.0, 1.0]``, mono or channel-interleaved,
            as returned by :class:`~song_chord_lyrics_analyzer.audio.decode.DecodedAudio`.
        channels: How many channels are interleaved in ``samples``.
        buckets: Requested resolution, i.e. one bucket per drawn column.

    Returns:
        The peaks. A track shorter than ``buckets`` frames produces one bucket
        per frame instead of empty buckets, so ``bucket_count`` is the number of
        columns the caller should actually draw. An empty decode gives an empty
        :class:`WaveformPeaks`, not an error: there is simply nothing to draw.

    Raises:
        InputError: When ``channels`` or ``buckets`` is not positive.
    """
    if channels < 1:
        raise InputError(f"channels must be positive, got {channels!r}")
    if buckets < 1:
        raise InputError(f"buckets must be positive, got {buckets!r}")

    frames = len(samples) // channels
    if frames < 1:
        return WaveformPeaks(minimums=(), maximums=())

    count = min(buckets, frames)
    minimums: list[float] = []
    maximums: list[float] = []
    for index in range(count):
        # Bucket boundaries in frames, then widened to whole frames so the two
        # channels of one instant always land in the same bucket.
        first = (index * frames) // count
        last = max(first + 1, ((index + 1) * frames) // count)
        low, high = _extremes(samples[first * channels : last * channels])
        minimums.append(low)
        maximums.append(high)
    return WaveformPeaks(minimums=tuple(minimums), maximums=tuple(maximums))


def peaks_of(audio: DecodedAudio, *, buckets: int = DEFAULT_PEAK_BUCKETS) -> WaveformPeaks:
    """Reduce a decoded file to waveform peaks.

    Args:
        audio: The decoded audio to reduce.
        buckets: Requested resolution, i.e. one bucket per drawn column.

    Returns:
        The peaks of that file (see :func:`waveform_peaks`).
    """
    return waveform_peaks(audio.samples, channels=audio.channels, buckets=buckets)
