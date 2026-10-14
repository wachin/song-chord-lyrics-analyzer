"""The external lyric bases: ``.lrc`` and ``.srt`` parsed into LyricSegments.

Every rule the parsers document is pinned here, including the ones a dirty
real-world file exercises: metadata tags, offsets, repeated stamps, enhanced
word stamps, missing indices, joined block lines. What the file does not say
is never invented - the last LRC line is open-ended, a stamp with no word
stays skipped, and malformed timings are errors with hints, never guesses.
"""

from __future__ import annotations

import pytest

from song_chord_lyrics_analyzer.alignment import parse_timed_text, parse_timed_text_file
from song_chord_lyrics_analyzer.alignment.lrc import parse_lrc_text
from song_chord_lyrics_analyzer.alignment.srt import parse_srt_text
from song_chord_lyrics_analyzer.utils.errors import InputError


class TestTheLrcParser:
    def test_a_basic_file_becomes_a_playback_ordered_base(self) -> None:
        parsed = parse_lrc_text(
            "[00:01.00]hello world\n[00:05.00]second line\n",
            name="song.lrc",
        )

        assert [(line.text, line.start, line.end) for line in parsed] == [
            ("hello world", 1.0, 5.0),
            ("second line", 5.0, None),  # the file ends here: open-ended
        ]
        assert [line.source for line in parsed] == ["lrc"] * 2

    def test_the_fraction_is_padded_right_not_parsed_decimal(self) -> None:
        parsed = parse_lrc_text("[01:02.5]tram\n[01:02.55]locomotive\n")

        # .5 stands for 500 ms (writers truncate hundredths), not 50 or 0.5 ms.
        assert parsed[0].start == (1 * 60.0 + 2.5)
        assert parsed[1].start == (1 * 60.0 + 2.55)

    def test_repeated_stamps_repeat_the_same_text(self) -> None:
        parsed = parse_lrc_text("[00:04.00][00:09.00]chorus\n")

        assert [(line.text, line.start) for line in parsed] == [
            ("chorus", 4.0),
            ("chorus", 9.0),
        ]
        # The first repetition runs until the second one starts.
        assert parsed[0].end == 9.0
        assert parsed[1].end is None

    def test_metadata_tags_never_become_lyric_lines(self) -> None:
        parsed = parse_lrc_text(
            "[ti:Song]\n[ar:Artist]\n[by:encoder]\n[00:01.00]real line\n",
        )

        assert [(line.text, line.start) for line in parsed] == [("real line", 1.0)]

    def test_offset_shifts_every_stamp_in_the_files_direction(self) -> None:
        delayed = parse_lrc_text("[offset:2000]\n[00:01.00]slow\n")
        earlier = parse_lrc_text("[offset:-2000]\n[00:05.00]fast\n")

        assert delayed[0].start == 3.0
        assert earlier[0].start == 3.0

    def test_enhanced_word_stamps_become_word_timestamps(self) -> None:
        parsed = parse_lrc_text(
            "[00:10.00]karaoke <00:10.50>deux <00:11.00>trois\n[00:20.00]next\n",
        )

        line = parsed[0]
        assert line.text == "karaoke deux trois"
        assert [(word.text, word.start, word.end) for word in line.words] == [
            ("deux", 10.5, 11.0),
            ("trois", 11.0, 20.0),  # the singer sings until the next line starts
        ]
        assert line.has_word_timestamps is True

    def test_a_stamp_without_a_word_is_skipped_not_guessed(self) -> None:
        parsed = parse_lrc_text(
            "[00:10.00]<00:10.50>only <00:11.00>\n",
        )

        assert parsed[0].text == "only"
        assert [(word.text, word.start) for word in parsed[0].words] == [("only", 10.5)]

    def test_an_open_ended_line_leaves_its_last_word_open(self) -> None:
        parsed = parse_lrc_text("[00:10.00]so long <00:10.50>farewell\n")

        assert parsed[0].end is None
        assert parsed[0].words[-1].end is None

    def test_untimed_lines_stay_visible_and_unaddressed_by_the_clock(self) -> None:
        parsed = parse_lrc_text(
            "[00:01.00]timed\nplain as daylight\n",
        )

        assert [(line.text, line.start) for line in parsed] == [
            ("timed", 1.0),
            ("plain as daylight", None),
        ]

    def test_out_of_order_lines_are_sorted_stably(self) -> None:
        parsed = parse_lrc_text(
            "[00:03.00]second\n[00:01.00]first\n[00:02.00]between\n",
        )

        assert [line.text for line in parsed] == ["first", "between", "second"]

    def test_an_empty_or_untagged_file_is_an_error(self) -> None:
        with pytest.raises(InputError, match="no lyric lines"):
            parse_lrc_text("[ti:nothing][ar:here]\n", name="empty.lrc")

    def test_garbage_bracket_tags_are_skipped(self) -> None:
        parsed = parse_lrc_text("[Instrumental]\n[00:01.00]real\n")

        assert [line.text for line in parsed] == ["real"]


class TestTheSrtParser:
    def test_a_basic_file_becomes_a_base_with_both_boundaries(self) -> None:
        parsed = parse_srt_text(
            "1\n00:00:01,000 --> 00:00:04,500\nhello subtitles\n\n"
            "2\n00:00:05,000 --> 00:00:08,000\nbye\n",
            name="song.srt",
        )

        assert [(line.text, line.start, line.end) for line in parsed] == [
            ("hello subtitles", 1.0, 4.5),
            ("bye", 5.0, 8.0),
        ]
        assert [line.source for line in parsed] == ["srt"] * 2

    def test_a_blocks_internal_lines_become_one_segment(self) -> None:
        parsed = parse_srt_text(
            "1\n00:00:01,000 --> 00:00:04,500\nfirst subtitle line\nsecond line\n",
        )

        # A lyric segment is one display line; the file's break is not kept.
        assert parsed[0].text == "first subtitle line second line"

    def test_the_index_line_is_optional_and_unverified(self) -> None:
        parsed = parse_srt_text("00:00:01,000 --> 00:00:02,000\nno index here\n")
        indexed = parse_srt_text(
            "7\n00:00:01,000 --> 00:00:02,000\none\n\n7\n00:00:03,000 --> 00:00:04,000\ntwo\n",
        )

        assert [line.text for line in parsed] == ["no index here"]
        assert [line.text for line in indexed] == ["one", "two"]

    def test_a_dot_ms_separator_is_accepted_like_a_comma(self) -> None:
        parsed = parse_srt_text("1\n00:00:01.000 --> 00:00:02.000\nspotted\n")

        assert (parsed[0].start, parsed[0].end) == (1.0, 2.0)

    def test_trailing_markers_after_the_arrow_are_ignored(self) -> None:
        parsed = parse_srt_text(
            "1\n00:00:01,000 --> 00:00:02,000 X1:20 Y1:20\nmarked\n",
        )

        assert (parsed[0].start, parsed[0].end) == (1.0, 2.0)

    def test_blocks_with_or_without_text_are_kept_or_skipped_honestly(self) -> None:
        parsed = parse_srt_text(
            "1\n00:00:01,000 --> 00:00:02,000\n\n"  # no text at all
            "2\n00:00:03,000 --> 00:00:04,000\n[Music]\n\n"  # text exists
            "3\n00:00:05,000 --> 00:00:06,000\nreal\n",  # ordinary
        )

        # A block with empty text is silence, never a made lyric; but the
        # file's written text ([Music], ♪ ...) is what it is, never relabelled.
        assert [line.text for line in parsed] == ["[Music]", "real"]

    def test_apparent_silence_markers_stay_lyrics_when_text_exists(self) -> None:
        parsed = parse_srt_text("1\n00:00:01,000 --> 00:00:02,000\n♪ humming ♪\n")

        # The file says the text; the parser does not relabel it as anything.
        assert parsed[0].text == "♪ humming ♪"

    def test_an_inverted_timing_is_reported_not_normalized(self) -> None:
        with pytest.raises(InputError, match="before it starts"):
            parse_srt_text("1\n00:00:04,000 --> 00:00:02,000\nbackwards\n")

    def test_a_broken_timing_arrow_is_reported_with_the_hint(self) -> None:
        with pytest.raises(InputError, match="cannot be parsed"):
            parse_srt_text("1\nbroken --> timing\nwords\n")

    def test_a_file_without_blocks_is_an_error(self) -> None:
        with pytest.raises(InputError, match="no subtitle blocks"):
            parse_srt_text("not a subtitle file\nat all\n", name="song.srt")


class TestTheFormatDispatch:
    def test_the_suffix_decides_and_is_never_second_guessed(self, tmp_path: object) -> None:
        from pathlib import Path

        base = Path(str(tmp_path))
        lrc = base / "song.lrc"
        lrc.write_text("[00:01.00]lyric\n", encoding="utf-8")

        parsed = parse_timed_text(lrc)
        assert [line.text for line in parsed] == ["lyric"]

    def test_a_renamed_file_is_reported_not_auto_detected(self, tmp_path: object) -> None:
        from pathlib import Path

        mystery = Path(str(tmp_path)) / "song.txt"
        mystery.write_text("[00:01.00]lyric\n", encoding="utf-8")

        with pytest.raises(InputError, match=r"unknown lyric format '\.txt'"):
            parse_timed_text(mystery)

    def test_an_unreadable_file_reports_instead_of_raising_raw(self, tmp_path: object) -> None:
        from pathlib import Path

        missing = Path(str(tmp_path)) / "nope.lrc"
        with pytest.raises(InputError, match="Could not read"):
            parse_timed_text(missing)

    def test_a_non_utf8_file_is_reported(self, tmp_path: object) -> None:
        from pathlib import Path

        gbk = Path(str(tmp_path)) / "song.lrc"
        gbk.write_bytes("[00:01.00]caf\xe9\n".encode("gbk"))

        with pytest.raises(InputError, match="not UTF-8"):
            parse_timed_text(gbk)

    def test_parse_timed_text_file_matches_parse_timed_text(self, tmp_path: object) -> None:
        from pathlib import Path

        source = Path(str(tmp_path)) / "song.srt"
        source.write_text("1\n00:00:01,000 --> 00:00:02,000\nsame\n", encoding="utf-8")

        assert list(parse_timed_text_file(source)) == list(parse_timed_text(source))
        assert all(line.source == "srt" for line in parse_timed_text_file(source))
