"""Chord segmentation metrics (roadmap section 44) - timing-aware views.

The timing-free views in :mod:`song_chord_lyrics_analyzer.metrics.chords` say
nothing about *when* a chord happens. These three metrics do, and each is a
dependency-free re-implementation of a published definition rather than a new
invention:

* :func:`segment_overlap` - MIREX ``MeanSeg``: ``min(UnderSeg, OverSeg)``, both
  ``1 - directional Hamming distance`` of the chord-boundary sets (Harte et
  al., "Towards automatic extraction of harmony information", 2010).
* :func:`chord_change_detection` - boundary-detection hit rate (precision,
  recall, F-measure) with a tolerance window and a maximal one-to-one matching
  between change points (Bello et al., 2005; as packaged by ``mir_eval``).
* :func:`timing_error` - median distance from each reference change point to
  the closest hypothesis change point, and vice versa (``mir_eval``
  ``deviation``).

The reference values are pinned by ``tests/fixtures/chord_metrics_oracle.json``,
produced by ``mir_eval`` over the committed GuitarSet takes. Segments are timed
``(start, end, label)`` triples, matching :func:`evaluation.duration_csr`;
labels are ignored here, only the boundaries matter.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = [
    "chord_change_detection",
    "segment_overlap",
    "timing_error",
]

Segment = tuple[float, float, str]

#: Boundary times are rounded to this many decimals before de-duplication, the
#: same ``q`` the reference implementation uses, so near-identical edges from
#: float arithmetic collapse into one change point.
_BOUNDARY_DECIMALS = 5


def _intervals(segments: Sequence[Segment]) -> list[tuple[float, float]]:
    """The (start, end) pairs of timed segments."""
    return [(float(start), float(end)) for start, end, _ in segments]


def _raw_boundaries(intervals: Sequence[tuple[float, float]]) -> list[float]:
    """Sorted unique change points of a segmentation (starts and ends)."""
    return sorted({value for start, end in intervals for value in (start, end)})


def _rounded_boundaries(intervals: Sequence[tuple[float, float]]) -> list[float]:
    """Change points rounded before de-duplication (hit-rate/deviation view)."""
    return sorted(
        {round(value, _BOUNDARY_DECIMALS) for start, end in intervals for value in (start, end)}
    )


def _directional_hamming_distance(
    source: Sequence[tuple[float, float]],
    target_boundaries: Sequence[float],
) -> float:
    """Fraction of ``source``'s span not covered by its longest ``target``-cut piece.

    For each source interval, cut it at every target boundary that falls inside
    and subtract the longest resulting piece: a target boundary splitting a
    source interval scores a mismatch, one that does not scores nothing.
    """
    span = source[-1][1] - source[0][0]
    if span <= 0:
        return 0.0
    total = 0.0
    for start, end in source:
        duration = end - start
        cuts = [start, *[t for t in target_boundaries if start <= t < end], end]
        longest = max(cuts[index + 1] - cuts[index] for index in range(len(cuts) - 1))
        total += duration - longest
    return total / span


def segment_overlap(ref: Sequence[Segment], hyp: Sequence[Segment]) -> float:
    """MIREX ``MeanSeg`` chord segmentation overlap, in ``[0, 1]``.

    ``1.0`` means the two segmentations agree on every boundary; a segmentation
    that never introduces a boundary where the other has one is not penalised,
    so the score is the *minimum* of the over- and under-segmentation views.
    """
    ref_intervals = _intervals(ref)
    hyp_intervals = _intervals(hyp)
    if not ref_intervals or not hyp_intervals:
        return 0.0
    hyp_boundaries = _raw_boundaries(hyp_intervals)
    ref_boundaries = _raw_boundaries(ref_intervals)
    over = 1.0 - _directional_hamming_distance(ref_intervals, hyp_boundaries)
    under = 1.0 - _directional_hamming_distance(hyp_intervals, ref_boundaries)
    return min(over, under)


def _match_count(
    reference: Sequence[float],
    estimated: Sequence[float],
    window: float,
) -> int:
    """Maximum number of one-to-one matches within ``window`` seconds.

    Both inputs are sorted; on a line the greedy earliest-feasible pairing is
    optimal, so a single pass suffices.
    """
    ref_index = est_index = matches = 0
    while ref_index < len(reference) and est_index < len(estimated):
        if estimated[est_index] < reference[ref_index] - window:
            est_index += 1
        elif estimated[est_index] > reference[ref_index] + window:
            ref_index += 1
        else:
            matches += 1
            ref_index += 1
            est_index += 1
    return matches


def chord_change_detection(
    ref: Sequence[Segment],
    hyp: Sequence[Segment],
    *,
    window: float = 0.5,
    trim: bool = False,
) -> dict[str, float]:
    """Precision/recall/F-measure of detected chord-change points.

    A change point is a segment boundary; each reference boundary is matched to
    at most one hypothesis boundary within ``window`` seconds. Two empty
    boundary sets, or either side empty, score 0.0/0.0/0.0. With ``trim`` the
    first and last boundaries (the track start/end markers) are ignored.
    """
    ref_boundaries = _rounded_boundaries(_intervals(ref))
    hyp_boundaries = _rounded_boundaries(_intervals(hyp))
    if trim:
        ref_boundaries = ref_boundaries[1:-1]
        hyp_boundaries = hyp_boundaries[1:-1]
    if not ref_boundaries or not hyp_boundaries:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    matches = _match_count(ref_boundaries, hyp_boundaries, window)
    precision = matches / len(hyp_boundaries)
    recall = matches / len(ref_boundaries)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _median(values: list[float]) -> float:
    """Median, averaging the two middle values for an even-sized input."""
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def timing_error(ref: Sequence[Segment], hyp: Sequence[Segment]) -> dict[str, float]:
    """Median change-point timing error in both directions, in seconds.

    For each reference boundary, the distance to the closest hypothesis
    boundary (and the other way round); the median of each set is reported, so
    one wild boundary cannot dominate. ``nan`` when either side has no
    boundaries.
    """
    ref_boundaries = _rounded_boundaries(_intervals(ref))
    hyp_boundaries = _rounded_boundaries(_intervals(hyp))
    if not ref_boundaries or not hyp_boundaries:
        return {"reference_to_hypothesis": float("nan"), "hypothesis_to_reference": float("nan")}
    reference_to_hypothesis = _median(
        [min(abs(reference - hyp) for hyp in hyp_boundaries) for reference in ref_boundaries]
    )
    hypothesis_to_reference = _median(
        [min(abs(hyp - reference) for reference in ref_boundaries) for hyp in hyp_boundaries]
    )
    return {
        "reference_to_hypothesis": reference_to_hypothesis,
        "hypothesis_to_reference": hypothesis_to_reference,
    }
