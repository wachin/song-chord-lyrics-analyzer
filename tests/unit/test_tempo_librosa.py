"""Unit tests for the librosa tempo engine (roadmap sections 33 and 44).

The dependency-free half (metrical alternatives) is tested directly; the
librosa front end is exercised only where the optional DSP stack is installed,
exactly as :meth:`LibrosaTempoEngine.is_available` promises.
"""

from __future__ import annotations

import pytest

from fixtures.audio import write_click_wav
from song_chord_lyrics_analyzer.engines import EngineKind, LibrosaTempoEngine
from song_chord_lyrics_analyzer.engines import tempo_librosa as tempo_module
from song_chord_lyrics_analyzer.models.confidence import ConfidenceScore
from song_chord_lyrics_analyzer.utils.errors import AudioFileNotFoundError, DependencyError

ENGINE = LibrosaTempoEngine()


class TestMetricalAlternatives:
    def test_half_and_double_readings_are_both_reported(self) -> None:
        assert tempo_module.metrical_alternatives(120.0) == [60.0, 240.0]

    def test_a_non_positive_bpm_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            tempo_module.metrical_alternatives(0.0)

    def test_a_non_finite_bpm_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            tempo_module.metrical_alternatives(float("nan"))


class TestEngineContract:
    def test_identity(self) -> None:
        assert ENGINE.name == "librosa-tempo"
        assert ENGINE.kind is EngineKind.TEMPO

    def test_is_available_reports_a_plain_bool(self) -> None:
        assert isinstance(ENGINE.is_available(), bool)

    def test_engine_info_declares_that_it_reports_no_confidence(self) -> None:
        info = ENGINE.engine_info()
        assert info.name == "librosa-tempo"
        assert info.kind == "tempo"
        assert info.version
        assert info.license == "GPL-3.0-or-later"
        assert info.capabilities["half_double_alternatives"] is True
        assert info.capabilities["confidence"] is False

    def test_missing_audio_file_is_reported(self, tmp_path) -> None:
        with pytest.raises(AudioFileNotFoundError):
            ENGINE.detect_tempo(tmp_path / "absent.wav", {})

    def test_missing_dsp_stack_is_a_dependency_error(self, tmp_path, monkeypatch) -> None:
        wav = write_click_wav(tmp_path / "clicks.wav", bpm=120.0, beats=4)

        def _unavailable() -> None:
            raise ImportError("no numpy here")

        monkeypatch.setattr(tempo_module, "_import_front_end", _unavailable)
        with pytest.raises(DependencyError, match="numpy and librosa") as excinfo:
            ENGINE.detect_tempo(wav, {})
        assert "pip install" in str(excinfo.value)
        assert ENGINE.is_available() is False


@pytest.mark.skipif(
    not ENGINE.is_available(),
    reason="optional DSP stack (numpy/librosa) not installed",
)
class TestFullAnalysis:
    """End-to-end runs; executed only where the optional front end exists."""

    def test_a_click_track_is_tracked_within_a_few_bpm(self, tmp_path) -> None:
        wav = write_click_wav(tmp_path / "clicks.wav", bpm=120.0, beats=24)

        result = ENGINE.detect_tempo(wav, {})

        assert result.engine == "librosa-tempo"
        assert result.tempo is not None
        # librosa reads a 120 BPM click track slightly under 120 (117.45
        # measured); a few BPM of tolerance is the honest bound for a baseline.
        assert result.tempo.bpm == pytest.approx(120.0, abs=3.0)
        assert result.tempo.source == "librosa-tempo"
        assert result.tempo.is_ambiguous
        assert result.tempo.alternatives == pytest.approx(
            [result.tempo.bpm / 2, result.tempo.bpm * 2]
        )

    def test_confidence_is_unknown_rather_than_invented(self, tmp_path) -> None:
        wav = write_click_wav(tmp_path / "clicks.wav", bpm=120.0, beats=24)

        result = ENGINE.detect_tempo(wav, {})

        assert result.tempo is not None
        assert result.tempo.confidence == ConfidenceScore.unknown("librosa-tempo")
        assert result.tempo.confidence.is_known is False

    def test_run_cost_is_measured_not_estimated(self, tmp_path) -> None:
        wav = write_click_wav(tmp_path / "clicks.wav", bpm=120.0, beats=24)

        result = ENGINE.detect_tempo(wav, {})

        assert result.processing_time_seconds is not None
        assert result.processing_time_seconds > 0.0
        performance = result.metadata["performance"]
        assert performance["audio_seconds"] == pytest.approx(12.0, abs=0.2)
        assert performance["device"] == "cpu"
