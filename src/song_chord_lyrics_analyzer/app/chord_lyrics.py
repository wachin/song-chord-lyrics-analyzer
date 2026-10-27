"""Place chords above the lyric words they belong to (roadmap Phase F).

Phase F already put the chord layer and the lyric layer on **one** playback
clock (``SongSession.chord_at`` / ``lyric_at`` / ``word_at``). This module adds
the presentation the two layers were waiting for: a chord chart in which every
chord sits above the word that is sounding when the chord changes, the layout
Chordify and Chord AI are known for.

The alignment is a *projection*, not a second clock:

* a chord is placed over the timed word whose ``start <= chord.start < end``,
  or over the first word that starts after it when the chord lands before the
  first word; a word without timestamps is never used as an anchor;
* a line without word timestamps falls back to a proportional position between
  the line's own start and end, which is the best the evidence supports;
* a chord that starts in an instrumental gap (an intro, a break, a solo) is
  drawn in its own chord-only row, so instrumental harmony is visible instead
  of being silently attached to the next lyric line;
* a chord that starts before the first lyric line but overlaps it is shown at
  the start of that line; a chord that merely spans into a line from a previous
  line is not repeated, because only changes are placed.

The result is pure data, so it is covered with plain lists and no Qt, no audio
and no engine: :class:`ChordLyricLine` carries the text, the placed chords and
the pre-built monospace chord row, and the widget only paints it.

Canonical labels stay sharp-spelled in the document; ``prefer_flats`` respells
them for a flat key through
:mod:`song_chord_lyrics_analyzer.normalization.spelling`.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from song_chord_lyrics_analyzer.app.lyrics_view import lyric_lines
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricWord
from song_chord_lyrics_analyzer.models.music import ChordEvent
from song_chord_lyrics_analyzer.normalization.spelling import spell_chord_label

__all__ = [
    "INSTRUMENTAL_TEXT",
    "ChordLyricLine",
    "PlacedChord",
    "chord_lyric_lines",
]

#: Text drawn under a chord-only row, marking a stretch without lyric lines.
INSTRUMENTAL_TEXT = "· · ·"

#: A gap row longer than this is split so the chord labels stay readable.
MAX_CHORDS_PER_GAP_ROW = 8

#: Minimum character width of a chord-only row.
MIN_GAP_ROW_WIDTH = 24


@dataclass(frozen=True)
class PlacedChord:
    """One chord seated at a character column of a lyric line.

    Attributes:
        label: The label to draw, already spelled for the song's key.
        start: Chord onset in seconds (the evidence the placement rests on).
        end: Chord end in seconds when the engine reported one.
        column: Zero-based character column in the lyric text. The chord row
            is monospace and padded, so this column is exactly above the word.
        word_index: Index of the anchored word in the segment's word list, or
            ``None`` when the line carries no word timestamps and the position
            is proportional.
    """

    label: str
    start: float
    end: float | None
    column: int
    word_index: int | None


@dataclass(frozen=True)
class ChordLyricLine:
    """One drawn row: the lyric line (or an instrumental gap) plus its chords.

    Attributes:
        text: The lyric text, or :data:`INSTRUMENTAL_TEXT` for a gap row.
        chords: The chords placed over this row, in time order.
        chord_row: The pre-built monospace chord row, with one character per
            lyric character and trailing spaces stripped. Empty when the row
            has no chords.
        segment: The lyric segment this row draws, or ``None`` for a gap row.
        is_gap: Whether the row is a chord-only instrumental stretch.
        start: Row start in seconds when known (a chord onset for a gap row).
        end: Row end in seconds when known.
    """

    text: str
    chords: tuple[PlacedChord, ...]
    chord_row: str
    segment: LyricSegment | None = None
    is_gap: bool = False
    start: float | None = None
    end: float | None = None

    @property
    def has_chords(self) -> bool:
        """Whether this row carries at least one chord label."""
        return bool(self.chords)


@dataclass(frozen=True)
class _Timed:
    """A chord paired with the end the next chord or the track gives it."""

    start: float
    end: float
    label: str
    source: ChordEvent


def _line_text(segment: LyricSegment) -> str:
    """The text to draw for a segment: its own, or its words joined."""
    return segment.text or " ".join(word.text for word in segment.words)


def _word_offsets(text: str, words: Sequence[LyricWord]) -> list[int]:
    """Character offset of every word inside ``text``, found in order.

    Repeated words are resolved by searching from the end of the previous one,
    so ``"la la"`` maps its second word to column 3 rather than to column 0.
    A word the text does not contain (an edited line, a punctuation mismatch)
    falls back to the current cursor, which keeps the offsets monotonic instead
    of inventing a match.
    """
    offsets: list[int] = []
    cursor = 0
    for word in words:
        found = text.find(word.text, cursor) if word.text else -1
        if found < 0:
            found = min(cursor, len(text))
        offsets.append(found)
        cursor = found + len(word.text)
    return offsets


def _anchor_column(
    position: float,
    text: str,
    words: Sequence[LyricWord],
    offsets: Sequence[int],
    *,
    start: float | None,
    end: float | None,
) -> tuple[int, int | None]:
    """The column and word index a chord onset is drawn above.

    Timed words win: the chord sits over the word sounding at ``position``.
    Without them the position is interpolated across the line, and with no
    line geometry either the chord starts at column zero. The column is always
    clamped inside the text, so a malformed timestamp can never draw a chord
    past the end of the line.
    """
    if not text:
        return 0, None
    timed = [
        (offset, word.start, index)
        for index, (word, offset) in enumerate(zip(words, offsets, strict=False))
        if word.start is not None
    ]
    if timed:
        if position <= timed[0][1]:
            return max(0, min(timed[0][0], len(text) - 1)), timed[0][2]
        starts = [item[1] for item in timed]
        chosen = timed[max(0, bisect_right(starts, position) - 1)]
        return max(0, min(chosen[0], len(text) - 1)), chosen[2]
    if start is not None and end is not None and end > start:
        fraction = min(1.0, max(0.0, (position - start) / (end - start)))
        return min(len(text) - 1, round(fraction * (len(text) - 1))), None
    return 0, None


def _resolve_collisions(placements: list[PlacedChord]) -> list[PlacedChord]:
    """Nudge labels apart so no two chords overwrite each other.

    Onset times are evidence, so the first chord keeps its exact column. A
    later chord that would collide moves right until one clear space separates
    it from every label already placed. A word with two quick chord changes can
    therefore push the second label past the word, which is honest: the lyric
    text no longer has a character to anchor it to.
    """
    placed: list[PlacedChord] = []
    for chord in sorted(placements, key=lambda item: (item.column, item.start)):
        column = chord.column
        changed = True
        while changed:
            changed = False
            for other in placed:
                other_end = other.column + len(other.label)
                if other.column <= column < other_end + 1 or (
                    column <= other.column < column + len(chord.label) + 1
                ):
                    column = other_end + 1
                    changed = True
        placed.append(
            PlacedChord(
                label=chord.label,
                start=chord.start,
                end=chord.end,
                column=column,
                word_index=chord.word_index,
            )
        )
    return placed


def _chord_row(placements: Sequence[PlacedChord], text: str) -> str:
    """Render the monospace chord row for ``placements`` above ``text``.

    The row is exactly as wide as the lyric text or the last placed label,
    whichever is longer, so a chord above the last word is never truncated.
    """
    width = len(text)
    for chord in placements:
        width = max(width, chord.column + len(chord.label))
    if width <= 0:
        return ""
    row = [" "] * width
    for chord in placements:
        row[chord.column : chord.column + len(chord.label)] = list(chord.label)
    return "".join(row).rstrip()


def _place_on_line(
    segment: LyricSegment,
    events: Sequence[_Timed],
    *,
    line_end: float,
    prefer_flats: bool,
) -> ChordLyricLine:
    """Build one lyric line with its chords seated over its words."""
    text = _line_text(segment)
    words = list(segment.words)
    offsets = _word_offsets(text, words)
    placements: list[PlacedChord] = []
    for event in events:
        column, word_index = _anchor_column(
            event.start,
            text,
            words,
            offsets,
            start=segment.start,
            end=line_end,
        )
        placements.append(
            PlacedChord(
                label=spell_chord_label(event.label, prefer_flats=prefer_flats),
                start=event.start,
                end=event.source.end,
                column=column,
                word_index=word_index,
            )
        )
    resolved = _resolve_collisions(placements)
    return ChordLyricLine(
        text=text,
        chords=tuple(resolved),
        chord_row=_chord_row(resolved, text),
        segment=segment,
        start=segment.start,
        end=segment.end,
    )


def _gap_rows(
    events: Sequence[_Timed],
    *,
    prefer_flats: bool,
) -> list[ChordLyricLine]:
    """Chord-only rows for harmony that sounds between lyric lines."""
    rows: list[ChordLyricLine] = []
    for begin in range(0, len(events), MAX_CHORDS_PER_GAP_ROW):
        chunk = list(events[begin : begin + MAX_CHORDS_PER_GAP_ROW])
        span_start = chunk[0].start
        span_end = max(chunk[-1].end, span_start + 1.0)
        width = max(
            MIN_GAP_ROW_WIDTH,
            min(80, 6 + sum(len(event.label) + 2 for event in chunk)),
        )
        placements: list[PlacedChord] = []
        for event in chunk:
            fraction = (event.start - span_start) / (span_end - span_start)
            column = min(width - 1, max(0, round(fraction * (width - 1))))
            placements.append(
                PlacedChord(
                    label=spell_chord_label(event.label, prefer_flats=prefer_flats),
                    start=event.start,
                    end=event.source.end,
                    column=column,
                    word_index=None,
                )
            )
        resolved = _resolve_collisions(placements)
        rows.append(
            ChordLyricLine(
                text=INSTRUMENTAL_TEXT,
                chords=tuple(resolved),
                chord_row=_chord_row(resolved, ""),
                is_gap=True,
                start=span_start,
                end=span_end,
            )
        )
    return rows


def _timed_lines(ordered: Sequence[LyricSegment]) -> list[LyricSegment]:
    """The segments that can own a position on the clock."""
    return [segment for segment in ordered if segment.start is not None]


def chord_lyric_lines(
    lyrics: Iterable[LyricSegment],
    chords: Iterable[ChordEvent],
    *,
    prefer_flats: bool = False,
    max_chords_per_gap_row: int = MAX_CHORDS_PER_GAP_ROW,
) -> tuple[ChordLyricLine, ...]:
    """Build the chord-over-lyrics chart for one document.

    Args:
        lyrics: The canonical lyric segments, in any order.
        chords: The effective chord layer (engine output plus user edits), in
            any order. Only changes are drawn; a chord spanning a line break is
            not repeated on the next line.
        prefer_flats: Spell chord roots and slash basses for a flat key. The
            canonical document is never rewritten.
        max_chords_per_gap_row: Split a long instrumental stretch into rows of
            at most this many chords. Must be positive.

    Returns:
        The rows in display order: timed lyric lines and instrumental gap rows
        interleaved by time, then every untimed lyric line in document order.

    Raises:
        ValueError: When ``max_chords_per_gap_row`` is not positive.
    """
    if max_chords_per_gap_row <= 0:
        raise ValueError(f"max_chords_per_gap_row must be positive, got {max_chords_per_gap_row!r}")
    ordered = lyric_lines(lyrics)
    timed = _timed_lines(ordered)
    untimed = [segment for segment in ordered if segment.start is None]

    raw_chords = sorted(chords, key=lambda event: (event.start, event.end or event.start))
    timed_chords: list[_Timed] = []
    for index, chord_event in enumerate(raw_chords):
        next_start = raw_chords[index + 1].start if index + 1 < len(raw_chords) else None
        end = chord_event.end
        if end is None:
            end = next_start if next_start is not None else chord_event.start
        timed_chords.append(
            _Timed(
                start=chord_event.start,
                end=max(end, chord_event.start),
                label=chord_event.to_label(),
                source=chord_event,
            )
        )

    line_starts = [float(segment.start) for segment in timed if segment.start is not None]
    line_ends: list[float] = []
    for position, segment in enumerate(timed):
        if segment.end is not None:
            line_ends.append(segment.end)
            continue
        following = line_starts[position + 1] if position + 1 < len(line_starts) else None
        if following is not None:
            line_ends.append(following)
            continue
        last_chord = max(
            (chord.end for chord in timed_chords),
            default=float(segment.start or 0.0),
        )
        start = float(segment.start or 0.0)
        # An open-ended last line runs to the last chord it can claim. Falling
        # back to a fixed four seconds only when the document has no chord
        # after it keeps a chord near the start of a long line near the start
        # of that line instead of stretching the line arbitrarily.
        line_ends.append(last_chord if last_chord > start else start + 4.0)

    assigned: list[list[_Timed]] = [[] for _ in timed]
    gaps: list[_Timed] = []
    for timed_event in timed_chords:
        index = bisect_right(line_starts, timed_event.start) - 1
        if index >= 0 and timed_event.start < line_ends[index]:
            assigned[index].append(timed_event)
            continue
        if index < 0 and timed and timed_event.end > float(timed[0].start or 0.0):
            # A chord sounding across the first line's start is that line's
            # opening harmony; a chord that ends before it is an intro-only row.
            assigned[0].append(timed_event)
            continue
        gaps.append(timed_event)

    rows: list[ChordLyricLine] = []
    for index, segment in enumerate(timed):
        rows.append(
            _place_on_line(
                segment,
                assigned[index],
                line_end=line_ends[index],
                prefer_flats=prefer_flats,
            )
        )
    # Gaps are grouped by the lyric line they precede, not globally: a chord
    # before the first line and a chord after the last one must stay on their
    # own sides of the lyrics instead of sharing one wide instrumental row.
    gap_groups: dict[int, list[_Timed]] = {}
    for event in gaps:
        gap_groups.setdefault(bisect_right(line_starts, event.start), []).append(event)
    for key in sorted(gap_groups):
        rows.extend(_gap_rows(gap_groups[key], prefer_flats=prefer_flats))
    rows.sort(
        key=lambda row: (
            row.start if row.start is not None else float("inf"),
            0 if row.is_gap else 1,
        )
    )
    rows.extend(
        ChordLyricLine(
            text=_line_text(segment),
            chords=(),
            chord_row="",
            segment=segment,
            start=None,
            end=None,
        )
        for segment in untimed
    )
    return tuple(rows)
