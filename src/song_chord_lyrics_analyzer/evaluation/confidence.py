"""Per-event chord confidence: mapping, calibration and reporting.

The baseline chord engine reports a *score margin* for every event — how much
better the winning state scored than the best competing state over the frames
that event covers — and turns it into a confidence with a logistic whose
constants were fitted on GuitarSet (``engines/chroma_baseline.py`` owns those
constants: they are the engine's own model).

This module is the measurement half, kept separate from the engine so a number
can be checked rather than trusted:

* :func:`probability` is the logistic itself, overflow-safe;
* :func:`fit_logistic` re-derives the constants from recorded events, so the
  calibration can be reproduced from the repository
  (``scripts/chord_benchmark.py --fit-confidence``);
* :func:`calibration_report` and :func:`combine_reports` turn events into a
  duration-weighted calibration table, a risk-coverage curve, the expected
  calibration error and the Brier score.

Every figure is computed from explicit margins, durations and reference
agreement; nothing here invents a number. A confidence is a probability of the
event's label being right **on the corpus it was calibrated on**; the docs state
that caveat wherever the number is cited.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from song_chord_lyrics_analyzer.models.confidence import ConfidenceLevel, level_for_value
from song_chord_lyrics_analyzer.utils.errors import InputError

__all__ = [
    "CONFIDENCE_THRESHOLDS",
    "EventOutcome",
    "LogisticFit",
    "apply_fit",
    "calibration_report",
    "combine_reports",
    "fit_logistic",
    "probability",
]

#: Confidence thresholds at which the report states coverage and accuracy.
#: They are the boundaries a user would act on (0.5 is a coin flip, 0.9 means
#: "act without checking"), not tuned values.
CONFIDENCE_THRESHOLDS: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9)


@dataclass(frozen=True)
class EventOutcome:
    """One chord event as the confidence measurements see it.

    Attributes:
        seconds: How long the event claims the timeline (positive).
        correct_seconds: How much of that time the reference labels the same
            way (in ``[0, seconds]``); the same rule ``duration_csr`` applies.
        confidence: The confidence the engine reported, or ``None`` when it
            reported none. ``None`` is unknown, never zero.
        margin: The raw score margin behind a derived confidence, when the
            engine kept it; required to fit a mapping, not to report one.
    """

    seconds: float
    correct_seconds: float
    confidence: float | None = None
    margin: float | None = None

    def __post_init__(self) -> None:
        if self.seconds <= 0.0:
            raise ValueError(f"event seconds must be positive, got {self.seconds!r}")
        if self.correct_seconds < 0.0:
            raise ValueError(f"correct_seconds must not be negative, got {self.correct_seconds!r}")
        if self.correct_seconds > self.seconds + 1e-9:
            raise ValueError(
                f"correct_seconds {self.correct_seconds!r} exceeds the event's "
                f"{self.seconds!r} seconds"
            )
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be within [0.0, 1.0], got {self.confidence!r}")

    @property
    def correct_fraction(self) -> float:
        """Share of the event's duration the reference agrees with."""
        return self.correct_seconds / self.seconds

    @property
    def error(self) -> float:
        """``1 - correct_fraction``: the part of the event that is a miss."""
        return 1.0 - self.correct_fraction


@dataclass(frozen=True)
class LogisticFit:
    """A fitted logistic mapping a score margin to a probability.

    ``slope`` and ``intercept`` are the two parameters of
    ``p = sigmoid(slope * margin + intercept)``. ``converged`` reports whether
    Newton's method met its tolerance; a fit that did not converge must not be
    adopted as a model.
    """

    slope: float
    intercept: float
    events: int
    seconds: float
    iterations: int
    converged: bool


def _sigmoid_argument(margin: float, slope: float, intercept: float) -> float:
    return slope * float(margin) + intercept


def probability(margin: float, *, slope: float, intercept: float) -> float:
    """The logistic ``sigmoid(slope * margin + intercept)``, evaluated safely.

    The exponent is split by sign so neither tail overflows: a very negative
    argument returns a tiny positive number and a very positive one returns a
    number below 1.0, instead of raising ``OverflowError``.
    """
    z = _sigmoid_argument(margin, slope, intercept)
    if z >= 0.0:
        return 1.0 / (1.0 + math.exp(-z))
    scaled = math.exp(z)
    return scaled / (1.0 + scaled)


def fit_logistic(
    outcomes: Sequence[EventOutcome],
    *,
    initial: tuple[float, float] = (8.0, 0.0),
    iterations: int = 100,
    tolerance: float = 1e-10,
) -> LogisticFit:
    """Fit the margin-to-probability logistic by duration-weighted IRLS.

    Every event contributes a Bernoulli trial of its own correct fraction,
    weighted by its duration: a ten-second chord that is right for eight
    seconds counts eight times more than a one-second chord. That matches the
    duration-weighted metric the calibration is meant to describe
    (``duration_csr``), so a probability of 0.7 means "70 % of the time this
    label would be right", not "70 % of the events".

    Args:
        outcomes: Events whose ``margin`` is set. A confidence is **not**
            required: only the margin is fitted, so an engine's own mapping
            cannot influence the one being fitted.
        initial: Starting ``(slope, intercept)``.
        iterations: Maximum Newton steps.
        tolerance: Stop when both parameter updates are smaller than this.

    Returns:
        The fitted parameters with the data they were fitted on.

    Raises:
        InputError: When fewer than two events carry a margin, when their total
            duration is zero, or when every event has the same correctness —
            no mapping can be identified from that data, and inventing one is
            exactly what this module refuses to do.
    """
    usable = [event for event in outcomes if event.margin is not None]
    if len(usable) < 2:
        raise InputError(
            "A confidence mapping needs at least two events with a score margin.",
            hint=(
                "Measure a corpus with --fit-confidence; its events carry metadata['score_margin']."
            ),
        )
    seconds = sum(event.seconds for event in usable)
    if seconds <= 0.0:
        raise InputError("A confidence mapping needs events with a positive total duration.")
    fractions = {round(event.correct_fraction, 12) for event in usable}
    if len(fractions) == 1:
        raise InputError(
            "Every event has the same correctness, so no margin-to-confidence "
            "mapping can be identified.",
            hint="Use a corpus where some events are wrong; a perfect or empty run proves nothing.",
        )

    slope, intercept = (float(initial[0]), float(initial[1]))
    converged = False
    step = 0
    for _ in range(iterations):
        step += 1
        gradient_slope = gradient_intercept = 0.0
        h_slope_slope = h_slope_intercept = h_intercept_intercept = 0.0
        for event in usable:
            margin = float(event.margin)  # type: ignore[arg-type]
            predicted = probability(margin, slope=slope, intercept=intercept)
            residual = (predicted - event.correct_fraction) * event.seconds
            gradient_slope += residual * margin
            gradient_intercept += residual
            variance = event.seconds * predicted * (1.0 - predicted)
            h_slope_slope += variance * margin * margin
            h_slope_intercept += variance * margin
            h_intercept_intercept += variance
        determinant = h_slope_slope * h_intercept_intercept - h_slope_intercept**2
        if abs(determinant) < 1e-12:
            break
        delta_slope = (
            h_intercept_intercept * gradient_slope - h_slope_intercept * gradient_intercept
        ) / determinant
        delta_intercept = (
            h_slope_slope * gradient_intercept - h_slope_intercept * gradient_slope
        ) / determinant
        slope -= delta_slope
        intercept -= delta_intercept
        if abs(delta_slope) < tolerance and abs(delta_intercept) < tolerance:
            converged = True
            break

    return LogisticFit(
        slope=slope,
        intercept=intercept,
        events=len(usable),
        seconds=seconds,
        iterations=step,
        converged=converged,
    )


def apply_fit(
    outcomes: Sequence[EventOutcome],
    fit: LogisticFit,
) -> list[EventOutcome]:
    """Re-score ``outcomes`` with ``fit``, keeping each event's margin.

    Events without a margin are returned unchanged (their confidence stays what
    it was); everything with one gets ``probability(margin)`` so a held-out set
    can be reported with a mapping it did not influence.
    """
    scored: list[EventOutcome] = []
    for event in outcomes:
        if event.margin is None:
            scored.append(event)
            continue
        scored.append(
            EventOutcome(
                seconds=event.seconds,
                correct_seconds=event.correct_seconds,
                confidence=probability(event.margin, slope=fit.slope, intercept=fit.intercept),
                margin=event.margin,
            )
        )
    return scored


def _band_key(value: float) -> str:
    return level_for_value(value).value


def calibration_report(
    outcomes: Sequence[EventOutcome],
    *,
    thresholds: tuple[float, ...] = CONFIDENCE_THRESHOLDS,
) -> dict[str, Any]:
    """Describe confidence against correctness on one take, as raw sums.

    The returned structure keeps *seconds* rather than ratios because the
    caller aggregates many takes before dividing: a duration-weighted
    calibration table cannot be built by averaging per-take percentages.

    Structure::

        {
          "events": int, "seconds": float, "correct_seconds": float,
          "unknown_events": int, "unknown_seconds": float,
          "brier_seconds": float,          # sum((p - correct_fraction)^2 * seconds)
          "bands": {"very_low": {"events", "seconds", "correct_seconds",
                                 "confidence_seconds"}, ...},
          "thresholds": {"0.50": {"events", "seconds", "correct_seconds"}, ...},
        }

    ``confidence_seconds`` is the duration-weighted sum of the reported values,
    so a band's mean confidence is that sum over its seconds. A threshold never
    keeps an event without a confidence: an unknown number is not a high one.
    """
    report: dict[str, Any] = {
        "events": len(outcomes),
        "seconds": 0.0,
        "correct_seconds": 0.0,
        "unknown_events": 0,
        "unknown_seconds": 0.0,
        "brier_seconds": 0.0,
        "bands": {
            level.value: {
                "events": 0,
                "seconds": 0.0,
                "correct_seconds": 0.0,
                "confidence_seconds": 0.0,
            }
            for level in ConfidenceLevel
            if level is not ConfidenceLevel.UNKNOWN
        },
        "thresholds": {
            f"{threshold:.2f}": {"events": 0, "seconds": 0.0, "correct_seconds": 0.0}
            for threshold in thresholds
        },
    }
    for event in outcomes:
        report["seconds"] += event.seconds
        report["correct_seconds"] += event.correct_seconds
        if event.confidence is None:
            report["unknown_events"] += 1
            report["unknown_seconds"] += event.seconds
            continue
        band = report["bands"][_band_key(event.confidence)]
        band["events"] += 1
        band["seconds"] += event.seconds
        band["correct_seconds"] += event.correct_seconds
        band["confidence_seconds"] += event.confidence * event.seconds
        report["brier_seconds"] += (event.confidence - event.correct_fraction) ** 2 * event.seconds
        for key, entry in report["thresholds"].items():
            if event.confidence >= float(key):
                entry["events"] += 1
                entry["seconds"] += event.seconds
                entry["correct_seconds"] += event.correct_seconds
    return report


def combine_reports(
    reports: Sequence[dict[str, Any]],
    *,
    thresholds: tuple[float, ...] = CONFIDENCE_THRESHOLDS,
) -> dict[str, Any]:
    """Pool per-take :func:`calibration_report` results into one report.

    Sums the durations and correct durations, then derives the rates, so a long
    take weighs what it lasts. Bands and thresholds absent from every take are
    still reported (with zero coverage) rather than omitted, so two runs can be
    compared field by field.

    Returns ``{}`` for an empty input — an absent measurement is not a zero.
    """
    if not reports:
        return {}
    totals: dict[str, Any] = {
        "events": 0,
        "seconds": 0.0,
        "correct_seconds": 0.0,
        "unknown_events": 0,
        "unknown_seconds": 0.0,
        "brier_seconds": 0.0,
        "bands": {
            level.value: {
                "events": 0,
                "seconds": 0.0,
                "correct_seconds": 0.0,
                "confidence_seconds": 0.0,
            }
            for level in ConfidenceLevel
            if level is not ConfidenceLevel.UNKNOWN
        },
        "thresholds": {
            f"{threshold:.2f}": {"events": 0, "seconds": 0.0, "correct_seconds": 0.0}
            for threshold in thresholds
        },
    }
    for report in reports:
        totals["events"] += int(report["events"])
        for key in ("seconds", "correct_seconds", "unknown_seconds", "brier_seconds"):
            totals[key] += float(report[key])
        totals["unknown_events"] += int(report["unknown_events"])
        for band, values in report["bands"].items():
            pooled = totals["bands"].setdefault(
                band,
                {"events": 0, "seconds": 0.0, "correct_seconds": 0.0, "confidence_seconds": 0.0},
            )
            pooled["events"] += int(values["events"])
            pooled["seconds"] += float(values["seconds"])
            pooled["correct_seconds"] += float(values["correct_seconds"])
            pooled["confidence_seconds"] += float(values["confidence_seconds"])
        for key, values in report["thresholds"].items():
            pooled = totals["thresholds"].setdefault(
                key, {"events": 0, "seconds": 0.0, "correct_seconds": 0.0}
            )
            pooled["events"] += int(values["events"])
            pooled["seconds"] += float(values["seconds"])
            pooled["correct_seconds"] += float(values["correct_seconds"])

    seconds = float(totals["seconds"])
    known_seconds = seconds - float(totals["unknown_seconds"])
    totals["accuracy"] = totals["correct_seconds"] / seconds if seconds > 0.0 else None
    totals["known_fraction"] = known_seconds / seconds if seconds > 0.0 else None
    totals["brier"] = totals["brier_seconds"] / known_seconds if known_seconds > 0.0 else None

    weighted_error = 0.0
    for band in totals["bands"].values():
        band_seconds = band["seconds"]
        band["accuracy"] = band["correct_seconds"] / band_seconds if band_seconds > 0.0 else None
        band["mean_confidence"] = (
            band["confidence_seconds"] / band_seconds if band_seconds > 0.0 else None
        )
        if band_seconds > 0.0 and band["accuracy"] is not None:
            weighted_error += band_seconds * abs(band["mean_confidence"] - band["accuracy"])
    totals["ece"] = weighted_error / known_seconds if known_seconds > 0.0 else None

    for threshold in totals["thresholds"].values():
        threshold["coverage"] = threshold["seconds"] / seconds if seconds > 0.0 else 0.0
        kept = threshold["seconds"]
        threshold["accuracy"] = threshold["correct_seconds"] / kept if kept > 0.0 else None
    return totals
