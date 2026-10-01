"""Chord scoring semantics, verified against the CSR oracle fixture.

Every function here is pinned by ``tests/unit/test_csr_oracle.py`` against
``tests/fixtures/csr_oracle.json``: 22 GuitarSet comping takes x {instructed,
performed} annotations x {raw, triad-reduced} views, with expected
duration-CSR values recorded by the measurement harness on 2026-09-29 and
re-verified after a rebuild (2026-10-01). The semantics themselves are
original re-implementations from published definitions (MIREX-2010 equality
as scored by AceEval; Harte ``Root:quality[/bass]`` labels as shipped by
GuitarSet) — no code was copied.

Scoring rules that the oracle forced (do not "simplify" them away):

* a bracketed voicing tuple *replaces* the base voicing (``C:(1,5)`` is
  root+fifth only; degrees decode with the major-scale semitones and ``*``
  prefixes omit);
* an out-of-vocabulary head re-parses as ``root+head`` before falling back to
  a dominant/major reading (``Em/1`` sounds as E minor, ``min7`` as a minor
  seventh);
* :func:`mirex_equal` rescues an intersection of 2 pitch classes to a match
  when the *reference* carries a non-root bass — a direct note slash
  (``C/E``) or a Harte degree slash (``D#/5`` — the parser stores degree
  slashes as extension text, so the degree is decoded here) — that sounds
  inside the hypothesis; augmented/diminished references match from 2;
  a failed rescue returns 0.0 immediately, before the bass bonuses can apply.
* :func:`triad_reduce` keeps the ``m`` spelling for minor heads and collapses
  everything else to its root, including out-of-enum spellings
  (``E5``, ``Ehdim7``, ``A#m11`` -> ``E``, ``E``, ``A#``).
"""

from __future__ import annotations

import re

from song_chord_lyrics_analyzer.models.music import (
    PITCH_CLASS_NAMES,
    ChordQuality,
)
from song_chord_lyrics_analyzer.normalization.chords import parse_chord_label

__all__ = [
    "chord_pcs",
    "duration_csr",
    "mirex_equal",
    "reduce_ref_view",
    "triad_reduce",
]

#: Harte scale degrees -> semitones, for degree slashes (``D#/5`` -> root + 7)
#: and bracketed voicing tuples.
_SCALE_DEGREES: dict[int, int] = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}

#: MIREX-2010 quality -> relative pitch-class intervals, for the qualities the
#: enum can express.
_MIREX_INTERVALS: dict[ChordQuality, tuple[int, ...]] = {
    ChordQuality.MAJOR: (0, 4, 7),
    ChordQuality.MINOR: (0, 3, 7),
    ChordQuality.DOMINANT7: (0, 4, 7, 10),
    ChordQuality.MAJOR7: (0, 4, 7, 11),
    ChordQuality.MINOR7: (0, 3, 7, 10),
    ChordQuality.SUS2: (0, 2, 7),
    ChordQuality.SUS4: (0, 5, 7),
    ChordQuality.DIMINISHED: (0, 3, 6),
    ChordQuality.AUGMENTED: (0, 4, 8),
    ChordQuality.ADD9: (0, 2, 4, 7),
    ChordQuality.SIXTH: (0, 4, 7, 9),
    ChordQuality.MINOR_SIXTH: (0, 3, 7, 9),
    ChordQuality.NINTH: (0, 2, 4, 7, 10),
    ChordQuality.MINOR_NINTH: (0, 2, 3, 7, 10),
}

#: Raw extension token -> intervals, for Harte-world labels the enum lacks
#: (``C5``, ``C13``, ``Cminmaj7``, ...). Tokens are the quality head after the
#: ``min`` -> ``m`` spelling fold (``min7`` -> ``m7``).
_EXTENSION_INTERVALS: dict[str, tuple[int, ...]] = {
    "5": (0, 7),
    "7": (0, 4, 7, 10),
    "9": (0, 2, 4, 7, 10),
    "11": (0, 2, 4, 5, 7, 10),
    "13": (0, 2, 4, 7, 9, 10),
    "maj7": (0, 4, 7, 11),
    "maj9": (0, 2, 4, 7, 11),
    "maj13": (0, 2, 4, 7, 9, 11),
    "m7": (0, 3, 7, 10),
    "m9": (0, 2, 3, 7, 10),
    "m11": (0, 2, 3, 5, 7, 10),
    "minmaj7": (0, 3, 7, 11),
    "dim7": (0, 3, 6, 9),
    "hdim7": (0, 3, 6, 9),
    "7(#9)": (0, 3, 4, 7, 10),
    "7(#5)": (0, 4, 8, 10),
    "sus4(b7)": (0, 5, 7, 10),
}

#: Harte quality spellings -> our canonical suffixes.
_HARTE_QUALITY: dict[str, str] = {
    "maj": "",
    "major": "",
    "min": "m",
    "minor": "m",
    "min7": "m7",
    "min6": "m6",
    "min9": "m9",
    "min11": "m11",
}

#: Flat spellings normalise to the canonical sharp names.
_FLAT_TO_SHARP: dict[str, str] = {
    "Cb": "B",
    "Db": "C#",
    "Eb": "D#",
    "Fb": "E",
    "Gb": "F#",
    "Ab": "G#",
    "Bb": "A#",
}


def harte_to_label(value: str) -> str:
    """Convert a Harte ``Root:quality[/bass]`` label to our canonical form.

    ``Bb:min7`` -> ``A#m7``, ``F#:7/5`` -> ``F#7/5``, ``N`` stays ``N``.
    """
    value = value.strip()
    if value in ("N", "N*", ""):
        return "N"
    root, _, rest = value.partition(":")
    root = _FLAT_TO_SHARP.get(root, root)
    if not rest:
        return root
    quality, _, bass = rest.partition("/")
    quality = _HARTE_QUALITY.get(quality, quality)
    out = f"{root}{quality}"
    if bass:
        out += f"/{_FLAT_TO_SHARP.get(bass, bass)}"
    return out


def _decode_tuple(token: str) -> tuple[set[int], set[int]]:
    """Decode a bracketed voicing tuple: ``(13,*5)`` -> added/omitted semitones."""
    add: set[int] = set()
    omit: set[int] = set()
    for tok in token.split(","):
        tok = tok.strip()
        if not tok:
            continue
        omitting = tok.startswith("*")
        tok = tok.lstrip("*")
        match = re.fullmatch(r"([b#]*)(\d+)", tok)
        if not match:
            continue
        accidental, degree = match.group(1), int(match.group(2))
        degree = ((degree - 1) % 7) + 1
        semis = _SCALE_DEGREES[degree] + accidental.count("#") - accidental.count("b")
        (omit if omitting else add).add(semis % 12)
    return add, omit


def chord_pcs(label: str) -> tuple[frozenset[int], int | None, str | None]:
    """Pitch-class set, root pitch class and bass note name of one chord label.

    Labels outside the enum vocabulary fall back to the raw-extension table,
    then to re-parsing ``root+head`` as a chord (``Em/1`` reads as ``Em``),
    and finally to a best-effort dominant/major reading. A bracketed tuple
    *replaces* the base voicing (``D:(1,5)/5`` is root+fifth only), so
    Harte-world labels like ``B7(13,*5)`` still yield a sensible set.
    """
    parsed = parse_chord_label(label)
    if parsed.quality is ChordQuality.NO_CHORD or parsed.root is None:
        return frozenset(), None, None
    root = PITCH_CLASS_NAMES.index(parsed.root)
    intervals: tuple[int, ...] | None = _MIREX_INTERVALS.get(parsed.quality)
    if intervals is None:
        suffix = parsed.extensions[0] if parsed.extensions else ""
        # Slash-chord basses and bracketed tensions parse as part of the
        # suffix; take the quality head before the first ``(`` or ``/``
        # (``min7(*5)/1`` -> ``min7``), then map min->m spellings.
        head = re.split(r"[(/]", suffix, maxsplit=1)[0]
        if head.startswith("min"):
            head = "m" + head[3:]
        base = _EXTENSION_INTERVALS.get(head)
        if base is None:
            base = _MIREX_INTERVALS.get(parse_chord_label(f"{parsed.root}{head}").quality)
        if base is None:
            base = (
                _MIREX_INTERVALS[ChordQuality.DOMINANT7]
                if "7" in head
                else _MIREX_INTERVALS[ChordQuality.MAJOR]
            )
        pitch_set = set(base)
        tup = re.search(r"\(([^)]*)\)", suffix)
        if tup:
            add, omit = _decode_tuple(tup.group(1))
            pitch_set = (add | {0}) - omit
        intervals = tuple(sorted(pitch_set))
    pcs = frozenset((root + interval) % 12 for interval in intervals)
    return pcs, root, parsed.bass


def _bass_pc(label: str, root: int, bass: str | None) -> int | None:
    """Bass pitch class: a direct note slash (``C/E``) or a degree slash (``D#/5``)."""
    if bass:
        return PITCH_CLASS_NAMES.index(bass) % 12
    if "/" not in label:
        return None
    match = re.fullmatch(r"([b#]?)([1-7])", label.rsplit("/", 1)[-1])
    if not match:
        return None
    semis = (
        _SCALE_DEGREES[int(match.group(2))] + match.group(1).count("#") - match.group(1).count("b")
    )
    return (root + semis) % 12


def mirex_equal(ref: str, hyp: str) -> float:
    """MIREX-2010 equality of two chord labels (1.0 match, 0.0 mismatch).

    A match needs a pitch-class intersection of 3 — 2 when the *reference* is
    augmented or diminished. An intersection of 2 is rescued to a match when
    the reference's non-root bass note (a note slash or a Harte degree slash)
    sounds inside the hypothesis; bracket-voicing tuples opt out of the
    rescue. ``N`` matches only ``N``.
    """
    if ref == "N" or hyp == "N":
        return 1.0 if ref == hyp else 0.0
    ref_pcs, ref_root, ref_bass = chord_pcs(ref)
    hyp_pcs, _, _ = chord_pcs(hyp)
    if not ref_pcs or not hyp_pcs or ref_root is None:
        # chord_pcs only yields an empty set (or no root) for unparseable
        # input and for ``N``-world labels, handled above.
        return 1.0 if ref == hyp else 0.0
    threshold = (
        2
        if parse_chord_label(ref).quality in (ChordQuality.AUGMENTED, ChordQuality.DIMINISHED)
        else 3
    )
    intersection = len(ref_pcs & hyp_pcs)
    if intersection >= threshold:
        score = 1.0
    elif intersection == 2 and "(" not in ref:
        bass = _bass_pc(ref, ref_root, ref_bass)
        if bass is None or bass == ref_root or bass not in hyp_pcs:
            return 0.0
        score = 1.0
    else:
        return 0.0
    hyp_bass = parse_chord_label(hyp).bass
    if (
        ref_bass
        and ref_bass != parse_chord_label(ref).root
        and PITCH_CLASS_NAMES.index(ref_bass) in hyp_pcs
    ):
        score += 1.0
    if (
        hyp_bass
        and hyp_bass != parse_chord_label(hyp).root
        and PITCH_CLASS_NAMES.index(hyp_bass) in ref_pcs
    ):
        score += 1.0
    return score


def triad_reduce(labels: list[str]) -> list[str]:
    """Reduce labels to the 24-triad vocabulary (major/minor/N, flat aliases kept).

    The bracket/slash-stripped head drives the reduction: a minor head keeps
    its ``m`` spelling, ``N`` stays ``N``, and every other quality — including
    out-of-enum spellings like ``E5``, ``Ehdim7``, ``A#m11`` — collapses to
    its root.
    """
    out: list[str] = []
    for label in labels:
        head = label.split("(")[0].split("/")[0]
        parsed = parse_chord_label(head)
        if parsed.quality is ChordQuality.NO_CHORD or parsed.root is None:
            out.append("N" if parsed.quality is ChordQuality.NO_CHORD else label)
        elif parsed.quality is ChordQuality.MINOR:
            out.append(f"{parsed.root}m")
        else:
            out.append(parsed.root)
    return out


def reduce_ref_view(
    segments: list[tuple[float, float, str]],
) -> list[tuple[float, float, str]]:
    """Apply :func:`triad_reduce` to timed (start, end, label) segments."""
    return [(start, end, triad_reduce([label])[0]) for start, end, label in segments]


def duration_csr(
    ref: list[tuple[float, float, str]],
    hyp: list[tuple[float, float, str]],
) -> dict[str, float]:
    """Duration-weighted Chord Sequence Recall (AceEval ``crossSegment``).

    Zips the two segmentations over the overlapping timeline; overlapping time
    where the labels agree (:func:`mirex_equal`) counts toward the recall, so
    ``csr = agreeing seconds / reference seconds``.
    """
    if not ref:
        return {"csr": 0.0, "equal_s": 0.0, "total_s": 0.0}
    equal = total = 0.0
    i = j = 0
    while i < len(ref) and j < len(hyp):
        ref_start, ref_end, ref_label = ref[i]
        hyp_start, hyp_end, hyp_label = hyp[j]
        overlap = min(ref_end, hyp_end) - max(ref_start, hyp_start)
        if overlap > 0:
            total += overlap
            if mirex_equal(ref_label, hyp_label) > 0:
                equal += overlap
        if ref_end <= hyp_end:
            i += 1
        else:
            j += 1
    return {"csr": equal / total if total else 0.0, "equal_s": equal, "total_s": total}
