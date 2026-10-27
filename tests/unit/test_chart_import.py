"""Importing a user's plain-text chart as the timed lyric/chord source.

The chart has the right words and chords but no timestamps; the detector and
the transcript have timestamps but the wrong text. These tests pin the two
alignments that combine them: chart chords take detected times and keep chart
labels, chart words take transcript times and keep chart text.
"""

from __future__ import annotations

import pytest

from song_chord_lyrics_analyzer.app.chart_import import import_chart
from song_chord_lyrics_analyzer.models.lyrics import LyricSegment, LyricWord
from song_chord_lyrics_analyzer.models.music import ChordEvent, ChordQuality

CHART = """\
A test song
An invented artist

[Intro]
C G

[Verse]
C          G
hello old friend
Am         F
we meet again
"""


def _detected() -> list[ChordEvent]:
    labels = ["C", "G", "C", "G", "Am", "F"]
    return [
        ChordEvent(
            start=float(index * 2),
            end=float(index * 2 + 2),
            root=label.rstrip("m"),
            quality=ChordQuality.MINOR if label.endswith("m") else ChordQuality.MAJOR,
            label=label,
        )
        for index, label in enumerate(labels)
    ]


def _words(spec: list[tuple[str, float, float]]) -> list[LyricWord]:
    return [LyricWord(text=text, start=start, end=end) for text, start, end in spec]


def _transcript() -> list[LyricSegment]:
    return [
        LyricSegment(
            text="hello old friend",
            start=4.0,
            end=7.0,
            words=_words([("hello", 4.0, 5.0), ("old", 5.0, 6.0), ("friend", 6.0, 7.0)]),
        ),
        LyricSegment(
            text="we meet again",
            start=8.0,
            end=11.0,
            words=_words([("we", 8.0, 9.0), ("meet", 9.0, 10.0), ("again", 10.0, 11.0)]),
        ),
    ]


class TestChartImport:
    def test_chart_chords_keep_chart_labels_and_take_detected_times(self) -> None:
        imported = import_chart(CHART, detected_chords=_detected(), transcript=_transcript())

        assert [event.label for event in imported.chords] == ["C", "G", "C", "G", "Am", "F"]
        assert [(event.start, event.end) for event in imported.chords] == [
            (0.0, 2.0),
            (2.0, 4.0),
            (4.0, 6.0),
            (6.0, 8.0),
            (8.0, 10.0),
            (10.0, 12.0),
        ]
        assert all(event.source == "chart" for event in imported.chords)

    def test_chart_lyrics_replace_the_transcript_text_but_keep_its_timings(self) -> None:
        imported = import_chart(CHART, detected_chords=_detected(), transcript=_transcript())

        assert imported.lyrics is not None
        assert [line.text for line in imported.lyrics] == ["hello old friend", "we meet again"]
        first = imported.lyrics[0]
        assert first.start == 4.0
        assert first.end == 7.0
        assert [word.text for word in first.words] == ["hello", "old", "friend"]
        assert [(word.start, word.end) for word in first.words] == [
            (4.0, 5.0),
            (5.0, 6.0),
            (6.0, 7.0),
        ]
        assert all(word.source == "chart" for word in first.words)

    def test_title_and_artist_before_the_first_section_are_not_sung(self) -> None:
        imported = import_chart(CHART, detected_chords=_detected(), transcript=_transcript())

        assert imported.chart.content_lyrics == ("hello old friend", "we meet again")
        assert "test song" not in " ".join(line.text for line in imported.lyrics or ())

    def test_a_chart_chord_with_no_detection_still_has_a_word_anchor(self) -> None:
        # The final chart F has no detected event at all, but the chart puts it
        # over a timed word, so the chart-first timeline still places it.
        detected = _detected()[:-1]
        imported = import_chart(CHART, detected_chords=detected, transcript=_transcript())

        assert [event.label for event in imported.chords] == ["C", "G", "C", "G", "Am", "F"]
        assert not any("interpolated" in warning for warning in imported.warnings)
        assert all(
            event.start is not None and event.end is not None and event.end > event.start
            for event in imported.chords
        )

    def test_a_word_anchor_wins_over_a_later_detected_boundary(self) -> None:
        detected = _detected()
        detected[2] = ChordEvent(
            start=5.0,
            end=9.0,
            root="C",
            quality=ChordQuality.MAJOR,
            label="C",
        )
        imported = import_chart(CHART, detected_chords=detected, transcript=_transcript())

        assert imported.chords[2].start == 4.0

    def test_instrumental_chords_are_distributed_between_the_anchors(self) -> None:
        chart = "[Verse]\nC          G\nhello old friend\nD E\nAm\nwe meet again\n"
        imported = import_chart(chart, detected_chords=_detected(), transcript=_transcript())

        assert [event.label for event in imported.chords] == ["C", "G", "D", "E", "Am"]
        assert [round(event.start, 3) for event in imported.chords] == [
            4.0,
            6.0,
            6.667,
            7.333,
            8.0,
        ]

    def test_a_detector_substitution_does_not_change_the_chart_label(self) -> None:
        detected = _detected()
        detected[4] = ChordEvent(
            start=8.0,
            end=10.0,
            root="A",
            quality=ChordQuality.MAJOR,
            label="A",
        )
        imported = import_chart(CHART, detected_chords=detected, transcript=_transcript())

        assert imported.chords[4].label == "Am"
        assert imported.chords[4].start == 8.0

    def test_a_transcript_with_typos_still_anchors_the_matching_words(self) -> None:
        transcript = [
            LyricSegment(
                text="helo old frend",
                start=4.0,
                end=7.0,
                words=_words([("helo", 4.0, 5.0), ("old", 5.0, 6.0), ("frend", 6.0, 7.0)]),
            ),
            LyricSegment(
                text="we meet again",
                start=8.0,
                end=11.0,
                words=_words([("we", 8.0, 9.0), ("meet", 9.0, 10.0), ("again", 10.0, 11.0)]),
            ),
        ]
        imported = import_chart(CHART, detected_chords=_detected(), transcript=transcript)

        assert imported.lyrics is not None
        words = imported.lyrics[0].words
        assert [(word.text, word.start) for word in words] == [
            ("hello", 4.0),
            ("old", 5.0),
            ("friend", 6.0),
        ]

    def test_long_misspelled_words_still_anchor(self) -> None:
        transcript = [
            LyricSegment(
                text="satisfascer",
                start=2.0,
                end=3.0,
                words=_words([("satisfascer", 2.0, 3.0)]),
            )
        ]
        chart = "[Intro]\nC\nsatisfacer\n"
        imported = import_chart(chart, detected_chords=_detected(), transcript=transcript)

        assert imported.lyrics is not None
        assert imported.lyrics[0].words[0].start == 2.0

    def test_no_timed_transcript_keeps_the_chart_chords_and_returns_no_lyrics(self) -> None:
        imported = import_chart(CHART, detected_chords=_detected(), transcript=[])

        assert imported.chords
        assert imported.lyrics is None
        assert any("no timed transcript" in warning for warning in imported.warnings)

    def test_a_chart_with_lyrics_can_be_timed_without_detected_chords(self) -> None:
        imported = import_chart(CHART, detected_chords=[], transcript=_transcript())

        assert [event.label for event in imported.chords] == ["C", "G", "C", "G", "Am", "F"]
        assert imported.warnings == ()

    def test_no_detected_chords_and_no_lyrics_means_no_timed_chords(self) -> None:
        imported = import_chart("[Intro]\nC G\n", detected_chords=[], transcript=[])

        assert imported.chords == ()
        assert any("no detected chords" in warning for warning in imported.warnings)

    def test_a_chord_only_chart_keeps_the_transcript(self) -> None:
        imported = import_chart(
            "[Intro]\nC G\n", detected_chords=_detected(), transcript=_transcript()
        )

        assert imported.chords
        assert imported.lyrics is None
        assert any("no lyric lines" in warning for warning in imported.warnings)

    def test_an_empty_chart_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no chord line"):
            import_chart("[Intro]\n", detected_chords=_detected(), transcript=_transcript())
