"""Unit tests for the Krumhansl-Schmuckler key engine (roadmap sections 31/32).

The dependency-free correlation half is tested directly; the librosa front end
is exercised only where the optional DSP stack is installed, exactly as
:meth:`KrumhanslKeyEngine.is_available` promises.
"""

from __future__ import annotations

import pytest

from fixtures.audio import write_chord_wav
from song_chord_lyrics_analyzer.engines import EngineKind, KrumhanslKeyEngine
from song_chord_lyrics_analyzer.engines import key_krumhansl as key_module
from song_chord_lyrics_analyzer.models.music import KeyMode
from song_chord_lyrics_analyzer.utils.errors import AudioFileNotFoundError, DependencyError

ENGINE = KrumhanslKeyEngine()

_MAJOR = key_module.MAJOR_PROFILE
_MINOR = key_module.MINOR_PROFILE
#: The C-rooted minor profile rotated so A (pitch class 9) is the tonic.
_A_MINOR = tuple(_MINOR[(index - 9) % 12] for index in range(12))


class TestPearsonCorrelation:
    def test_identical_sequences_correlate_at_one(self) -> None:
        assert key_module.pearson_correlation([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(
            1.0
        )

    def test_reversed_sequences_correlate_at_minus_one(self) -> None:
        assert key_module.pearson_correlation([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]) == pytest.approx(
            -1.0
        )

    def test_a_flat_sequence_has_no_correlation(self) -> None:
        assert key_module.pearson_correlation([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) == 0.0

    def test_empty_sequences_correlate_at_zero(self) -> None:
        assert key_module.pearson_correlation([], []) == 0.0

    def test_a_length_mismatch_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="equal lengths"):
            key_module.pearson_correlation([1.0], [1.0, 2.0])


class TestEstimateKey:
    def test_the_c_major_profile_maps_to_c_major(self) -> None:
        candidate = key_module.estimate_key(_MAJOR)
        assert candidate is not None
        assert candidate.tonic == "C"
        assert candidate.mode is KeyMode.MAJOR
        assert candidate.correlation == pytest.approx(1.0)

    def test_the_a_minor_profile_maps_to_a_minor(self) -> None:
        candidate = key_module.estimate_key(_A_MINOR)
        assert candidate is not None
        assert candidate.tonic == "A"
        assert candidate.mode is KeyMode.MINOR

    def test_rotating_the_profile_moves_the_tonic(self) -> None:
        d_major = tuple(_MAJOR[(index - 2) % 12] for index in range(12))
        candidate = key_module.estimate_key(d_major)
        assert candidate is not None
        assert candidate.tonic == "D"
        assert candidate.mode is KeyMode.MAJOR

    def test_a_tonic_heavy_pitch_class_profile_picks_that_key(self) -> None:
        profile = [0.1] * 12
        for pitch in (0, 4, 7):
            profile[pitch] = 1.0
        candidate = key_module.estimate_key(profile)
        assert candidate is not None
        assert candidate.tonic == "C"
        assert candidate.mode is KeyMode.MAJOR

    def test_a_silent_profile_yields_no_key(self) -> None:
        assert key_module.estimate_key([0.0] * 12) is None

    def test_a_wrong_length_profile_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="12 values"):
            key_module.estimate_key([1.0] * 11)


class TestEngineContract:
    def test_identity(self) -> None:
        assert ENGINE.name == "krumhansl"
        assert ENGINE.kind is EngineKind.KEY

    def test_is_available_reports_a_plain_bool(self) -> None:
        assert isinstance(ENGINE.is_available(), bool)

    def test_engine_info_describes_capabilities(self) -> None:
        info = ENGINE.engine_info()
        assert info.name == "krumhansl"
        assert info.kind == "key"
        assert info.version
        assert info.license == "GPL-3.0-or-later"
        assert info.capabilities["profiles"] == "krumhansl-kessler"

    def test_missing_audio_file_is_reported(self, tmp_path) -> None:
        with pytest.raises(AudioFileNotFoundError):
            ENGINE.detect_key(tmp_path / "absent.wav", {})

    def test_missing_dsp_stack_is_a_dependency_error(self, tmp_path, monkeypatch) -> None:
        wav = write_chord_wav(tmp_path / "tone.wav", chords=[(0, 4, 7)], seconds_per_chord=0.2)

        def _unavailable() -> None:
            raise ImportError("no numpy here")

        monkeypatch.setattr(key_module, "_import_front_end", _unavailable)
        with pytest.raises(DependencyError, match="numpy and librosa") as excinfo:
            ENGINE.detect_key(wav, {})
        assert "pip install" in str(excinfo.value)
        assert ENGINE.is_available() is False


@pytest.mark.skipif(
    not ENGINE.is_available(),
    reason="optional DSP stack (numpy/librosa) not installed",
)
class TestFullAnalysis:
    """End-to-end runs; executed only where the optional front end exists."""

    def test_a_c_major_progression_is_read_as_c_major(self, tmp_path) -> None:
        wav = write_chord_wav(
            tmp_path / "progression.wav",
            chords=[(0, 4, 7), (5, 9, 0), (7, 11, 2), (0, 4, 7)],
            seconds_per_chord=1.0,
        )
        result = ENGINE.detect_key(wav, {})

        assert result.engine == "krumhansl"
        assert result.key is not None
        assert result.key.tonic == "C"
        assert result.key.mode is KeyMode.MAJOR
        assert result.key.source == "krumhansl"
        assert result.key.confidence.value is not None
        assert 0.0 <= result.key.confidence.value <= 1.0
        assert result.processing_time_seconds is not None
        assert result.processing_time_seconds > 0.0
        assert result.metadata["performance"]["audio_seconds"] == pytest.approx(4.0, abs=0.2)
        assert len(result.raw["pitch_class_profile"]) == 12
