"""The analysis pipeline (roadmap sections 8, 9, 47, 61 and 62).

``run_analysis`` is what finally assembles the canonical document, so these
tests pin its contract: every layer that ran is present, a layer that failed or
was unavailable becomes a warning instead of losing the document, and
provenance says which engines and which input produced it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from fixtures.audio import write_sine_wav
from fixtures.fake_chord_engine import FakeChordEngine
from fixtures.fake_key_tempo_engines import FakeKeyEngine, FakeLyricsEngine, FakeTempoEngine
from song_chord_lyrics_analyzer.analysis import (
    StepStatus,
    run_analysis,
    with_lyrics_from_timed_text,
)
from song_chord_lyrics_analyzer.cli.main import main
from song_chord_lyrics_analyzer.engines import EngineRegistry
from song_chord_lyrics_analyzer.models.analysis import RunStatus
from song_chord_lyrics_analyzer.utils.errors import DependencyError, InputError

#: Sentinel for "register the default fake"; ``None`` means "register nothing
#: for that layer", which is how the missing-layer behaviour is tested.
_DEFAULT = object()


def _registry(
    *,
    chords: Any = None,
    key: Any = None,
    tempo: Any = None,
    lyrics: Any = _DEFAULT,
) -> EngineRegistry:
    registry = EngineRegistry()
    registry.register(chords if chords is not None else FakeChordEngine())
    registry.register(key if key is not None else FakeKeyEngine())
    registry.register(tempo if tempo is not None else FakeTempoEngine())
    if lyrics is _DEFAULT:
        registry.register(FakeLyricsEngine())
    elif lyrics is not None:
        registry.register(lyrics)
    return registry


def _audio(tmp_path: Path) -> Path:
    return write_sine_wav(tmp_path / "song.wav", seconds=1.0, channels=1)


class TestRunAnalysis:
    def test_every_ran_layer_lands_in_the_document(self, tmp_path: Path) -> None:
        outcome = run_analysis(_audio(tmp_path), registry=_registry())

        document = outcome.result
        assert len(document.chords) == 2
        assert document.key is not None
        assert document.key.label == "C major"
        assert document.tempo is not None
        assert document.tempo.bpm == 120.0
        assert document.has_lyrics is True
        assert [segment.text for segment in document.lyrics] == ["hola mundo"]
        assert document.run.status is RunStatus.SUCCEEDED
        assert len(outcome.steps) == 4
        assert [step.status for step in outcome.steps] == [StepStatus.OK] * 4
        assert outcome.total_processing_seconds == pytest.approx(2.5 + 1.5 + 0.5 + 2.0)

    def test_a_missing_lyrics_layer_is_skipped_and_never_invented(self, tmp_path: Path) -> None:
        """The lyrics layer is the only one that may honestly be absent."""
        outcome = run_analysis(_audio(tmp_path), registry=_registry(lyrics=None))

        assert outcome.result.has_lyrics is False
        assert outcome.result.lyrics == []
        assert outcome.result.run.status is RunStatus.PARTIAL
        skipped = [step for step in outcome.steps if step.status is StepStatus.SKIPPED]
        assert [(step.kind, step.detail) for step in skipped] == [
            ("lyrics", "no engine registered")
        ]

    def test_provenance_records_engines_configuration_and_input(self, tmp_path: Path) -> None:
        audio = _audio(tmp_path)
        outcome = run_analysis(audio, registry=_registry())

        provenance = outcome.result.provenance
        assert sorted(provenance.engines) == [
            "fake-chords",
            "fake-key",
            "fake-lyrics",
            "fake-tempo",
        ]
        assert provenance.configuration == {
            "chords": "fake-chords",
            "key": "fake-key",
            "lyrics": "fake-lyrics",
            "tempo": "fake-tempo",
        }
        assert provenance.input_path == str(audio.resolve())
        assert provenance.input_hash is not None
        assert len(provenance.input_hash) == 64
        assert provenance.python_version
        assert provenance.platform

    def test_hash_can_be_skipped(self, tmp_path: Path) -> None:
        outcome = run_analysis(_audio(tmp_path), registry=_registry(), input_hash=False)
        assert outcome.result.provenance.input_hash is None

    def test_raw_engine_payload_is_preserved(self, tmp_path: Path) -> None:
        registry = _registry(chords=FakeChordEngine(raw={"frame_labels": ["C", "G"]}))
        outcome = run_analysis(_audio(tmp_path), registry=registry)
        assert outcome.result.raw["fake-chords"] == {"frame_labels": ["C", "G"]}

    def test_an_unavailable_engine_is_skipped_and_the_rest_survives(self, tmp_path: Path) -> None:
        outcome = run_analysis(
            _audio(tmp_path), registry=_registry(key=FakeKeyEngine(available=False))
        )

        document = outcome.result
        assert document.run.status is RunStatus.PARTIAL
        assert document.chords
        assert document.tempo is not None
        assert document.key is None
        skipped = [step for step in outcome.steps if step.status is StepStatus.SKIPPED]
        assert [step.kind for step in skipped] == ["key"]
        assert any("fake-key" in warning for warning in document.warnings)

    def test_an_engine_failure_warns_without_losing_the_document(self, tmp_path: Path) -> None:
        outcome = run_analysis(
            _audio(tmp_path),
            registry=_registry(chords=FakeChordEngine(failure=RuntimeError("boom"))),
        )

        document = outcome.result
        assert document.run.status is RunStatus.PARTIAL
        assert document.chords == []
        assert document.key is not None
        assert document.tempo is not None
        assert any("boom" in warning for warning in document.warnings)
        assert document.run.errors
        failed = [step for step in outcome.steps if step.status is StepStatus.FAILED]
        assert [step.kind for step in failed] == ["chords"]

    def test_no_usable_engine_is_a_dependency_error(self, tmp_path: Path) -> None:
        registry = _registry(
            chords=FakeChordEngine(available=False),
            key=FakeKeyEngine(available=False),
            tempo=FakeTempoEngine(available=False),
            lyrics=FakeLyricsEngine(available=False),
        )

        with pytest.raises(DependencyError, match="No analysis engine could run"):
            run_analysis(_audio(tmp_path), registry=registry)

    def test_an_unknown_override_is_reported(self, tmp_path: Path) -> None:
        registry = _registry(
            chords=FakeChordEngine(available=False),
            key=FakeKeyEngine(available=False),
            tempo=FakeTempoEngine(available=False),
            lyrics=FakeLyricsEngine(available=False),
        )

        with pytest.raises(DependencyError, match="No analysis engine could run"):
            run_analysis(_audio(tmp_path), registry=registry)

    def test_an_override_selects_that_engine(self, tmp_path: Path) -> None:
        chosen = FakeTempoEngine(bpm=90.0)
        registry = _registry(tempo=chosen)
        outcome = run_analysis(_audio(tmp_path), registry=registry, engines={"tempo": "fake-tempo"})
        assert outcome.result.tempo is not None
        assert outcome.result.tempo.bpm == pytest.approx(chosen.bpm)

    def test_missing_audio_file_is_reported(self, tmp_path: Path) -> None:
        with pytest.raises(Exception, match=r"[Nn]ot found"):
            run_analysis(tmp_path / "absent.wav", registry=_registry())


class TestAnalyzeCommand:
    def _patch(self, monkeypatch, **kwargs) -> EngineRegistry:
        registry = _registry(**kwargs)
        real = run_analysis

        def _fake(audio_path: Path, **options):
            return real(audio_path, registry=registry, **options)

        monkeypatch.setattr("song_chord_lyrics_analyzer.cli.commands.analyze.run_analysis", _fake)
        return registry

    def test_report_is_printed(self, tmp_path: Path, capsys, monkeypatch) -> None:
        self._patch(monkeypatch)
        assert main(["analyze", str(_audio(tmp_path))]) == 0

        output = capsys.readouterr().out
        assert "Analysis" in output
        assert "Status:   succeeded" in output
        assert "Chords: 2" in output
        assert "Lyrics: 1 segment, 2 words" in output
        assert "Key:    C major" in output
        assert "Tempo:  120.0 BPM" in output
        assert "Total processing:" in output
        assert "sha256:" in output

    def test_json_flag_prints_the_canonical_document(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        self._patch(monkeypatch)
        assert main(["analyze", str(_audio(tmp_path)), "--json"]) == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload["run"]["status"] == "succeeded"
        assert len(payload["chords"]) == 2
        assert payload["lyrics"][0]["text"] == "hola mundo"
        assert payload["key"]["tonic"] == "C"
        assert payload["tempo"]["bpm"] == 120.0
        assert payload["provenance"]["configuration"]["lyrics"] == "fake-lyrics"
        assert payload["provenance"]["input_hash"]

    def test_partial_run_still_exits_zero_and_shows_warnings(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        self._patch(monkeypatch, key=FakeKeyEngine(available=False))
        assert main(["analyze", str(_audio(tmp_path))]) == 0

        output = capsys.readouterr().out
        assert "Status:   partial" in output
        assert "skipped" in output
        assert "Warnings" in output

    def test_no_hash_flag_omits_the_digest(self, tmp_path: Path, capsys, monkeypatch) -> None:
        self._patch(monkeypatch)
        assert main(["analyze", str(_audio(tmp_path)), "--no-hash"]) == 0
        assert "sha256:" not in capsys.readouterr().out

    def test_engine_override_is_accepted(self, tmp_path: Path, capsys, monkeypatch) -> None:
        self._patch(monkeypatch)
        assert main(["analyze", str(_audio(tmp_path)), "--engine", "chords=fake-chords"]) == 0
        assert "fake-chords" in capsys.readouterr().out

    def test_malformed_override_is_an_input_error(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        self._patch(monkeypatch)
        assert main(["analyze", str(_audio(tmp_path)), "--engine", "chords"]) == 2
        assert "Invalid --engine value" in capsys.readouterr().err

    def test_unknown_layer_is_an_input_error(self, tmp_path: Path, capsys, monkeypatch) -> None:
        self._patch(monkeypatch)
        assert main(["analyze", str(_audio(tmp_path)), "--engine", "beats=fake"]) == 2
        assert "Unknown analysis layer" in capsys.readouterr().err

    def test_the_lyrics_layer_can_be_overridden_like_any_other(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        self._patch(monkeypatch)
        assert main(["analyze", str(_audio(tmp_path)), "--engine", "lyrics=fake-lyrics"]) == 0
        output = capsys.readouterr().out
        assert "lyrics   fake-lyrics" in output
        assert "1 lyric segment, 2 words" in output

    def test_unknown_engine_is_an_input_error(self, tmp_path: Path, capsys, monkeypatch) -> None:
        self._patch(monkeypatch)
        assert main(["analyze", str(_audio(tmp_path)), "--engine", "chords=nope"]) == 2
        assert "Unknown chords engine" in capsys.readouterr().err

    def test_lyrics_from_flag_takes_the_lyrics_from_a_lrc_file(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        self._patch(monkeypatch)
        source = tmp_path / "song.lrc"
        source.write_text("[00:10.00]external line\n", encoding="utf-8")

        assert main(["analyze", str(_audio(tmp_path)), "--lyrics-from", str(source)]) == 0

        output = capsys.readouterr().out
        assert "lyrics   timed-text" in output
        assert "2 lyric segments" not in output  # the file's one line, not the engine's
        assert "1 lyric segment from song.lrc" in output

    def test_lyrics_from_flag_reaches_the_json_document(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        self._patch(monkeypatch)
        source = tmp_path / "song.lrc"
        source.write_text("[00:10.00]external line\n", encoding="utf-8")

        assert main(["analyze", str(_audio(tmp_path)), "--json", "--lyrics-from", str(source)]) == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload["lyrics"][0]["text"] == "external line"
        assert payload["lyrics"][0]["source"] == "lrc"
        assert payload["provenance"]["configuration"]["lyrics_from"].endswith("song.lrc")

    def test_lyrics_from_flag_with_a_broken_file_is_an_input_error(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        self._patch(monkeypatch)
        source = tmp_path / "song.lrc"
        source.write_text("[ti:only tags]\n", encoding="utf-8")

        assert main(["analyze", str(_audio(tmp_path)), "--lyrics-from", str(source)]) == 2
        assert "no lyric lines" in capsys.readouterr().err


class TestLyricsFromTimedText:
    """The Phase F replacement: one external file becomes the lyric layer.

    Service-level rules beyond what the CLI can show: the file wins, the
    engine rows stay untouched on the original outcome, and a read or parse
    failure raises before anything is changed.
    """

    @staticmethod
    def _lrc(tmp_path: Path, text: str) -> Path:
        source = tmp_path / "song.lrc"
        source.write_text(text, encoding="utf-8")
        return source

    def test_the_file_wins_over_the_engine_layer(self, tmp_path: Path) -> None:
        outcome = run_analysis(_audio(tmp_path), registry=_registry())
        source = self._lrc(tmp_path, "[00:02.50]from file\n[00:07.00]second line\n")

        merged = with_lyrics_from_timed_text(outcome, source)

        assert [(line.text, line.start, line.end) for line in merged.result.lyrics] == [
            ("from file", 2.5, 7.0),
            ("second line", 7.0, None),
        ]
        assert all(line.source == "lrc" for line in merged.result.lyrics)
        assert [(line.text, line.start) for line in outcome.result.lyrics] == [
            ("hola mundo", None)
        ]  # the engine's untimed row, untouched by the merge

    def test_the_step_summary_names_the_file_and_the_run_recovers(self, tmp_path: Path) -> None:
        registry = _registry()
        complete = run_analysis(_audio(tmp_path), registry=registry)
        assert complete.result.run.status == RunStatus.SUCCEEDED
        failing = _registry(lyrics=FakeLyricsEngine(available=False))
        outcome = run_analysis(_audio(tmp_path), registry=failing)
        assert outcome.result.run.status == RunStatus.PARTIAL

        merged = with_lyrics_from_timed_text(
            outcome, self._lrc(tmp_path, "[00:01.00]line one\n[00:02.00]two\n")
        )

        lyrics_step = next(step for step in merged.steps if step.kind == "lyrics")
        assert lyrics_step.engine == "timed-text"
        assert lyrics_step.status is StepStatus.OK
        assert lyrics_step.detail == "2 lyric segments from song.lrc"
        assert lyrics_step.processing_time_seconds is None
        assert merged.result.run.status == RunStatus.SUCCEEDED

    def test_a_skipped_lyrics_step_is_replaced_and_the_run_recovers(self, tmp_path: Path) -> None:
        outcome = run_analysis(_audio(tmp_path), registry=_registry(lyrics=None))
        skipped = next(step for step in outcome.steps if step.kind == "lyrics")
        assert skipped.status is StepStatus.SKIPPED
        assert outcome.result.run.status == RunStatus.PARTIAL  # the only missing layer

        merged = with_lyrics_from_timed_text(
            outcome, self._lrc(tmp_path, "[00:01.00]late arrival\n")
        )

        lyrics_step = next(step for step in merged.steps if step.kind == "lyrics")
        assert lyrics_step.engine == "timed-text" and lyrics_step.status is StepStatus.OK
        # Every layer now delivered something: the run is a success again.
        assert merged.result.run.status == RunStatus.SUCCEEDED

    def test_provenance_records_where_the_lyrics_came_from(self, tmp_path: Path) -> None:
        outcome = run_analysis(_audio(tmp_path), registry=_registry())
        source = self._lrc(tmp_path, "[00:01.00]line\n")

        merged = with_lyrics_from_timed_text(outcome, source)

        assert merged.result.provenance.configuration["lyrics_from"] == str(source)
        assert merged.result.provenance.configuration["lyrics"] == "fake-lyrics"
        assert outcome.result.provenance.configuration.get("lyrics_from") is None

    def test_a_parse_failure_leaves_the_outcome_untouched(self, tmp_path: Path) -> None:
        outcome = run_analysis(_audio(tmp_path), registry=_registry())
        source = self._lrc(tmp_path, "[ti:no lyrics here]\n")

        with pytest.raises(InputError, match="no lyric lines"):
            with_lyrics_from_timed_text(outcome, source)

        assert outcome.result.lyrics and outcome.result.lyrics[0].text == "hola mundo"
