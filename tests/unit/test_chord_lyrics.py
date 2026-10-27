"""Chords above the lyric words they belong to (roadmap Phase F).

The presenter is plain data: it projects the effective chord layer and the
effective lyric layer onto one chart. These tests pin the alignment rules that
make the chart trustworthy:

* a chord sits above the timed word sounding at its onset, so a change in the
  middle of a line lands in the middle of the line, not at its start;
* a line without word timestamps falls back to a proportional column;
* a chord that starts in an instrumental gap gets its own chord-only row;
* a chord spanning into a line is not repeated (only changes are drawn);
* canonical labels are respelled for a flat key, never rewritten in the model.
"""

from __future__ import annotations

import pytest

from song_chord_lyrics_analyzer.app.chord_lyrics import (
    INSTRUMENTAL_TEXT,
    chord_lyric_lines,
)
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricWord
from song_chord_lyrics_analyzer.models.music import ChordEvent
from song_chord_lyrics_analyzer.normalization.chords import parse_chord_label


def _word(text: str, start: float | None, end: float | None = None) -> LyricWord:
    return LyricWord(text=text, start=start, end=end)


def _segment(
    text: str,
    start: float | None,
    end: float | None = None,
    words: list[LyricWord] | None = None,
) -> LyricSegment:
    return LyricSegment(text=text, start=start, end=end, words=words or [])


def _chord(label: str, start: float, end: float | None = None) -> ChordEvent:
    parsed = parse_chord_label(label)
    return ChordEvent(
        start=start,
        end=end,
        root=parsed.root,
        quality=parsed.quality,
        bass=parsed.bass,
        label=label,
    )


LINE = _segment(
    "hola mundo",
    0.0,
    4.0,
    [_word("hola", 0.0, 1.8), _word("mundo", 1.8, 3.9)],
)


class TestOneLine:
    def test_a_chord_change_lands_over_the_word_that_starts_it(self) -> None:
        rows = chord_lyric_lines([LINE], [_chord("G", 0.0, 2.0), _chord("C", 2.5, 4.0)])

        assert len(rows) == 1
        row = rows[0]
        assert [placed.label for placed in row.chords] == ["G", "C"]
        assert [placed.column for placed in row.chords] == [0, 5]
        assert [placed.word_index for placed in row.chords] == [0, 1]
        assert row.chord_row == "G    C"

    def test_a_chord_before_the_first_word_anchors_the_first_word(self) -> None:
        line = _segment(
            "uno dos",
            5.0,
            8.0,
            [_word("uno", 5.5, 6.5), _word("dos", 6.5, 7.9)],
        )

        rows = chord_lyric_lines([line], [_chord("Am", 5.2, 6.5)])

        assert rows[0].chords[0].column == 0
        assert rows[0].chords[0].word_index == 0

    def test_without_word_timestamps_the_column_is_proportional(self) -> None:
        line = _segment("abcdefghij", 0.0, 4.0)

        rows = chord_lyric_lines([line], [_chord("C", 1.0, 4.0)])

        # 25 % of the way through a ten-character line -> column 2.
        assert rows[0].chords[0].column == 2
        assert rows[0].chords[0].word_index is None

    def test_two_chords_on_one_word_are_nudged_apart_not_overwritten(self) -> None:
        rows = chord_lyric_lines(
            [LINE],
            [_chord("G", 0.0, 0.2), _chord("C", 0.2, 1.8)],
        )

        first, second = rows[0].chords
        assert first.column == 0
        assert second.column == 2  # one clear space after "G"
        assert rows[0].chord_row == "G C"

    def test_the_chord_row_is_as_wide_as_the_last_label(self) -> None:
        line = _segment("a", 0.0, 2.0, [_word("a", 0.0, 2.0)])

        rows = chord_lyric_lines([line], [_chord("Cmaj7", 0.0, 2.0)])

        assert rows[0].chord_row == "Cmaj7"  # never truncated above a short word

    def test_silence_is_a_label_like_any_other(self) -> None:
        rows = chord_lyric_lines([LINE], [_chord("N", 0.0, 4.0)])

        assert rows[0].chords[0].label == "N"


class TestInstrumentalGaps:
    def test_chords_before_the_first_line_get_their_own_row(self) -> None:
        line = _segment(
            "hola",
            5.0,
            7.0,
            [_word("hola", 5.0, 7.0)],
        )

        rows = chord_lyric_lines(
            [line],
            [_chord("G", 0.0, 1.0), _chord("D", 2.0, 3.0)],
        )

        assert [row.is_gap for row in rows] == [True, False]
        gap = rows[0]
        assert gap.text == INSTRUMENTAL_TEXT
        assert [placed.label for placed in gap.chords] == ["G", "D"]
        assert "G" in gap.chord_row and "D" in gap.chord_row
        assert rows[1].chords == ()

    def test_a_chord_sounding_across_the_first_line_start_belongs_to_that_line(self) -> None:
        line = _segment(
            "hola",
            2.0,
            4.0,
            [_word("hola", 2.0, 4.0)],
        )

        rows = chord_lyric_lines([line], [_chord("G", 1.0, 3.0), _chord("C", 3.0, 4.0)])

        assert [row.is_gap for row in rows] == [False]
        assert [placed.label for placed in rows[0].chords] == ["G", "C"]
        assert rows[0].chords[0].column == 0

    def test_a_chord_that_ends_before_the_line_is_only_a_gap(self) -> None:
        line = _segment("hola", 5.0, 7.0, [_word("hola", 5.0, 7.0)])

        rows = chord_lyric_lines([line], [_chord("G", 0.0, 1.0), _chord("C", 6.0, 7.0)])

        assert [row.is_gap for row in rows] == [True, False]
        assert [placed.label for placed in rows[0].chords] == ["G"]
        assert [placed.label for placed in rows[1].chords] == ["C"]

    def test_a_long_gap_is_split_into_readable_rows(self) -> None:
        chords = [_chord("C", float(index), float(index) + 0.5) for index in range(20)]

        rows = chord_lyric_lines([], chords, max_chords_per_gap_row=8)

        assert [len(row.chords) for row in rows] == [8, 8, 4]
        assert all(row.is_gap for row in rows)

    def test_a_non_positive_gap_width_is_refused(self) -> None:
        with pytest.raises(ValueError, match="max_chords_per_gap_row"):
            chord_lyric_lines([], [_chord("C", 0.0, 1.0)], max_chords_per_gap_row=0)

    def test_a_song_with_only_chords_has_only_gap_rows(self) -> None:
        rows = chord_lyric_lines([], [_chord("C", 0.0, 2.0), _chord("G", 2.0, 4.0)])

        assert rows
        assert all(row.is_gap for row in rows)
        assert all(row.text == INSTRUMENTAL_TEXT for row in rows)


class TestOrderingAndUntimedLines:
    def test_timed_rows_are_interleaved_by_time_and_untimed_lines_come_last(self) -> None:
        first = _segment("first", 0.0, 4.0, [_word("first", 0.0, 4.0)])
        second = _segment("second", 8.0, 12.0, [_word("second", 8.0, 12.0)])
        untimed = _segment("after the song", None)

        rows = chord_lyric_lines(
            [untimed, second, first],
            [_chord("C", 0.0, 4.0), _chord("G", 5.0, 6.0), _chord("Am", 8.0, 12.0)],
        )

        assert [row.text for row in rows] == ["first", "· · ·", "second", "after the song"]
        assert [row.is_gap for row in rows] == [False, True, False, False]
        assert rows[-1].chords == ()

    def test_an_untimed_line_has_no_chords(self) -> None:
        rows = chord_lyric_lines([_segment("untimed", None)], [_chord("C", 0.0, 1.0)])

        assert [row.is_gap for row in rows] == [True, False]
        assert rows[1].chords == ()


class TestSpellingAndEvidence:
    def test_a_flat_key_respells_the_drawn_labels(self) -> None:
        rows = chord_lyric_lines(
            [LINE],
            [_chord("A#", 0.0, 2.0), _chord("D#m", 2.0, 4.0)],
            prefer_flats=True,
        )

        assert [placed.label for placed in rows[0].chords] == ["Bb", "Ebm"]
        assert rows[0].chord_row == "Bb   Ebm"

    def test_the_placements_keep_the_original_onset(self) -> None:
        rows = chord_lyric_lines([LINE], [_chord("C", 0.4, 3.0)])

        assert rows[0].chords[0].start == 0.4
        assert rows[0].chords[0].end == 3.0
