"""The shared decode service (roadmap Phase A).

``decode_audio`` is the one entry point the analysis engines and the playback
layer are meant to share, so its contract is pinned here: floats in ``[-1, 1]``,
an explicit sample rate and channel count, and an honest failure when the
optional DSP stack is the only thing that can serve the request.

The standard-library WAV half runs everywhere; the librosa half is exercised
only where that optional stack is installed, exactly as the engine tests do.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from fixtures.audio import write_sine_wav, write_wav_bytes
from song_chord_lyrics_analyzer.audio.decode import (
    BACKEND_AUTO,
    BACKEND_DSP,
    BACKEND_WAVE,
    DecodedAudio,
    decode_audio,
    decode_with_wave,
)
from song_chord_lyrics_analyzer.utils.errors import (
    AudioFileNotFoundError,
    DependencyError,
    InputError,
    UnsupportedAudioError,
)


def _dsp_available() -> bool:
    try:
        importlib.import_module("librosa")
        importlib.import_module("numpy")
    except ImportError:
        return False
    return True


requires_dsp = pytest.mark.skipif(
    not _dsp_available(),
    reason="optional DSP stack (numpy/librosa) not installed",
)


def _mono_wav(directory: Path, *, seconds: float = 1.0) -> Path:
    return write_sine_wav(directory / "mono.wav", seconds=seconds, channels=1, amplitude=0.2)


class TestDecodedAudioModel:
    def test_rejects_a_non_positive_sample_rate(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="sample_rate"):
            DecodedAudio(
                path=tmp_path / "a.wav", samples=[], sample_rate=0, channels=1, backend="wave"
            )

    def test_rejects_a_non_positive_channel_count(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="channels"):
            DecodedAudio(
                path=tmp_path / "a.wav", samples=[], sample_rate=44100, channels=0, backend="wave"
            )


class TestWaveDecoder:
    """The dependency-free half: any machine, uncompressed WAV only."""

    def test_a_mono_tone_decodes_to_its_samples(self, tmp_path: Path) -> None:
        wav = _mono_wav(tmp_path)
        decoded = decode_with_wave(wav)

        assert decoded.backend == BACKEND_WAVE
        assert decoded.path == wav.resolve()
        assert decoded.sample_rate == 44100
        assert decoded.channels == 1
        assert decoded.is_mono
        assert decoded.frame_count == 44100
        assert decoded.duration == pytest.approx(1.0, abs=1e-3)
        assert len(decoded.samples) == decoded.frame_count
        assert max(decoded.samples) == pytest.approx(0.2, abs=5e-3)
        assert min(decoded.samples) == pytest.approx(-0.2, abs=5e-3)
        assert all(-1.0 <= value <= 1.0 for value in decoded.samples)

    def test_every_sample_is_a_float(self, tmp_path: Path) -> None:
        decoded = decode_with_wave(_mono_wav(tmp_path))
        assert all(isinstance(value, float) for value in decoded.samples)

    def test_stereo_channels_stay_interleaved(self, tmp_path: Path) -> None:
        wav = write_sine_wav(tmp_path / "stereo.wav", seconds=0.5, channels=2)
        decoded = decode_with_wave(wav, mono=False)

        assert decoded.channels == 2
        assert not decoded.is_mono
        assert decoded.frame_count == 22050
        assert len(decoded.samples) == decoded.frame_count * 2

    def test_mono_flag_averages_the_channels(self, tmp_path: Path) -> None:
        wav = write_sine_wav(tmp_path / "stereo.wav", seconds=0.5, channels=2)
        decoded = decode_with_wave(wav, mono=True)

        assert decoded.channels == 1
        assert decoded.frame_count == 22050

    def test_offset_and_duration_select_a_window(self, tmp_path: Path) -> None:
        wav = _mono_wav(tmp_path, seconds=2.0)
        decoded = decode_with_wave(wav, offset=0.5, duration=0.25)

        assert decoded.duration == pytest.approx(0.25, abs=1e-3)
        assert decoded.frame_count == pytest.approx(11025, abs=2)

    def test_a_window_past_the_end_yields_no_samples(self, tmp_path: Path) -> None:
        decoded = decode_with_wave(_mono_wav(tmp_path), offset=5.0)
        assert decoded.frame_count == 0
        assert decoded.duration == 0.0

    def test_a_missing_file_is_reported(self, tmp_path: Path) -> None:
        with pytest.raises(AudioFileNotFoundError):
            decode_with_wave(tmp_path / "absent.wav")

    def test_a_directory_is_reported(self, tmp_path: Path) -> None:
        directory = tmp_path / "folder.wav"
        directory.mkdir()
        with pytest.raises(InputError, match="directory"):
            decode_with_wave(directory)

    def test_a_non_wav_payload_is_reported(self, tmp_path: Path) -> None:
        junk = write_wav_bytes(tmp_path / "notes.flac")
        with pytest.raises(UnsupportedAudioError):
            decode_with_wave(junk)

    def test_a_negative_offset_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(InputError, match="offset"):
            decode_with_wave(_mono_wav(tmp_path), offset=-1.0)

    def test_a_non_positive_duration_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(InputError, match="duration"):
            decode_with_wave(_mono_wav(tmp_path), duration=0.0)


class TestDecodeAudioService:
    def test_an_unknown_backend_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(InputError, match="backend"):
            decode_audio(_mono_wav(tmp_path), backend="magic")

    def test_auto_decodes_a_wav_on_any_machine(self, tmp_path: Path) -> None:
        decoded = decode_audio(_mono_wav(tmp_path), backend=BACKEND_AUTO)

        assert decoded.backend in {BACKEND_DSP, BACKEND_WAVE}
        assert decoded.sample_rate == 44100
        assert decoded.channels == 1
        assert decoded.duration == pytest.approx(1.0, abs=1e-3)

    def test_the_wave_backend_refuses_to_resample(self, tmp_path: Path) -> None:
        """Silently ignoring a requested rate would be a lie about the samples."""
        wav = _mono_wav(tmp_path)
        with pytest.raises(DependencyError, match="Resampling") as excinfo:
            decode_audio(wav, sample_rate=8000, backend=BACKEND_WAVE)
        assert "pip install" in str(excinfo.value)

    def test_forcing_the_dsp_backend_without_it_is_a_dependency_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from song_chord_lyrics_analyzer.audio import decode as decode_module

        def _unavailable() -> tuple[object, object]:
            raise DependencyError("no numpy here", hint="pip install numpy librosa")

        monkeypatch.setattr(decode_module, "_import_dsp", _unavailable)
        with pytest.raises(DependencyError, match="numpy"):
            decode_audio(_mono_wav(tmp_path), backend=BACKEND_DSP)

    def test_a_missing_file_is_reported_by_the_service(self, tmp_path: Path) -> None:
        with pytest.raises(AudioFileNotFoundError):
            decode_audio(tmp_path / "absent.wav", backend=BACKEND_WAVE)


@requires_dsp
class TestDspDecoder:
    """The librosa half: compressed formats and rate conversion."""

    def test_auto_prefers_the_dsp_backend(self, tmp_path: Path) -> None:
        assert decode_audio(_mono_wav(tmp_path)).backend == BACKEND_DSP

    def test_samples_are_float32_and_in_range(self, tmp_path: Path) -> None:
        decoded = decode_audio(_mono_wav(tmp_path), backend=BACKEND_DSP)
        assert decoded.samples.dtype.name == "float32"
        assert float(abs(decoded.samples).max()) == pytest.approx(0.2, abs=5e-3)

    def test_resampling_to_a_target_rate(self, tmp_path: Path) -> None:
        decoded = decode_audio(_mono_wav(tmp_path), sample_rate=8000, backend=BACKEND_DSP)

        assert decoded.sample_rate == 8000
        assert decoded.duration == pytest.approx(1.0, abs=5e-3)
        assert decoded.frame_count == pytest.approx(8000, abs=40)

    def test_stereo_channels_stay_interleaved(self, tmp_path: Path) -> None:
        # The fixture writes the same tone into both channels, so interleaving
        # must put the identical sample at even and odd offsets.
        wav = write_sine_wav(tmp_path / "stereo.wav", seconds=0.5, channels=2)
        decoded = decode_audio(wav, mono=False, backend=BACKEND_DSP)

        assert decoded.channels == 2
        assert len(decoded.samples) == decoded.frame_count * 2
        left = decoded.samples[0::2]
        right = decoded.samples[1::2]
        assert [float(value) for value in left] == pytest.approx(
            [float(value) for value in right], abs=1e-6
        )

    def test_the_dsp_and_wave_backends_agree_on_a_wav(self, tmp_path: Path) -> None:
        wav = _mono_wav(tmp_path, seconds=0.5)
        dsp = decode_audio(wav, backend=BACKEND_DSP)
        stdlib = decode_audio(wav, backend=BACKEND_WAVE)

        assert dsp.sample_rate == stdlib.sample_rate
        assert dsp.channels == stdlib.channels
        assert dsp.duration == pytest.approx(stdlib.duration, abs=1e-3)
        assert [float(value) for value in dsp.samples] == pytest.approx(stdlib.samples, abs=5e-3)

    def test_the_window_matches_the_wave_backend(self, tmp_path: Path) -> None:
        wav = _mono_wav(tmp_path, seconds=2.0)
        dsp = decode_audio(wav, offset=0.5, duration=0.25, backend=BACKEND_DSP)
        stdlib = decode_audio(wav, offset=0.5, duration=0.25, backend=BACKEND_WAVE)

        assert dsp.duration == pytest.approx(stdlib.duration, abs=1e-3)
        assert dsp.frame_count == pytest.approx(stdlib.frame_count, abs=2)

    def test_the_backend_label_is_recorded(self, tmp_path: Path) -> None:
        assert decode_audio(_mono_wav(tmp_path)).backend == BACKEND_DSP

    def test_the_dsp_backend_reads_a_generated_tone(self, tmp_path: Path) -> None:
        decoded = decode_audio(_mono_wav(tmp_path), backend=BACKEND_DSP)
        assert decoded.duration == pytest.approx(1.0, abs=5e-3)
        assert decoded.frame_count == pytest.approx(44100, abs=40)
