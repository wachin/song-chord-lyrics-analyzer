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
from fixtures.fake_key_tempo_engines import FakeKeyEngine, FakeLyricsEngine, FakeTempoEngine
from song_chord_lyrics_analyzer.benchmark import BenchmarkCase, build_report, run_engine_on_cases
from song_chord_lyrics_analyzer.engines.base import EngineKind
from song_chord_lyrics_analyzer.models.analysis import EngineInfo
from song_chord_lyrics_analyzer.models.music import ChordEvent, ChordQuality, KeyMode
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
        assert runs[0].kind == "chords"
        assert runs[0].summary == "2 chords"
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


class _BeatStub:
    """An engine kind the benchmark cannot score yet."""

    name = "fake-beats"
    kind = EngineKind.BEATS

    def is_available(self) -> bool:
        return True

    def engine_info(self) -> EngineInfo:
        return EngineInfo(name=self.name, kind=self.kind.value)

    def detect_beats(self, audio_path: Path, options: dict) -> object:  # pragma: no cover
        raise AssertionError("an unscoreable engine must never be run")


def _other_case(tmp_path: Path, reference: dict) -> BenchmarkCase:
    (tmp_path / "song.wav").write_bytes(b"RIFFfake")
    return BenchmarkCase(
        song="song_a",
        reference=reference,
        hypothesis={},
        audio="song.wav",
        source=tmp_path / "case.json",
    )


class TestRunOtherEngineKinds:
    """The runner dispatches on the engine kind and fills that family."""

    def test_key_engine_fills_and_scores_the_key_family(self, tmp_path: Path) -> None:
        case = _other_case(tmp_path, {"key": "C major"})
        engine = FakeKeyEngine(tonic="C", mode=KeyMode.MAJOR)

        updated, runs = run_engine_on_cases([case], engine)

        assert updated[0].hypothesis["key"] == "C major"
        assert updated[0].engine == "fake-key"
        assert runs[0].kind == "key"
        assert runs[0].summary == "key C major"
        assert runs[0].processing_time_seconds == 1.5
        assert build_report(updated)["cases"][0]["metrics"]["key.exact"] == 1.0

    def test_unresolved_key_is_scored_as_unknown_not_skipped(self, tmp_path: Path) -> None:
        case = _other_case(tmp_path, {"key": "C major"})
        engine = FakeKeyEngine(tonic=None, mode=KeyMode.UNKNOWN)

        updated, runs = run_engine_on_cases([case], engine)

        assert updated[0].hypothesis["key"] == "unknown"
        assert runs[0].summary == "key unknown"
        metrics = build_report(updated)["cases"][0]["metrics"]
        assert metrics["key.exact"] == 0.0
        assert metrics["key.relation"] == "unknown"

    def test_tempo_engine_fills_and_scores_the_tempo_family(self, tmp_path: Path) -> None:
        case = _other_case(tmp_path, {"tempo_bpm": 120.0})
        engine = FakeTempoEngine(bpm=121.0)

        updated, runs = run_engine_on_cases([case], engine)

        assert updated[0].hypothesis["tempo_bpm"] == 121.0
        assert runs[0].kind == "tempo"
        assert runs[0].summary == "121.0 BPM"
        metrics = build_report(updated)["cases"][0]["metrics"]
        assert metrics["tempo.absolute_bpm_error"] == 1.0

    def test_lyrics_engine_fills_and_scores_the_lyrics_family(self, tmp_path: Path) -> None:
        case = _other_case(tmp_path, {"lyrics_text": "hola mundo"})
        engine = FakeLyricsEngine()

        updated, runs = run_engine_on_cases([case], engine)

        assert updated[0].hypothesis["lyrics_text"] == "hola mundo"
        assert updated[0].hypothesis["lyrics_words"] == [
            {"text": "hola", "start": 0.5},
            {"text": "mundo", "start": 1.5},
        ]
        assert runs[0].kind == "lyrics"
        metrics = build_report(updated)["cases"][0]["metrics"]
        assert metrics["lyrics.wer"] == 0.0

    def test_unscoreable_kind_is_refused_before_any_run(self, tmp_path: Path) -> None:
        case = _other_case(tmp_path, {"beats": []})
        with pytest.raises(InputError, match="cannot score"):
            run_engine_on_cases([case], _BeatStub())

    def test_stored_hypothesis_fields_survive_the_key_run(self, tmp_path: Path) -> None:
        (tmp_path / "song.wav").write_bytes(b"RIFFfake")
        case = BenchmarkCase(
            song="song_a",
            reference={"key": "C major"},
            hypothesis={"lyrics_text": "stored"},
            audio="song.wav",
            source=tmp_path / "case.json",
        )

        updated, _ = run_engine_on_cases([case], FakeKeyEngine())

        assert updated[0].hypothesis["lyrics_text"] == "stored"
        assert updated[0].hypothesis["key"] == "C major"
