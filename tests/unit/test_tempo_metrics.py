"""Tempo metrics (roadmap section 44): absolute, half-time and double-time error.

The hand cases in ``tests/fixtures/key_oracle.json`` pin the three deviations;
the tests below also cover the interpretation helper, input validation and the
``TempoEstimate`` adapter.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from song_chord_lyrics_analyzer.metrics import tempo_bpms, tempo_error, tempo_interpretation
from song_chord_lyrics_analyzer.models.music import ConfidenceScore, TempoEstimate

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"
ORACLE = json.loads((FIXTURE_DIR / "key_oracle.json").read_text(encoding="utf-8"))


class TestTempoErrorHandCases:
    def test_exact_tempo_has_zero_absolute_error(self) -> None:
        assert tempo_error(120.0, 120.0) == {
            "absolute_bpm_error": 0.0,
            "half_tempo_error": 120.0,
            "double_tempo_error": 60.0,
        }

    def test_half_time_estimate_scores_zero_on_half_view(self) -> None:
        errors = tempo_error(120.0, 60.0)
        assert errors["absolute_bpm_error"] == 60.0
        assert errors["half_tempo_error"] == 0.0
        assert errors["double_tempo_error"] == 90.0

    def test_double_time_estimate_scores_zero_on_double_view(self) -> None:
        errors = tempo_error(120.0, 240.0)
        assert errors["absolute_bpm_error"] == 120.0
        assert errors["half_tempo_error"] == 360.0
        assert errors["double_tempo_error"] == 0.0

    def test_small_offset_is_absolute(self) -> None:
        errors = tempo_error(120.0, 125.0)
        assert errors["absolute_bpm_error"] == 5.0
        assert errors["half_tempo_error"] == 130.0
        assert errors["double_tempo_error"] == 57.5


class TestTempoInterpretation:
    def test_names_the_closest_reading(self) -> None:
        assert tempo_interpretation(120.0, 120.0) == "same"
        assert tempo_interpretation(120.0, 60.0) == "half"
        assert tempo_interpretation(120.0, 240.0) == "double"

    def test_ambiguous_tie_prefers_the_faced_value(self) -> None:
        # At 80 BPM the absolute and half views are both 40 BPM off, so the
        # first reading (the estimate taken at face value) wins the tie.
        assert tempo_error(120.0, 80.0) == {
            "absolute_bpm_error": 40.0,
            "half_tempo_error": 40.0,
            "double_tempo_error": 80.0,
        }
        assert tempo_interpretation(120.0, 80.0) == "same"


class TestValidation:
    @pytest.mark.parametrize("bad", [0.0, -1.0, math.nan, math.inf])
    def test_non_positive_or_non_finite_raises(self, bad: float) -> None:
        with pytest.raises(ValueError, match="positive BPM"):
            tempo_error(120.0, bad)
        with pytest.raises(ValueError, match="positive BPM"):
            tempo_error(bad, 120.0)


class TestTempoOracle:
    @pytest.mark.parametrize(
        "case",
        ORACLE["tempos"],
        ids=lambda c: f"{c['reference_bpm']}->{c['estimated_bpm']}",
    )
    def test_matches_hand_cases(self, case: dict) -> None:
        assert tempo_error(case["reference_bpm"], case["estimated_bpm"]) == pytest.approx(
            case["expected"]
        )


class TestTempoAdapters:
    def test_tempo_bpms_from_estimates(self) -> None:
        estimates = [
            TempoEstimate(bpm=120.0, confidence=ConfidenceScore(value=0.9)),
            TempoEstimate(bpm=97.5, alternatives=[195.0]),
        ]
        assert tempo_bpms(estimates) == [120.0, 97.5]

    def test_estimate_feeds_the_metrics(self) -> None:
        reference = TempoEstimate(bpm=120.0)
        estimate = TempoEstimate(bpm=60.0, alternatives=[120.0])
        errors = tempo_error(tempo_bpms([reference])[0], tempo_bpms([estimate])[0])
        assert errors["half_tempo_error"] == 0.0
        assert estimate.is_ambiguous is True
