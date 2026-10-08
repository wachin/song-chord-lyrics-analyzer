"""Waveform peaks: the reduction the Phase D timeline draws.

The interesting properties are exact: a bucket never loses the extremes of the
frames it covers, buckets are cut in frames so an interleaved stereo file stays
aligned, and a track shorter than the requested resolution still produces one
bucket per frame instead of empty columns. Nothing here needs numpy, which is
the point - the same code serves the DSP backend and the standard library one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fixtures.audio import write_sine_wav
from song_chord_lyrics_analyzer.audio.decode import DecodedAudio, decode_with_wave
from song_chord_lyrics_analyzer.audio.peaks import (
    DEFAULT_PEAK_BUCKETS,
    WaveformPeaks,
    peaks_of,
    waveform_peaks,
)
from song_chord_lyrics_analyzer.utils.errors import InputError


class _SliceOfNumpyLike:
    """A slice with its own ``min``/``max``, the way a numpy slice has them."""

    def __init__(self, values: list[float]) -> None:
        self._values = values

    def min(self) -> float:
        return min(self._values)

    def max(self) -> float:
        return max(self._values)


class NumpyLike:
    """A stand-in for a numpy array: slices that carry their own extremes."""

    def __init__(self, values: list[float]) -> None:
        self._values = values

    def __len__(self) -> int:
        return len(self._values)

    def __getitem__(self, item: slice) -> _SliceOfNumpyLike:
        return _SliceOfNumpyLike(self._values[item])


class TestTheReduction:
    def test_a_bucket_keeps_the_extremes_of_the_frames_it_covers(self) -> None:
        peaks = waveform_peaks([0.0, 0.5, -0.5, 1.0], buckets=2)

        assert len(peaks) == 2
        assert peaks.minimums == (0.0, -0.5)
        assert peaks.maximums == (0.5, 1.0)
        assert peaks.at(1) == (-0.5, 1.0)

    def test_the_same_samples_reduce_to_one_bucket_however_they_are_grouped(self) -> None:
        samples = [0.1, -0.2, 0.3, -0.4, 0.5, -0.6]

        one = waveform_peaks(samples, buckets=1)
        two = waveform_peaks(samples, buckets=2)

        assert one.minimums == (min(samples),)
        assert one.maximums == (max(samples),)
        assert two.minimums == (-0.2, -0.6)
        assert two.maximums == (0.3, 0.5)
        assert min(two.minimums) == min(one.minimums)

    def test_a_short_track_gives_one_bucket_per_frame_not_empty_columns(self) -> None:
        peaks = waveform_peaks([0.25, -0.25], buckets=100)

        assert peaks.bucket_count == 2
        assert peaks.maximums == (0.25, -0.25)

    def test_an_interleaved_stereo_bucket_keeps_both_channels_of_one_instant(self) -> None:
        # Two frames: (L=0.5, R=-0.5) then (L=1.0, R=1.0).
        peaks = waveform_peaks([0.5, -0.5, 1.0, 1.0], channels=2, buckets=2)

        assert peaks.minimums == (-0.5, 1.0)
        assert peaks.maximums == (0.5, 1.0)

    def test_an_empty_decode_has_nothing_to_draw_instead_of_failing(self) -> None:
        peaks = waveform_peaks([], buckets=8)

        assert peaks.is_empty is True
        assert len(peaks) == 0
        assert peaks.minimums == ()

    def test_it_uses_the_arrays_own_extremes_when_the_slice_has_them(self) -> None:
        peaks = waveform_peaks(NumpyLike([0.1, -0.9, 0.4, 0.8]), buckets=2)

        assert peaks.minimums == (-0.9, 0.4)
        assert peaks.maximums == (0.1, 0.8)


class TestValidation:
    def test_buckets_must_be_positive(self) -> None:
        with pytest.raises(InputError, match="buckets must be positive"):
            waveform_peaks([0.0], buckets=0)

    def test_channels_must_be_positive(self) -> None:
        with pytest.raises(InputError, match="channels must be positive"):
            waveform_peaks([0.0], channels=0)

    def test_the_two_half_arrays_must_have_the_same_length(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            WaveformPeaks(minimums=(0.0,), maximums=())

    def test_the_default_resolution_is_the_documented_one(self) -> None:
        peaks = waveform_peaks([0.0] * (DEFAULT_PEAK_BUCKETS * 2))

        assert peaks.bucket_count == DEFAULT_PEAK_BUCKETS


class TestFromDecodedAudio:
    def test_peaks_of_a_real_wav_cover_the_whole_file(self, tmp_path: Path) -> None:
        path = write_sine_wav(tmp_path / "tone.wav", seconds=1.0, channels=1, amplitude=0.5)
        audio = decode_with_wave(path)

        peaks = peaks_of(audio, buckets=50)

        assert peaks.bucket_count == 50
        # A sine at 0.5 amplitude: every bucket reaches near the peak and dips.
        assert max(peaks.maximums) == pytest.approx(0.5, abs=0.01)
        assert min(peaks.minimums) == pytest.approx(-0.5, abs=0.01)

    def test_peaks_are_plain_floats_even_when_the_samples_are_not(self) -> None:
        audio = DecodedAudio(
            path=Path("x.wav"),
            samples=NumpyLike([0.1, 0.2]),
            sample_rate=8000,
            channels=1,
            backend="dsp",
        )

        peaks = peaks_of(audio, buckets=1)

        assert peaks.at(0) == (0.1, 0.2)
