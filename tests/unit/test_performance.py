"""Unit tests for the section 45 performance harness.

Every figure must come from a real measurement on the machine running the
test: a number the platform cannot report stays ``None`` instead of being
guessed (roadmap sections 43 and 45).
"""

from __future__ import annotations

import math
import time

import pytest

from song_chord_lyrics_analyzer.performance import (
    PerformanceProbe,
    PerformanceReport,
    free_disk_bytes,
    measure_performance,
    model_size_bytes,
    peak_rss_bytes,
    real_time_factor,
)


class TestRealTimeFactor:
    def test_audio_per_computation_ratio(self) -> None:
        assert real_time_factor(60.0, 30.0) == 2.0

    def test_faster_than_real_time_is_above_one(self) -> None:
        factor = real_time_factor(35.208, 18.84)
        assert factor is not None
        assert factor > 1.0

    def test_missing_audio_duration_is_not_guessed(self) -> None:
        assert real_time_factor(None, 10.0) is None

    def test_missing_processing_time_is_not_guessed(self) -> None:
        assert real_time_factor(60.0, None) is None

    @pytest.mark.parametrize(
        ("audio", "processing"),
        [(0.0, 10.0), (60.0, 0.0), (-1.0, 10.0), (60.0, -10.0)],
    )
    def test_non_positive_inputs_have_no_factor(self, audio: float, processing: float) -> None:
        assert real_time_factor(audio, processing) is None

    @pytest.mark.parametrize(
        ("audio", "processing"),
        [(math.inf, 10.0), (60.0, math.nan), (math.nan, math.nan)],
    )
    def test_non_finite_inputs_have_no_factor(self, audio: float, processing: float) -> None:
        assert real_time_factor(audio, processing) is None


class TestPlatformMeasurements:
    def test_peak_rss_is_a_real_positive_number_when_available(self) -> None:
        value = peak_rss_bytes()
        if value is not None:
            assert isinstance(value, int)
            assert value > 0

    def test_model_size_reads_a_file(self, tmp_path) -> None:
        target = tmp_path / "weights.bin"
        target.write_bytes(b"x" * 1024)
        assert model_size_bytes(target) == 1024

    def test_model_size_sums_a_directory_tree(self, tmp_path) -> None:
        (tmp_path / "a").write_bytes(b"y" * 100)
        nested = tmp_path / "nested"
        nested.mkdir()
        (nested / "b").write_bytes(b"z" * 50)
        assert model_size_bytes(tmp_path) == 150

    def test_missing_model_is_not_reported_as_zero(self, tmp_path) -> None:
        assert model_size_bytes(tmp_path / "absent") is None

    def test_free_disk_is_a_real_positive_number(self, tmp_path) -> None:
        value = free_disk_bytes(tmp_path)
        assert value is not None
        assert value > 0


class TestPerformanceProbe:
    def test_start_stop_measures_positive_wall_time(self) -> None:
        probe = PerformanceProbe()
        probe.start()
        time.sleep(0.02)
        report = probe.stop()
        assert report.processing_time_seconds >= 0.02
        assert probe.report is report

    def test_stop_before_start_is_rejected(self) -> None:
        probe = PerformanceProbe()
        with pytest.raises(RuntimeError, match="before start"):
            probe.stop()

    def test_double_start_is_rejected(self) -> None:
        probe = PerformanceProbe()
        probe.start()
        with pytest.raises(RuntimeError, match="twice"):
            probe.start()
        probe.stop()

    def test_real_time_factor_uses_audio_set_before_stop(self) -> None:
        probe = PerformanceProbe(audio_seconds=60.0)
        probe.start()
        report = probe.stop()
        assert report.audio_seconds == 60.0
        assert report.real_time_factor is not None
        assert report.real_time_factor > 0.0

    def test_report_defaults_honestly(self) -> None:
        report = PerformanceReport(processing_time_seconds=1.0)
        assert report.device == "cpu"
        assert report.vram_bytes is None  # CPU run: no VRAM figure, ever
        assert report.peak_rss_bytes is None
        assert report.real_time_factor is None

    def test_model_and_disk_sizes_are_attached_when_paths_are_given(self, tmp_path) -> None:
        weights = tmp_path / "model.bin"
        weights.write_bytes(b"m" * 2048)
        probe = PerformanceProbe(model_path=weights, disk_path=tmp_path)
        probe.start()
        report = probe.stop()
        assert report.model_size_bytes == 2048
        assert report.disk_free_bytes is not None
        assert report.disk_free_bytes > 0

    def test_no_model_path_means_no_model_size(self) -> None:
        probe = PerformanceProbe()
        probe.start()
        report = probe.stop()
        assert report.model_size_bytes is None
        assert report.disk_free_bytes is None

    def test_tracemalloc_reports_python_peak_when_requested(self) -> None:
        with measure_performance(trace_python=True) as probe:
            _ = [0] * 100_000
        assert probe.report is not None
        assert probe.report.peak_python_bytes is not None
        assert probe.report.peak_python_bytes > 0

    def test_tracing_is_off_by_default(self) -> None:
        with measure_performance() as probe:
            pass
        assert probe.report is not None
        assert probe.report.peak_python_bytes is None

    def test_as_dict_is_json_friendly(self) -> None:
        report = PerformanceReport(processing_time_seconds=1.5, real_time_factor=2.0)
        payload = report.as_dict()
        assert payload["processing_time_seconds"] == 1.5
        assert payload["real_time_factor"] == 2.0
        assert payload["device"] == "cpu"
        assert payload["vram_bytes"] is None


class TestMeasurePerformance:
    def test_context_manager_reports_after_the_block(self) -> None:
        with measure_performance(audio_seconds=10.0) as probe:
            time.sleep(0.01)
        assert probe.report is not None
        assert probe.report.processing_time_seconds >= 0.01
        assert probe.report.real_time_factor is not None

    def test_report_is_still_recorded_when_the_block_fails(self) -> None:
        probe = PerformanceProbe(audio_seconds=1.0)
        with pytest.raises(ValueError, match="boom"), probe:
            raise ValueError("boom")
        assert probe.report is not None
        assert probe.report.processing_time_seconds >= 0.0
