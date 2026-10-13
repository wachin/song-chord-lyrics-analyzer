"""Editing the chord and lyric layers without touching the engine (Phase G).

The roadmap's rule for user corrections is a **separate overlay** over the
engine output: the engine's events are never overwritten - provenance stays,
both front ends read the same effective layer, and the raw output remains
exactly as the analysis produced it. This module implements that rule with
the same three plain pieces for both layers:

* :func:`effective_chords` and :func:`effective_lyrics` fold a list of
  commands over the base (engine) events and return the effective layer: the
  base order, minus what a command consumed, plus what a command produced -
  user-produced events marked ``source=USER_SOURCE`` so provenance is always
  readable.
* Every command (:class:`SetChordLabel`, :class:`SplitChord`,
  :class:`MergeChords`, :class:`TrimChord`, :class:`DeleteChord`,
  :class:`InsertChord` over chords; :class:`SetLyricText`,
  :class:`SetLyricTiming`, :class:`DeleteLyric`, :class:`InsertLyric` over
  lyric lines) applies to a list and returns a new one; the input is never
  mutated, and a command that cannot address its target raises
  :class:`~utils.errors.InputError`. Chord commands subclass
  :class:`ChordCommand`, lyric commands :class:`LyricCommand` - that marker
  is how the stack tells the two layers apart while keeping **one** tape.
* :class:`CommandStack` is the undo/redo tape over both base layers: push to
  apply, ``undo`` to unapply the last command, ``redo`` to apply it again -
  so a single ``Ctrl+Z`` walks back through chord and lyric edits in the
  order they were made. Because the bases are never touched, undo needs no
  stored snapshots.

Lyric lines are addressed by their **display index** - the position the
lyrics view draws them at - because a line may carry no timestamp at all,
while chords always have a start to address. :func:`effective_lyrics`
re-applies display order after every command, so the index a command
resolves against is always the list it was validated against, both live and
when a saved tape replays.

Nothing here imports Qt, numpy or an engine; the layers are tested with
plain lists, and the GUI pushes commands exactly the way a CLI would.
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from song_chord_lyrics_analyzer.app.lyrics_view import lyric_lines
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment
from song_chord_lyrics_analyzer.models.music import (
    NOTE_NAME_TO_PITCH_CLASS,
    ChordEvent,
    ChordQuality,
)
from song_chord_lyrics_analyzer.normalization.chords import transpose_note_name
from song_chord_lyrics_analyzer.utils.errors import InputError

__all__ = [
    "ChordCommand",
    "CommandStack",
    "DeleteChord",
    "DeleteLyric",
    "EditCommand",
    "InsertChord",
    "InsertLyric",
    "LyricCommand",
    "MERGE_SOURCE",
    "SIMPLIFY_SOURCE",
    "TRANSPOSE_SOURCE",
    "USER_SOURCE",
    "MergeChords",
    "SetChordLabel",
    "SetLyricText",
    "SetLyricTiming",
    "SimplifyChords",
    "SplitChord",
    "TransposeChords",
    "TrimChord",
    "effective_chords",
    "effective_lyrics",
]

#: Provenance source of a single-user correction.
USER_SOURCE = "user"

#: Provenance source of an event produced by merging two or more.
MERGE_SOURCE = "user-merge"

#: Provenance source of an event rewritten by a document-level transpose.
TRANSPOSE_SOURCE = "user-transpose"

#: Provenance source of an event rewritten by the simplification table.
SIMPLIFY_SOURCE = "user-simplify"

#: Suffixes the label parser accepts, mapped to their quality. Keeping the
#: table small is deliberate: it edits what the engines produce (triads,
#: sevenths, suspensions, explicit silence) and leaves everything else to
#: :class:`ChordQuality.OTHER` with the label kept verbatim.
_QUALITIES: dict[str, ChordQuality] = {
    "": ChordQuality.MAJOR,
    "m": ChordQuality.MINOR,
    "7": ChordQuality.DOMINANT7,
    "maj7": ChordQuality.MAJOR7,
    "m7": ChordQuality.MINOR7,
    "sus2": ChordQuality.SUS2,
    "sus4": ChordQuality.SUS4,
    "dim": ChordQuality.DIMINISHED,
    "aug": ChordQuality.AUGMENTED,
    "add9": ChordQuality.ADD9,
    "6": ChordQuality.SIXTH,
    "m6": ChordQuality.MINOR_SIXTH,
    "9": ChordQuality.NINTH,
    "m9": ChordQuality.MINOR_NINTH,
}

#: Suffixes that plausibly name a chord quality, for the ``OTHER`` fallback.
#: Anything else after the root is a typo, not an exotic quality - rejecting it
#: is what keeps "banana" out of the document while "13b9" gets through.
_CHORDISH = re.compile(r"(?:sus|add|maj|min|dim|aug|m|[0-9#b])+\Z")


class ChordCommand:
    """One reversible edit over a sequence of :class:`ChordEvent`."""

    def apply(self, events: Sequence[ChordEvent]) -> list[ChordEvent]:
        """The chord list with the edit applied; the input is not mutated."""
        raise NotImplementedError


class LyricCommand:
    """One reversible edit over a sequence of :class:`LyricSegment`."""

    def apply(self, lines: Sequence[LyricSegment]) -> list[LyricSegment]:
        """The lyric list with the edit applied; the input is not mutated."""
        raise NotImplementedError


#: Either layer's edit. The two markers - not a structural protocol - are what
#: lets :class:`CommandStack` dispatch each command to its own layer while the
#: tape itself stays one ordered list (one undo covers both layers).
EditCommand = ChordCommand | LyricCommand


def _find(events: Sequence[ChordEvent], start: float) -> int:
    """The index of the event starting exactly at ``start``."""
    for index, event in enumerate(events):
        if event.start == start:
            return index
    raise InputError(
        f"No chord event starts at {start!r} seconds.",
        hint="Chord edits address events by their exact start time.",
    )


def _user_version(original: ChordEvent, **changes: object) -> ChordEvent:
    """A user's edition of ``original``, provenance-stamped and re-labelled."""
    carried = changes.pop("label_carry", None)
    keep_label = carried if isinstance(carried, str) else None
    edited = original.__class__(**{**_as_kwargs(original), **changes})  # type: ignore[arg-type]
    edited.source = USER_SOURCE
    # OTHER evidence keeps the user's text verbatim ("C13b9" stays "C13b9");
    # parsed evidence re-renders from the parts, so "Am7" stays "Am7".
    edited.label = keep_label if keep_label is not None else edited.to_label()
    return edited


def _as_kwargs(event: ChordEvent) -> dict[str, object]:
    return {
        "start": event.start,
        "end": event.end,
        "root": event.root,
        "quality": event.quality,
        "bass": event.bass,
        "extensions": list(event.extensions),
        "label": event.label,
        "confidence": event.confidence,
        "source": event.source,
        "metadata": dict(event.metadata),
    }


@dataclass(frozen=True)
class DeleteChord(ChordCommand):
    """Remove one chord from the effective layer, addressed by its start.

    Deleting the wrong event is easy to undo, so the command is deliberately
    conservative: no auto-merge of the gap, no relabelling - the neighbours
    keep everything they had and an uncovered span behaves like any other gap.
    """

    start: float

    def apply(self, events: Sequence[ChordEvent]) -> list[ChordEvent]:
        index = _find(events, self.start)
        return [*events[:index], *events[index + 1 :]]


def _merge_version(first: ChordEvent, second: ChordEvent) -> ChordEvent:
    """The merge of two adjacent chords: the first's evidence, the union span."""
    merged = ChordEvent(
        start=first.start,
        end=second.end if second.end is not None else first.end,
        root=first.root,
        quality=first.quality,
        bass=first.bass,
        extensions=list(first.extensions),
        confidence=first.confidence,
    )
    merged.source = MERGE_SOURCE
    merged.label = merged.to_label()
    return merged


def _parse_label(text: str) -> dict[str, object]:
    """Structured evidence from a user-typed chord label.

    ``"N"`` is explicit silence; anything else must start with a canonical
    note name, optionally with an accepted quality suffix. A suffix outside
    the table keeps the whole label as :class:`ChordQuality.OTHER` evidence -
    the user's text is never silently dropped, but it is not inventively
    parsed either. A bass part (``"C/E"``) is *not* accepted here; splitting
    evidence that fine from free text is later-phase work.
    """
    label = text.strip()
    if not label:
        raise InputError("A chord label cannot be empty.")
    if label.upper() == "N":
        return {"root": None, "quality": ChordQuality.NO_CHORD, "bass": None}
    if "/" in label:
        raise InputError(
            f"Slash chords (got {label!r}) are not editable as free text yet.",
            hint='Edit the root and quality, e.g. "Am", "G7", "Fsus4", or "N".',
        )
    root = label[0].upper()
    if len(label) > 1 and label[1] == "#":
        root += "#"
    elif len(label) > 1 and label[1] == "b":
        raise InputError(
            f"Flats are not canonical pitch names (got {label!r}).",
            hint="Use the sharp spelling, e.g. A# instead of Bb.",
        )
    if root not in NOTE_NAME_TO_PITCH_CLASS:
        raise InputError(
            f"Cannot parse root note in chord {text!r}.",
            hint='Use a canonical note like C, C#, F#; or "N" for silence.',
        )
    suffix = label[len(root) :]
    quality = _QUALITIES.get(suffix)
    if quality is None:
        if suffix and not _CHORDISH.fullmatch(suffix):
            raise InputError(
                f"Cannot parse the chord quality in {text!r}.",
                hint='Use a known suffix like "m", "7", "sus4"; or just the '
                'root, e.g. "C"; or "N" for silence.',
            )
        return {"root": root, "quality": ChordQuality.OTHER, "bass": None}
    return {"root": root, "quality": quality, "bass": None}


@dataclass(frozen=True)
class SetChordLabel(ChordCommand):
    """Correct the musical evidence of one chord, keeping its timing.

    The typed label is parsed into canonical evidence (root, quality); the
    event's timing, confidence and metadata are kept, so the correction is a
    chord-level relabel, not a rewrite. ``"N"`` makes the event explicit
    silence, replacing whatever was there - the same evidence the engines
    produce for a "no chord" span.
    """

    start: float
    label: str

    def apply(self, events: Sequence[ChordEvent]) -> list[ChordEvent]:
        index = _find(events, self.start)
        evidence = _parse_label(self.label)
        # Pass the user's text on when the quality is OTHER, so an exotic
        # suffix like "13b9" survives rendering instead of collapsing to "C".
        keep_label = self.label.strip() if evidence["quality"] is ChordQuality.OTHER else None
        changed = _user_version(events[index], label_carry=keep_label, **evidence)
        return [*events[:index], changed, *events[index + 1 :]]


@dataclass(frozen=True)
class SplitChord(ChordCommand):
    """Cut one chord in two at ``at`` seconds; both halves keep its evidence."""

    start: float
    at: float

    def __post_init__(self) -> None:
        if self.at <= self.start:
            raise InputError(
                f"split position ({self.at!r}) must be after the chord start ({self.start!r})."
            )

    def apply(self, events: Sequence[ChordEvent]) -> list[ChordEvent]:
        index = _find(events, self.start)
        event = events[index]
        if event.end is not None and self.at >= event.end:
            raise InputError(
                f"split position ({self.at!r}) is not inside the chord "
                f"({event.start!r}..{event.end!r})."
            )
        kept = _user_version(event, end=self.at)
        remainder = _user_version(event, start=self.at)
        return [*events[:index], kept, remainder, *events[index + 1 :]]


@dataclass(frozen=True)
class MergeChords(ChordCommand):
    """Merge two adjacent chords (by start) into one spanning both.

    The merged event keeps the first chord's evidence and spans from the
    first's start to the second's end (or its own, if the second is open
    ended). An open-ended first chord absorbs the second's span.
    """

    first_start: float
    second_start: float

    def __post_init__(self) -> None:
        if self.second_start <= self.first_start:
            raise InputError(
                f"second chord ({self.second_start!r}) must start after the "
                f"first ({self.first_start!r})."
            )

    def apply(self, events: Sequence[ChordEvent]) -> list[ChordEvent]:
        first_index = _find(events, self.first_start)
        second_index = _find(events, self.second_start)
        if second_index != first_index + 1:
            raise InputError(
                "Only adjacent chords can be merged: something sits between "
                f"{self.first_start!r} and {self.second_start!r}.",
                hint="Delete or trim the chord in between first.",
            )
        merged = _merge_version(events[first_index], events[second_index])
        return [*events[:first_index], merged, *events[second_index + 1 :]]


@dataclass(frozen=True)
class TrimChord(ChordCommand):
    """Move one boundary of a chord: its start later, or its end earlier.

    An explicit-trim chord that would end where it starts is rejected here; a
    zero-length chord has nothing to draw and nothing to seek to.
    """

    start: float
    new_start: float | None = None
    new_end: float | None = None

    def __post_init__(self) -> None:
        if self.new_start is None and self.new_end is None:
            raise InputError("A trim moves at least one boundary: give new_start or new_end.")
        if self.new_start is not None and self.new_start < 0:
            raise InputError(f"new_start must not be negative, got {self.new_start!r}")

    def apply(self, events: Sequence[ChordEvent]) -> list[ChordEvent]:
        index = _find(events, self.start)
        event = events[index]
        new_start = event.start if self.new_start is None else self.new_start
        new_end = event.end if self.new_end is None else self.new_end
        if self.new_start is not None and self.new_start > event.start:
            if event.end is not None and self.new_start >= event.end:
                raise InputError(
                    f"new_start ({self.new_start!r}) is not inside the chord "
                    f"({event.start!r}..{event.end!r})."
                )
            if event.end is None:
                raise InputError(
                    "An open-ended chord cannot be trimmed from the start: its end is unknown.",
                )
        if new_end is not None and new_end <= new_start:
            raise InputError(f"a trimmed chord must stay non-empty: {new_start!r}..{new_end!r}.")
        changed = _user_version(event, start=new_start, end=new_end)
        return [*events[:index], changed, *events[index + 1 :]]


@dataclass(frozen=True)
class InsertChord(ChordCommand):
    """Add a chord of the user's choosing at a time the layer does not cover.

    The evidence comes from the same parser as :class:`SetChordLabel`, so the
    user types ``"Am"`` or ``"N"`` and gets the same canonical event an edit
    produces — ``source="user"``, no engine fields carried over. The insert
    point must be uncovered by every event (not merely free between two) so
    an insertion can never silently overlap an engine's guess.
    """

    at: float
    label: str
    end: float | None = None

    def __post_init__(self) -> None:
        if self.end is not None and self.end <= self.at:
            raise InputError(f"the inserted chord must stay non-empty: {self.at!r}..{self.end!r}.")

    def apply(self, events: Sequence[ChordEvent]) -> list[ChordEvent]:
        event = _inserted(events, self.at, self.label, self.end)
        index = bisect.bisect_left([e.start for e in events], self.at)
        return [*events[:index], event, *events[index:]]


def _inserted(events: Sequence[ChordEvent], at: float, label: str, end: float | None) -> ChordEvent:
    """Build the fresh user event for an insertion, validating coverage."""
    evidence = _parse_label(label)
    inserted = ChordEvent(start=at, end=end, **evidence)  # type: ignore[arg-type]
    inserted.source = USER_SOURCE
    inserted.label = label.strip() if evidence["quality"] is ChordQuality.OTHER else inserted.label
    for event in events:
        if event.end is not None and event.start <= at < event.end:
            raise InputError(
                f"the time {at!r} is already covered by the chord "
                f"{event.start!r}..{event.end!r}; trim or split it first.",
                hint="Insert only into uncovered time, scoped by the split or trim.",
            )
    return inserted


# -- document-level transforms (Phase H) ----------------------------------


@dataclass(frozen=True)
class TransposeChords(ChordCommand):
    """Rewrite every editable event of the whole layer by ``semitones``.

    The whole-layer re-labelling the roadmap calls the transpose workflow:
    timing, confidence and metadata are untouched, roots and slash basses
    move, and provenance is stamped ``source="user-transpose"``. Silence,
    unrecognised (``OTHER``/``UNKNOWN``) and evidence-less events are left
    exactly as the analysis produced them - transposing them would *invent*
    the interpretation the engine never claimed (the same rule
    :func:`~normalization.chords.transpose_chord_label` runs on). Applying it
    twice moves by ``2 * semitones``, so undo is simply the opposite offset -
    no snapshots on the tape.
    """

    semitones: int

    def __post_init__(self) -> None:
        if not -11 <= self.semitones <= 11:
            raise InputError(
                f"semitones must be within -11..+11, got {self.semitones!r}",
                hint="An octave is the same music; use the in-octave offset.",
            )
        if self.semitones == 0:
            raise InputError("A transpose of 0 semitones changes nothing.")

    def apply(self, events: Sequence[ChordEvent]) -> list[ChordEvent]:
        out: list[ChordEvent] = []
        for event in events:
            editable = (
                event.root is not None
                and event.quality is not ChordQuality.NO_CHORD
                # Unrecognised evidence is un-transposable by the same rule the
                # library transpose runs on: rewriting a raw label would invent
                # precision the engine never claimed ("B13b9" stays "B13b9").
                and event.quality is not ChordQuality.OTHER
                and event.quality is not ChordQuality.UNKNOWN
            )
            if not editable:
                out.append(event)
                continue
            edited = _user_version(
                event,
                root=transpose_note_name(event.root, self.semitones),  # type: ignore[arg-type]
                bass=(
                    transpose_note_name(event.bass, self.semitones)
                    if event.bass is not None
                    else None
                ),
            )
            edited.source = TRANSPOSE_SOURCE
            out.append(edited)
        return out


#: The simplification table (roadmap Phase H): qualities reduced to the
#: triad underneath them. Extensions and alterations collapse; voicings that
#: already are triads (susensions, dim, aug) and evidence without a parsed
#: quality are deliberately untouched. Documented and tested together so the
#: table is a decision, not an accident.
_SIMPLIFICATION: dict[ChordQuality, ChordQuality] = {
    ChordQuality.DOMINANT7: ChordQuality.MAJOR,
    ChordQuality.MAJOR7: ChordQuality.MAJOR,
    ChordQuality.ADD9: ChordQuality.MAJOR,
    ChordQuality.SIXTH: ChordQuality.MAJOR,
    ChordQuality.NINTH: ChordQuality.MAJOR,
    ChordQuality.MINOR7: ChordQuality.MINOR,
    ChordQuality.MINOR_SIXTH: ChordQuality.MINOR,
    ChordQuality.MINOR_NINTH: ChordQuality.MINOR,
}


@dataclass(frozen=True)
class SimplifyChords(ChordCommand):
    """Collapse extensions/alterations to the triad the table declares.

    ``Am7`` becomes ``Am``, ``Cmaj7`` becomes ``C``; suspensions, dim, aug
    and unrecognised evidence stay verbatim. Timing and confidence are kept;
    provenance is stamped ``source="user-simplify"``. Idempotent: applying it
    to an already-triad layer changes nothing.
    """

    def apply(self, events: Sequence[ChordEvent]) -> list[ChordEvent]:
        out: list[ChordEvent] = []
        for event in events:
            reduced = _SIMPLIFICATION.get(event.quality)
            if reduced is None:
                out.append(event)
                continue
            edited = _user_version(event, quality=reduced)
            edited.source = SIMPLIFY_SOURCE
            out.append(edited)
        return out


# -- the lyric layer ------------------------------------------------------


def _find_line(lines: Sequence[LyricSegment], index: int) -> int:
    """The index itself, once it addresses a line of ``lines``."""
    if not 0 <= index < len(lines):
        raise InputError(
            f"No lyric line at position {index}: the document has {len(lines)}.",
            hint="Lyric edits address lines by their position in the lyrics view.",
        )
    return index


def _lyric_version(
    original: LyricSegment,
    *,
    text: str,
    start: float | None,
    end: float | None,
) -> LyricSegment:
    """A user's edition of ``original``, provenance-stamped.

    The engine's word annotations ride along untouched: they are still the
    evidence for *when* each word sounded, and the overlay rule keeps the
    engine layer itself on the other side of ``CommandStack.base``.
    """
    return LyricSegment(
        text=text,
        start=start,
        end=end,
        words=list(original.words),
        confidence=original.confidence,
        language=original.language,
        source=USER_SOURCE,
        kind=original.kind,
    )


@dataclass(frozen=True)
class SetLyricText(LyricCommand):
    """Replace the words of one lyric line, keeping its timings.

    The whole line's text is replaced in one command - correcting a line is
    rewriting it, not editing a word at a time - while the line's timestamps,
    its engine words and its kind stay exactly as they were. An empty line is
    rejected: blanking a line is deleting it, and the tape should say so.
    """

    index: int
    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise InputError(
                "A lyric line cannot be empty.",
                hint="Delete the line instead of blanking it.",
            )

    def apply(self, lines: Sequence[LyricSegment]) -> list[LyricSegment]:
        index = _find_line(lines, self.index)
        changed = _lyric_version(
            lines[index], text=self.text.strip(), start=lines[index].start, end=lines[index].end
        )
        return [*lines[:index], changed, *lines[index + 1 :]]


@dataclass(frozen=True)
class SetLyricTiming(LyricCommand):
    """Move one boundary of a lyric line: its start, its end, or both.

    A line the engine left without timestamps gains them here (its start may
    be set while its end stays open), which is how an untimed line joins the
    clock. An end may not be set before a start exists - a boundary anchored
    to nothing marks no time on the clock - and a line that would end where
    it starts is rejected, so nothing invisible enters the layer.
    """

    index: int
    new_start: float | None = None
    new_end: float | None = None

    def __post_init__(self) -> None:
        if self.new_start is None and self.new_end is None:
            raise InputError(
                "A timing edit moves at least one boundary: give new_start or new_end."
            )
        if self.new_start is not None and self.new_start < 0:
            raise InputError(f"new_start must not be negative, got {self.new_start!r}")

    def apply(self, lines: Sequence[LyricSegment]) -> list[LyricSegment]:
        index = _find_line(lines, self.index)
        line = lines[index]
        start = line.start if self.new_start is None else self.new_start
        end = line.end if self.new_end is None else self.new_end
        if end is not None and start is None:
            raise InputError(
                "A lyric line needs a start before it can have an end.",
                hint="Set the start first, then the end.",
            )
        if end is not None and start is not None and end <= start:
            raise InputError(f"a lyric line must stay non-empty: {start!r}..{end!r}.")
        changed = _lyric_version(line, text=line.text, start=start, end=end)
        return [*lines[:index], changed, *lines[index + 1 :]]


@dataclass(frozen=True)
class DeleteLyric(LyricCommand):
    """Remove one lyric line from the effective layer, addressed by index.

    No auto-merge of neighbours, no re-timing of anything else: deleting the
    wrong line is one undo away, so the command stays as conservative as
    :class:`DeleteChord`.
    """

    index: int

    def apply(self, lines: Sequence[LyricSegment]) -> list[LyricSegment]:
        index = _find_line(lines, self.index)
        return [*lines[:index], *lines[index + 1 :]]


@dataclass(frozen=True)
class InsertLyric(LyricCommand):
    """Add a line of the user's choosing to the transcript.

    The line enters at the end of the layer; a timed line re-sorts into
    playback order with the fold's next display pass, an untimed line joins
    the dimmed group until the user gives it a start. As with
    :class:`InsertChord`, a timed insertion may not overlap a line the engine
    already placed - filling a gap is fine, arguing with the engine's guess
    about *whose* span covers an instant is not.
    """

    text: str
    start: float | None = None
    end: float | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise InputError(
                "A lyric line cannot be empty.",
                hint="Give the line its words, or do not insert it.",
            )
        if self.start is not None and self.start < 0:
            raise InputError(f"start must not be negative, got {self.start!r}")
        if self.end is not None:
            if self.start is None:
                raise InputError(
                    "A lyric line needs a start before it can have an end.",
                    hint="Insert with a start (or untimed) and set the end afterwards.",
                )
            if self.end <= self.start:
                raise InputError(f"a lyric line must stay non-empty: {self.start!r}..{self.end!r}.")

    def apply(self, lines: Sequence[LyricSegment]) -> list[LyricSegment]:
        inserted = LyricSegment(
            text=self.text.strip(),
            start=self.start,
            end=self.end,
            source=USER_SOURCE,
        )
        for line in lines:
            if line.start is None or self.start is None:
                continue  # an untimed line claims no time to overlap
            line_end = float("inf") if line.end is None else line.end
            inserted_end = float("inf") if self.end is None else self.end
            if line.start < inserted_end and self.start < line_end:
                raise InputError(
                    f"the time {self.start!r} is already part of the lyric line "
                    f"{line.start!r}..{line.end!r}.",
                    hint="Insert only into uncovered time, or edit the existing line.",
                )
        return [*lines, inserted]


def effective_chords(
    base: Iterable[ChordEvent],
    commands: Iterable[ChordCommand],
) -> list[ChordEvent]:
    """The effective chord layer: ``commands``, applied in order over ``base``.

    The returned list is in playback order, each event with the evidence
    either the engine or the user produced - ``source`` always tells which.
    The inputs are never mutated; an invalid command raises before any of its
    successors is applied, so the base layer survives a failed batch intact.
    """
    events = sorted(base, key=lambda event: event.start)
    for command in commands:
        events = command.apply(events)
    return sorted(events, key=lambda event: event.start)


def effective_lyrics(
    base: Iterable[LyricSegment],
    commands: Iterable[LyricCommand],
) -> list[LyricSegment]:
    """The effective lyric layer: ``commands``, applied in order over ``base``.

    Display order - the timed lines in playback order, then the untimed ones
    (``lyric_lines``) - is established on the base **and re-applied after every
    command**. That repetition is what makes display-index addressing sound:
    a line that gains or moves its timestamps jumps to its new place before
    the next command resolves, so each command's index is validated against
    exactly the list it will replay against, live and from a saved tape.

    The inputs are never mutated; an invalid command raises before any of its
    successors is applied, so the base layer survives a failed batch intact.
    """
    lines = list(lyric_lines(base))
    for command in commands:
        lines = list(lyric_lines(command.apply(lines)))
    return lines


class CommandStack:
    """Undo/redo over one base layer per kind: chords and lyrics.

    The bases are given once (the engine's events and lines, in any order)
    and never mutated. ``push`` applies a command to the current effective
    layer of *its own kind* and records it on the one shared tape; ``undo``/
    ``redo`` move commands between the applied and redo tapes, whichever
    layer they address, so a single undo walks back through the user's
    history in the order they made it. :attr:`effective` and
    :attr:`effective_lyrics` are the layers both front ends read. Pushing
    after an undo discards the redo tape, as every editor does.
    """

    def __init__(
        self,
        base: Iterable[ChordEvent],
        *,
        lyrics: Iterable[LyricSegment] = (),
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self._base = tuple(base)
        self._lyrics_base = tuple(lyrics)
        self._applied: list[EditCommand] = []
        self._redo: list[EditCommand] = []
        self._on_change = on_change

    # -- state -------------------------------------------------------------

    @property
    def effective(self) -> list[ChordEvent]:
        """The current chord layer: base + every applied chord command."""
        chords = [command for command in self._applied if isinstance(command, ChordCommand)]
        return effective_chords(self._base, chords)

    @property
    def effective_lyrics(self) -> list[LyricSegment]:
        """The current lyric layer: base + every applied lyric command."""
        lines = [command for command in self._applied if isinstance(command, LyricCommand)]
        return effective_lyrics(self._lyrics_base, lines)

    @property
    def base(self) -> tuple[ChordEvent, ...]:
        """The untouched engine chord layer, exactly as the analysis produced it."""
        return self._base

    @property
    def base_lyrics(self) -> tuple[LyricSegment, ...]:
        """The untouched engine lyric layer, exactly as the analysis produced it."""
        return self._lyrics_base

    def effective_chord_at(self, position: float) -> ChordEvent | None:
        """The effective chord sounding at ``position``, or ``None``.

        Same half-open ``start <= position < end`` coverage as
        ``SongSession.chord_at``, but over the edited layer: after an edit,
        the window must show and edit what the user just made, not what the
        engine guessed.
        """
        events = self.effective
        hit: ChordEvent | None = None
        for event in events:
            if event.start <= position and (event.end is None or position < event.end):
                hit = event
            elif event.start > position:
                break
        return hit if hit is not None else None

    @property
    def can_undo(self) -> bool:
        return bool(self._applied)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def applied(self) -> tuple[EditCommand, ...]:
        """The applied commands, oldest first - what persistence serialises."""
        return tuple(self._applied)

    def __len__(self) -> int:
        """How many commands are applied (the depth of the undo tape)."""
        return len(self._applied)

    # -- tape --------------------------------------------------------------

    def push(self, command: EditCommand) -> None:
        """Apply ``command`` and record it; the redo tape is discarded.

        A command that cannot address its event or line raises and leaves the
        stack exactly as it was - a bad edit never poisons the undo tape.
        """
        if isinstance(command, LyricCommand):
            command.apply(self.effective_lyrics)
        else:
            command.apply(self.effective)
        self._applied.append(command)
        self._redo.clear()
        self._notify()

    def undo(self) -> EditCommand | None:
        """Take the last applied command back; ``None`` when nothing to undo."""
        if not self._applied:
            return None
        command = self._applied.pop()
        self._redo.append(command)
        self._notify()
        return command

    def redo(self) -> EditCommand | None:
        """Reapply the most recently undone command; ``None`` when none."""
        if not self._redo:
            return None
        command = self._redo.pop()
        self._applied.append(command)
        self._notify()
        return command

    def _notify(self) -> None:
        if self._on_change is not None:
            self._on_change()
