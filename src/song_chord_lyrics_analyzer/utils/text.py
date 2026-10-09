"""Small text helpers for the counts a person reads (roadmap section 63).

The CLI and the window both report how much of a layer a document carries:
``"1 segment, 2 words"``, not ``"1 segments, 2 words"``. Keeping the agreement
in one place means the two front ends cannot disagree about the same document,
which is the same reason the presenters live in :mod:`app`.

Standard library only, like the rest of :mod:`utils`.
"""

from __future__ import annotations

__all__ = ["pluralize"]


def pluralize(count: int, noun: str) -> str:
    """Return ``count`` and ``noun`` with an English plural when needed.

    Args:
        count: How many there are. Negative counts are formatted as-is; only the
            plural form of ``noun`` depends on ``count == 1``.
        noun: The singular noun, e.g. ``"segment"``.

    Returns:
        ``"1 segment"`` for one, ``"0 segments"`` and ``"2 segments"``
        otherwise. Nouns whose plural is irregular (``"lyrics"``) should be
        passed already plural.
    """
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"
