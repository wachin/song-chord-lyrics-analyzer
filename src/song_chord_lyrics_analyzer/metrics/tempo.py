"""Tempo metrics (roadmap section 44) - absolute, half- and double-time error.

Reference and estimate are positive BPM values. Half-time and double-time
ambiguity is *reported*, never normalised away (roadmap section 44 and the
tempo-estimation convention in ``docs/BENCHMARK.md``): :func:`tempo_error`
returns all three deviations at once and leaves the interpretation to the
caller, and :func:`tempo_interpretation` names the closest one without hiding
the others.

All three are plain absolute BPM differences, each under one reading of the
estimate:

* ``absolute_bpm_error`` - the estimate taken at face value;
* ``half_tempo_error`` - the estimate read as half-time, so it is doubled
  before comparing (a half-time estimate scores 0 here);
* ``double_tempo_error`` - the estimate read as double-time, so it is halved
  before comparing (a double-time estimate scores 0 here).
"""

from __future__ import annotations

import math

__all__ = [
    "tempo_error",
    "tempo_interpretation",
]


def _validate_bpm(value: float, label: str) -> float:
    """Return ``value`` as a float, rejecting non-positive or non-finite BPM."""
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be a positive BPM value, got {value!r}")
    return float(value)


def tempo_error(reference_bpm: float, estimated_bpm: float) -> dict[str, float]:
    """Absolute BPM errors under the three metrical readings of the estimate.

    ``half_tempo_error`` doubles the estimate before comparing and
    ``double_tempo_error`` halves it, so a correctly metered estimate scores 0
    on ``absolute_bpm_error`` and an octave-off one scores 0 on the matching
    view. The smallest value names the most likely reading; ties favour the
    estimate taken at face value.
    """
    reference = _validate_bpm(reference_bpm, "reference_bpm")
    estimate = _validate_bpm(estimated_bpm, "estimated_bpm")
    return {
        "absolute_bpm_error": abs(reference - estimate),
        "half_tempo_error": abs(reference - 2.0 * estimate),
        "double_tempo_error": abs(reference - estimate / 2.0),
    }


def tempo_interpretation(reference_bpm: float, estimated_bpm: float) -> str:
    """Which reading of the estimate is closest: ``"same"``, ``"half"`` or ``"double"``."""
    errors = tempo_error(reference_bpm, estimated_bpm)
    readings = (
        ("same", errors["absolute_bpm_error"]),
        ("half", errors["half_tempo_error"]),
        ("double", errors["double_tempo_error"]),
    )
    return min(readings, key=lambda reading: reading[1])[0]
