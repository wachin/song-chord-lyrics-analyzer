"""Key metrics (roadmap section 44) - exact accuracy and relationship views.

Keys are written as ``"C major"`` / ``"F# minor"``, the same string
:attr:`~song_chord_lyrics_analyzer.models.music.KeyEstimate.label` renders, and
enharmonic spellings (``"C# major"`` / ``"Db major"``) compare equal through the
canonical model's pitch-class table. ``"unknown"`` (or ``"X"``) means the key
could not be determined and is never scored as a match.

Two metrics are the roadmap's own:

* :func:`exact_key_accuracy` - the fraction of estimates whose tonic and mode
  match the reference;
* :func:`relative_key_error` - the fraction that is the *relative* major/minor
  of the reference, the documented confusion this project keeps seeing.

They sit on :func:`key_relation`, which also names the perfect-fifth and
parallel relationships, and on :func:`weighted_key_score`, a dependency-free
re-implementation of ``mir_eval.key.weighted_score`` that
``tests/fixtures/key_oracle.json`` pins this module against (the reference
values were produced by ``mir_eval`` 0.8.2 over GuitarSet's own annotated keys).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from song_chord_lyrics_analyzer.models.music import NOTE_NAME_TO_PITCH_CLASS

__all__ = [
    "exact_key_accuracy",
    "key_relation",
    "key_relation_counts",
    "relative_key_error",
    "same_key",
    "weighted_key_score",
]

#: Tokens that mean "this key is not known".
_UNKNOWN_TOKENS = frozenset({"unknown", "x", "none", ""})

#: Relation name -> mir_eval's heuristic weight, kept as the single mapping both
#: :func:`weighted_key_score` and the oracle fixture use.
RELATION_WEIGHT: dict[str, float] = {
    "exact": 1.0,
    "fifth": 0.5,
    "relative": 0.3,
    "parallel": 0.2,
    "other": 0.0,
    "unknown": 0.0,
}


def _parse_key(label: str) -> tuple[int | None, str | None]:
    """Return ``(pitch class, mode)`` or ``(None, None)`` when unresolved."""
    text = label.strip()
    if text.lower() in _UNKNOWN_TOKENS:
        return None, None
    parts = text.split()
    if len(parts) != 2:
        raise ValueError(f"key must look like 'C major' or 'unknown', got {label!r}")
    tonic, mode = parts
    mode = mode.lower()
    if tonic.lower() in _UNKNOWN_TOKENS or mode not in {"major", "minor", "other"}:
        return None, None
    if tonic not in NOTE_NAME_TO_PITCH_CLASS:
        # mir_eval ignores the case of the key name; the canonical model already
        # spells it, so this only rescues caller-supplied labels.
        tonic = tonic.title()
    if tonic not in NOTE_NAME_TO_PITCH_CLASS:
        raise ValueError(f"unknown tonic in key label: {label!r}")
    return NOTE_NAME_TO_PITCH_CLASS[tonic], mode


def key_relation(reference: str, estimate: str) -> str:
    """Name the relationship between two keys.

    One of ``"exact"``, ``"fifth"`` (estimate a perfect fifth above),
    ``"relative"`` (same key signature, other mode), ``"parallel"`` (same
    tonic, other mode), ``"other"`` or ``"unknown"`` when either side is
    unresolved. The order of the checks mirrors ``mir_eval.key.weighted_score``.
    """
    reference_pc, reference_mode = _parse_key(reference)
    estimate_pc, estimate_mode = _parse_key(estimate)
    if reference_pc is None or estimate_pc is None:
        return "unknown"
    if reference_pc == estimate_pc and reference_mode == estimate_mode:
        return "exact"
    if estimate_mode == reference_mode and (estimate_pc - reference_pc) % 12 == 7:
        return "fifth"
    if (
        estimate_mode != reference_mode
        and reference_mode == "major"
        and (estimate_pc - reference_pc) % 12 == 9
    ):
        return "relative"
    if (
        estimate_mode != reference_mode
        and reference_mode == "minor"
        and (estimate_pc - reference_pc) % 12 == 3
    ):
        return "relative"
    if estimate_mode != reference_mode and reference_pc == estimate_pc:
        return "parallel"
    return "other"


def same_key(reference: str, estimate: str) -> bool:
    """Whether two keys are exactly equal (enharmonic spellings count as equal)."""
    return key_relation(reference, estimate) == "exact"


def weighted_key_score(reference: str, estimate: str) -> float:
    """MIREX-style heuristic key score in ``[0, 1]`` (see :data:`RELATION_WEIGHT`)."""
    return RELATION_WEIGHT[key_relation(reference, estimate)]


def _check_lengths(references: Sequence[str], estimates: Sequence[str]) -> None:
    if len(references) != len(estimates):
        raise ValueError(
            f"expected as many references as estimates, got {len(references)} and {len(estimates)}"
        )


def exact_key_accuracy(references: Sequence[str], estimates: Sequence[str]) -> float:
    """Fraction of keys whose tonic and mode match exactly, in ``[0, 1]``.

    Empty input scores ``0.0`` (there is nothing to be accurate about), matching
    the chord and boundary metrics' "empty sides score zero" convention.
    """
    _check_lengths(references, estimates)
    if not references:
        return 0.0
    hits = sum(
        same_key(reference, estimate)
        for reference, estimate in zip(references, estimates, strict=True)
    )
    return hits / len(references)


def relative_key_error(references: Sequence[str], estimates: Sequence[str]) -> float:
    """Fraction of estimates that are the relative major/minor of the reference.

    This is the project's recurring failure mode made a metric: a major key
    called by its relative minor (or the reverse) is not an ordinary mistake,
    so it is reported on its own. Empty input scores ``0.0``.
    """
    _check_lengths(references, estimates)
    if not references:
        return 0.0
    hits = sum(
        key_relation(reference, estimate) == "relative"
        for reference, estimate in zip(references, estimates, strict=True)
    )
    return hits / len(references)


def key_relation_counts(references: Sequence[str], estimates: Sequence[str]) -> dict[str, int]:
    """How many pairs fall into each relation, with every relation present."""
    _check_lengths(references, estimates)
    counts = Counter(
        key_relation(reference, estimate)
        for reference, estimate in zip(references, estimates, strict=True)
    )
    return {relation: counts.get(relation, 0) for relation in RELATION_WEIGHT}
