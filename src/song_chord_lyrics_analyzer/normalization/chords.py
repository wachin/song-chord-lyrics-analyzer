"""Chord label normalization (roadmap sections 13, 38 and 71).

This module separates *detected evidence* (the raw label an engine emitted)
from an *interpreted* chord. Unrecognised labels are never silently upgraded
into a precise chord: they keep their raw text and land in
:attr:`ChordQuality.OTHER` or :attr:`ChordQuality.UNKNOWN`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from song_chord_lyrics_analyzer.models.music import (
    CHORD_QUALITY_SUFFIX,
    NOTE_NAME_TO_PITCH_CLASS,
    PITCH_CLASS_NAMES,
    ChordQuality,
)

__all__ = [
    "NO_CHORD_LABELS",
    "ParsedChord",
    "normalize_note_name",
    "parse_chord_label",
    "render_chord_label",
    "transpose_chord_label",
    "transpose_note_name",
]

#: Labels that mean "no chord is playing".
NO_CHORD_LABELS = frozenset({"n", "nc", "no chord", "nochord", "none", "silence", "x"})

#: Characters engines use to mean sharp / flat / natural.
_UNICODE_REPLACEMENTS = {
    "\u266f": "#",  # MUSIC SHARP SIGN
    "\u266d": "b",  # MUSIC FLAT SIGN
    "\u266e": "",  # MUSIC NATURAL SIGN
    "\u0394": "maj",  # GREEK CAPITAL DELTA
    "\u00b0": "dim",  # DEGREE SIGN
}

#: Suffix -> interpreted quality. Phase 1 and 2 vocabulary plus common aliases.
SUFFIX_TO_QUALITY: dict[str, ChordQuality] = {
    "": ChordQuality.MAJOR,
    "maj": ChordQuality.MAJOR,
    "major": ChordQuality.MAJOR,
    "M": ChordQuality.MAJOR,
    "m": ChordQuality.MINOR,
    "min": ChordQuality.MINOR,
    "-": ChordQuality.MINOR,
    "minor": ChordQuality.MINOR,
    "7": ChordQuality.DOMINANT7,
    "dom7": ChordQuality.DOMINANT7,
    "maj7": ChordQuality.MAJOR7,
    "M7": ChordQuality.MAJOR7,
    "ma7": ChordQuality.MAJOR7,
    "m7": ChordQuality.MINOR7,
    "min7": ChordQuality.MINOR7,
    "-7": ChordQuality.MINOR7,
    "sus2": ChordQuality.SUS2,
    "sus4": ChordQuality.SUS4,
    "sus": ChordQuality.SUS4,
    "dim": ChordQuality.DIMINISHED,
    "o": ChordQuality.DIMINISHED,
    "aug": ChordQuality.AUGMENTED,
    "+": ChordQuality.AUGMENTED,
    "add9": ChordQuality.ADD9,
    "6": ChordQuality.SIXTH,
    "maj6": ChordQuality.SIXTH,
    "m6": ChordQuality.MINOR_SIXTH,
    "min6": ChordQuality.MINOR_SIXTH,
    "9": ChordQuality.NINTH,
    "m9": ChordQuality.MINOR_NINTH,
    "min9": ChordQuality.MINOR_NINTH,
}

_CHORD_RE = re.compile(r"^(?P<root>[A-Ga-g])(?P<accidental>[#b]{0,2})(?P<suffix>.*)$")
_BASS_RE = re.compile(r"^([A-Ga-g][#b]{0,2})$")


@dataclass(frozen=True)
class ParsedChord:
    """Result of parsing a chord label.

    Attributes:
        raw: The original label, byte-for-byte as supplied.
        root: Canonical sharp-spelled root, or ``None`` for "no chord".
        quality: Interpreted quality, ``OTHER``/``UNKNOWN`` when ambiguous.
        bass: Canonical slash-chord bass, when present.
        extensions: Uninterpreted suffix text for ``OTHER`` chords.
    """

    raw: str
    root: str | None = None
    quality: ChordQuality = ChordQuality.UNKNOWN
    bass: str | None = None
    extensions: tuple[str, ...] = ()

    @property
    def is_no_chord(self) -> bool:
        """Whether the label explicitly means "no chord"."""
        return self.quality is ChordQuality.NO_CHORD

    @property
    def is_recognized(self) -> bool:
        """Whether the quality was actually interpreted."""
        return self.quality not in (ChordQuality.OTHER, ChordQuality.UNKNOWN)

    @property
    def label(self) -> str:
        """Canonical rendering of the parsed chord."""
        return render_chord_label(
            self.root, self.quality, bass=self.bass, extensions=self.extensions
        )


def normalize_note_name(name: str) -> str:
    """Return the canonical sharp-spelled name of a note.

    Raises:
        ValueError: When ``name`` is not a recognised note spelling.
    """
    text = name.strip()
    for symbol, replacement in _UNICODE_REPLACEMENTS.items():
        text = text.replace(symbol, replacement)
    if not text:
        raise ValueError("empty note name")
    capitalized = text[0].upper() + text[1:]
    if capitalized not in NOTE_NAME_TO_PITCH_CLASS:
        raise ValueError(f"unknown note name: {name!r}")
    return PITCH_CLASS_NAMES[NOTE_NAME_TO_PITCH_CLASS[capitalized]]


def _split_slash_chord(suffix: str) -> tuple[str, str | None, bool]:
    """Split ``maj7/G`` into ``("maj7", "G", True)``.

    Returns:
        Tuple of (quality suffix, bass note, whether the bass part was valid).
    """
    if "/" not in suffix:
        return suffix, None, True
    quality_suffix, _, bass_text = suffix.partition("/")
    if not _BASS_RE.match(bass_text):
        return suffix, None, False
    return quality_suffix, bass_text, True


def parse_chord_label(label: str) -> ParsedChord:
    """Parse a chord label emitted by an engine or typed by a user.

    This function never raises for musical reasons: unparsable input keeps its
    raw text and is reported as :attr:`ChordQuality.UNKNOWN`.
    """
    raw = label.strip()
    if not raw:
        return ParsedChord(raw=label, quality=ChordQuality.UNKNOWN)

    normalized = raw
    for symbol, replacement in _UNICODE_REPLACEMENTS.items():
        normalized = normalized.replace(symbol, replacement)

    if normalized.lower() in NO_CHORD_LABELS:
        return ParsedChord(raw=label, quality=ChordQuality.NO_CHORD)

    match = _CHORD_RE.match(normalized)
    if match is None:
        return ParsedChord(raw=label, quality=ChordQuality.UNKNOWN)

    root_text = f"{match.group('root').upper()}{match.group('accidental')}"
    root = normalize_note_name(root_text)

    suffix, bass_text, bass_valid = _split_slash_chord(match.group("suffix"))
    if not bass_valid:
        return ParsedChord(
            raw=label,
            root=root,
            quality=ChordQuality.OTHER,
            extensions=(match.group("suffix"),),
        )

    bass = normalize_note_name(bass_text) if bass_text else None

    quality = SUFFIX_TO_QUALITY.get(suffix)
    if quality is None:
        # Case differences matter musically ("M7" is major seventh while "m7" is
        # minor seventh), so exact matches are resolved first and a lenient
        # lower-case lookup only handles non-ambiguous spellings like "MAJ7".
        case_insensitive = SUFFIX_TO_QUALITY.get(suffix.lower())
        if case_insensitive is not None:
            return ParsedChord(raw=label, root=root, quality=case_insensitive, bass=bass)
        return ParsedChord(
            raw=label, root=root, quality=ChordQuality.OTHER, bass=bass, extensions=(suffix,)
        )

    return ParsedChord(raw=label, root=root, quality=quality, bass=bass)


def render_chord_label(
    root: str | None,
    quality: ChordQuality,
    *,
    bass: str | None = None,
    extensions: tuple[str, ...] = (),
) -> str:
    """Render a chord label from structured parts.

    ``OTHER`` chords reuse their stored suffix text so that transposition never
    loses the original extension spelling.
    """
    if quality is ChordQuality.NO_CHORD:
        return "N"
    if root is None:
        # No evidence is not the same as silence: unknown stays visible.
        return "?"
    if quality is ChordQuality.OTHER:
        suffix = "".join(extensions)
    else:
        suffix = CHORD_QUALITY_SUFFIX.get(quality, "")
    label = f"{root}{suffix}"
    if bass is not None and bass != root:
        label = f"{label}/{bass}"
    return label


def transpose_note_name(name: str, semitones: int) -> str:
    """Transpose a note name by ``semitones``.

    The result always uses canonical sharp spelling; enharmonic respelling for
    flat keys is a later, presentation-only concern.
    """
    canonical = normalize_note_name(name)
    index = PITCH_CLASS_NAMES.index(canonical)
    return PITCH_CLASS_NAMES[(index + semitones) % 12]


def transpose_chord_label(label: str, semitones: int) -> str:
    """Transpose a chord label while preserving quality and slash bass.

    Unrecognised labels are returned unchanged: transposing evidence that was
    never interpreted would create false precision.
    """
    parsed = parse_chord_label(label)
    if parsed.is_no_chord or parsed.root is None:
        return "N" if parsed.is_no_chord else parsed.raw
    if not parsed.is_recognized:
        return parsed.raw

    new_root = transpose_note_name(parsed.root, semitones)
    new_bass = transpose_note_name(parsed.bass, semitones) if parsed.bass else None
    return render_chord_label(new_root, parsed.quality, bass=new_bass)
