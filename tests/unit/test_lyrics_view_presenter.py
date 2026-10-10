"""The lyrics-view presenter: which line, which word, right now (``[F]`` item 1).

The roadmap asks the lyrics view to draw the ``LyricSegment``/``LyricWord``
lines on the same clock as the chord bands, highlighting the word whose
timestamps cover the playhead. These tests pin that decision as the pure
functions in ``app.lyrics_view``, without a display, a model or an audio
decode - the same way the chord bands are tested.

The rules under test come straight from the canonical model, never invented:

* a segment without timestamps is never active on the clock (dictated after the
  timed ones, dimmed);
* a segment covers ``start <= position < end``, half-open, exactly like
  ``SongSession.chord_at``, and a missing ``end`` runs open-ended;
* a word without a start is never active; a word without an end stays active
  until the next word's start or the segment's end, whichever comes first.
"""

from __future__ import annotations

import pytest

from song_chord_lyrics_analyzer.app import lyric_at, lyric_lines, word_at
from song_chord_lyrics_analyzer.models.confidence import ConfidenceScore
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricWord
from song_chord_lyrics_analyzer.utils.errors import InputError


def _word(text: str, start: float | None, end: float | None = None) -> LyricWord:
    return LyricWord(text=text, start=start, end=end, confidence=ConfidenceScore.unknown())


def _segment(
    text: str,
    start: float | None,
    end: float | None = None,
    words: list[LyricWord] | None = None,
) -> LyricSegment:
    return LyricSegment(text=text, start=start, end=end, words=words or [])


class TestLyricLines:
    def test_an_empty_document_orders_to_nothing(self) -> None:
        assert lyric_lines([]) == ()

    def test_timed_segments_are_sorted_onto_the_song_clock(self) -> None:
        lines = lyric_lines([_segment("later", 10.0), _segment("first", 2.0)])

        assert [line.text for line in lines] == ["first", "later"]

    def test_a_stable_sort_keeps_segments_that_start_together_in_document_order(
        self,
    ) -> None:
        a = _segment("a", 5.0)
        b = _segment("b", 5.0)
        lines = lyric_lines([a, b])

        assert [line.text for line in lines] == ["a", "b"]

    def test_untimed_segments_are_drawn_after_the_timed_ones(self) -> None:
        untimed = _segment("unknown time", None)
        timed = _segment("timed", 1.0)

        lines = lyric_lines([untimed, timed])

        assert [line.text for line in lines] == ["timed", "unknown time"]

    def test_document_order_of_untimed_segments_is_kept(self) -> None:
        lines = lyric_lines([_segment("b", None), _segment("a", None)])

        assert [line.text for line in lines] == ["b", "a"]


class TestLyricAt:
    def test_the_line_under_the_playhead_is_returned(self) -> None:
        lines = lyric_lines([_segment("before", 0.0, 10.0), _segment("now", 10.0, 20.0)])

        assert lyric_at(lines, 10.0) == lines[1]  # "before" ends at 10.0, "now" starts
        assert lyric_at(lines, 15.0) == lines[1]
        assert lyric_at(lines, 20.0) is None  # half-open: end is not covered

    def test_before_the_first_line_and_in_a_gap_nothing_is_claimed(self) -> None:
        lines = lyric_lines([_segment("one", 5.0, 8.0), _segment("two", 12.0, 15.0)])

        assert lyric_at(lines, 0.0) is None
        assert lyric_at(lines, 10.0) is None

    def test_an_open_ended_last_line_stays_active(self) -> None:
        lines = lyric_lines([_segment("last", 10.0, None)])

        assert lyric_at(lines, 999.0) == lines[0]

    def test_untimed_lines_are_never_active(self) -> None:
        lines = lyric_lines([_segment("untimed", None)])

        assert lyric_at(lines, 0.0) is None

    def test_no_lines_at_all_means_nothing(self) -> None:
        assert lyric_at(lyric_lines([]), 1.0) is None

    def test_a_negative_position_is_refused(self) -> None:
        with pytest.raises(InputError, match="must not be negative"):
            lyric_at([], -0.1)


class TestWordAt:
    def test_the_word_covered_by_the_playhead_is_returned(self) -> None:
        segment = _segment("line", 0.0, 10.0, [_word("a", 0.0, 2.0), _word("b", 2.0, 4.0)])

        assert word_at(segment, 2.0).text == "b"  # type: ignore[union-attr]
        assert word_at(segment, 1.0).text == "a"  # type: ignore[union-attr]
        assert word_at(segment, 4.0) is None  # past the last word's end

    def test_no_segment_means_no_word(self) -> None:
        assert word_at(None, 1.0) is None

    def test_a_segment_without_words_means_no_word(self) -> None:
        assert word_at(_segment("line", 0.0, 2.0), 1.0) is None

    def test_a_word_without_a_start_is_never_active(self) -> None:
        segment = _segment("line", 0.0, 4.0, [_word("untimed", None, None)])

        assert word_at(segment, 1.0) is None

    def test_a_mix_of_timed_and_untimed_words_still_works(self) -> None:
        segment = _segment("line", 0.0, 6.0, [_word("untimed", None), _word("timed", 2.0, None)])

        active = word_at(segment, 3.0)

        assert active == segment.words[1]  # type: ignore[index]
        assert active.text == "timed"  # type: ignore[union-attr]

    def test_an_open_word_stays_active_until_the_next_word_starts(self) -> None:
        segment = _segment("line", 0.0, 10.0, [_word("a", 0.0, None), _word("b", 4.0, None)])

        assert word_at(segment, 3.9).text == "a"  # type: ignore[union-attr]
        assert word_at(segment, 4.0).text == "b"  # type: ignore[union-attr]
        assert word_at(segment, 9.9).text == "b"  # type: ignore[union-attr]

    def test_an_open_last_word_closes_at_the_segment_end(self) -> None:
        segment = _segment("line", 0.0, 5.0, [_word("a", 3.0, None)])

        assert word_at(segment, 4.9).text == "a"  # type: ignore[union-attr]
        assert word_at(segment, 5.0) is None

    def test_an_open_and_unbounded_word_never_closes(self) -> None:
        segment = _segment("line", 0.0, None, [_word("a", 3.0, None)])

        assert word_at(segment, 1_000.0).text == "a"  # type: ignore[union-attr]

    def test_a_negative_position_is_refused(self) -> None:
        with pytest.raises(InputError, match="must not be negative"):
            word_at(None, -1.0)
