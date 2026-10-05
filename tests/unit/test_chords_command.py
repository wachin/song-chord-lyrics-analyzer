"""``songlab chords`` command (roadmap section 47): engine selection and output."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fixtures.fake_chord_engine import FakeChordEngine
from song_chord_lyrics_analyzer.cli.commands.chords import resolve_engine
from song_chord_lyrics_analyzer.cli.main import main
from song_chord_lyrics_analyzer.engines import EngineRegistry
from song_chord_lyrics_analyzer.utils.errors import AudioFileNotFoundError, InputError


def _patch_registry(monkeypatch, engine: FakeChordEngine) -> None:
    registry = EngineRegistry()
    registry.register(engine)
    monkeypatch.setattr(
        "song_chord_lyrics_analyzer.cli.commands.chords.create_default_registry",
        lambda: registry,
    )


def _touch_audio(tmp_path: Path) -> Path:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"RIFF....")
    return audio


class TestResolveEngine:
    def test_explicit_name_must_be_registered(self, monkeypatch) -> None:
        _patch_registry(monkeypatch, FakeChordEngine())
        assert resolve_engine("fake-chords").name == "fake-chords"

    def test_default_prefers_the_available_engine(self, monkeypatch) -> None:
        _patch_registry(monkeypatch, FakeChordEngine())
        assert resolve_engine(None).name == "fake-chords"

    def test_unknown_name_lists_the_registered_ones(self, monkeypatch) -> None:
        _patch_registry(monkeypatch, FakeChordEngine())
        with pytest.raises(InputError, match="Unknown chords engine"):
            resolve_engine("nope")

    def test_no_registered_engine_is_an_input_error(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "song_chord_lyrics_analyzer.cli.commands.chords.create_default_registry",
            EngineRegistry,
        )
        with pytest.raises(InputError, match="No chord engine"):
            resolve_engine(None)


class TestChordsCommand:
    def test_reports_chords_and_run_cost(self, tmp_path: Path, capsys, monkeypatch) -> None:
        _patch_registry(monkeypatch, FakeChordEngine())
        audio = _touch_audio(tmp_path)

        assert main(["chords", str(audio)]) == 0

        out = capsys.readouterr().out
        assert "Chords" in out
        assert "Engine:   fake-chords 9.9.0" in out
        assert "Duration: 4.000 s" in out
        assert "Chords:   2" in out
        assert "C" in out
        assert "G" in out
        assert "Real-time factor: 1.60" in out
        assert "Peak RSS:         4.05 MiB" in out

    def test_engine_flag_selects_the_named_engine(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        engine = FakeChordEngine()
        _patch_registry(monkeypatch, engine)
        audio = _touch_audio(tmp_path)

        assert main(["chords", str(audio), "--engine", "fake-chords"]) == 0
        assert engine.calls == [audio]

    def test_time_flags_reach_the_engine_options(self, tmp_path: Path, monkeypatch) -> None:
        engine = FakeChordEngine()
        _patch_registry(monkeypatch, engine)
        audio = _touch_audio(tmp_path)

        assert (
            main(["chords", str(audio), "--start", "1.5", "--end", "3.0", "--min-duration", "0.2"])
            == 0
        )
        options = engine.options_seen[0]
        assert options.start == 1.5
        assert options.end == 3.0
        assert options.minimum_duration == 0.2

    def test_json_flag_prints_canonical_json(self, tmp_path: Path, capsys, monkeypatch) -> None:
        _patch_registry(monkeypatch, FakeChordEngine())
        audio = _touch_audio(tmp_path)

        assert main(["chords", str(audio), "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["engine"] == "fake-chords"
        assert payload["chords"][0]["label"] == "C"
        assert payload["chords"][0]["quality"] == "major"
        assert payload["audio_path"] == str(audio)

    def test_unknown_engine_is_an_input_error(self, tmp_path: Path, capsys, monkeypatch) -> None:
        _patch_registry(monkeypatch, FakeChordEngine())
        audio = _touch_audio(tmp_path)
        assert main(["chords", str(audio), "--engine", "nope"]) == 2
        err = capsys.readouterr().err
        assert "Unknown chords engine" in err
        assert "fake-chords" in err

    def test_unavailable_engine_is_a_dependency_error(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        _patch_registry(monkeypatch, FakeChordEngine(available=False))
        audio = _touch_audio(tmp_path)
        assert main(["chords", str(audio)]) == 3
        assert "not available" in capsys.readouterr().err

    def test_missing_audio_file_is_an_input_error(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        failure = AudioFileNotFoundError(tmp_path / "nope.wav")
        _patch_registry(monkeypatch, FakeChordEngine(failure=failure))
        assert main(["chords", str(tmp_path / "nope.wav")]) == 2
        assert "not found" in capsys.readouterr().err

    def test_negative_start_is_rejected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        _patch_registry(monkeypatch, FakeChordEngine())
        audio = _touch_audio(tmp_path)
        assert main(["chords", str(audio), "--start", "-1"]) == 2
        assert "--start" in capsys.readouterr().err

    def test_end_before_start_is_rejected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        _patch_registry(monkeypatch, FakeChordEngine())
        audio = _touch_audio(tmp_path)
        assert main(["chords", str(audio), "--start", "5", "--end", "2"]) == 2
        assert "--end" in capsys.readouterr().err

    def test_negative_min_duration_is_rejected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        _patch_registry(monkeypatch, FakeChordEngine())
        audio = _touch_audio(tmp_path)
        assert main(["chords", str(audio), "--min-duration", "-0.1"]) == 2
        assert "--min-duration" in capsys.readouterr().err
