"""Agreement with a hand-written plain-text chord chart (roadmap Phase J).

A musician's chord chart is the cheapest reference many real songs have: it
lists the harmony in performance order, but it usually has **no timestamps**.
That is enough for one honest question — *does the detector find the chart's
chords, in order?* — and not enough for the duration-weighted CSR used on
GuitarSet, which needs timed reference segments. This module implements the
sequence question and states its limits instead of pretending to be a timed
benchmark.

The chart format is the common plain-text one::

    [Intro]
    G A Bm F#m
    G A Bm A

    G A                    Bm
       No hay nadie ni nada

A line whose every token is a chord is a chord line; section headers in square
brackets are recorded and otherwise ignored; a line containing any non-chord
token is lyric text and does not contribute chords. ``|`` separators are
accepted. The parser is deliberately conservative: it will never turn a lyric
word into a chord, and it refuses to guess at a chart it does not understand.

:func:`align_chord_sequences` aligns the chart's chords to the detected ones
with Needleman–Wunsch on the triad-reduced labels. A match is the same triad
(the same rule as the triad-reduced CSR view), a substitution is a different
triad in the same position, a missing chord is one the detector never found and
an extra is one the detector found but the chart does not list. Repeats matter:
both sequences are aligned in performance order.

This is **sequence agreement**, not accuracy over time and not a claim about a
different performance of the song. A chart with an abridged intro or a repeated
chorus written only once will show missing/extra chords that are not detector
mistakes; the report says so, and the caller should read the alignment rather
than only its percentage.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

from song_chord_lyrics_analyzer.models.music import ChordQuality
from song_chord_lyrics_analyzer.normalization.chords import parse_chord_label

__all__ = [
    "Alignment",
    "AlignmentOp",
    "ChartChord",
    "ChartWord",
    "ChordChart",
    "align_chord_sequences",
    "parse_chord_chart",
    "triad_label",
]

#: One chord token: a root, an optional quality, and an optional slash bass.
#: ``N``/``N.C.`` are explicit no-chord markers, matching the canonical model.
_CHORD_TOKEN = re.compile(
    r"^(?:N(?:\.C\.)?|"
    r"[A-G](?:#|b)?(?:maj7|m7|m6|m9|add9|sus2|sus4|dim|aug|m|7|6|9)?"
    r"(?:/[A-G](?:#|b)?)?)$"
)

#: Separators inside one chord line: whitespace and the bar line.
_SEPARATOR = re.compile(r"[\s|]+")


def triad_label(label: str) -> str:
    """The 24-triad label a chart or engine label reduces to.

    ``A#m7/D#`` becomes ``A#m``, ``D7`` becomes ``D`` and ``C/G`` becomes
    ``C``: the detected engine is a triad detector, so the comparison is made on
    the triad level. Unlike the CSR ``triad_reduce`` (which keeps ``m`` only for
    a plain minor quality), every minor family keeps its ``m`` here, because a
    chart ``Bm7`` and a detected ``Bm`` are the same harmony for this question.
    ``N.C.`` is normalised to the canonical ``N``.
    """
    normalized = "N" if label in {"N", "N.C.", "NC"} else label
    parsed = parse_chord_label(normalized)
    if parsed.quality is ChordQuality.NO_CHORD or parsed.root is None:
        return "N" if parsed.quality is ChordQuality.NO_CHORD else normalized
    if parsed.quality in {
        ChordQuality.MINOR,
        ChordQuality.MINOR7,
        ChordQuality.MINOR_SIXTH,
        ChordQuality.MINOR_NINTH,
    }:
        return f"{parsed.root}m"
    return parsed.root


@dataclass(frozen=True)
class ChartWord:
    """One word of a chart lyric line and its character column.

    Attributes:
        text: The word as written.
        column: Zero-based character offset in the raw lyric line; the chord
            line above the lyric uses the same coordinate system.
    """

    text: str
    column: int


@dataclass(frozen=True)
class ChartChord:
    """One chord token and, when the chart places it over a lyric, its word.

    Attributes:
        text: The chord as written.
        column: Zero-based character offset in the chord line.
        lyric_line: Index into :attr:`ChordChart.content_lyrics` when the next
            non-empty line is a lyric line, otherwise ``None`` (an intro or an
            instrumental chord line).
        word_index: Index of the lyric word nearest to the chord's column, or
            ``None`` for an instrumental chord line.
    """

    text: str
    column: int
    lyric_line: int | None = None
    word_index: int | None = None


@dataclass(frozen=True)
class ChordChart:
    """The chords and context read from one plain-text chart.

    Attributes:
        chords: Every chart chord, in performance order, spelled as written.
        chord_lines: The chord-only lines as tuples, for a readable report.
        sections: Section names in square brackets, in order.
        lyric_lines: Lyric text lines, kept for a future chart import; they do
            not contribute chords.
        content_lyrics: Lyric text lines after the chart's first section header
            or chord line. The lines before it are title/artist metadata, not
            sung text, so a chart import starts here.
        chord_tokens: The same chords as :attr:`chords`, with their column and,
            when the chart places them above a lyric line, the word they sit
            over. A chart import uses this for sub-line placement.
        lyric_words: The words of :attr:`content_lyrics`, with their columns.
        source: The file name the chart came from, when the caller has one.
    """

    chords: tuple[str, ...]
    chord_lines: tuple[tuple[str, ...], ...]
    sections: tuple[str, ...]
    lyric_lines: tuple[str, ...]
    content_lyrics: tuple[str, ...] = ()
    chord_tokens: tuple[ChartChord, ...] = ()
    lyric_words: tuple[tuple[ChartWord, ...], ...] = ()
    source: str | None = None

    @property
    def is_empty(self) -> bool:
        """Whether the chart contains no chord at all."""
        return not self.chords


def _tokens(line: str) -> list[str]:
    """Whitespace/bar-separated tokens of one non-empty line."""
    return [token for token in _SEPARATOR.split(line.strip()) if token]


def _spanned_tokens(line: str) -> list[tuple[str, int]]:
    """Chord tokens of a chord line with their zero-based character columns."""
    return [
        (match.group(), match.start())
        for match in re.finditer(r"[^|\s]+", line)
        if _CHORD_TOKEN.match(match.group())
    ]


def _spanned_words(line: str) -> tuple[ChartWord, ...]:
    """Words of a lyric line with their zero-based character columns."""
    return tuple(ChartWord(match.group(), match.start()) for match in re.finditer(r"\S+", line))


def _chart_word_index(words: Sequence[ChartWord], column: int) -> int | None:
    """The lyric word a chord column sits over.

    The chord takes the word at or immediately before its column, which is how
    a person reads a chord placed above a syllable. A chord before the first
    word or after the last one belongs to that edge word rather than being
    rejected; the chart's indentation is often approximate.
    """
    if not words:
        return None
    starts = [word.column for word in words]
    index = bisect_right(starts, column) - 1
    return max(0, min(index, len(words) - 1))


@dataclass
class _ChartEntry:
    """One non-empty chart line while the parse is being assembled."""

    kind: str  # "section", "chord" or "lyric"
    raw: str
    tokens: tuple[str, ...] = ()
    content_index: int | None = None


def parse_chord_chart(text: str, *, source: str | None = None) -> ChordChart:
    """Read a plain-text chord chart into ordered chords and lyric context.

    Args:
        text: The chart file's contents.
        source: Optional file name recorded in the result.

    Returns:
        The parsed chart. A chart with no chord line is returned with
        :attr:`ChordChart.is_empty` true rather than being rejected here, so a
        caller can report the problem with the file name it knows.

    Raises:
        ValueError: When ``text`` is empty. An empty file is a wrong argument,
            not a chart with zero chords; reporting it loudly is the only way
            a user can tell the difference from a chart of silence.
    """
    if not text.strip():
        raise ValueError("the chord chart is empty")
    entries: list[_ChartEntry] = []
    sections: list[str] = []
    lyric_lines: list[str] = []
    content_lyrics: list[str] = []
    content_started = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            sections.append(stripped[1:-1].strip())
            entries.append(_ChartEntry("section", raw))
            content_started = True
            continue
        tokens = tuple(_tokens(stripped))
        if tokens and all(_CHORD_TOKEN.match(token) for token in tokens):
            entries.append(_ChartEntry("chord", raw, tokens=tokens))
            content_started = True
            continue
        lyric_lines.append(stripped)
        content_index = None
        if content_started:
            content_index = len(content_lyrics)
            content_lyrics.append(stripped)
        entries.append(_ChartEntry("lyric", raw, content_index=content_index))
    chords: list[str] = []
    chord_lines: list[tuple[str, ...]] = []
    chord_tokens: list[ChartChord] = []
    for index, entry in enumerate(entries):
        if entry.kind != "chord":
            continue
        chord_lines.append(entry.tokens)
        following = entries[index + 1] if index + 1 < len(entries) else None
        lyric = following if following is not None and following.kind == "lyric" else None
        content_index = lyric.content_index if lyric is not None else None
        words = _spanned_words(lyric.raw) if lyric is not None else ()
        previous_word = -1
        for token, column in _spanned_tokens(entry.raw):
            chords.append(token)
            word_index = _chart_word_index(words, column) if content_index is not None else None
            if word_index is not None and words:
                # Chords in one line are read left to right and each successive
                # chord belongs to a later word. Chart spacing is often a
                # character or two off, so a plain nearest-column match would
                # put ``G A`` over the same word; advance to the next word
                # before falling back to the nearest one.
                word_index = max(word_index, previous_word + 1)
                word_index = min(word_index, len(words) - 1)
                previous_word = word_index
            chord_tokens.append(
                ChartChord(
                    text=token,
                    column=column,
                    lyric_line=content_index,
                    word_index=word_index,
                )
            )
    lyric_words = tuple(
        _spanned_words(entry.raw)
        for entry in entries
        if entry.kind == "lyric" and entry.content_index is not None
    )
    return ChordChart(
        chords=tuple(chords),
        chord_lines=tuple(chord_lines),
        sections=tuple(sections),
        lyric_lines=tuple(lyric_lines),
        content_lyrics=tuple(content_lyrics),
        chord_tokens=tuple(chord_tokens),
        lyric_words=lyric_words,
        source=source,
    )


@dataclass(frozen=True)
class AlignmentOp:
    """One column of the chart-to-detection alignment.

    Attributes:
        reference: The chart chord, or ``None`` for an extra detection.
        hypothesis: The detected chord, or ``None`` for a missing chart chord.
        kind: ``"match"``, ``"substitution"``, ``"missing"`` or ``"extra"``.
        reference_index: Zero-based index in the chart sequence, when present.
        hypothesis_index: Zero-based index in the detected sequence, when
            present. Chart import uses these to map a chart chord onto the
            detected event's timestamps.
    """

    reference: str | None
    hypothesis: str | None
    kind: str
    reference_index: int | None = None
    hypothesis_index: int | None = None


@dataclass(frozen=True)
class Alignment:
    """The result of aligning a chart sequence to a detected sequence.

    Attributes:
        ops: The alignment columns, in order.
        score: Needleman–Wunsch score (0 is a perfect match; a substitution
            and a gap each cost 1).
    """

    ops: tuple[AlignmentOp, ...]
    score: int

    @property
    def matches(self) -> int:
        """Number of chart chords found in the same order."""
        return sum(1 for op in self.ops if op.kind == "match")

    @property
    def substitutions(self) -> tuple[AlignmentOp, ...]:
        """Chart/detection pairs with different triads."""
        return tuple(op for op in self.ops if op.kind == "substitution")

    @property
    def missing(self) -> tuple[str, ...]:
        """Chart chords the detector never produced."""
        return tuple(op.reference for op in self.ops if op.kind == "missing" and op.reference)

    @property
    def extra(self) -> tuple[str, ...]:
        """Detections the chart does not list."""
        return tuple(op.hypothesis for op in self.ops if op.kind == "extra" and op.hypothesis)

    @property
    def chart_total(self) -> int:
        """Chords on the chart side of the alignment."""
        return self.matches + len(self.substitutions) + len(self.missing)

    @property
    def detected_total(self) -> int:
        """Chords on the detected side of the alignment."""
        return self.matches + len(self.substitutions) + len(self.extra)

    @property
    def recall(self) -> float:
        """Share of chart chords found (a perfect empty alignment is 1.0)."""
        if self.chart_total == 0:
            return 1.0 if self.detected_total == 0 else 0.0
        return self.matches / self.chart_total

    @property
    def precision(self) -> float:
        """Share of detections the chart lists (a perfect empty alignment is 1.0)."""
        if self.detected_total == 0:
            return 1.0 if self.chart_total == 0 else 0.0
        return self.matches / self.detected_total


def align_chord_sequences(
    reference: Sequence[str],
    hypothesis: Sequence[str],
    *,
    substitution_cost: int = 1,
    gap_cost: int = 1,
) -> Alignment:
    """Align a chart's chords to a detected chord sequence.

    Both sides are reduced to triads first, so ``D7`` on the chart matches a
    detected ``D`` and ``A#m`` matches ``Bbm``. The alignment is
    Needleman–Wunsch with a flat substitution cost (1 by default) and a flat
    gap cost; a match costs 0. Ties prefer a match, then a chart chord kept
    (missing), then a detection kept (extra), which keeps the report stable.

    Args:
        reference: The chart's chords, in performance order.
        hypothesis: The detected labels, in performance order.
        substitution_cost: Cost of pairing different triads. Must be
            non-negative.
        gap_cost: Cost of a missing or extra chord. Must be non-negative.

    Returns:
        The alignment and its score.

    Raises:
        ValueError: When a cost is negative.
    """
    if substitution_cost < 0 or gap_cost < 0:
        raise ValueError("alignment costs must not be negative")
    ref = [triad_label(label) for label in reference]
    hyp = [triad_label(label) for label in hypothesis]
    rows, cols = len(ref), len(hyp)
    scores = [[0] * (cols + 1) for _ in range(rows + 1)]
    moves: list[list[str]] = [[""] * (cols + 1) for _ in range(rows + 1)]
    for row in range(1, rows + 1):
        scores[row][0] = row * gap_cost
        moves[row][0] = "missing"
    for col in range(1, cols + 1):
        scores[0][col] = col * gap_cost
        moves[0][col] = "extra"
    for row in range(1, rows + 1):
        for col in range(1, cols + 1):
            same = ref[row - 1] == hyp[col - 1]
            pair = scores[row - 1][col - 1] + (0 if same else substitution_cost)
            missing = scores[row - 1][col] + gap_cost
            extra = scores[row][col - 1] + gap_cost
            best = min(pair, missing, extra)
            scores[row][col] = best
            # Deterministic tie rule: a pair wins ties, then keeping the chart
            # chord, then keeping the detection. It makes a rerun comparable.
            if pair == best:
                moves[row][col] = "match" if same else "substitution"
            elif missing == best:
                moves[row][col] = "missing"
            else:
                moves[row][col] = "extra"
    ops: list[AlignmentOp] = []
    row, col = rows, cols
    while row > 0 or col > 0:
        move = moves[row][col]
        if move in {"match", "substitution"}:
            ops.append(
                AlignmentOp(
                    reference=reference[row - 1],
                    hypothesis=hypothesis[col - 1],
                    kind=move,
                    reference_index=row - 1,
                    hypothesis_index=col - 1,
                )
            )
            row -= 1
            col -= 1
        elif move == "missing":
            ops.append(
                AlignmentOp(
                    reference=reference[row - 1],
                    hypothesis=None,
                    kind="missing",
                    reference_index=row - 1,
                )
            )
            row -= 1
        else:  # extra
            ops.append(
                AlignmentOp(
                    reference=None,
                    hypothesis=hypothesis[col - 1],
                    kind="extra",
                    hypothesis_index=col - 1,
                )
            )
            col -= 1
    return Alignment(ops=tuple(reversed(ops)), score=scores[rows][cols])
