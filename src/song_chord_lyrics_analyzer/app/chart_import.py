"""Import a user-written plain-text chart as the timed lyric/chord base.

`evaluation/chart.py` answers *how well the detector agrees with a chart*. This
module answers the next question: *make the chart the thing the window shows.*
A user's chart has the right words and the right chords but no timestamps, so
the import needs two independent clocks:

* **Chords.** The chart's chord sequence is aligned to the detected chord
  sequence (`align_chord_sequences`). A matched or substituted chart chord takes
  the detected event's start and end; a chart chord with no detected counterpart
  gets an interpolated time between its neighbours. The *label* is always the
  chart's, so a detector mistake cannot re-enter the imported layer.
* **Lyrics.** The chart's sung lines are aligned word by word to the
  transcript's timed words. Exact normalized matches anchor a chart word to the
  transcript's start/end; the words between anchors are interpolated. The chart
  text (with its punctuation and accents) is what is stored; only the timings
  come from the transcript. Title/artist lines before the first section or
  chord line are not sung and are excluded.

The result is a pair of layers ready for `CommandStack` and the existing chart
presenter. Nothing here is a second player or a second clock: the events and
lines carry ordinary start/end seconds, and the session/presenters read them
exactly like engine output.

The import is honest about failure. If there are no detected chords, no timed
lyrics, or too few word anchors, the corresponding layer is returned empty or
``None`` together with a warning; the caller keeps what it had rather than
inventing a timeline.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from song_chord_lyrics_analyzer.evaluation.chart import (
    ChordChart,
    align_chord_sequences,
    parse_chord_chart,
)
from song_chord_lyrics_analyzer.models.confidence import ConfidenceScore
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricSegmentKind, LyricWord
from song_chord_lyrics_analyzer.models.music import ChordEvent, ChordQuality
from song_chord_lyrics_analyzer.normalization.chords import parse_chord_label

__all__ = ["ChartImport", "import_chart"]

#: Provenance source of an imported chart layer.
CHART_SOURCE = "chart"

_WORD = re.compile(r"\S+")
_NON_WORD = re.compile(r"[^0-9a-z]+")

#: A chart word must share at least this share of anchors for its lyrics to be
#: trusted. Below it the transcript is kept, because a handful of coincidental
#: words would place the chart's lines almost arbitrarily.
_MIN_ANCHOR_SHARE = 0.2


@dataclass(frozen=True)
class ChartImport:
    """The timed layers a chart import produced.

    Attributes:
        chords: Chart chords with times; empty when the chart has no chords or
            the detected timeline cannot place them.
        lyrics: Chart lyric lines with word timings, or ``None`` when the chart
            has no sung lines or they could not be aligned to the transcript.
            ``None`` means "keep the caller's lyrics", not "silence".
        warnings: Human-readable reasons a layer was kept, interpolated or
            dropped. The GUI shows these; nothing is silently guessed.
        chart: The parsed chart, for a report or a status line.
    """

    chords: tuple[ChordEvent, ...]
    lyrics: tuple[LyricSegment, ...] | None
    warnings: tuple[str, ...]
    chart: ChordChart


@dataclass
class _TimedWord:
    """One transcript word with a time span."""

    text: str
    start: float
    end: float


@dataclass
class _ChartWord:
    """One word of a chart lyric line, with a time filled in later."""

    text: str
    line_index: int
    word_index: int
    start: float | None = None
    end: float | None = None


def _normalized(word: str) -> str:
    """Lowercase ASCII letters/digits, for matching chart and transcript."""
    decomposed = unicodedata.normalize("NFKD", word)
    unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _NON_WORD.sub("", unaccented.lower())


def _words(text: str) -> list[str]:
    """Whitespace-separated words, keeping the original spelling."""
    return _WORD.findall(text)


def _same_word(left: str, right: str) -> bool:
    """Whether two normalized words are the same word for anchoring.

    Exact equality is the rule. For words of five characters or more a near
    spelling (``satisfascer`` / ``satisfacer``, ``frend`` / ``friend``) is
    accepted at a 0.8 similarity ratio. Short words are never fuzzy-matched:
    ``de``/``da`` and ``ni``/``no`` would anchor the wrong syllable too easily.
    """
    if not left or not right:
        return False
    if left == right:
        return True
    if len(left) < 5 or len(right) < 5:
        return False
    return SequenceMatcher(None, left, right).ratio() >= 0.8


def _transcript_words(segments: Sequence[LyricSegment]) -> list[_TimedWord]:
    """Every timed word of the transcript, in order.

    A segment whose words all carry timestamps contributes those words. A
    segment with text but no (or partial) word timestamps is split into words
    and distributed uniformly inside the segment's own start/end; that is the
    same evidence the line has, not an invented absolute time.
    """
    timed = sorted(
        (segment for segment in segments if segment.start is not None),
        key=lambda segment: float(segment.start or 0.0),
    )
    words: list[_TimedWord] = []
    for index, segment in enumerate(timed):
        start = float(segment.start or 0.0)
        following = timed[index + 1].start if index + 1 < len(timed) else None
        end = segment.end if segment.end is not None and segment.end > start else following
        if end is None or end <= start:
            end = start + max(0.8, 0.4 * len(_words(segment.text)))
        if segment.words and all(
            word.start is not None and word.end is not None and word.end > word.start
            for word in segment.words
        ):
            words.extend(
                _TimedWord(word.text, float(word.start), float(word.end))
                for word in segment.words
                if word.start is not None and word.end is not None
            )
            continue
        tokens = _words(segment.text or " ".join(word.text for word in segment.words))
        if not tokens:
            continue
        step = (end - start) / len(tokens)
        for offset, token in enumerate(tokens):
            words.append(
                _TimedWord(
                    token,
                    start + offset * step,
                    start + (offset + 1) * step,
                )
            )
    return words


def _chart_words(chart: ChordChart) -> list[_ChartWord]:
    """Every word of the chart's sung lines, in order, without times."""
    words: list[_ChartWord] = []
    for line_index, line in enumerate(chart.content_lyrics):
        for word_index, token in enumerate(_words(line)):
            words.append(_ChartWord(token, line_index, word_index))
    return words


def _word_pairs(
    chart_words: Sequence[_ChartWord], transcript: Sequence[_TimedWord]
) -> list[tuple[int, int]]:
    """Exact normalized word pairs from a global word alignment.

    Only exact normalized matches become anchors; a near-spelling is left for
    interpolation instead of being trusted as evidence. The alignment keeps
    order, so repeated words cannot jump backwards.
    """
    left = [_normalized(word.text) for word in chart_words]
    right = [_normalized(word.text) for word in transcript]
    rows, cols = len(left), len(right)
    scores = [[0] * (cols + 1) for _ in range(rows + 1)]
    moves: list[list[str]] = [[""] * (cols + 1) for _ in range(rows + 1)]
    for row in range(1, rows + 1):
        scores[row][0] = row
        moves[row][0] = "chart"
    for col in range(1, cols + 1):
        scores[0][col] = col
        moves[0][col] = "transcript"
    for row in range(1, rows + 1):
        for col in range(1, cols + 1):
            same = _same_word(left[row - 1], right[col - 1])
            pair = scores[row - 1][col - 1] + (0 if same else 1)
            drop_chart = scores[row - 1][col] + 1
            drop_transcript = scores[row][col - 1] + 1
            best = min(pair, drop_chart, drop_transcript)
            scores[row][col] = best
            if pair == best:
                moves[row][col] = "pair"
            elif drop_chart == best:
                moves[row][col] = "chart"
            else:
                moves[row][col] = "transcript"
    pairs: list[tuple[int, int]] = []
    row, col = rows, cols
    while row > 0 or col > 0:
        move = moves[row][col]
        if move == "pair":
            if _same_word(left[row - 1], right[col - 1]):
                pairs.append((row - 1, col - 1))
            row -= 1
            col -= 1
        elif move == "chart":
            row -= 1
        else:
            col -= 1
    return list(reversed(pairs))


def _average_duration(words: Sequence[_TimedWord]) -> float:
    """A robust per-word duration for interpolation; never zero."""
    if not words:
        return 0.35
    durations = [word.end - word.start for word in words if word.end > word.start]
    return statistics.median(durations) if durations else 0.35


def _fill_word_times(
    chart_words: Sequence[_ChartWord],
    transcript: Sequence[_TimedWord],
    pairs: Sequence[tuple[int, int]],
    *,
    duration: float | None,
) -> None:
    """Anchor matched chart words and interpolate the rest in place."""
    average = _average_duration([transcript[index] for _, index in pairs]) if pairs else 0.35
    average = max(0.1, average)
    for chart_index, transcript_index in pairs:
        source = transcript[transcript_index]
        chart_words[chart_index].start = source.start
        chart_words[chart_index].end = max(source.end, source.start + 0.05)
    anchors = sorted((index for index, _ in pairs))
    for index, word in enumerate(chart_words):
        if word.start is not None and word.end is not None:
            continue
        previous = max((anchor for anchor in anchors if anchor < index), default=None)
        following = min((anchor for anchor in anchors if anchor > index), default=None)
        if previous is not None and following is not None:
            prev_word = chart_words[previous]
            next_word = chart_words[following]
            assert prev_word.end is not None
            assert next_word.start is not None
            gap = max(0.0, next_word.start - prev_word.end)
            share = (index - previous) / (following - previous)
            start = prev_word.end + gap * share
            end = min(next_word.start, start + max(0.05, gap / max(1, following - previous)))
        elif previous is not None:
            prev_word = chart_words[previous]
            assert prev_word.end is not None
            start = prev_word.end + (index - previous) * average
            end = start + average
        elif following is not None:
            next_word = chart_words[following]
            assert next_word.start is not None
            start = max(0.0, next_word.start - (following - index) * average)
            end = min(next_word.start, start + average)
        else:  # no anchors; only reachable when the caller refused the import
            start = index * average
            end = start + average
        if duration is not None and duration > 0.0:
            start = min(start, max(0.0, duration - 0.05))
            end = min(end, duration)
        if end <= start:
            end = start + 0.05
        word.start, word.end = start, end


def _lyric_segments(
    chart: ChordChart,
    chart_words: Sequence[_ChartWord],
) -> tuple[LyricSegment, ...]:
    """Group the timed chart words into one segment per sung chart line."""
    by_line: dict[int, list[_ChartWord]] = {}
    for word in chart_words:
        by_line.setdefault(word.line_index, []).append(word)
    segments: list[LyricSegment] = []
    for line_index, text in enumerate(chart.content_lyrics):
        words = by_line.get(line_index, [])
        timed = [word for word in words if word.start is not None and word.end is not None]
        if not timed:
            continue
        previous_start = -1.0
        for position, word in enumerate(timed):
            start_value = word.start
            start = max(previous_start, start_value if start_value is not None else 0.0)
            end_value = word.end
            end = end_value if end_value is not None and end_value > start else start + 0.1
            if position + 1 < len(timed):
                following_start = timed[position + 1].start
                if following_start is not None:
                    end = min(end, max(start + 0.05, following_start))
            word.start, word.end = start, end
            previous_start = start
        # A sparse anchor at the end of a line can leave several words stacked
        # at the next line's start. Redistribute that trailing run across the
        # line's own span, so the last words are still reachable by the playhead
        # instead of all becoming active for 50 ms.
        line_start = float(timed[0].start or 0.0)
        line_end = max(float(word.end or 0.0) for word in timed)
        cut = len(timed)
        while cut > 1:
            current = timed[cut - 1]
            before = timed[cut - 2]
            current_start = float(current.start or 0.0)
            before_start = float(before.start or 0.0)
            if (
                current.end is not None
                and current.end - current_start > 0.06
                and current_start > before_start
            ):
                break
            cut -= 1
        if cut < len(timed) and cut > 0:
            anchor_start = float(timed[cut - 1].start or line_start)
            span = line_end - anchor_start
            count = len(timed) - cut + 1
            if span > 0.1 and count > 1:
                step = span / count
                for offset, word in enumerate(timed[cut - 1 :], start=cut - 1):
                    word.start = anchor_start + (offset - (cut - 1)) * step
                    word.end = float(word.start) + step
        word_models = [
            LyricWord(
                text=word.text,
                start=word.start,
                end=word.end,
                confidence=ConfidenceScore.unknown(CHART_SOURCE),
                source=CHART_SOURCE,
            )
            for word in timed
            if word.start is not None and word.end is not None
        ]
        start = min(float(word.start or 0.0) for word in timed)
        end = max(float(word.end or 0.0) for word in timed)
        if end <= start:
            end = start + 0.05
        segments.append(
            LyricSegment(
                text=text,
                start=start,
                end=end,
                words=word_models,
                confidence=ConfidenceScore.unknown(CHART_SOURCE),
                source=CHART_SOURCE,
                kind=LyricSegmentKind.LYRICS,
            )
        )
    segments.sort(key=lambda segment: float(segment.start or 0.0))
    for position in range(1, len(segments)):
        previous = segments[position - 1]
        following = segments[position]
        if (
            previous.end is not None
            and following.start is not None
            and previous.end > following.start
        ):
            previous.end = following.start
            if previous.end <= float(previous.start or 0.0):
                previous.end = float(previous.start or 0.0) + 0.05
    return tuple(segments)


def _event_end(event: ChordEvent, following: ChordEvent | None, duration: float | None) -> float:
    """The end of a detected event, completing the last one from the track."""
    if event.end is not None and event.end > event.start:
        return float(event.end)
    if following is not None and following.start > event.start:
        return float(following.start)
    if duration is not None and duration > event.start:
        return float(duration)
    return event.start + 0.5


def _chart_events(
    chart: ChordChart,
    detected: Sequence[ChordEvent],
    *,
    duration: float | None,
) -> tuple[tuple[ChordEvent, ...], tuple[str, ...]]:
    """Time every chart chord from the aligned detected sequence."""
    warnings: list[str] = []
    if not chart.chords:
        return (), ("the chart has no chord lines",)
    if not detected:
        return (), ("there are no detected chords to time the chart against",)
    alignment = align_chord_sequences(chart.chords, [event.label for event in detected])
    mapped: dict[int, tuple[float, float]] = {}
    for operation in alignment.ops:
        if operation.reference_index is None or operation.hypothesis_index is None:
            continue
        if operation.kind not in {"match", "substitution"}:
            continue
        event = detected[operation.hypothesis_index]
        following = (
            detected[operation.hypothesis_index + 1]
            if operation.hypothesis_index + 1 < len(detected)
            else None
        )
        mapped[operation.reference_index] = (
            float(event.start),
            _event_end(event, following, duration),
        )
    if not mapped:
        return (), ("no chart chord could be aligned to the detected sequence",)
    durations = [end - start for start, end in mapped.values() if end > start]
    average = statistics.median(durations) if durations else 0.5
    average = max(0.1, average)
    missing = len(chart.chords) - len(mapped)
    if missing:
        warnings.append(
            f"{missing} chart chord(s) had no detected counterpart; their times were interpolated"
        )
    count = len(chart.chords)
    times: list[tuple[float, float] | None] = [None] * count
    for index, span in mapped.items():
        times[index] = span
    first, last = min(mapped), max(mapped)
    # A chart can carry an intro (or a repeated section) that the detector
    # missed entirely. There is no gap before the first mapped chord then, so
    # share the first mapped span between the leading chart chords and that
    # chord; the chart's order is preserved instead of its first chords being
    # silently dropped.
    if first > 0:
        first_start, first_end = mapped[first]
        slots = first + 1
        step = (first_start if first_start > 0.0 else first_end) / slots
        step = max(0.05, step)
        for index in range(first):
            times[index] = (index * step, (index + 1) * step)
        if first_start <= 0.0:
            times[first] = (first * step, max((first + 1) * step, first_end))
    # Symmetrically, a tail with no detected counterpart runs to the track end
    # when the duration is known, or shares the last mapped span otherwise.
    if last < count - 1:
        last_start, last_end = mapped[last]
        trailing = count - 1 - last
        if duration is not None and duration > last_end:
            step = max(0.05, (duration - last_end) / trailing)
            for offset, index in enumerate(range(last + 1, count), start=1):
                times[index] = (
                    last_end + (offset - 1) * step,
                    last_end + offset * step,
                )
        else:
            slots = trailing + 1
            step = max(0.05, (last_end - last_start) / slots)
            times[last] = (last_start, last_start + step)
            for offset, index in enumerate(range(last + 1, count), start=1):
                times[index] = (
                    last_start + offset * step,
                    last_start + (offset + 1) * step,
                )
    for index in range(count):
        if times[index] is not None:
            continue
        previous_index = max(
            (position for position in range(index) if times[position] is not None),
            default=None,
        )
        following_index = min(
            (position for position in range(index + 1, count) if times[position] is not None),
            default=None,
        )
        if previous_index is not None and following_index is not None:
            prev_span = times[previous_index]
            next_span = times[following_index]
            assert prev_span is not None and next_span is not None
            _prev_start, prev_end = prev_span
            next_start, _next_end = next_span
            share = (index - previous_index) / (following_index - previous_index)
            start = prev_end + max(0.0, next_start - prev_end) * share
            end = min(next_start, start + max(0.05, average))
        elif previous_index is not None:
            prev_span = times[previous_index]
            assert prev_span is not None
            start = prev_span[1] + (index - previous_index) * average
            end = start + average
        else:
            next_span = times[following_index]  # type: ignore[index]
            assert next_span is not None
            start = max(0.0, next_span[0] - (following_index - index) * average)  # type: ignore[operator]
            end = min(next_span[0], start + average)
        times[index] = (start, end)
    resolved = [span for span in times if span is not None]
    assert len(resolved) == count
    events: list[ChordEvent] = []
    for index, (start, end) in enumerate(resolved):
        if duration is not None and duration > 0.0:
            start = min(start, max(0.0, duration - 0.05))
            end = min(end, duration)
        if end <= start:
            end = start + 0.05
        label = chart.chords[index]
        parsed = parse_chord_label(label)
        if parsed.quality is ChordQuality.NO_CHORD or label in {"N", "N.C.", "NC"}:
            events.append(
                ChordEvent.silence(
                    start,
                    end,
                    source=CHART_SOURCE,
                    confidence=ConfidenceScore.unknown(CHART_SOURCE),
                    metadata={"chart_import": True, "chart_label": label},
                )
            )
            continue
        events.append(
            ChordEvent(
                start=start,
                end=end,
                root=parsed.root,
                quality=parsed.quality,
                bass=parsed.bass,
                label=label,
                source=CHART_SOURCE,
                confidence=ConfidenceScore.unknown(CHART_SOURCE),
                metadata={"chart_import": True, "chart_label": label},
            )
        )
    events.sort(key=lambda event: event.start)
    for position in range(1, len(events)):
        previous_event = events[position - 1]
        following_event = events[position]
        if previous_event.end is None or previous_event.end > following_event.start:
            previous_event.end = following_event.start
    return tuple(event for event in events if event.end is None or event.end > event.start), tuple(
        warnings
    )


def import_chart(
    text: str,
    *,
    detected_chords: Sequence[ChordEvent],
    transcript: Sequence[LyricSegment],
    duration: float | None = None,
    source: str | None = None,
) -> ChartImport:
    """Turn a plain-text chart into timed chord and lyric layers.

    Args:
        text: The chart file's contents.
        detected_chords: The engine's chord events, used only for timing.
        transcript: The engine's timed lyric layer, used only for timing.
        duration: Track length in seconds, when known; it clamps the last ends.
        source: Optional chart file name recorded in warnings/reporting.

    Returns:
        The timed layers and warnings. ``lyrics`` is ``None`` when the chart has
        no sung lines or too few word anchors; the caller should keep the
        transcript then. ``chords`` is empty when it cannot be timed.

    Raises:
        ValueError: When the chart is empty or has no chord line.
    """
    chart = parse_chord_chart(text, source=source)
    if chart.is_empty:
        raise ValueError("the chord chart has no chord line")
    chords, warnings = _chart_events(chart, detected_chords, duration=duration)
    chart_words = _chart_words(chart)
    lyrics: tuple[LyricSegment, ...] | None = None
    if not chart_words:
        warnings = (*warnings, "the chart has no lyric lines; the transcript is kept")
    else:
        transcript_words = _transcript_words(transcript)
        if not transcript_words:
            warnings = (*warnings, "there are no timed transcript words to place the chart lyrics")
        else:
            pairs = _word_pairs(chart_words, transcript_words)
            share = len(pairs) / len(chart_words)
            if not pairs or share < _MIN_ANCHOR_SHARE:
                warnings = (
                    *warnings,
                    "the chart's lyrics could not be matched to the transcript; "
                    "the transcript is kept",
                )
            else:
                _fill_word_times(chart_words, transcript_words, pairs, duration=duration)
                lyrics = _lyric_segments(chart, chart_words)
                if len(pairs) < len(chart_words):
                    warnings = (
                        *warnings,
                        f"{len(pairs)} of {len(chart_words)} chart words were matched; "
                        "the rest were interpolated",
                    )
    return ChartImport(chords=chords, lyrics=lyrics, warnings=warnings, chart=chart)
