"""The analysis summary: what the Phase D panel shows, without a display.

The rule under test is the project's rule about evidence: a row is present and
truthful when the document has the value, and absent when it does not. An engine
that was skipped is reported as skipped - never as a layer that produced nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from fixtures.fake_analysis import STEPS, analysis_outcome
from song_chord_lyrics_analyzer.analysis.service import StepOutcome, StepStatus
from song_chord_lyrics_analyzer.app.summary import SummaryRow, summarize
from song_chord_lyrics_analyzer.models.analysis import AnalysisResult
from song_chord_lyrics_analyzer.models.music import TempoEstimate


def _rows(document: AnalysisResult, steps: Sequence[StepOutcome] = STEPS) -> dict[str, str]:
    """The rows as a mapping, for readable assertions."""
    return {row.label: row.value for row in summarize(document, steps=steps)}


class TestRows:
    def test_the_panel_shows_the_file_the_duration_and_what_was_found(self) -> None:
        rows = _rows(analysis_outcome("song.wav").result)

        assert rows["File"] == "song.wav"
        assert rows["Duration"] == "00:00:04.000"
        assert rows["Chords"] == "4 events from fake-chords"
        assert rows["Key"] == "C major"
        assert rows["Tempo"] == "120.0 BPM"

    def test_the_engines_that_ran_are_named_by_layer(self) -> None:
        rows = _rows(analysis_outcome("song.wav").result)

        assert rows["Engines"] == "chords=fake-chords, key=fake-key"

    def test_a_skipped_engine_is_reported_as_skipped(self) -> None:
        rows = _rows(analysis_outcome("song.wav").result)

        assert rows["Skipped"] == "tempo (fake-tempo): not available"

    def test_a_failed_engine_is_reported_with_its_reason(self) -> None:
        steps = (
            StepOutcome("chords", "chroma-baseline", StepStatus.OK, "4 chords"),
            StepOutcome("tempo", "librosa-tempo", StepStatus.FAILED, "no audio device"),
        )

        rows = _rows(analysis_outcome("song.wav").result, steps)

        assert rows["Failed"] == "tempo (librosa-tempo): no audio device"
        assert rows["Engines"] == "chords=chroma-baseline"

    def test_the_provenance_of_the_run_is_shown(self) -> None:
        rows = _rows(analysis_outcome("song.wav").result)

        assert rows["Run"] == "succeeded"
        assert rows["Application"]
        assert rows["Python"] == "3.13.5"
        assert rows["Platform"].startswith("Linux")

    def test_a_recorded_input_hash_is_shortened_to_compare_runs_by_eye(self) -> None:
        outcome = analysis_outcome("song.wav")
        outcome.result.provenance.input_hash = "a" * 64

        rows = _rows(outcome.result)

        assert rows["Input SHA-256"] == "aaaaaaaaaaaa..."

    def test_the_number_of_warnings_is_shown_when_there_are_any(self) -> None:
        quiet = _rows(analysis_outcome("song.wav").result)
        noisy = _rows(analysis_outcome("song.wav", warnings=["one", "two"]).result)

        assert "Warnings" not in quiet
        assert noisy["Warnings"] == "2"


class TestMissingEvidence:
    def test_a_document_with_no_chords_says_so_instead_of_showing_a_zero(self) -> None:
        rows = _rows(analysis_outcome("song.wav", chords=[]).result)

        assert rows["Chords"] == "none detected"

    def test_no_key_guess_is_reported_as_unknown(self) -> None:
        outcome = analysis_outcome("song.wav")
        outcome.result.key = None

        assert _rows(outcome.result)["Key"] == "unknown"

    def test_no_tempo_guess_leaves_the_row_out(self) -> None:
        outcome = analysis_outcome("song.wav")
        outcome.result.tempo = None

        assert "Tempo" not in _rows(outcome.result)

    def test_an_ambiguous_tempo_keeps_the_competing_interpretations(self) -> None:
        outcome = analysis_outcome("song.wav")
        outcome.result.tempo = TempoEstimate(bpm=120.0, alternatives=[60.0, 240.0], meter="4/4")

        assert _rows(outcome.result)["Tempo"] == "120.0 BPM (also 60.0, 240.0 BPM) in 4/4"

    def test_a_document_without_audio_skips_the_file_rows(self) -> None:
        outcome = analysis_outcome("song.wav")
        outcome.result.audio = None

        rows = _rows(outcome.result)

        assert "File" not in rows
        assert "Duration" not in rows
        assert rows["Key"] == "C major"

    def test_the_result_is_a_tuple_of_typed_rows(self) -> None:
        rows = summarize(analysis_outcome("song.wav").result, steps=STEPS)

        assert isinstance(rows, tuple)
        assert all(isinstance(row, SummaryRow) for row in rows)
        assert all(row.label and row.value for row in rows)


class TestEngineFallback:
    def test_without_step_summaries_the_configuration_is_used(self) -> None:
        rows = _rows(analysis_outcome(Path("song.wav")).result, steps=())

        assert rows["Engines"] == "chords=fake-chords"

    def test_no_step_and_no_configuration_leaves_the_row_out(self) -> None:
        outcome = analysis_outcome("song.wav")
        outcome.result.provenance.configuration = {}

        assert "Engines" not in _rows(outcome.result, steps=())
