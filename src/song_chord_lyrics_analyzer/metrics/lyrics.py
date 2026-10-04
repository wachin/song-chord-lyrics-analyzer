"""Lyrics metrics (roadmap section 44) - WER, CER and word timestamp error.

Text is compared after one documented normalization: NFKC, lower-cased,
punctuation/symbols/separators turned into spaces, whitespace collapsed. The
same normalization is applied to both sides, so case and punctuation never make
a transcript wrong (the lyrics-ASR investigation in
``docs/ENGINE_COMPARISON.md`` used the same rule).

* :func:`word_error_rate` - Levenshtein distance over the normalized words,
  divided by the number of reference words (the standard WER);
* :func:`character_error_rate` - the same over normalized characters, including
  the single spaces between words;
* :func:`word_timestamp_error` - median and mean absolute start-time difference
  over the words the two sequences share, matched by the same edit-distance
  alignment, so a shifted or missing word cannot silently dominate.

Both error rates are ratios over the reference, so an empty reference raises
rather than producing a meaningless zero. A word timestamp needs a start time to
be scorable; words without one are excluded by the adapters instead of being
invented. ``tests/fixtures/lyrics_oracle.json`` pins the two rates against
``jiwer`` 4.0.0.
"""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Sequence

__all__ = [
    "character_error_rate",
    "normalize_text",
    "word_error_rate",
    "word_timestamp_error",
]

#: A word as the timestamp metric sees it: its text and its start in seconds.
TimedWord = tuple[str, float]


def normalize_text(text: str) -> str:
    """NFKC, lower-cased, punctuation/symbols to spaces, whitespace collapsed."""
    folded = unicodedata.normalize("NFKC", text).lower()
    spaced = "".join(
        " " if unicodedata.category(character)[0] in {"P", "S", "Z"} else character
        for character in folded
    )
    return " ".join(spaced.split())


def _levenshtein(reference: Sequence[object], hypothesis: Sequence[object]) -> int:
    """Edit distance with unit insertion, deletion and substitution costs."""
    previous = list(range(len(hypothesis) + 1))
    for row, reference_item in enumerate(reference, start=1):
        current = [row]
        for column, hypothesis_item in enumerate(hypothesis, start=1):
            cost = 0 if reference_item == hypothesis_item else 1
            current.append(
                min(previous[column] + 1, current[column - 1] + 1, previous[column - 1] + cost)
            )
        previous = current
    return previous[-1]


def _alignment_pairs(
    reference: Sequence[object],
    hypothesis: Sequence[object],
) -> list[tuple[int | None, int | None]]:
    """One optimal edit-distance alignment as ``(reference index, hypothesis index)``.

    Unpaired insertions and deletions carry ``None`` on the missing side.
    """
    rows, columns = len(reference), len(hypothesis)
    distance = [[0] * (columns + 1) for _ in range(rows + 1)]
    for row in range(1, rows + 1):
        distance[row][0] = row
    for column in range(1, columns + 1):
        distance[0][column] = column
    for row in range(1, rows + 1):
        for column in range(1, columns + 1):
            cost = 0 if reference[row - 1] == hypothesis[column - 1] else 1
            distance[row][column] = min(
                distance[row - 1][column] + 1,
                distance[row][column - 1] + 1,
                distance[row - 1][column - 1] + cost,
            )
    pairs: list[tuple[int | None, int | None]] = []
    row, column = rows, columns
    while row > 0 or column > 0:
        substitution_cost = (
            0 if row > 0 and column > 0 and reference[row - 1] == hypothesis[column - 1] else 1
        )
        if (
            row > 0
            and column > 0
            and distance[row][column] == distance[row - 1][column - 1] + substitution_cost
        ):
            pairs.append((row - 1, column - 1))
            row -= 1
            column -= 1
        elif row > 0 and distance[row][column] == distance[row - 1][column] + 1:
            pairs.append((row - 1, None))
            row -= 1
        else:
            pairs.append((None, column - 1))
            column -= 1
    pairs.reverse()
    return pairs


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Standard WER: normalized word edit distance over reference word count."""
    reference_words = normalize_text(reference).split()
    if not reference_words:
        raise ValueError("reference must contain at least one word")
    hypothesis_words = normalize_text(hypothesis).split()
    return _levenshtein(reference_words, hypothesis_words) / len(reference_words)


def character_error_rate(reference: str, hypothesis: str) -> float:
    """CER: normalized character edit distance over reference character count.

    Spaces between words are part of the normalized string and therefore count.
    """
    reference_characters = normalize_text(reference)
    if not reference_characters:
        raise ValueError("reference must contain at least one character")
    hypothesis_characters = normalize_text(hypothesis)
    return _levenshtein(list(reference_characters), list(hypothesis_characters)) / len(
        reference_characters
    )


def _median(values: Sequence[float]) -> float:
    """Median, averaging the two middle values for an even-sized input."""
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def word_timestamp_error(
    reference: Sequence[TimedWord],
    hypothesis: Sequence[TimedWord],
) -> dict[str, float]:
    """Median and mean absolute start-time error over aligned equal words.

    The two text sequences are aligned with the same edit-distance recurrence as
    :func:`word_error_rate`; only aligned pairs whose words are equal contribute,
    and their ``|reference.start - hypothesis.start|`` is summarized. ``nan``
    with zero matched words when nothing lines up.
    """
    pairs = _alignment_pairs([word[0] for word in reference], [word[0] for word in hypothesis])
    errors = [
        abs(reference[reference_index][1] - hypothesis[hypothesis_index][1])
        for reference_index, hypothesis_index in pairs
        if reference_index is not None
        and hypothesis_index is not None
        and reference[reference_index][0] == hypothesis[hypothesis_index][0]
    ]
    if not errors:
        return {
            "median_seconds": math.nan,
            "mean_seconds": math.nan,
            "matched_words": 0.0,
        }
    return {
        "median_seconds": _median(errors),
        "mean_seconds": sum(errors) / len(errors),
        "matched_words": float(len(errors)),
    }
