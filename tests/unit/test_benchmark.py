"""Benchmark command (roadmap section 46): case loading, scoring and reports."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from fixtures.audio import write_sine_wav
from fixtures.fake_chord_engine import FakeChordEngine
from song_chord_lyrics_analyzer.benchmark import (
    BenchmarkCase,
    build_report,
    load_case,
    load_cases,
    score_case,
    to_csv,
    to_json,
    to_markdown,
    write_reports,
)
from song_chord_lyrics_analyzer.cli.main import main
from song_chord_lyrics_analyzer.engines import EngineRegistry
from song_chord_lyrics_analyzer.utils.errors import InputError

FULL_CASE = {
    "song": "song_a",
    "engine": "engine-x",
    "engine_version": "1.0",
    "model": "tiny",
    "duration_seconds": 30.0,
    "processing_time_seconds": 12.0,
    "peak_memory_bytes": 111,
    "reference": {
        "lyrics_text": "hola mundo",
        "lyrics_words": [{"text": "hola", "start": 0.0}, {"text": "mundo", "start": 1.0}],
        "chords": [
            {"start": 0.0, "end": 4.0, "label": "C"},
            {"start": 4.0, "end": 8.0, "label": "G"},
        ],
        "chord_labels": ["C", "G"],
        "key": "C major",
        "tempo_bpm": 120.0,
    },
    "hypothesis": {
        "lyrics_text": "hola Mundo!",
        "lyrics_words": [{"text": "hola", "start": 0.1}, {"text": "mundo", "start": 0.9}],
        "chords": [
            {"start": 0.0, "end": 4.0, "label": "C"},
            {"start": 4.0, "end": 8.0, "label": "G"},
        ],
        "chord_labels": ["C", "G"],
        "key": "A minor",
        "tempo_bpm": 60.0,
    },
}


def _write_cases(directory: Path, *documents: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for index, document in enumerate(documents):
        (directory / f"case_{index}.json").write_text(json.dumps(document), encoding="utf-8")
    return directory


class TestLoadCases:
    def test_loads_a_directory_in_filename_order(self, tmp_path: Path) -> None:
        directory = _write_cases(tmp_path / "cases", FULL_CASE, {**FULL_CASE, "song": "song_b"})
        cases = load_cases(directory)
        assert [case.song for case in cases] == ["song_a", "song_b"]

    def test_missing_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(InputError):
            load_cases(tmp_path / "nope")

    def test_empty_directory_raises(self, tmp_path: Path) -> None:
        (tmp_path / "empty").mkdir()
        with pytest.raises(InputError):
            load_cases(tmp_path / "empty")

    def test_missing_field_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"reference": {}, "hypothesis": {}}), encoding="utf-8")
        with pytest.raises(InputError, match="song"):
            load_case(path)

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(InputError, match="valid JSON"):
            load_case(path)


class TestScoreCase:
    def test_every_family_is_scored(self) -> None:
        case = BenchmarkCase(
            song="song_a",
            reference=FULL_CASE["reference"],
            hypothesis=FULL_CASE["hypothesis"],
            engine="engine-x",
        )
        metrics = score_case(case)["metrics"]
        assert metrics["lyrics.wer"] == 0.0
        assert metrics["lyrics.word_timestamp_matched_words"] == 2.0
        assert metrics["chords.segment_overlap"] == 1.0
        assert metrics["chords.exact_f1"] == 1.0
        assert metrics["key.relation"] == "relative"
        assert metrics["key.exact"] == 0.0
        assert metrics["key.relative"] == 1.0
        assert metrics["tempo.half_tempo_error"] == 0.0
        assert metrics["tempo.interpretation"] == "half"

    def test_only_supported_families_are_reported(self) -> None:
        case = BenchmarkCase(
            song="song_a",
            reference={"key": "C major"},
            hypothesis={"key": "C major"},
        )
        metrics = score_case(case)["metrics"]
        assert set(metrics) == {"key.relation", "key.weighted_score", "key.exact", "key.relative"}

    def test_empty_reference_text_is_not_scored(self) -> None:
        case = BenchmarkCase(
            song="song_a",
            reference={"lyrics_text": "!!!"},
            hypothesis={"lyrics_text": "hi"},
        )
        assert score_case(case)["metrics"] == {}

    def test_performance_real_time_factor_is_reported_for_a_recorded_run(self) -> None:
        case = BenchmarkCase(
            song="song_a",
            reference={},
            hypothesis={},
            duration_seconds=30.0,
            processing_time_seconds=12.0,
        )
        assert score_case(case)["metrics"]["performance.real_time_factor"] == 2.5

    def test_performance_is_absent_without_a_recorded_run(self) -> None:
        case = BenchmarkCase(
            song="song_a",
            reference={},
            hypothesis={},
            duration_seconds=30.0,
        )
        assert "performance.real_time_factor" not in score_case(case)["metrics"]

        zero_processing = BenchmarkCase(
            song="song_b",
            reference={},
            hypothesis={},
            duration_seconds=30.0,
            processing_time_seconds=0.0,
        )
        assert "performance.real_time_factor" not in score_case(zero_processing)["metrics"]


class TestBuildReport:
    def test_summary_averages_per_engine(self) -> None:
        cases = [
            BenchmarkCase("a", {"key": "C major"}, {"key": "C major"}, engine="x"),
            BenchmarkCase("b", {"key": "C major"}, {"key": "A minor"}, engine="x"),
        ]
        report = build_report(cases)
        assert report["summary"]["x"]["cases"] == 2
        assert report["summary"]["x"]["key.exact"] == 0.5
        assert report["summary"]["x"]["key.relative"] == 0.5


class TestReportWriters:
    def _report(self) -> dict:
        return build_report(
            [
                BenchmarkCase(
                    "song_a",
                    FULL_CASE["reference"],
                    FULL_CASE["hypothesis"],
                    engine="engine-x",
                )
            ]
        )

    def test_json_round_trips(self) -> None:
        payload = json.loads(to_json(self._report()))
        assert payload["cases"][0]["song"] == "song_a"
        assert payload["cases"][0]["metrics"]["key.relation"] == "relative"

    def test_csv_has_one_row_per_case_and_metric_columns(self) -> None:
        rows = list(csv.reader(io.StringIO(to_csv(self._report()))))
        assert rows[0][:2] == ["song", "engine"]
        assert "lyrics.wer" in rows[0]
        assert len(rows) == 2
        assert rows[1][0] == "song_a"

    def test_markdown_has_summary_and_cases(self) -> None:
        markdown = to_markdown(self._report())
        assert "# Benchmark" in markdown
        assert "## Summary (mean per engine)" in markdown
        assert "## Cases" in markdown
        assert "song_a" in markdown

    def test_write_reports_creates_three_files(self, tmp_path: Path) -> None:
        written = write_reports(self._report(), tmp_path / "out")
        assert sorted(path.name for path in written) == [
            "benchmark.csv",
            "benchmark.json",
            "benchmark.md",
        ]
        assert all(path.exists() for path in written)


class TestBenchmarkCommand:
    def test_writes_reports_and_prints_summary(self, tmp_path: Path, capsys) -> None:
        cases = _write_cases(tmp_path / "cases", FULL_CASE)
        output = tmp_path / "out"
        assert main(["benchmark", str(cases), "--output", str(output)]) == 0
        assert "Benchmark" in capsys.readouterr().out
        assert (output / "benchmark.json").exists()

    def test_json_flag_prints_the_report(self, tmp_path: Path, capsys) -> None:
        cases = _write_cases(tmp_path / "cases", FULL_CASE)
        assert main(["benchmark", str(cases), "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["cases"][0]["song"] == "song_a"

    def test_missing_directory_is_an_input_error(self, tmp_path: Path, capsys) -> None:
        assert main(["benchmark", str(tmp_path / "nope"), "--output", str(tmp_path / "out")]) == 2
        assert "not found" in capsys.readouterr().err


class TestBenchmarkWithEngine:
    """``--engine`` runs a chord engine over cases that declare audio."""

    def _audio_case(self, tmp_path: Path) -> Path:
        cases_dir = tmp_path / "cases"
        cases_dir.mkdir()
        write_sine_wav(cases_dir / "song.wav", seconds=1.0)
        document = {
            "song": "song_a",
            "audio": "song.wav",
            "reference": {
                "chords": [{"start": 0.0, "end": 2.0, "label": "C"}],
                "chord_labels": ["C"],
            },
            "hypothesis": {},
        }
        (cases_dir / "case_0.json").write_text(json.dumps(document), encoding="utf-8")
        return cases_dir

    def _patch_registry(self, monkeypatch, engine: FakeChordEngine) -> None:
        registry = EngineRegistry()
        registry.register(engine)
        monkeypatch.setattr(
            "song_chord_lyrics_analyzer.cli.commands.benchmark.create_default_registry",
            lambda: registry,
        )

    def test_engine_run_fills_the_report_with_measured_cost(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        self._patch_registry(monkeypatch, FakeChordEngine())
        cases = self._audio_case(tmp_path)
        output = tmp_path / "out"

        assert (
            main(["benchmark", str(cases), "--output", str(output), "--engine", "fake-chords"]) == 0
        )

        out = capsys.readouterr().out
        assert "Engine runs" in out
        assert "2 chords in 2.500 s" in out
        assert "real-time factor 1.60" in out
        payload = json.loads((output / "benchmark.json").read_text(encoding="utf-8"))
        row = payload["cases"][0]
        assert row["engine"] == "fake-chords"
        assert row["processing_time_seconds"] == 2.5
        assert row["peak_memory_bytes"] == 4_242_424
        assert row["metrics"]["performance.real_time_factor"] == 1.6
        # ref ["C"] vs hyp ["C", "G"]: precision 1/2, recall 1/1 -> F1 2/3
        assert row["metrics"]["chords.exact_f1"] == pytest.approx(2 / 3)

    def test_json_output_stays_pure_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        self._patch_registry(monkeypatch, FakeChordEngine())
        cases = self._audio_case(tmp_path)

        assert main(["benchmark", str(cases), "--json", "--engine", "fake-chords"]) == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload["cases"][0]["engine"] == "fake-chords"

    def test_unknown_engine_lists_the_registered_ones(self, tmp_path: Path, capsys) -> None:
        cases = self._audio_case(tmp_path)
        assert main(["benchmark", str(cases), "--engine", "nope"]) == 2
        err = capsys.readouterr().err
        assert "Unknown" in err
        assert "chroma-baseline" in err

    def test_unavailable_engine_is_a_dependency_error(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        self._patch_registry(monkeypatch, FakeChordEngine(available=False))
        cases = self._audio_case(tmp_path)
        assert main(["benchmark", str(cases), "--engine", "fake-chords"]) == 3
        assert "not available" in capsys.readouterr().err

    def test_without_the_flag_nothing_is_run(self, tmp_path: Path, capsys) -> None:
        cases = self._audio_case(tmp_path)
        output = tmp_path / "out"
        assert main(["benchmark", str(cases), "--output", str(output)]) == 0
        assert "Engine runs" not in capsys.readouterr().out
        payload = json.loads((output / "benchmark.json").read_text(encoding="utf-8"))
        assert payload["cases"][0]["engine"] is None
        assert "chords.exact_f1" not in payload["cases"][0]["metrics"]
