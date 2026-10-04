"""Benchmark engine runs (roadmap sections 45 and 46): the case runner.

The runner is the piece that finally lets ``songlab benchmark`` report numbers
somebody actually measured: the engine fills the hypothesis, and its section
45 performance block fills duration, processing time and peak memory. The
reference side and cases without audio are never touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fixtures.fake_chord_engine import FakeChordEngine
from song_chord_lyrics_analyzer.benchmark import BenchmarkCase, build_report, run_engine_on_cases
from song_chord_lyrics_analyzer.models.music import ChordEvent, ChordQuality
from song_chord_lyrics_analyzer.utils.errors import (
    AudioFileNotFoundError,
    DependencyError,
    InputError,
)


def _case(audio: str | None = "song.wav", **overrides) -> BenchmarkCase:
    values = {
        "song": "song_a",
        "reference": {
            "chords": [
                {"start": 0.0, "end": 2.0, "label": "C"},
                {"start": 2.0, "end": 4.0, "label": "G"},
            ],
            "chord_labels": ["C", "G"],
        },
        "hypothesis": {"lyrics_text": "stored"},
        "audio": audio,
    }
    values.update(overrides)
    return BenchmarkCase(**values)


def _write_case(directory: Path, document: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "case.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


class TestRunEngineOnCases:
    def test_hypothesis_and_measured_cost_are_filled(self, tmp_path: Path) -> None:
        (tmp_path / "song.wav").write_bytes(b"RIFFfake")
        case = _case(source=tmp_path / "case.json")
        engine = FakeChordEngine()

        updated, runs = run_engine_on_cases([case], engine)

        result = updated[0]
        assert result.hypothesis["chords"] == [
            {"start": 0.0, "end": 2.0, "label": "C"},
            {"start": 2.0, "end": 4.0, "label": "G"},
        ]
        assert result.hypothesis["chord_labels"] == ["C", "G"]
        assert result.engine == "fake-chords"
        assert result.engine_version == "9.9.0"
        assert result.processing_time_seconds == 2.5
        assert result.peak_memory_bytes == 4_242_424
        assert result.duration_seconds == 4.0
        # stored fields the engine knows nothing about survive
        assert result.hypothesis["lyrics_text"] == "stored"

        assert len(runs) == 1
        assert runs[0].chord_count == 2
        assert runs[0].processing_time_seconds == 2.5

    def test_input_cases_are_never_mutated(self, tmp_path: Path) -> None:
        (tmp_path / "song.wav").write_bytes(b"RIFFfake")
        case = _case(source=tmp_path / "case.json")

        updated, _ = run_engine_on_cases([case], FakeChordEngine())

        assert case.hypothesis == {"lyrics_text": "stored"}
        assert case.engine is None
        assert updated[0] is not case

    def test_case_without_audio_keeps_its_stored_hypothesis(self) -> None:
        case = _case(audio=None)
        engine = FakeChordEngine()

        updated, runs = run_engine_on_cases([case], engine)

        assert updated[0] is case
        assert updated[0].hypothesis == {"lyrics_text": "stored"}
        assert runs == []
        assert engine.calls == []

    def test_relative_audio_is_resolved_against_the_case_file(self, tmp_path: Path) -> None:
        (tmp_path / "song.wav").write_bytes(b"RIFFfake")
        case = _case(audio="song.wav", source=tmp_path / "case.json")
        engine = FakeChordEngine()

        _, runs = run_engine_on_cases([case], engine)

        assert engine.calls == [tmp_path / "song.wav"]
        assert runs[0].audio == tmp_path / "song.wav"

    def test_stored_duration_wins_over_the_measured_window(self, tmp_path: Path) -> None:
        (tmp_path / "song.wav").write_bytes(b"RIFFfake")
        case = _case(source=tmp_path / "case.json", duration_seconds=99.0)

        updated, _ = run_engine_on_cases([case], FakeChordEngine())

        assert updated[0].duration_seconds == 99.0

    def test_missing_final_end_is_completed_from_the_audio_duration(self, tmp_path: Path) -> None:
        (tmp_path / "song.wav").write_bytes(b"RIFFfake")
        open_ended = [
            ChordEvent(start=0.0, end=2.0, root="C", quality=ChordQuality.MAJOR),
            ChordEvent(start=2.0, end=None, root="G", quality=ChordQuality.MAJOR),
        ]
        case = _case(source=tmp_path / "case.json")

        updated, _ = run_engine_on_cases(
            [case], FakeChordEngine(chords=open_ended, audio_seconds=4.5)
        )

        assert updated[0].hypothesis["chords"][-1] == {
            "start": 2.0,
            "end": 4.5,
            "label": "G",
        }

    def test_undeterminable_end_is_a_user_facing_error(self, tmp_path: Path) -> None:
        (tmp_path / "song.wav").write_bytes(b"RIFFfake")
        open_ended = [ChordEvent(start=0.0, end=None, root="C", quality=ChordQuality.MAJOR)]
        case = _case(source=tmp_path / "case.json")

        with pytest.raises(InputError, match="cannot determine"):
            run_engine_on_cases([case], FakeChordEngine(chords=open_ended, audio_seconds=None))

    def test_unavailable_engine_is_refused_before_any_run(self) -> None:
        with pytest.raises(DependencyError, match="not available"):
            run_engine_on_cases([_case(audio=None)], FakeChordEngine(available=False))

    def test_missing_audio_file_is_reported(self, tmp_path: Path) -> None:
        case = _case(source=tmp_path / "case.json")  # no song.wav on disk
        with pytest.raises(AudioFileNotFoundError, match=r"song\.wav"):
            run_engine_on_cases([case], FakeChordEngine())

    def test_engine_crash_becomes_a_user_facing_error(self, tmp_path: Path) -> None:
        (tmp_path / "song.wav").write_bytes(b"RIFFfake")
        case = _case(source=tmp_path / "case.json")
        engine = FakeChordEngine(failure=RuntimeError("decoder exploded"))

        with pytest.raises(InputError, match="failed on case 'song_a'") as excinfo:
            run_engine_on_cases([case], engine)
        assert "decoder exploded" in str(excinfo.value)


class TestRunFeedsTheReport:
    def test_measured_numbers_reach_every_report_format(self, tmp_path: Path) -> None:
        (tmp_path / "song.wav").write_bytes(b"RIFFfake")
        case = _case(source=tmp_path / "case.json")

        updated, _ = run_engine_on_cases([case], FakeChordEngine())
        report = build_report(updated)

        metrics = report["cases"][0]["metrics"]
        assert metrics["chords.exact_f1"] == 1.0
        assert metrics["performance.real_time_factor"] == 4.0 / 2.5
        row = report["cases"][0]
        assert row["processing_time_seconds"] == 2.5
        assert row["peak_memory_bytes"] == 4_242_424
        assert report["summary"]["fake-chords"]["performance.real_time_factor"] == 1.6

    def test_empty_result_scores_zero_rather_than_disappearing(self, tmp_path: Path) -> None:
        (tmp_path / "song.wav").write_bytes(b"RIFFfake")
        case = _case(source=tmp_path / "case.json")

        updated, _ = run_engine_on_cases([case], FakeChordEngine(chords=[]))
        metrics = build_report(updated)["cases"][0]["metrics"]

        assert metrics["chords.exact_f1"] == 0.0
        assert metrics["chords.segment_overlap"] == 0.0
