"""Agreement between a hand-written chord chart and a detected sequence.

These tests pin the parser's conservative choices (a lyric line never becomes
chords) and the alignment's semantics (a match is a triad, a substitution is a
different triad in place, a gap is missing or extra). They use invented charts,
never a copyrighted song.
"""

from __future__ import annotations

import pytest

from song_chord_lyrics_analyzer.evaluation.chart import (
    Alignment,
    ChartWord,
    align_chord_sequences,
    parse_chord_chart,
    triad_label,
)

CHART = """\
A test song
An invented artist

[Intro]
G A Bm F#m
G | A | Bm | A

G A                    Bm
   some invented lyric line
                     F#m
   another invented line
Bm A
"""


class TestParseChordChart:
    def test_chord_lines_are_read_in_performance_order(self) -> None:
        chart = parse_chord_chart(CHART)

        assert chart.chords == (
            "G",
            "A",
            "Bm",
            "F#m",
            "G",
            "A",
            "Bm",
            "A",
            "G",
            "A",
            "Bm",
            "F#m",
            "Bm",
            "A",
        )

    def test_sections_are_recorded_not_parsed_as_chords(self) -> None:
        chart = parse_chord_chart(CHART)

        assert chart.sections == ("Intro",)
        assert "Intro" not in chart.chords

    def test_lyric_lines_are_kept_but_never_become_chords(self) -> None:
        chart = parse_chord_chart(CHART)

        assert chart.lyric_lines == (
            "A test song",
            "An invented artist",
            "some invented lyric line",
            "another invented line",
        )
        assert "song" not in chart.chords

    def test_chord_lines_keep_their_grouping(self) -> None:
        chart = parse_chord_chart(CHART)

        assert chart.chord_lines[0] == ("G", "A", "Bm", "F#m")
        assert chart.chord_lines[1] == ("G", "A", "Bm", "A")

    def test_chord_columns_anchor_to_the_lyric_line_below(self) -> None:
        chart = parse_chord_chart(CHART)
        anchored = [
            (token.text, token.word_index)
            for token in chart.chord_tokens
            if token.lyric_line is not None
        ]

        assert anchored == [("G", 0), ("A", 1), ("Bm", 3), ("F#m", 2)]
        assert chart.lyric_words[0] == (
            ChartWord("some", 3),
            ChartWord("invented", 8),
            ChartWord("lyric", 17),
            ChartWord("line", 23),
        )

    def test_an_instrumental_chord_line_has_no_lyric_anchor(self) -> None:
        chart = parse_chord_chart(CHART)
        intro = [token for token in chart.chord_tokens if token.text in {"F#m", "Bm"}]

        assert any(token.lyric_line is None for token in intro)

    def test_bar_separators_are_accepted(self) -> None:
        chart = parse_chord_chart("| C | G | Am | F |\n")

        assert chart.chords == ("C", "G", "Am", "F")

    def test_a_slash_chord_is_kept_as_written(self) -> None:
        chart = parse_chord_chart("C/G D/F#\n")

        assert chart.chords == ("C/G", "D/F#")
        assert triad_label("C/G") == "C"

    def test_no_chord_markers_are_accepted(self) -> None:
        chart = parse_chord_chart("N N.C.\n")

        assert chart.chords == ("N", "N.C.")
        assert triad_label("N.C.") == "N"

    def test_an_empty_file_is_an_error(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            parse_chord_chart("  \n\t\n")

    def test_a_file_with_no_chord_line_is_an_empty_chart(self) -> None:
        chart = parse_chord_chart("just words\nand more words\n")

        assert chart.is_empty is True
        assert chart.chords == ()
        assert chart.lyric_lines == ("just words", "and more words")

    def test_the_source_name_is_recorded(self) -> None:
        chart = parse_chord_chart(CHART, source="song.txt")

        assert chart.source == "song.txt"


class TestTriadLabel:
    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("C", "C"),
            ("Cm", "Cm"),
            ("C7", "C"),
            ("Cmaj7", "C"),
            ("Cm7", "Cm"),
            ("Bm7", "Bm"),
            ("Am9", "Am"),
            ("Csus4", "C"),
            ("C/G", "C"),
            ("A#m", "A#m"),
            ("Bb", "A#"),
            ("N.C.", "N"),
        ],
    )
    def test_the_triad_view_matches_the_csr_reduction(self, label: str, expected: str) -> None:
        assert triad_label(label) == expected


class TestAlignment:
    def test_an_exact_sequence_has_no_gaps(self) -> None:
        alignment = align_chord_sequences(["C", "G", "Am", "F"], ["C", "G", "Am", "F"])

        assert alignment.matches == 4
        assert alignment.substitutions == ()
        assert alignment.missing == ()
        assert alignment.extra == ()
        assert alignment.score == 0
        assert alignment.recall == 1.0
        assert alignment.precision == 1.0

    def test_a_different_triad_in_place_is_a_substitution(self) -> None:
        alignment = align_chord_sequences(["C", "G"], ["C", "Am"])

        assert alignment.matches == 1
        assert [op.kind for op in alignment.substitutions] == ["substitution"]
        assert alignment.substitutions[0].reference == "G"
        assert alignment.substitutions[0].hypothesis == "Am"
        assert alignment.score == 1
        assert alignment.recall == 0.5
        assert alignment.precision == 0.5

    def test_a_chart_chord_with_no_counterpart_is_missing(self) -> None:
        alignment = align_chord_sequences(["C", "G", "Am"], ["C", "Am"])

        assert alignment.matches == 2
        assert alignment.missing == ("G",)
        assert alignment.extra == ()
        assert alignment.recall == pytest.approx(2 / 3)
        assert alignment.precision == 1.0

    def test_a_detection_with_no_chart_chord_is_extra(self) -> None:
        alignment = align_chord_sequences(["C", "Am"], ["C", "G", "Am"])

        assert alignment.matches == 2
        assert alignment.missing == ()
        assert alignment.extra == ("G",)
        assert alignment.recall == 1.0
        assert alignment.precision == pytest.approx(2 / 3)

    def test_sevenths_and_flat_spellings_match_on_the_triad_level(self) -> None:
        alignment = align_chord_sequences(["Bb", "D7", "Gm"], ["A#", "D", "Gm"])

        assert alignment.matches == 3
        assert alignment.score == 0

    def test_an_empty_chart_against_an_empty_detection_is_perfect(self) -> None:
        alignment = align_chord_sequences([], [])

        assert alignment.matches == 0
        assert alignment.recall == 1.0
        assert alignment.precision == 1.0

    def test_an_empty_chart_against_detections_has_no_recall(self) -> None:
        alignment = align_chord_sequences([], ["C"])

        assert alignment.recall == 0.0
        assert alignment.extra == ("C",)

    def test_negative_costs_are_refused(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            align_chord_sequences(["C"], ["C"], gap_cost=-1)

    def test_the_alignment_is_a_sequence_of_readable_columns(self) -> None:
        alignment = align_chord_sequences(["C", "G"], ["C", "Am"])

        assert [op.kind for op in alignment.ops] == ["match", "substitution"]

    def test_the_alignment_is_deterministic(self) -> None:
        first: Alignment = align_chord_sequences(["C", "G", "Am"], ["C", "F", "Am"])
        second = align_chord_sequences(["C", "G", "Am"], ["C", "F", "Am"])

        assert first == second
