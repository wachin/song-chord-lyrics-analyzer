"""Unit tests for per-event chord confidence (Phase I P2).

The engine reports a confidence from a score margin; this module is how that
number is checked. The tests cover the three claims the mapping makes: it is
bounded and monotone, it can be refitted from recorded events, and its
calibration/risk-coverage report weighs events by duration instead of by count.
All inputs are constructed here, so the tests need no corpus and no DSP stack.
"""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from song_chord_lyrics_analyzer.evaluation import (
    CONFIDENCE_THRESHOLDS,
    EventOutcome,
    apply_fit,
    calibration_report,
    combine_reports,
    fit_logistic,
    probability,
)
from song_chord_lyrics_analyzer.utils.errors import InputError

#: A logistic the synthetic tests can recover exactly.
SLOPE = 20.0
INTERCEPT = 0.3


def _event(
    margin: float | None,
    *,
    seconds: float = 1.0,
    correct: float | None = None,
    confidence: float | None = None,
) -> EventOutcome:
    """An outcome whose agreement follows the logistic unless overridden."""
    if correct is None:
        correct = seconds * probability(margin or 0.0, slope=SLOPE, intercept=INTERCEPT)
    return EventOutcome(
        seconds=seconds,
        correct_seconds=min(seconds, max(0.0, correct)),
        confidence=confidence,
        margin=margin,
    )


class TestEventOutcome:
    def test_correct_fraction_and_error_are_complements(self) -> None:
        event = EventOutcome(seconds=4.0, correct_seconds=1.0)
        assert event.correct_fraction == pytest.approx(0.25)
        assert event.error == pytest.approx(0.75)

    def test_confidence_is_optional_and_unknown_is_not_zero(self) -> None:
        assert EventOutcome(seconds=1.0, correct_seconds=1.0).confidence is None

    @pytest.mark.parametrize(
        ("seconds", "correct"),
        [(0.0, 0.0), (-1.0, 0.0), (1.0, -0.1), (1.0, 1.5)],
    )
    def test_impossible_durations_are_rejected(self, seconds: float, correct: float) -> None:
        with pytest.raises(ValueError):
            EventOutcome(seconds=seconds, correct_seconds=correct)

    def test_confidence_outside_the_unit_interval_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            EventOutcome(seconds=1.0, correct_seconds=0.0, confidence=1.5)


class TestProbability:
    def test_zero_margin_returns_the_intercept_alone(self) -> None:
        assert probability(0.0, slope=SLOPE, intercept=INTERCEPT) == pytest.approx(
            1.0 / (1.0 + math.exp(-INTERCEPT))
        )

    def test_the_mapping_is_strictly_monotone(self) -> None:
        values = [
            probability(margin / 100.0, slope=SLOPE, intercept=INTERCEPT)
            for margin in range(-20, 21)
        ]
        assert all(later > earlier for earlier, later in pairwise(values))

    def test_extreme_margins_stay_inside_the_unit_interval(self) -> None:
        """A logistic must not overflow into ``nan`` or leave ``[0, 1]``."""
        for margin in (-1e6, -50.0, 50.0, 1e6):
            value = probability(margin, slope=SLOPE, intercept=INTERCEPT)
            assert 0.0 <= value <= 1.0
            assert not math.isnan(value)


class TestFitLogistic:
    def test_the_known_logistic_is_recovered(self) -> None:
        """With fractional agreement the weighted fit has an exact answer."""
        margins = [step / 100.0 for step in range(-20, 21)]
        outcomes = [_event(margin, seconds=2.0) for margin in margins]

        fit = fit_logistic(outcomes)

        assert fit.converged is True
        assert fit.slope == pytest.approx(SLOPE, rel=1e-3)
        assert fit.intercept == pytest.approx(INTERCEPT, abs=1e-3)
        assert fit.events == len(outcomes)
        assert fit.seconds == pytest.approx(2.0 * len(outcomes))

    def test_events_without_a_margin_are_ignored(self) -> None:
        with_margin = [_event(margin / 100.0) for margin in range(-10, 11)]
        without = [EventOutcome(seconds=1.0, correct_seconds=1.0)]

        fit = fit_logistic([*with_margin, *without])

        assert fit.events == len(with_margin)

    def test_duration_is_the_weight(self) -> None:
        """A long event moves the mapping more than a short one."""

        def dataset(wrong_seconds: float) -> list[EventOutcome]:
            return [
                EventOutcome(seconds=1.0, correct_seconds=1.0, margin=0.1),
                EventOutcome(seconds=1.0, correct_seconds=0.0, margin=-0.1),
                # A high margin that the reference disagrees with, made heavy
                # or light: it must pull the slope down in proportion.
                EventOutcome(seconds=wrong_seconds, correct_seconds=0.0, margin=0.1),
            ]

        light = fit_logistic(dataset(1.0))
        heavy = fit_logistic(dataset(10.0))

        assert heavy.slope < light.slope

    def test_too_few_events_with_a_margin_is_an_error(self) -> None:
        with pytest.raises(InputError, match="at least two events"):
            fit_logistic([_event(0.1)])

    def test_identical_correctness_cannot_identify_a_mapping(self) -> None:
        outcomes = [EventOutcome(seconds=1.0, correct_seconds=1.0, margin=m) for m in (0.1, 0.2)]
        with pytest.raises(InputError, match="same correctness"):
            fit_logistic(outcomes)

    def test_an_empty_input_is_an_error(self) -> None:
        with pytest.raises(InputError, match="at least two events"):
            fit_logistic([])


class TestApplyFit:
    def test_every_event_with_a_margin_is_rescored(self) -> None:
        fit = fit_logistic([_event(margin / 50.0) for margin in range(-5, 6)])
        outcomes = [_event(margin=0.1, confidence=0.01)]

        scored = apply_fit(outcomes, fit)

        assert scored[0].confidence == pytest.approx(
            probability(0.1, slope=fit.slope, intercept=fit.intercept)
        )
        assert scored[0].margin == 0.1
        assert scored[0].seconds == outcomes[0].seconds

    def test_an_event_without_a_margin_keeps_its_confidence(self) -> None:
        fit = fit_logistic([_event(margin / 50.0) for margin in range(-5, 6)])
        untouched = EventOutcome(seconds=1.0, correct_seconds=0.0, confidence=None, margin=None)

        assert apply_fit([untouched], fit) == [untouched]


class TestCalibrationReport:
    def test_bands_and_thresholds_are_duration_weighted(self) -> None:
        outcomes = [
            EventOutcome(seconds=4.0, correct_seconds=4.0, confidence=0.92),
            EventOutcome(seconds=2.0, correct_seconds=0.0, confidence=0.10),
            EventOutcome(seconds=1.0, correct_seconds=1.0, confidence=0.70),
        ]

        report = calibration_report(outcomes)

        assert report["events"] == 3
        assert report["seconds"] == pytest.approx(7.0)
        assert report["correct_seconds"] == pytest.approx(5.0)
        assert report["unknown_events"] == 0
        assert report["bands"]["very_high"]["seconds"] == pytest.approx(4.0)
        assert report["bands"]["very_low"]["correct_seconds"] == pytest.approx(0.0)
        assert report["bands"]["high"]["events"] == 1
        # 0.70 is the first threshold the 1-second event reaches.
        assert report["thresholds"]["0.70"]["seconds"] == pytest.approx(5.0)
        assert report["thresholds"]["0.90"]["seconds"] == pytest.approx(4.0)

    def test_an_unknown_confidence_is_never_kept_by_a_threshold(self) -> None:
        outcomes = [EventOutcome(seconds=3.0, correct_seconds=0.0, confidence=None)]

        report = calibration_report(outcomes)

        assert report["unknown_events"] == 1
        assert report["unknown_seconds"] == pytest.approx(3.0)
        assert all(entry["events"] == 0 for entry in report["thresholds"].values())
        assert report["brier_seconds"] == 0.0

    def test_brier_uses_the_event_squared_error(self) -> None:
        outcomes = [EventOutcome(seconds=2.0, correct_seconds=0.0, confidence=0.8)]

        report = calibration_report(outcomes)

        assert report["brier_seconds"] == pytest.approx(0.64 * 2.0)


class TestCombineReports:
    def test_pooling_weighs_each_take_by_its_duration(self) -> None:
        long_take = calibration_report(
            [EventOutcome(seconds=9.0, correct_seconds=9.0, confidence=0.9)]
        )
        short_take = calibration_report(
            [EventOutcome(seconds=1.0, correct_seconds=0.0, confidence=0.9)]
        )

        pooled = combine_reports([long_take, short_take])

        assert pooled["accuracy"] == pytest.approx(0.9)
        assert pooled["thresholds"]["0.90"]["coverage"] == pytest.approx(1.0)
        assert pooled["thresholds"]["0.90"]["accuracy"] == pytest.approx(0.9)

    def test_an_empty_report_set_is_empty_not_zero(self) -> None:
        assert combine_reports([]) == {}

    def test_calibration_error_compares_each_band_with_its_accuracy(self) -> None:
        # One band, predicted 0.9, actually right 50 % of the time: ECE = 0.4.
        report = calibration_report(
            [
                EventOutcome(seconds=1.0, correct_seconds=1.0, confidence=0.9),
                EventOutcome(seconds=1.0, correct_seconds=0.0, confidence=0.9),
            ]
        )

        pooled = combine_reports([report])

        assert pooled["bands"]["very_high"]["mean_confidence"] == pytest.approx(0.9)
        assert pooled["bands"]["very_high"]["accuracy"] == pytest.approx(0.5)
        assert pooled["ece"] == pytest.approx(0.4)

    def test_every_threshold_stays_in_the_report(self) -> None:
        report = calibration_report(
            [EventOutcome(seconds=1.0, correct_seconds=0.0, confidence=0.5)]
        )

        pooled = combine_reports([report, report])

        assert set(pooled["thresholds"]) == {
            f"{threshold:.2f}" for threshold in CONFIDENCE_THRESHOLDS
        }
        assert pooled["thresholds"]["0.90"]["coverage"] == 0.0
        assert pooled["thresholds"]["0.90"]["accuracy"] is None

    def test_unknown_seconds_leave_the_known_fraction_visible(self) -> None:
        known = calibration_report([EventOutcome(seconds=1.0, correct_seconds=1.0, confidence=0.9)])
        unknown = calibration_report([EventOutcome(seconds=3.0, correct_seconds=3.0)])

        pooled = combine_reports([known, unknown])

        assert pooled["known_fraction"] == pytest.approx(0.25)
        assert pooled["brier"] == pytest.approx((0.9 - 1.0) ** 2)
