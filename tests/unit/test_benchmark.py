"""Benchmark command (roadmap section 46): case loading, scoring and reports."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

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
