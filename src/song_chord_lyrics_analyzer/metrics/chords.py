"""Chord metrics (roadmap section 44) - timing-free sequence scoring.

This is the library home of the metric suite the recognition harness used to
carry locally. The scoring primitives themselves (MIREX-2010 equality,
duration-weighted CSR, Harte decoding, triad reduction) already live in
:mod:`song_chord_lyrics_analyzer.evaluation` and stay the single source of
truth; this module adds the sequence-level aggregations on top of them:

* :func:`align` - a dependency-free Needleman-Wunsch alignment scored by an
  arbitrary label predicate (the harness used a NumPy matrix for the same
  recurrence);
* :func:`evaluate` - all timing-free views over one reference/hypothesis pair
  (exact, root, quality and MIREX F1, multiset F1, palette F1, hypothesis
  chord count).

The reference implementations are pinned byte-for-byte by
``tests/fixtures/chord_metrics_oracle.json``, whose expected values were
produced by the original NumPy harness over the committed GuitarSet takes.
Nothing here invents numbers: the fixture records its provenance and inputs.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence

from song_chord_lyrics_analyzer.evaluation import mirex_equal
from song_chord_lyrics_analyzer.normalization.chords import parse_chord_label

__all__ = [
    "align",
    "evaluate",
    "same_quality",
    "same_root",
]


def same_root(ref: str, hyp: str) -> bool:
    """Whether two chord labels share a root (``N`` has no root, so never)."""
    ref_parsed, hyp_parsed = parse_chord_label(ref), parse_chord_label(hyp)
    return ref_parsed.root is not None and ref_parsed.root == hyp_parsed.root


def same_quality(ref: str, hyp: str) -> bool:
    """Whether two chord labels share an interpreted quality."""
    return parse_chord_label(ref).quality is parse_chord_label(hyp).quality


def _exact(ref: str, hyp: str) -> bool:
    """Whether two chord labels are byte-for-byte equal."""
    return ref == hyp


def align(
    ref_seq: Sequence[str],
    hyp_seq: Sequence[str],
    predicate: Callable[[str, str], float],
    *,
    gap_cost: float = 1.0,
    mismatch_cost: float | None = None,
) -> dict[str, float]:
    """Needleman-Wunsch alignment scored by ``predicate(ref, hyp)``.

    ``mismatch_cost`` defaults to ``-gap_cost / 2`` (the recorded plain view);
    callers that want the max-match tie-break (e.g. the MIREX view) pass
    ``-gap_cost``, which forces the traceback through match-carrying diagonals.

    Returns the alignment-level ``precision``, ``recall``, ``f1``, ``matches``
    (as a float) and summed ``score``. Two empty sequences score a perfect
    1.0/1.0/1.0 with no matches, matching the harness.
    """
    if mismatch_cost is None:
        mismatch_cost = -gap_cost / 2.0
    n, m = len(ref_seq), len(hyp_seq)
    if n == 0 and m == 0:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "matches": 0.0, "score": 0.0}

    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] - gap_cost
    for j in range(1, m + 1):
        dp[0][j] = dp[0][j - 1] - gap_cost
    for i in range(1, n + 1):
        prev, row = dp[i - 1], dp[i]
        ref_label = ref_seq[i - 1]
        for j in range(1, m + 1):
            score = predicate(ref_label, hyp_seq[j - 1])
            pair = score if score > 0 else mismatch_cost
            row[j] = max(prev[j - 1] + pair, prev[j] - gap_cost, row[j - 1] - gap_cost)

    i, j = n, m
    matches = 0.0
    total_score = 0.0
    while i > 0 and j > 0:
        score = predicate(ref_seq[i - 1], hyp_seq[j - 1])
        pair = score if score > 0 else mismatch_cost
        diagonal = dp[i - 1][j - 1] + pair
        up = dp[i - 1][j] - gap_cost
        left = dp[i][j - 1] - gap_cost
        best = max(diagonal, up, left)
        if diagonal == best:
            if score > 0:
                matches += 1
                total_score += score
            i, j = i - 1, j - 1
        elif up >= left:
            i -= 1
        else:
            j -= 1

    precision = matches / m if m else 0.0
    recall = matches / n if n else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "matches": matches,
        "score": total_score,
    }


def _prf(metrics: Mapping[str, float]) -> dict[str, float]:
    """Keep only the precision/recall/F1 triple of an alignment result."""
    return {
        "precision": metrics["precision"],
        "recall": metrics["recall"],
        "f1": metrics["f1"],
    }


def evaluate(ref: Sequence[str], hyp: Sequence[str]) -> dict[str, object]:
    """All timing-free sequence views over one reference/hypothesis pair.

    Four labelled views (``exact``, ``root``, ``quality``, ``mirex``) each carry
    a precision/recall/F1 triple from :func:`align`; ``multiset_f1`` and
    ``palette_f1`` compare the label inventories as a bag and as a set;
    ``hyp_chords`` counts the hypothesis labels that are not ``N``.
    """
    exact = align(ref, hyp, _exact)
    root = align(ref, hyp, same_root)
    quality = align(ref, hyp, same_quality)
    mirex = align(ref, hyp, mirex_equal, mismatch_cost=-1.0)

    ref_counts, hyp_counts = Counter(ref), Counter(hyp)
    intersection = sum((ref_counts & hyp_counts).values())
    multiset_f1 = 2 * intersection / (len(ref) + len(hyp)) if ref or hyp else 1.0

    ref_palette, hyp_palette = set(ref), set(hyp)
    palette_f1 = (
        2 * len(ref_palette & hyp_palette) / (len(ref_palette) + len(hyp_palette))
        if ref_palette or hyp_palette
        else 1.0
    )

    return {
        "exact": _prf(exact),
        "root": _prf(root),
        "quality": _prf(quality),
        "mirex": _prf(mirex),
        "multiset_f1": multiset_f1,
        "palette_f1": palette_f1,
        "hyp_chords": len([label for label in hyp if label != "N"]),
    }
