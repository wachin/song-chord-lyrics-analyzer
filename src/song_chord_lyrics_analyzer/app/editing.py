"""Editing the chord layer without touching the engine's answer (Phase G).

The roadmap's rule for user corrections is a **separate overlay** over the
engine output: the engine's events are never overwritten - provenance stays,
both front ends read the same effective layer, and the raw output remains
exactly as the analysis produced it. This module implements that rule for
chords with three plain pieces:

* :func:`effective_chords` folds a list of commands over the base (engine)
  events and returns the effective chord layer: the base order, minus what a
  command consumed, plus what a command produced - user-produced events marked
  ``source=USER_SOURCE`` so provenance is always readable.
* Every command (:class:`SetChordLabel`, :class:`SplitChord`,
  :class:`MergeChords`, :class:`TrimChord`) applies to an event list and
  returns a new one; the input is never mutated, and a command that cannot
  address its event raises :class:`~utils.errors.InputError`.
* :class:`CommandStack` is the undo/redo tape over one base layer: push to
  apply, ``undo`` to unapply the last command, ``redo`` to apply it again.
  Because the base is never touched, undo needs no stored snapshots.

Nothing here imports Qt, numpy or an engine; the layer is tested with plain
lists, and the GUI pushes commands exactly the way a CLI would.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from song_chord_lyrics_analyzer.models.music import (
    NOTE_NAME_TO_PITCH_CLASS,
    ChordEvent,
    ChordQuality,
)
from song_chord_lyrics_analyzer.utils.errors import InputError

__all__ = [
    "CommandStack",
    "EditCommand",
    "MERGE_SOURCE",
    "USER_SOURCE",
    "MergeChords",
    "SetChordLabel",
    "SplitChord",
    "TrimChord",
    "effective_chords",
]

#: Provenance source of a single-user correction.
USER_SOURCE = "user"

#: Provenance source of an event produced by merging two or more.
MERGE_SOURCE = "user-merge"

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


class EditCommand(Protocol):
    """One reversible edit over a sequence of :class:`ChordEvent`."""

    def apply(self, events: Sequence[ChordEvent]) -> list[ChordEvent]:
        """The chord list with the edit applied; the input is not mutated."""


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
class SetChordLabel:
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
class SplitChord:
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
class MergeChords:
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
class TrimChord:
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


def effective_chords(
    base: Iterable[ChordEvent],
    commands: Iterable[EditCommand],
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


class CommandStack:
    """Undo/redo over one base chord layer.

    The base is given once (the engine's events, in any order) and never
    mutated. ``push`` applies a command to the current effective layer and
    records it; ``undo``/``redo`` move commands between the applied and redo
    tapes; :attr:`effective` is the layer both front ends read. Pushing after
    an undo discards the redo tape, as every editor does.
    """

    def __init__(
        self,
        base: Iterable[ChordEvent],
        *,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self._base = tuple(base)
        self._applied: list[EditCommand] = []
        self._redo: list[EditCommand] = []
        self._on_change = on_change

    # -- state -------------------------------------------------------------

    @property
    def effective(self) -> list[ChordEvent]:
        """The current chord layer: base + every applied command."""
        return effective_chords(self._base, self._applied)

    @property
    def base(self) -> tuple[ChordEvent, ...]:
        """The untouched engine layer, exactly as the analysis produced it."""
        return self._base

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

    def __len__(self) -> int:
        """How many commands are applied (the depth of the undo tape)."""
        return len(self._applied)

    # -- tape --------------------------------------------------------------

    def push(self, command: EditCommand) -> None:
        """Apply ``command`` and record it; the redo tape is discarded.

        A command that cannot address its event raises and leaves the stack
        exactly as it was - a bad edit never poisons the undo tape.
        """
        current = effective_chords(self._base, self._applied)
        command.apply(current)  # validates now, before it is recorded
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
